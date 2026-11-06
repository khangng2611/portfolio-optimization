import httpx
import pytest
from chat_service.provider import Provider, render


@pytest.mark.parametrize(
    "output",
    [
        {
            "sections": ["weights"],
            "facts_hash": "b" * 64,
            "input_tokens": 10,
            "output_tokens": 10,
        },
        {
            "sections": ["trade"],
            "facts_hash": "a" * 64,
            "input_tokens": 10,
            "output_tokens": 10,
        },
        {
            "sections": ["weights"],
            "facts_hash": "a" * 64,
            "input_tokens": 99999,
            "output_tokens": 10,
        },
        {
            "sections": ["weights"],
            "facts_hash": "a" * 64,
            "input_tokens": 10,
            "output_tokens": 10,
            "text": "AAA 99%",
        },
        {
            "sections": ["weights", "weights"],
            "facts_hash": "a" * 64,
            "input_tokens": 10,
            "output_tokens": 10,
        },
    ],
)
def test_provider_rejects_ungrounded_schema_or_budget(monkeypatch, output):
    monkeypatch.setenv("CHAT_PROVIDER_URL", "https://provider.test/explain")
    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kw: original(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json=output)
            ),
            **kw,
        ),
    )
    sections, metadata = Provider().explain(
        {"weights": ["0.5", "0.5"], "asset_ids": ["AAA", "BBB"]}, "a" * 64
    )
    assert sections is None and metadata["reason"] == "UNVERIFIED_OUTPUT"


@pytest.mark.parametrize(
    "exception,reason",
    [
        (httpx.ReadTimeout("timeout"), "TIMEOUT"),
        (httpx.ConnectError("down"), "PROVIDER_UNAVAILABLE"),
    ],
)
def test_provider_outage_falls_back(monkeypatch, exception, reason):
    monkeypatch.setenv("CHAT_PROVIDER_URL", "https://provider.test/explain")

    import json

    original = httpx.AsyncClient

    def serve(request):
        payload = json.loads(request.content)
        assert payload["max_output_tokens"] == 448
        assert "owner_user_id" not in payload["facts"]
        raise exception

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kw: original(transport=httpx.MockTransport(serve), **kw),
    )
    sections, metadata = Provider().explain({"owner_user_id": "private"}, "a" * 64)
    assert sections is None and metadata["reason"] == reason
    assert "AAA: 50.00%" in render(
        {"asset_ids": ["AAA", "BBB"], "weights": ["0.5", "0.5"]}, sections
    )


def test_provider_wall_clock_deadline_covers_slow_body(monkeypatch):
    import asyncio
    import time

    original = httpx.AsyncClient

    class SlowStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            for _ in range(100):
                await asyncio.sleep(0.01)
                yield b" "

    async def serve(request):
        return httpx.Response(200, stream=SlowStream(), request=request)

    monkeypatch.setenv("CHAT_PROVIDER_URL", "https://provider.test/explain")
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kw: original(transport=httpx.MockTransport(serve), **kw),
    )
    started = time.monotonic()
    provider = Provider()
    provider.timeout_seconds = 0.04
    sections, meta = provider.explain({}, "a" * 64)
    assert sections is None and meta["reason"] == "TIMEOUT"
    assert time.monotonic() - started < 0.5


def test_provider_stops_reading_when_body_budget_is_exceeded(monkeypatch):
    original = httpx.AsyncClient
    consumed = []

    class LargeStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            for n in range(100):
                consumed.append(n)
                yield b"x" * 2048

    async def serve(request):
        return httpx.Response(200, stream=LargeStream(), request=request)

    monkeypatch.setenv("CHAT_PROVIDER_URL", "https://provider.test/explain")
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kw: original(transport=httpx.MockTransport(serve), **kw),
    )
    sections, metadata = Provider().explain({}, "a" * 64)
    assert sections is None and metadata["reason"] == "UNVERIFIED_OUTPUT"
    assert len(consumed) == 5


def test_template_explains_canonical_limits_without_raw_dictionary_or_hash_wall():
    facts = {
        "asset_ids": ["FPT", "VCB"],
        "weights": ["0.5", "0.5"],
        "constraints": {"max_position_weight": 0.5, "risk_aversion": 3.0},
        "as_of_date": "2026-11-03",
        "core_version": "0.1.0",
        "input_hash": "a" * 64,
        "policy_version_id": "risk-policy-v1:growth:private-reference",
    }
    explanation = render(facts)
    assert "FPT: 50.00%" in explanation
    assert "50.00%" in explanation
    assert "2026-11-03" in explanation and "0.1.0" in explanation
    assert facts["input_hash"] not in explanation
    assert "{'" not in explanation
