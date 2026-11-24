from datetime import datetime, timedelta, timezone
import json

import numpy as np
import pandas as pd
import pytest

from portfolio_contracts import canonical_hash
from portfolio_contracts.assets import candidate_hash
from scripts import gold_shadow_score as score
from scripts.gold_shadow_marks import CaptureUnavailable, Captures

ASSETS = ["ACB", "BID", "CTG", "DGC", "FPT", "GOLD", "VFF"]
AS_OF = datetime(2028, 1, 1, tzinfo=timezone.utc)


class Market:
    def __init__(self, n=28, missing=(), flagged=()):
        self.sessions = list(pd.bdate_range("2026-11-25", periods=n).strftime("%Y-%m-%d"))
        self.provenance, self.calendar_errors = {}, {}
        self.missing, self.flagged = missing, flagged

    def mark(self, i, assets, previous=None):
        if i in self.missing:
            raise CaptureUnavailable("missing verified receipt")
        prices = {a: 100. for a in assets}
        prices["ACB"] = 100. if i < 2 else 120.
        return dict(prices=prices, share_factors={a: 1. for a in assets}, bid=99., ask=101., provider_carry_flag=i in self.flagged, day=self.sessions[i],
                    nav_date=self.sessions[i], nav_vintage=self.sessions[i + 5])


def seal(row, **changes):
    row = row | changes
    row.pop("receipt_sha256", None)
    return row | {"receipt_sha256": canonical_hash(row)}


def target(market, i=0, **changes):
    day = market.sessions[i]
    issue = datetime.fromisoformat(day + "T19:00:00+07:00")
    expiry = issue + timedelta(hours=14)
    return seal(dict(job_id=f"job-{i}", status="TARGET", study_id=score.STUDY_ID, protocol_sha256=score.PROTOCOL_SHA256,
                     series_id="portfolio1", data_policy_id="data", applied_selection="auto-k5", constraints_hash="a"*64,
                     view_protocol="gold-k5-derived-v1", policy_version="hybrid", risk_profile="growth",
                     selection_policy_id="user-k5-v1", candidate_hash=candidate_hash(ASSETS),
                     horizon_sessions=5, execution_lag_sessions=1, registered_at=issue.isoformat(),
                     enrolled_at=score.REGISTERED_AT.isoformat(), decision_session=day,
                     issued_at=issue.isoformat(), witnessed_at=issue.isoformat(), decision_at=issue.isoformat(), issue_before=expiry.isoformat(),
                     valid_until=expiry.isoformat(), asset_ids=ASSETS, selected_equity_ids=ASSETS[:5],
                     production_weights=[.5, 0., 0., 0., 0., .2, .3], shadow_weights=[.3, 0., 0., 0., 0., .4, .3],
                     forecast={"prediction_5d": .01}), **changes)


def run(market, *rows):
    return score.report(rows, market, AS_OF)


def test_paired_issue_drift_costs_and_duplicate_handling():
    market = Market()
    first, next_row = target(market), target(market, 5)
    repeated_day = seal(first, job_id="z")
    same_date_other = seal(first, job_id="other", series_id="portfolio2")
    # Reordering the candidate vector at a later cutoff cannot swap holdings.
    next_row = seal(next_row, asset_ids=ASSETS[::-1], production_weights=next_row["production_weights"][::-1],
                    shadow_weights=next_row["shadow_weights"][::-1])
    result = run(market, repeated_day, next_row, first, first, target(market, 1), same_date_other)
    assert result["duplicate_exports"] == 1 and result["context_count"] == 2
    cohort = result["cohorts"][0]
    assert cohort["counts"] == {"MATURE": 2, "DUPLICATE_DATE": 1, "OVERLAPPING_WINDOW": 1}
    first, next_row = cohort["events"][0], cohort["events"][-1]
    assert first["execution_session"] == market.sessions[1] and first["exit_session"] == market.sessions[6]
    assert first["realized_spread_5d"] == pytest.approx(-.04)
    assert first["forecast_error_5d"] == pytest.approx(.05)
    for arm, equity, gold in (("production", .5, .2), ("shadow", .3, .4)):
        first_fill = first["arms"][arm]
        size = 1 / (1 + gold * .01 + (1-gold) * .001)
        assert first_fill["net_return"] == pytest.approx(size * (1 + equity * .2) - 1)
        assert first_fill["turnover"] == pytest.approx(1)
        assert first_fill["gold_spread_cost"] == pytest.approx(size * gold * .01)
        assert next_row["arms"][arm]["pre_weights"]["ACB"] == pytest.approx(equity * 1.2 / (1 + equity*.2))
        assert next_row["arms"][arm]["turnover"] < .1
    assert first["valuation_vintages"][-1]["nav_vintage"] == market.sessions[11]
    assert cohort["assessment"]["status"] == "INSUFFICIENT_EVIDENCE"
    json.dumps(result, allow_nan=False)


