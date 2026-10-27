"""Durable operator publication: real DB claims, recovery and immutable intents."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import json
from threading import Barrier

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from quant_service.models import Base
from test_snapshot_inputs import snapshot_fixture


def queue(tmp_path):
    from quant_service.publication_worker import PublicationQueue

    engine = create_engine(
        f"sqlite:///{tmp_path / 'quant.db'}", connect_args={"timeout": 20}
    )
    Base.metadata.create_all(engine)
    return PublicationQueue(sessionmaker(engine, expire_on_commit=False))


def request():
    snapshot, rows, now = snapshot_fixture()
    return (
        {
            "snapshot_id": snapshot["id"],
            "snapshot_hash": snapshot["content_hash"],
            "universe_id": "REAL",
        },
        snapshot,
        rows,
        now,
    )


def test_enqueue_conflict_restart_and_concurrent_claim(tmp_path):
    from quant_service.publication_worker import IdempotencyConflict

    q = queue(tmp_path)
    pins, _, _, now = request()
    job = q.enqueue("operator-1", pins, now=now)
    assert q.enqueue("operator-1", pins, now=now).id == job.id
    with pytest.raises(IdempotencyConflict):
        q.enqueue("operator-1", pins | {"universe_id": "OTHER"}, now=now)
    barrier = Barrier(4)

    def claim(_):
        barrier.wait()
        return queue(tmp_path).claim(now=now)

    with ThreadPoolExecutor(max_workers=4) as pool:
        claims = list(pool.map(claim, range(4)))
    claimed = [j for j in claims if j]
    assert len(claimed) == 1
    assert claimed[0].id == job.id
    assert claimed[0].attempts == 1
    assert queue(tmp_path).get(job.id).status == "RUNNING"


def test_reclaimed_lease_fences_old_worker_and_exhausts_crashes(tmp_path):
    q = queue(tmp_path)
    pins, _, _, now = request()
    job = q.enqueue("lease", pins, now=now, max_attempts=2)
    first = q.claim(now=now, lease_seconds=5)
    second = q.claim(now=now + timedelta(seconds=6), lease_seconds=5)
    assert second.id == first.id and second.lease_token != first.lease_token
    assert not q.complete(first, {"bundle_id": "stale"}, now=now + timedelta(seconds=7))
    assert q.claim(now=now + timedelta(seconds=12)) is None
    state = q.get(job.id)
    assert state.status == "FAILED" and state.safe_error == "LEASE_EXHAUSTED"


def test_retry_backoff_and_safe_error(tmp_path):
    q = queue(tmp_path)
    pins, _, _, now = request()
    job = q.enqueue("retry", pins, now=now, max_attempts=2)
    claim = q.claim(now=now)
    assert q.fail(claim, "MARKET_UNAVAILABLE", now=now)
    assert q.claim(now=now + timedelta(seconds=1)) is None
    claim = q.claim(now=now + timedelta(seconds=31))
    assert claim.attempts == 2
    q.fail(claim, "MARKET_UNAVAILABLE", now=now + timedelta(seconds=31))
    assert q.get(job.id).status == "FAILED"
    assert q.get(job.id).safe_error == "MARKET_UNAVAILABLE"


def test_due_slot_deduplicated_across_schedulers(tmp_path):
    from quant_service.publication_worker import enqueue_schedules

    q = queue(tmp_path)
    pins, _, _, now = request()
    config = [
        {
            "id": "daily-real",
            "anchor": now.isoformat(),
            "interval_seconds": 60,
            "request": pins,
        }
    ]
    with ThreadPoolExecutor(max_workers=3) as pool:
        batches = list(
            pool.map(lambda _: enqueue_schedules(q, config, now=now), range(3))
        )
    assert len({batch[0].id for batch in batches}) == 1
    assert (
        enqueue_schedules(q, config, now=now + timedelta(seconds=59))[0].id
        == batches[0][0].id
    )
    assert (
        enqueue_schedules(q, config, now=now + timedelta(seconds=60))[0].id
        != batches[0][0].id
    )
    assert enqueue_schedules(q, [], now=now) == []


def test_worker_crash_after_publication_reuses_artifact_without_market(tmp_path):
    from quant_service.publication_worker import process_one
    from quant_service.snapshot_publisher import publish_snapshot

    q = queue(tmp_path)
    pins, snapshot, rows, now = request()
    job = q.enqueue("crash", pins, now=now)
    first = q.claim(now=now, lease_seconds=1)
    original = publish_snapshot(
        tmp_path / "bundles",
        snapshot,
        rows,
        expected_hash=pins["snapshot_hash"],
        universe_id="REAL",
        now=now,
        publication_intent=job.id,
        intent_hash=job.body_hash,
    )

    class OfflineReader:
        def load(self, *_):
            raise AssertionError("A published intent must recover without Market")

    assert process_one(
        q, tmp_path / "bundles", OfflineReader(), now=now + timedelta(seconds=2)
    )
    state = q.get(job.id)
    assert state.status == "SUCCEEDED" and state.result == original
    assert (
        len(json.loads((tmp_path / "bundles/catalog.json").read_text())["bundles"]) == 1
    )
    assert not q.complete(first, {}, now=now + timedelta(seconds=3))


def test_intent_recovers_crash_before_catalog_and_expired_retry(tmp_path, monkeypatch):
    from pathlib import Path
    from quant_service.snapshot_publisher import publish_snapshot, recover_publication

    pins, snapshot, rows, now = request()
    original = Path.replace

    def crash(path, target):
        if str(target).endswith("catalog.json"):
            raise RuntimeError("crash after bundle fsync")
        return original(path, target)

    monkeypatch.setattr(Path, "replace", crash)
    with pytest.raises(RuntimeError):
        publish_snapshot(
            tmp_path,
            snapshot,
            rows,
            expected_hash=pins["snapshot_hash"],
            universe_id="REAL",
            now=now,
            publication_intent="stable",
            intent_hash="c" * 64,
        )
    bundle = next(tmp_path.glob("market-intent-*.json"))
    content = bundle.read_bytes()
    monkeypatch.setattr(Path, "replace", original)
    recovered = recover_publication(tmp_path, "stable", "c" * 64)
    replay = publish_snapshot(
        tmp_path,
        snapshot,
        rows,
        expected_hash=pins["snapshot_hash"],
        universe_id="REAL",
        now=now + timedelta(days=30),
        publication_intent="stable",
        intent_hash="c" * 64,
    )
    assert recovered == replay and bundle.read_bytes() == content
    with pytest.raises(ValueError, match="intent"):
        recover_publication(tmp_path, "stable", "d" * 64)


def test_operator_worker_is_only_rw_bundle_service():
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[2] / "infra/local/compose.yaml"
    ).read_text()
    assert "  quant-publication:\n" in source, (
        "durable publication needs a supervised worker"
    )
    publisher = source.split("  quant-publication:\n", 1)[1].split(
        "\n  portfolio-dispatch:", 1
    )[0]
    assert '["python", "-m", "quant_service.publication_worker", "run"]' in publisher
    assert 'PUBLICATION_SCHEDULES: "[]"' in publisher
    assert (
        'user: "${LOCAL_BUNDLE_UID:?Run bootstrap.py}:${LOCAL_BUNDLE_GID:?Run bootstrap.py}"'
        in publisher
    )
    assert "MARKET_READER_CLIENT_SECRET:" in publisher
    assert "BROKER_URL" not in publisher
    assert "./.generated/bundles:/bundles:rw" in publisher
    api = source.split("  quant-api:\n", 1)[1].split("\n  quant-publication:", 1)[0]
    assert "./.generated/bundles:/bundles:ro" in api


def test_explicit_invalid_model_and_boolean_retry_bounds_are_rejected(tmp_path):
    q = queue(tmp_path)
    pins, _, _, now = request()
    with pytest.raises(ValueError):
        q.enqueue("invalid-model", pins | {"model": {}}, now=now)
    with pytest.raises(ValueError):
        q.enqueue("invalid-retry", pins, now=now, max_attempts=True)


def test_orphan_recovery_never_promotes_older_output_above_newer(tmp_path, monkeypatch):
    from pathlib import Path
    from quant_service.snapshot_publisher import publish_snapshot, recover_publication

    pins, snapshot, rows, now = request()
    original = Path.replace

    def crash(path, target):
        if str(target).endswith("catalog.json"):
            raise RuntimeError("crash")
        return original(path, target)

    monkeypatch.setattr(Path, "replace", crash)
    with pytest.raises(RuntimeError):
        publish_snapshot(
            tmp_path,
            snapshot,
            rows,
            expected_hash=pins["snapshot_hash"],
            universe_id="REAL",
            now=now,
            publication_intent="older",
            intent_hash="c" * 64,
        )
    monkeypatch.setattr(Path, "replace", original)
    newer = publish_snapshot(
        tmp_path,
        snapshot,
        rows,
        expected_hash=pins["snapshot_hash"],
        universe_id="REAL",
        now=now + timedelta(seconds=1),
        publication_intent="newer",
        intent_hash="d" * 64,
    )
    older = recover_publication(tmp_path, "older", "c" * 64)
    entries = json.loads((tmp_path / "catalog.json").read_text())["bundles"]
    assert [e["bundle_id"] for e in entries] == [newer["bundle_id"], older["bundle_id"]]


def test_final_attempt_crash_recovers_success_without_another_build(tmp_path):
    from quant_service.publication_worker import process_one
    from quant_service.snapshot_publisher import publish_snapshot

    q = queue(tmp_path)
    pins, snapshot, rows, now = request()
    job = q.enqueue("last-attempt", pins, now=now, max_attempts=1)
    q.claim(now=now, lease_seconds=1)
    result = publish_snapshot(
        tmp_path / "bundles",
        snapshot,
        rows,
        expected_hash=pins["snapshot_hash"],
        universe_id="REAL",
        now=now,
        publication_intent=job.id,
        intent_hash=job.body_hash,
    )

    class OfflineReader:
        def load(self, *_):
            raise AssertionError("No retry of a bounded final attempt")

    process_one(
        q, tmp_path / "bundles", OfflineReader(), now=now + timedelta(seconds=2)
    )
    assert q.get(job.id).status == "SUCCEEDED"
    assert q.get(job.id).attempts == 1
    assert q.get(job.id).result == result


@pytest.mark.parametrize("terminal", [True, False])
def test_delayed_market_reader_cannot_publish_after_lease_is_lost(
    tmp_path, monkeypatch, terminal
):
    from threading import Event
    from quant_service import publication_worker as worker

    q = queue(tmp_path)
    pins, snapshot, rows, now = request()
    job = q.enqueue("stale-delayed", pins, now=now, max_attempts=1 if terminal else 2)
    entered, release = Event(), Event()
    clock = [now]
    monkeypatch.setattr(worker, "utcnow", lambda: clock[0])

    class DelayedReader:
        def load(self, *_):
            entered.set()
            assert release.wait(5)
            return snapshot, rows

    with ThreadPoolExecutor(max_workers=1) as pool:
        stale = pool.submit(
            worker.process_one, q, tmp_path / "bundles", DelayedReader()
        )
        assert entered.wait(5)
        clock[0] = now + timedelta(seconds=121)
        replacement = q.claim(now=clock[0])
        assert replacement is None if terminal else replacement.id == job.id
        release.set()
        assert stale.result(timeout=5)
    assert not (tmp_path / "bundles/catalog.json").exists()
    assert not list((tmp_path / "bundles").glob("market-intent-*.json"))
    assert q.get(job.id).status == ("FAILED" if terminal else "RUNNING")
    if replacement:
        assert q.get(job.id).lease_token == replacement.lease_token


def test_fenced_publication_crash_rolls_back_lease_and_recovers_final_attempt(tmp_path):
    from quant_service.publication_worker import process_one
    from quant_service.snapshot_publisher import publish_snapshot

    q = queue(tmp_path)
    pins, snapshot, rows, now = request()
    job = q.enqueue("fenced-crash", pins, now=now, max_attempts=1)
    claimed = q.claim(now=now, lease_seconds=1)

    class WorkerCrash(BaseException):
        pass

    def write_then_crash():
        publish_snapshot(
            tmp_path / "bundles",
            snapshot,
            rows,
            expected_hash=pins["snapshot_hash"],
            universe_id="REAL",
            now=now,
            publication_intent=job.id,
            intent_hash=job.body_hash,
        )
        raise WorkerCrash()

    with pytest.raises(WorkerCrash):
        q.publish_owned(claimed, write_then_crash, now=now)
    assert q.get(job.id).status == "RUNNING"
    assert q.get(job.id).result is None

    class OfflineReader:
        def load(self, *_):
            raise AssertionError("Recover without another Market request")

    process_one(
        q, tmp_path / "bundles", OfflineReader(), now=now + timedelta(seconds=2)
    )
    assert q.get(job.id).status == "SUCCEEDED"
    assert q.get(job.id).attempts == 1


def test_publication_row_lock_prevents_reclaimer_from_overwriting_success(tmp_path):
    from threading import Event

    q = queue(tmp_path)
    pins, _, _, now = request()
    job = q.enqueue("locked-publish", pins, now=now, max_attempts=1)
    claimed = q.claim(now=now, lease_seconds=1)
    entered, release, reclaim_started = Event(), Event(), Event()

    def operation():
        entered.set()
        assert release.wait(5)
        return {"bundle_id": "committed"}

    def reclaim():
        reclaim_started.set()
        return queue(tmp_path).claim(now=now + timedelta(seconds=121))

    with ThreadPoolExecutor(max_workers=2) as pool:
        publishing = pool.submit(q.publish_owned, claimed, operation, now=now)
        assert entered.wait(5)
        reclaiming = pool.submit(reclaim)
        assert reclaim_started.wait(5)
        release.set()
        assert publishing.result(timeout=5) == (True, {"bundle_id": "committed"})
        assert reclaiming.result(timeout=5) is None
    assert q.get(job.id).status == "SUCCEEDED"
    assert q.get(job.id).result == {"bundle_id": "committed"}
