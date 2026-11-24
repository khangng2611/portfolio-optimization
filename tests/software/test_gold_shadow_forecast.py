import csv
from datetime import date, timedelta
import json
from types import SimpleNamespace

import numpy as np
import pytest

from portfolio_contracts.assets import ASSET_IDS
from quant_service import gold_shadow_forecast as shadow

MEMBERS = ["MBB", "PLX", "SAB", "VHM", "VJC"]
ISSUE = "2026-11-24T09:05:00+00:00"


def inputs():
    try:
        eligible, _, _ = shadow._warmup()
    except FileNotFoundError:
        pytest.skip("Requires the local hash-pinned GOLD shadow warm-up")
    dates = [date.fromisoformat(r["date"]) for r in eligible]
    while dates[-1] < date(2026, 11, 23):
        following = dates[-1] + timedelta(days=1)
        while following.weekday() >= 5:
            following += timedelta(days=1)
        dates.append(following)
    t = len(dates)-1
    cols = list(ASSET_IDS)
    prices = np.ones((len(dates), len(cols)))
    # Exact archived April 24 feature vectors with a future issuance vintage.
    end = next(i for i, r in enumerate(eligible) if r["date"] == "2026-04-24")
    quotes = {}
    for day, row, index in zip(dates[-21:], eligible[end-20:end+1], range(t-20, t+1)):
        for asset in MEMBERS:
            prices[index, cols.index(asset)] = float(row[asset]) * 1000
        quotes[str(day - timedelta(days=1))] = dict(ask=float(row["GOLD"])*1000,
                                                      bid=float(row["GOLD"])*1000-1000, received_at=ISSUE)
    panel = SimpleNamespace(dates=dates, ids=cols, prices=prices, valid=np.ones_like(prices, dtype=bool),
                            known_seconds=np.zeros_like(prices, dtype=int), policy_seconds=np.zeros_like(prices, dtype=int),
                            index_at=lambda cutoff: t, panel_hash="synthetic", snapshot={"created_at":ISSUE})
    return panel, {"cutoff_at":ISSUE, "gold_quotes":quotes}


def test_bootstrap_matches_each_archived_xgboost_seed_and_derived_view():
    p, capture = inputs()
    f = shadow.forecast(p, p.dates[-1], MEMBERS, capture=capture)
    json.dumps(f, allow_nan=False)
    assert f["status"] == "active" and f["fit"]["bootstrap"] and f["fit"]["fit_date"] == "2026-04-24"
    assert f["calibration"]["historical_n"] == 283 and f["calibration"]["prospective_n"] == 0
    ref = shadow.Path(__file__).resolve().parents[2] / "phase2_gold_k5/revision/runs" / shadow.RUN
    reference = ref / "forecast_members.csv"
    if not reference.is_file():
        pytest.skip("Requires the local GOLD shadow member forecast receipt")
    with reference.open() as stream:
        expected = [r for r in csv.DictReader(stream) if r["date"] == "2026-04-24" and r["model"] in [*MEMBERS,"GOLD"]]
    assert len(expected) == 12
    for row in expected:
        component = f["components"][row["model"]]
        assert component["training_rows"] == 1533
        assert component["training_last_label_end"] == "2026-04-23"
        i = shadow.SEEDS.index(int(row["seed"]))
        assert component["seed_predictions"][i] == pytest.approx(float(row["prediction"]), abs=1e-8)
    predictions = [f["components"][a]["prediction_5d"] for a in MEMBERS]
    assert f["q_daily"] == pytest.approx((f["components"]["GOLD"]["prediction_5d"]-np.mean(predictions))/5)
    assert f["q_daily"] == pytest.approx(9.399214759469015e-06, abs=1e-8)


def test_gold_feature_uses_previous_calendar_day_and_receipt_cutoff():
    p, capture = inputs()
    capture["gold_quotes"][str(p.dates[-1])] = dict(bid=1, ask=2, received_at=ISSUE)
    before = shadow.forecast(p, p.dates[-1], MEMBERS, capture=capture)
    capture["gold_quotes"][str(p.dates[-1])]["ask"] = 800_000_000
    p.prices[:, p.ids.index("GOLD")] *= 500
    after = shadow.forecast(p, p.dates[-1], MEMBERS, capture=capture)
    assert before == after
    key = str(p.dates[-1] - timedelta(days=1))
    capture["gold_quotes"][key]["received_at"] = "2026-11-25T09:05:00+00:00"
    with pytest.raises(ValueError, match="FEATURE_UNAVAILABLE GOLD"):
        shadow.forecast(p, p.dates[-1], MEMBERS, capture=capture)
    with pytest.raises(ValueError, match="five distinct"):
        shadow.forecast(p, p.dates[-1], MEMBERS[:4], capture=capture)