def test_pending_abstention_missing_quote_and_research_cutoff():
    market = Market(10)
    first = target(market)
    rows = run(market, first, seal(first, job_id="skip", status="ABSTAIN", reason="fit_warmup"),
               seal(first, job_id="late", witnessed_at=first["issue_before"]))["cohorts"][0]
    assert rows["counts"] == {"PENDING": 1, "ABSTAIN": 1, "INELIGIBLE": 1}
    assert rows["assessment"]["mature_dates"] == 0
    just_before_witness = score.aware(first["issued_at"]) + timedelta(seconds=1)
    delayed = seal(first, witnessed_at=(just_before_witness + timedelta(seconds=1)).isoformat())
    assert score.report([delayed], market, just_before_witness)["excluded_after_as_of"] == 1
    market = Market(missing=[1])
    rows = run(market, first, target(market, 5))["cohorts"][0]
    assert rows["counts"] == {"UNRESOLVED": 2}
    assert rows["events"][-1]["reason"].startswith("prior_entry_unresolved:")
    for endpoint in (1, 6):
        cohort = run(Market(flagged=[endpoint]), first)["cohorts"][0]
        assert cohort["counts"] == {"NON_EXECUTABLE": 1}
        assert cohort["assessment"]["mature_dates"] == 0
    # An unresolved interior valuation does not undo the actual paper entry.
    cohort = run(Market(missing=[3]), first, target(market, 5))["cohorts"][0]
    assert cohort["counts"] == {"UNRESOLVED": 1, "MATURE": 1}
    assert cohort["events"][-1]["arms"]["shadow"]["turnover"] < .1
    assert cohort["all_fills"]["shadow"]["executions"] == 2
    assert cohort["all_fills"]["shadow"]["sum_one_way_turnover"] > 1
    assert cohort["all_fills"]["shadow"]["sum_gold_spread_cost_nav_fractions"] > .003
    assert cohort["assessment"]["censored_executions_through_sample_end"] == [first["job_id"]]
    with pytest.raises(ValueError, match="hash mismatch"):
        run(market, first | {"series_id": "other"})
    with pytest.raises(ValueError, match="Conflicting"):
        run(market, first, seal(first, series_id="other"))
    with pytest.raises(ValueError, match="protocol"):
        run(market, seal(first, protocol_sha256="different"))


def test_first_sixty_fixed_paired_dates_and_bootstrap():
    rng = np.random.default_rng(99)
    baseline = rng.normal(.0004, .006, (60,5))
    events = []
    for i, returns in enumerate(baseline):
        pair = {arm: dict(daily_returns=(returns + gain).tolist(), turnover=.1, gold_spread_cost=.0001, non_gold_fee=.0001)
                for arm, gain in (("production", 0), ("shadow", .0005))}
        events.append(dict(decision_session=str(i), arms=pair))
    assert score.assessment(events[:-1])["status"] == "INSUFFICIENT_EVIDENCE"
    result = score.assessment(events + events[:1])
    assert result["status"] == "MEETS_RESEARCH_CRITERIA" and result["paired_sessions"] == 300
    assert result["mature_dates"] == 61 and result["sample_end"] == "59"
    assert result["ci_95"][0] > 0 and min(result["leave_one_block_out_delta"]) > 0
    assert len(result["complete_20_date_blocks"]) == 3
    censored = [dict(job_id="incomplete-fill", decision_session="04")]
    assert score.assessment(events, censored)["status"] == "INSUFFICIENT_EVIDENCE"


def test_valuation_requires_same_day_source_and_does_not_use_rehearsal(tmp_path):
    (tmp_path/"rehearsal"/"2026-11-25"/"first").mkdir(parents=True)
    (tmp_path/"rehearsal"/"2026-11-25"/"first"/"summary.json").write_text("{}")
    market = Captures(tmp_path, AS_OF)
    assert market.sessions == [] and market.paths == {}
    with pytest.raises(CaptureUnavailable, match="no contemporaneous capture"):
        market._quote("2026-11-25")


