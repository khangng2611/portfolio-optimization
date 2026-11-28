"""Freeze the audited market panel and the exact HYBRID stream before scoring."""
import gzip
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
INPUT = HERE / "inputs"
TARGET = "outputs/step1/Step1_Submission_Readiness_20261012/04_Baseline_Target_Weights.csv"
CALENDAR = "extensions_C_v1/rebalance_calendar.csv"
VAL = "extensions_C_v1/inputs/prices_valuation.csv"
KNOWN = "extensions_C_v1/inputs/prices_eligible.csv"
LEDGER = "extensions_C_v1/inputs/availability_ledger.csv"
FUND = "trusted_baseline/datasets/funds/full/VFF.csv"
GOLD = "phase2_gold_k5/revision/alternate/provenance.csv"
SOURCES = [TARGET, CALENDAR, VAL, KNOWN, LEDGER, FUND, GOLD,
           "extensions_C_v1/inputs/availability_policy.json", "phase2_gold_k5/revision/alternate/source_policy.md",
           "phase2_ocb_deposits/rebalance_5/evidence/vff-prospectus.pdf",
           "phase2_rebalance/terms.md", "phase2_rebalance/protocol.json"]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def dated(path, column="date"):
    return pd.read_csv(ROOT / path, float_precision="round_trip").set_index(column, verify_integrity=True)


def main():
    anchor = INPUT / "registration.json"
    if anchor.exists():
        raise SystemExit("Registration already exists; use run.py for frozen replay.")
    weights = pd.read_csv(ROOT / TARGET, float_precision="round_trip").query("strategy == 'HYBRID'")
    cal = dated(CALENDAR, "decision_date")
    dates = weights[["decision_date", "date"]].drop_duplicates().set_index("decision_date")
    assert dates.index.equals(cal.index) and dates.date.equals(cal.assumed_execution_date)
    val, known = dated(VAL), dated(KNOWN)
    assert val.index.equals(known.index) and val.columns.equals(known.columns)
    assert val.index.is_monotonic_increasing and val.index[-1] == "2026-04-29"
    targets = weights.pivot(index="decision_date", columns="asset", values="target_weight")[val.columns]
    assert len(targets) == 310 and targets.index.equals(cal.index)
    assert np.isfinite(targets).all().all() and targets.min().min() >= 0
    assert np.allclose(targets.sum(axis=1), 1, atol=1e-8, rtol=0)
    assert np.array_equal(np.diff(val.index.get_indexer(cal.index)), np.full(len(cal)-1, 5))
    assert np.array_equal(val.index[val.index.get_indexer(cal.index)+1], cal.assumed_execution_date)
    g, vff = dated(GOLD), dated(FUND)
    nav = vff.nav_per_unit_vnd
    assert (g.archive_bid > 0).all() and (g.archive_bid <= g.archive_ask).all()
    ledger = pd.read_csv(ROOT / LEDGER, float_precision="round_trip")
    ll = ledger.pivot(index="session_date", columns="asset", values="price")[known.columns]
    assert np.array_equal(ll, known) and ll.index.equals(known.index)
    assert (ledger.available_at <= ledger.decision_at).all()
    vf = ledger.query("asset == 'VFF'").set_index("session_date").loc[val.index]
    vf_dates = vf.observed_at.str[:10]
    assert np.allclose(nav.loc[vf_dates], known.VFF * 1000, rtol=0, atol=1e-6)
    assert np.allclose(nav.reindex(val.index, method="ffill"), val.VFF * 1000, rtol=0, atol=1e-6)
    assert np.isfinite(val).all().all() and val.min().min() > 0
    assert np.isfinite(known).all().all() and known.min().min() > 0
    stocks = val.columns.difference(["VFF", "GOLD"])
    assert np.allclose(val[stocks], known[stocks], rtol=1e-14, atol=0)
    sessions = val.index[val.index >= cal.index[0]]
    frames = []
    for d in sessions:
        prior = (pd.Timestamp(d)-pd.Timedelta(days=1)).date().isoformat()
        day, previous = g.loc[d], g.loc[prior]
        bid, ask = day.archive_bid*1000, day.archive_ask*1000
        prev_bid, prev_ask = previous.archive_bid*1000, previous.archive_ask*1000
        marks = (val.loc[d]*1000).to_dict()
        marks["GOLD"] = (bid+ask)/2
        eligible = (known.loc[d]*1000).to_dict()
        eligible["GOLD"] = (prev_bid+prev_ask)/2
        frames.append(dict(date=d, prices=marks, eligible=eligible, gold_bid=bid, gold_ask=ask,
                           gold_tradable=bool(day.primary_fill_allowed),
                           permissive_gold=bool(day.permissive_fill_allowed),
                           gold_source=day.source, gold_observed_date=day.reference_date,
                           eligible_gold_observed_date=previous.reference_date,
                           eligible_gold_bid=prev_bid, eligible_gold_ask=prev_ask,
                           eligible_vff_date=vf_dates[d], vff_nav=nav.get(d),
                           vff_fee_rates=[.02, .015, .005] if d < "2021-06-11" else [.02, .005, 0.],
                           vff_min_buy=2000000 if d < "2022-06-10" else 100000,
                           vff_dealing_weekdays=[1] if d < "2021-09-01" else [1,3]))
    INPUT.mkdir(exist_ok=True)
    (INPUT/"frames.json.gz").write_bytes(gzip.compress(json.dumps(frames, allow_nan=False, separators=(",", ":")).encode(), mtime=0))
    targets.mask(targets<=1e-10, 0.).to_csv(INPUT/"targets.csv")
    coverage = cal[["assumed_execution_date"]].copy()
    for col in ["primary_fill_allowed", "permissive_fill_allowed", "source", "reference_age_days"]:
        coverage["gold_"+col] = g.loc[cal.assumed_execution_date, col].to_numpy()
    coverage.to_csv(INPUT/"coverage.csv")
    names = ["frames.json.gz", "targets.csv", "coverage.csv"]
    write_json(anchor, dict(frozen_at=datetime.now(timezone.utc).isoformat(), source_sha256={p:sha(ROOT/p) for p in SOURCES},
                            frozen_sha256={n:sha(INPUT/n) for n in names}, prepare_sha256=sha(Path(__file__)),
                            ordered_assets=val.columns.tolist(), market_sessions=len(frames), first=frames[0]["date"],
                            last=frames[-1]["date"], decisions=len(targets), primary_gold_next_session=int(coverage.gold_primary_fill_allowed.sum()),
                            permissive_gold_next_session=int(coverage.gold_permissive_fill_allowed.sum())))


if __name__ == "__main__":
    main()