def test_confidence_counts_only_mature_prior_errors():
    rows = [(str(i), .04 + i*.0001, .05 - i*.0001, i, "prospective") for i in range(21)]
    audit, conf = shadow._calibration(rows, 18)
    assert audit["n"] == 19 and conf is None
    audit, conf = shadow._calibration(rows, 19)
    assert audit["prospective_n"] == 20 and conf == .1


def test_warmup_hash_checked_before_fit(tmp_path, monkeypatch):
    monkeypatch.setattr(shadow, "__file__", "/observer/quant_service/gold_shadow_forecast.py")
    (tmp_path / "inputs").mkdir()
    (tmp_path / "inputs/prices_eligible.csv").write_text("changed")
    monkeypatch.setenv("GOLD_SHADOW_FORECAST_WARMUP", str(tmp_path))
    with pytest.raises(ValueError, match="HASH_MISMATCH"):
        shadow._warmup()


def test_live_epoch_uses_economic_marks_and_excludes_new_receipts(monkeypatch):
    p, capture = inputs()
    start = len(p.dates)
    for _ in range(20):
        day = p.dates[-1] + timedelta(days=1)
        while day.weekday() >= 5:
            day += timedelta(days=1)
        p.dates.append(day)
    shape = (len(p.dates), len(p.ids))
    index = np.arange(shape[0])
    p.prices = (99 + index + np.sin(index / 2))[:,None] * np.ones(shape)
    p.valid = np.ones(shape, dtype=bool)
    p.known_seconds, p.policy_seconds = (np.zeros(shape, dtype=int) for _ in range(2))
    p.index_at = lambda cutoff: len(p.dates)-1
    t = len(p.dates)-1
    fit = shadow.fit_index(t)
    capture["cutoff_at"] = shadow._iso(shadow._seconds(p.dates[t]))
    day = date(2026, 3, 1)
    while day <= p.dates[-1]:
        n = (day-date(2026, 3, 1)).days
        ask = float(150_000_000 + n * 500 + 100_000 * np.sin(n/7))
        stamp = shadow._iso(shadow._seconds(day+timedelta(days=1),0))
        capture["gold_quotes"][str(day)] = dict(bid=ask-1_000_000, ask=ask, received_at=stamp)
        day += timedelta(days=1)
    pin, quotes = SimpleNamespace(**vars(p)), {k:dict(v) for k,v in capture["gold_quotes"].items()}
    monkeypatch.setattr(shadow, "_epoch_source", lambda *args: (pin,quotes,{"epoch":"test"}))
    origin = p.dates[start+1]
    capture["prior_forecasts"] = [
        dict(decision_session=str(origin), selected_equity_ids=MEMBERS, issued_at=shadow._iso(shadow._seconds(origin)+2), prediction_5d=.045),
        dict(decision_session=str(p.dates[-3]), selected_equity_ids=MEMBERS, issued_at=shadow._iso(shadow._seconds(p.dates[-3])+2), prediction_5d=.0001),
    ]
    f = shadow.forecast(p,p.dates[-1],MEMBERS,capture=capture)
    gold = f["components"]["GOLD"]
    assert not f["fit"]["bootstrap"] and gold["training_last_origin"] == str(p.dates[fit-7])
    assert gold["training_last_label_end"] == str(p.dates[fit-1])
    assert gold["live_training_rows"] > 100 and f["calibration"]["prospective_n"] == 1
    # A Friday exit uses Friday's economic ask. A later monthly vintage cannot replace it at the fit epoch.
    exit_i = next(i for i in range(start,fit) if p.dates[i].weekday() == 4)
    quotes[str(p.dates[exit_i])]["received_at"] = shadow._iso(shadow._seconds(p.dates[fit])+1)
    altered = shadow.forecast(p,p.dates[-1],MEMBERS,capture=capture)
    assert altered["components"]["GOLD"]["live_training_rows"] < gold["live_training_rows"]
    assert altered["components"]["MBB"]["training_sha256"] == f["components"]["MBB"]["training_sha256"]
    # Once the source is pinned, later decision information changes the prediction row only.
    pin_digest = altered["components"]["GOLD"]["training_sha256"]
    capture["gold_quotes"][str(p.dates[t]-timedelta(days=1))]["ask"] *= 1.2
    again = shadow.forecast(p,p.dates[-1],MEMBERS,capture=capture)
    assert again["components"]["GOLD"]["training_sha256"] == pin_digest
    assert again["components"]["GOLD"]["features"] != altered["components"]["GOLD"]["features"]
    monkeypatch.setattr(shadow, "_epoch_source", lambda *args: (None, {}, {"source":None}))
    missing = shadow.forecast(p,p.dates[-1],MEMBERS,capture=capture)
    assert missing["status"] == "fit_warmup" and missing["reason"] == "NO_VALID_PUBLICATION_AT_MODEL_EPOCH"
    pin.valid = pin.valid.copy()
    pin.valid[:,p.ids.index(MEMBERS[-1])] = False
    monkeypatch.setattr(shadow, "_epoch_source", lambda *args: (pin, quotes, {"epoch":"test"}))
    missing = shadow.forecast(p,p.dates[-1],MEMBERS,capture=capture)
    assert missing["status"] == "fit_warmup" and missing["unavailable_asset"] == MEMBERS[-1]
    assert missing["q_daily"] is None and missing["components"] == {}