def test_raw_endpoint_quote_integrity_units_delay_and_vintage(tmp_path):
    from hashlib import sha256
    from datetime import date
    from market_service.hybrid_forward_capture import archive
    from market_service.phase1_sources import normalize_gold_archive
    from market_service.refresh_provider import BASE, normalized_csv
    from test_hybrid_forward_panel import calendar_capture

    batch, cutoff = calendar_capture(tmp_path)
    day = date(2026, 11, 24)
    started = cutoff - timedelta(hours=1)

    def add(name, raw, url, method, rows, **kwargs):
        receipt = dict(source=name, status="recorded", attempted_at=started.isoformat(),
                       available_by_decision=True, raw=archive(tmp_path, raw), request=kwargs | dict(
                           method=method, url=url, requested_at=started.isoformat(), received_at=started.isoformat()))
        if rows is not None:
            receipt.update(normalized_sha256=sha256(normalized_csv(rows, name)).hexdigest(),
                           latest_date=str(rows[-1][0]), row_count=len(rows))
        raw_receipt = json.dumps(receipt).encode()
        (batch/f"{name}.json").write_bytes(raw_receipt)
        summary_path = batch/"summary.json"
        summary = json.loads(summary_path.read_bytes())
        summary["receipts"][name] = sha256(raw_receipt).hexdigest()
        summary_path.write_text(json.dumps(summary))

    raw = """Vàng SJC 1L, 10L, 1KG · Hồ Chí Minh, triệu đồng / lượng
    <table class="gv-table"><tr><th>Ngày</th><th>Mua lại</th><th>Bạn trả</th></tr>
    <tr><td>24/11/2026</td><td>82,5</td><td>84,5 ▲</td></tr></table>""".encode()
    rows, _ = normalize_gold_archive(raw, 2026, 11)
    add("GOLD-2026-11", raw, "https://giavang.tv/lich-su/2026/11", "GET", rows)
    add("ACB", b'{"data_day":[{"t":"2026-11-24","c":1234}]}', BASE+"/stocks/ACB/data_day",
        "GET", [(day,1234)], **{"from": "2020-01-14", "to": str(day)})
    identity = dict(status=200, data=dict(rows=[dict(id=21, code="VFF", dataFundAssetType=dict(code="BOND"),
                                                    owner=dict(shortName="VINACAPITAL"))]))
    add("VFF-identity", json.dumps(identity).encode(), "https://api.fmarket.vn/res/products/filter", "POST", None,
        payload=dict(searchField="VFF", types=["NEW_FUND","TRADING_FUND"], pageSize=100))
    nav = dict(status=200, data=[dict(productId=21, nav=75, navDate="2026-11-18"),
                                 dict(productId=21, nav=95, navDate="2026-11-24")])
    add("VFF", json.dumps(nav).encode(), "https://api.fmarket.vn/res/product/get-nav-history", "POST",
        [(day-timedelta(days=6),75),(day,95)], payload=dict(isAllData=1, productId=21, fromDate=None, toDate="20261124"))
    market = Captures(tmp_path, cutoff)
    mark = market.mark(0, ["GOLD","ACB"])
    assert mark["ask"] == 84_500_000 and mark["prices"]["GOLD"] == 83_500_000
    assert mark["prices"]["ACB"] == 1234 and mark["nav_date"] is None
    assert market._nav("2026-11-20", str(day)) == (75., "2026-11-18")
    with pytest.raises(CaptureUnavailable, match="No genuine VFF NAV"):
        market._nav("2026-11-16", str(day))
    assert market.provenance[str(batch.relative_to(tmp_path))]["receipts"]["GOLD-2026-11"]["raw_sha256"] == sha256(raw).hexdigest()
    assert Captures(tmp_path, started).sessions == []
    (batch/"GOLD-2026-11.json").write_text("{}")
    with pytest.raises(CaptureUnavailable, match="receipt hash"):
        Captures(tmp_path, cutoff)._quote(str(day))


def test_adjusted_equity_vintage_rebases_existing_units_and_frozen_k5_label():
    class SplitMarket(Market):
        def mark(self, i, assets, previous=None):
            mark = super().mark(i, assets, previous)
            if i >= 3:
                mark["prices"]["ACB"] /= 2
                if previous and previous["day"] < self.sessions[3]:
                    mark["share_factors"]["ACB"] = 2.
            return mark

    original, split = Market(), SplitMarket()
    rows = [target(original), target(original, 5)]
    before = run(original, *rows)["cohorts"][0]["events"]
    after = run(split, *rows)["cohorts"][0]["events"]
    for old, new in zip(before, after, strict=True):
        assert old["realized_spread_5d"] == pytest.approx(new["realized_spread_5d"])
        for arm in score.ARMS:
            for key in ("daily_returns", "pre_weights", "net_return", "turnover", "non_gold_fee"):
                assert old["arms"][arm][key] == pytest.approx(new["arms"][arm][key])


def test_unheld_equity_requires_only_endpoints_and_no_vff_needs_no_nav_delay():
    class ThinMarket(Market):
        def mark(self, i, assets, previous=None):
            if i == 3 and "BID" in assets:
                raise CaptureUnavailable("unheld name has no close")
            if "VFF" in assets:
                raise AssertionError("No VFF exposure")
            return dict(prices={a:100. for a in assets | {"GOLD"}}, share_factors={a:1. for a in assets},
                        bid=99., ask=101., day=self.sessions[i], nav_date=None, nav_vintage=None,
                        provider_carry_flag=False)

    market = ThinMarket(7)
    names = ASSETS[:-1]
    first = target(market, asset_ids=names, candidate_hash=candidate_hash(names),
                   production_weights=[.5,0,0,0,0,.5], shadow_weights=[.6,0,0,0,0,.4])
    assert run(market, first)["cohorts"][0]["counts"] == {"MATURE": 1}
