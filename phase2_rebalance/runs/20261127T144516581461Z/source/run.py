"""Replay frozen HYBRID targets against one shared VND paper-account implementation."""
import gzip
import json
import math
import platform
import shutil
import subprocess
import sys
import time
import traceback
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from freeze import HERE, INPUT, ROOT, sha, write_json

sys.path.insert(0, str(ROOT / "services/portfolio/src"))
from portfolio_service import paper_ledger as ledger


def load():
    reg = json.loads((INPUT/"registration.json").read_text())
    amendment = json.loads((INPUT/"amendment.json").read_text())
    assert sha(INPUT/"registration.json") == amendment["original_registration_sha256"]
    assert sha(HERE/amendment["source"]) == amendment["sha256"]
    assert sha(HERE/"protocol.json") == reg["source_sha256"]["phase2_rebalance/protocol.json"]
    for n, checksum in reg["frozen_sha256"].items():
        assert sha(INPUT/n) == checksum, n
    frames = json.loads(gzip.decompress((INPUT/"frames.json.gz").read_bytes()))
    targets = pd.read_csv(INPUT/"targets.csv", index_col=0, float_precision="round_trip").to_dict("index")
    return json.loads((HERE/"protocol.json").read_text()), frames, targets


def simulate(frames, targets, scenario, arm, threshold, end):
    capital = scenario.get("capital", 10_000_000)
    state = ledger.new_account(capital)
    previous_nav, previous_cash = capital, capital
    quantities = defaultdict(float)
    daily, events, decisions, holdings = [], [], [], []
    overrides = {k:scenario[k] for k in ("stock_fee_bps", "vff_settlement") if k in scenario}
    first = next(iter(targets))
    for raw in frames:
        day = raw["date"]
        if day > end:
            break
        frame = {**raw, **overrides}
        if scenario.get("permissive_gold"):
            frame["gold_tradable"] = raw["permissive_gold"]
        opening_nav_at_marks = previous_cash + sum(q * frame["prices"][asset] for asset,q in quantities.items())
        day_events = ledger.advance(state, frame)
        events.extend(day_events)
        fills = [e for e in day_events if e["kind"] == "fill"]
        costs = sum(e["fee"] + e["tax"] + e["spread"] for e in fills)
        for e in fills:
            quantities[e["asset"]] += e["units"] * (1 if e["side"] == "buy" else -1)
        book = ledger.valuation(state, frame)
        assert math.isclose(opening_nav_at_marks-costs, book["total"], rel_tol=1e-11, abs_tol=.001), day
        for k in ("cash","reserved","receivable","total"):
            assert math.isfinite(book[k]) and book[k]>=-1e-7, (day, k)
        assert all(q >= -1e-8 for q in quantities.values())
        previous_cash = book["cash"] + book["reserved"] + book["receivable"]
        value = sum(p["value"] for p in book["positions"].values())
        assert abs(previous_cash + value - book["total"]) < .001
        submitted = forced = False
        if day in targets:
            weights = targets[day]
            quote = ledger.preview(state, weights, frame)
            forced = any(
                asset not in ("GOLD", "VFF") and weights.get(asset, 0)==0
                and sum(l["units"] for l in lots if l["available"]<=state["session"])*frame["eligible"][asset]>=1
                for asset,lots in state["lots"].items()
            ) and arm != "A"
            if day == first:
                reason = "opening"
            elif arm == "A":
                reason = "hold"
            elif quote["blocked"]:
                reason = quote["blocked"]
            elif forced:
                reason = "zero_target_equity"
            elif arm == "B":
                reason = "calendar"
            elif quote["drift"] >= threshold:
                reason = "threshold"
            else:
                reason = "below_threshold"
            if reason in ("opening", "calendar", "threshold", "zero_target_equity") and quote["orders"]:
                ledger.confirm(state, quote)
                submitted = True
            decisions.append(dict(date=day, drift=quote["drift"], submitted=submitted,
                                  compulsory=forced, reason=reason, legs=len(quote["orders"]) if submitted else 0))
        gross = sum(e["gross"] for e in fills)
        daily.append(dict(date=day, nav=book["total"], cash=book["cash"], reserved=book["reserved"],
                          receivable=book["receivable"], invested=value, net_return=book["total"]/previous_nav-1,
                          turnover=gross/(2*previous_nav), gross=gross, costs=costs, filled=bool(fills),
                          submitted=submitted, mandatory_submissions=(submitted and forced), open_orders=len(state["orders"])))
        holdings.append(dict(date=day, **{a:p["units"] for a,p in book["positions"].items()}))
        previous_nav = book["total"]
    return tuple(pd.DataFrame(x) for x in (daily, events, decisions, holdings))