def test_epoch_pin_survives_catalog_changes_and_detects_corruption(tmp_path,monkeypatch):
    monkeypatch.setenv("GOLD_SHADOW_FORECAST_EPOCHS",str(tmp_path))
    monkeypatch.setenv("BUNDLE_DIRECTORY",str(tmp_path/"bundles"))
    day = date(2026, 12, 1)
    cutoff = shadow._seconds(day)
    monkeypatch.setattr(shadow.SelectionCatalog, "_entries", lambda self: [])
    first = shadow._epoch_source(day,cutoff)
    assert first[0] is None and first[2]["source"] is None
    def changed(self):
        raise AssertionError("a pinned epoch was recomputed")
    monkeypatch.setattr(shadow.SelectionCatalog, "_entries", changed)
    assert first == shadow._epoch_source(day,cutoff)
    path = tmp_path/f"{day}.json"
    record = json.loads(path.read_text())
    record["cutoff_at"] = "2090-01-01T00:00:00+00:00"
    path.write_text(json.dumps(record))
    with pytest.raises(ValueError,match="EPOCH_PIN_MISMATCH"):
        shadow._epoch_source(day,cutoff)


def test_epoch_pins_last_live_bundle_by_cutoff_across_restart(tmp_path, monkeypatch):
    monkeypatch.setenv("GOLD_SHADOW_FORECAST_EPOCHS", str(tmp_path))
    monkeypatch.setenv("BUNDLE_DIRECTORY", "/bundles")
    monkeypatch.setenv("GOLD_SHADOW_DATASETS", "/datasets")
    monkeypatch.setenv("GOLD_SHADOW_ARCHIVE", "/archive.csv")
    day = date(2026,12,1)
    cutoff = shadow._seconds(day)
    ready = SimpleNamespace(bundle_hash="c"*64)
    value = dict(as_of_date=str(day), decision_at=shadow._iso(cutoff-30),
                 valid_until=shadow._iso(cutoff+1000), provenance=dict(panel_hash="pinned"),
                 panel=dict(file="panel.json", sha256="a"*64))
    entries = [(value,ready), (value | {"valid_until":shadow._iso(cutoff)},ready),
               (value | {"decision_at":shadow._iso(cutoff+1)},ready)]
    monkeypatch.setattr(shadow.SelectionCatalog, "_entries", lambda self: entries)
    p = SimpleNamespace(panel_hash="pinned", dates=[day], snapshot={"created_at":shadow._iso(cutoff-40)})
    monkeypatch.setattr(shadow, "load_panel", lambda *args: p)
    monkeypatch.setattr(shadow, "load_capture", lambda *args: dict(gold_quotes={"test":1}))
    first = shadow._epoch_source(day,cutoff)
    assert first[0] is p and first[2]["source"]["published_at"] == value["decision_at"]
    entries.clear()
    assert shadow._epoch_source(day,cutoff) == first
