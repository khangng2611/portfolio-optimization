"""Exercise the research clock, native solver, ledger, settlement and final seal on a closed fixture."""
from datetime import date, datetime, time, timedelta
import json
from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import hybrid_forward_study as study
import hybrid_forward_panel as panel


def test_sealed_pipeline_on_historical_fixture(tmp_path, monkeypatch):
    archive = tmp_path / "fixture"
    run = tmp_path / "research"
    run.mkdir()
    manifest = run / "manifest.json"
    manifest.write_text('{"fixture":true}')
    pin = study.digest(manifest.read_bytes())
    prices = pd.read_csv(study.PROJECT / study.BASELINE / "candidate_information_prices.csv",
                         index_col="date", parse_dates=True).iloc[:333]
    assets = list(prices)
    prices.loc[:, list(panel.EQUITY_IDS)] *= 1000
    sessions = list(prices.index.strftime("%Y-%m-%d"))
    first, last = (date.fromisoformat(sessions[i]) for i in (319, 331))
    monkeypatch.setattr(study, "FIRST_DAY", first)
    monkeypatch.setattr(study, "LAST_DAY", last)
    monkeypatch.setattr(study, "SETTLE_UNTIL", last + timedelta(days=7))

    def make_batch(phase, day):
        folder = archive / phase / str(day) / ("receipt-" + str(day))
        folder.mkdir(parents=True)
        (folder / "summary.json").write_text('{"status":"recorded"}')
        return folder

    def load_calendar(root, batch, cutoff, **kwargs):
        return [s for s in sessions if s <= batch.parent.name]

    def load_panel(root, batch, cutoff, **kwargs):
        days = load_calendar(root, batch, cutoff)
        return dict(information=prices.loc[:days[-1]], sessions=days, assets=assets,
                    provenance={"fixture_cutoff": cutoff.isoformat()})

    def load_valuation(root, batch, cutoff):
        if batch.parent.name == str(last + timedelta(days=7)):
            raise ValueError("Missing source in newest settlement")
        return dict(sessions=sessions, valuation=prices, assets=assets, provenance={"fixture": True})

    monkeypatch.setattr(panel, "load_calendar", load_calendar)
    monkeypatch.setattr(panel, "load_panel", load_panel)
    monkeypatch.setattr(panel, "load_valuation", load_valuation)
    for index in (319, 329):  # deliberately miss offset 5
        day = date.fromisoformat(sessions[index])
        make_batch("evaluation", day)
        now = datetime.combine(day, time(19, 30), study.VIETNAM)
        monkeypatch.setattr(study, "clock", lambda: now)
        result = study.tick(archive, run, now, pin)
        assert result["status"] in ("DECIDED", "HOLD")
        assert study.tick(archive, run, now, pin)["status"] == "ALREADY_RECORDED"
    rows = study.read_rows(run / "ledger", sessions[319:332])
    assert rows[0]["status"] == "DECIDED" and rows[0]["timing_verified"]
    assert rows[1]["reason"] == "MISSED_DECISION_WINDOW"
    make_batch("settlement", last + timedelta(days=6))
    make_batch("settlement", last + timedelta(days=7))
    now = datetime.combine(last + timedelta(days=8), time(1), study.VIETNAM)
    report = study.finalize(archive, run, now)
    assert report["status"] == "INSUFFICIENT_EVIDENCE"
    assert report["unobserved_cutoffs"] == [sessions[324]]
    assert set(report["profiles"]) == {"conservative", "balanced", "growth"}
    inputs = json.loads((run / "scoring-inputs.json").read_text())
    assert len(inputs["ledger"]) == 3 and len(inputs["rejected_settlement_batches"]) == 1
    assert study.finalize(archive, run, now) == report