def score(daily, after, end, capital):
    past = daily[daily.date<=after]
    start = capital if past.empty else past.nav.iloc[-1]
    window = daily[(daily.date>after)&(daily.date<=end)]
    series = np.r_[start, window.nav]
    return dict(start_date=window.date.iloc[0], end_date=window.date.iloc[-1], sessions=len(window),
                start_nav=start, end_nav=series[-1], net_return=series[-1]/start-1,
                max_drawdown=float(np.min(series/np.maximum.accumulate(series)-1)),
                turnover=window.turnover.sum(), fill_days=int(window.filled.sum()), costs_vnd=window.costs.sum(),
                submissions=int(window.submitted.sum()), compulsory_submissions=int(window.mandatory_submissions.sum()))


def joined(arms, index):
    return pd.concat([result[index].assign(arm=arm) for arm,result in arms.items()], ignore_index=True)


def analysis(out, manifest):
    protocol, frames, targets = load()
    cutoff, end = protocol["development_end"], protocol["evaluation_end"]
    sub = protocol["subperiod_end"]
    periods = {"full":("",end), "development":("",cutoff), "held_out":(cutoff,end),
               "held_out_1":(cutoff,sub), "held_out_2":(sub,end)}
    primary = protocol["sensitivity"][0]
    cap = protocol["capital"]
    development = []
    for t in protocol["thresholds"]:
        daily = simulate(frames, targets, primary, "C", t, cutoff)[0]
        assert daily.date.max()==cutoff
        development.append(dict(threshold=t, **score(daily, "", cutoff, cap)))
    dev = pd.DataFrame(development).sort_values(["net_return","turnover","threshold"],ascending=[False,True,True])
    dev.to_csv(out/"development.csv",index=False)
    chosen = float(dev.threshold.iloc[0])
    write_json(out/"selection.json",dict(threshold=chosen, locked_at=datetime.now(timezone.utc).isoformat(),
                                        cutoff=cutoff, development_sha256=sha(out/"development.csv"),
                                        registration_sha256=sha(INPUT/"registration.json")))
    all_scores, paired, trade_costs = [], [], []
    for experiment in protocol["sensitivity"]:
        name = experiment["name"]
        specs = {"A":None, "B":None, "C":chosen}
        if name == "base":
            specs.update({f"C_{int(100*t)}pct":t for t in protocol["thresholds"] if t!=chosen})
        arms = {a:simulate(frames,targets,experiment,a if a in ("A","B") else "C",t,end)
                for a,t in specs.items()}
        if name == "base":
            zero = simulate(frames, targets, experiment, "C", 0., end)
            for i in (0,1,3):
                pd.testing.assert_frame_equal(arms["B"][i],zero[i],check_exact=True)
            base_dev = score(arms["C"][0], "", cutoff, cap)
            assert base_dev["net_return"] == dev.net_return.iloc[0]
            opening_end = sorted(targets)[1]
            def opening(result):
                rows = result[1]
                return rows[rows.date<=opening_end].dropna(axis=1,how="all").reset_index(drop=True)
            for a in ("B","C"):
                pd.testing.assert_frame_equal(opening(arms[a]), opening(arms["A"]), check_exact=True)
            assert arms["A"][2].submitted.sum() == 1
            for i,n in enumerate(["daily.csv","events.csv","reviews.csv","units.csv"]):
                data = joined({a:arms[a] for a in ("A","B","C")}, i)
                if i==1:
                    data["sold_lots"]=data.sold_lots.map(lambda x:json.dumps(x) if isinstance(x,list) else "")
                data.to_csv(out/n,index=False)
        for a,result in arms.items():
            daily, events = result[:2]
            for period,(after,until) in periods.items():
                all_scores.append(dict(scenario=name, arm=a, threshold=specs[a], period=period,
                                       **score(daily, after, until, experiment.get("capital",cap))))
                if name != "base" or a not in ("A","B","C"):
                    continue
                fills = events[(events.kind=="fill")&(events.date>after)&(events.date<=until)]
                for asset,grp in fills.groupby("asset"):
                    trade_costs.append(dict(period=period,arm=a,asset=asset,fee=grp.fee.sum(),
                                            tax=grp.tax.sum(),spread=grp.spread.sum(),notional=grp.gross.sum()))
        for a,b in (("B","A"),("C","B")):
            left, right = (arms[k][0].set_index("date") for k in (a,b))
            for period,(after,until) in periods.items():
                r = pd.concat([left.net_return.rename(a),right.net_return.rename(b)],axis=1).loc[lambda d:(d.index>after)&(d.index<=until)]
                excluded = (np.log1p(r[a])-np.log1p(r[b])).abs().nlargest(5).index
                payment = (1+r).prod()-1
                trimmed = (1+r.drop(index=excluded)).prod()-1
                paired.append(dict(scenario=name, period=period, comparison=f"{a}-{b}", delta_return=payment[a]-payment[b],
                                   delta_without_five=trimmed[a]-trimmed[b], removed_dates=",".join(excluded)))
    pd.DataFrame(all_scores).to_csv(out/"summary.csv",index=False)
    pd.DataFrame(paired).to_csv(out/"paired.csv",index=False)
    pd.DataFrame(trade_costs).to_csv(out/"costs_by_asset.csv",index=False)
    manifest.update(selected_threshold=chosen, validations=["cash, units and NAV reconciliation each session on all scenarios",
                    "C threshold zero matches B fills, units and daily books exactly", "one opening basket in A",
                    "opening fills identical", "development segment replay equals selection"])


def main():
    start = datetime.now(timezone.utc)
    out = HERE/"runs"/start.strftime("%Y%m%dT%H%M%S%fZ")
    out.mkdir(parents=True)
    source = out/"source"
    source.mkdir()
    for f in (HERE/"run.py", HERE/"freeze.py", HERE/"protocol.json", HERE/"default-amendment.md", Path(ledger.__file__)):
        shutil.copyfile(f, source/f.name)
    previous = sorted(p.name for p in out.parent.iterdir() if p.name < out.name)
    manifest = dict(schema=1, run=out.name, parent_run=previous[-1] if previous else None, started_at=start.isoformat(), status="running",
                    working_directory=str(ROOT), timezone="Asia/Ho_Chi_Minh", argv=[sys.executable,*sys.argv],
                    registration_sha256=sha(INPUT/"registration.json"), amendment_sha256=sha(INPUT/"amendment.json"),
                    git_head=subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip(),
                    branch=subprocess.check_output(["git","branch","--show-current"],text=True).strip(),
                    dirty=bool(subprocess.check_output(["git","status","--porcelain"])), source_sha256={f.name:sha(f) for f in source.iterdir()},
                    environment=dict(python=sys.version, os=platform.platform(),cpu=platform.machine(),pandas=pd.__version__,numpy=np.__version__),
                    model="Frozen target replay; no retraining, inference, caches or solver.")
    write_json(out/"manifest.json",manifest)
    tick = time.monotonic()
    try:
        analysis(out,manifest)
        manifest.update(status="complete",exit_code=0)
    except Exception:
        (out/"stderr.log").write_text(traceback.format_exc())
        manifest.update(status="failed",exit_code=1)
        raise
    finally:
        manifest.update(elapsed_seconds=time.monotonic()-tick,ended_at=datetime.now(timezone.utc).isoformat(),
                        artifact_sha256={p.name:sha(p) for p in out.iterdir() if p.is_file() and p.name!="manifest.json"})
        write_json(out/"manifest.json",manifest)
        print(out.relative_to(ROOT),manifest["status"])


if __name__ == "__main__":
    main()
