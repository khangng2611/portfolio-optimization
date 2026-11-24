"""Capture GiaVang.TV monthly archive responses once and reconstruct the revision offline."""
import argparse
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from urllib.parse import urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = HERE / "snapshot"
READY = ROOT / "outputs/step1/readiness_20261012"
ORIGINAL = READY / "gold_archive_daily.csv"
CALENDAR = ROOT / "extensions_C_v1/inputs/prices_valuation.csv"
MONTHS = pd.period_range("2019-12", "2026-04", freq="M")
PRODUCT = "Vàng SJC 1L, 10L, 1KG · Hồ Chí Minh"
UNITS = "triệu đồng / lượng"
COLUMNS = ["Ngày", "Mua lại", "Bạn trả"]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def require(valid, message):
    if not valid:
        raise ValueError(message)


def capture_pages(jobs, folder, receipt_name):
    raw = OUT / folder
    raw.mkdir(parents=True, exist_ok=True)
    receipt = OUT / receipt_name
    records = json.loads(receipt.read_text()) if receipt.exists() else []
    saved = {r["url"]: r for r in records}
    with requests.Session() as session:
        for filename, url in jobs:
            path = raw / filename
            if url in saved:
                require(sha(path.read_bytes()) == saved[url]["sha256"], f"Existing evidence changed: {path}")
                continue
            require(not path.exists(), f"Unregistered evidence: {path}")
            response = session.get(url, timeout=(10, 30))
            received = datetime.now(timezone.utc).isoformat()
            response.raise_for_status()
            require(response.status_code == 200 and response.url.rstrip("/") == url, f"Unexpected response {url}")
            path.write_bytes(response.content)
            records.append(dict(file=filename, url=url, final_url=response.url, status=response.status_code,
                                received_at_utc=received, headers=dict(response.headers),
                                bytes=len(response.content), sha256=sha(response.content)))
            tmp = receipt.with_suffix(".tmp")
            write_json(tmp, records)
            tmp.replace(receipt)
            time.sleep(1)


def price(cell):
    value = cell.get_text(strip=True)
    require(re.fullmatch(r"\d+,\d{1,3}", value), f"Unexpected quote format: {value}")
    return int(Decimal(value.replace(",", ".")) * 1000)


def parse_month(receipt):
    path = OUT / "raw" / receipt["file"]
    data = path.read_bytes()
    require(sha(data) == receipt["sha256"], f"Digest mismatch: {path}")
    soup = BeautifulSoup(data, "html.parser")
    yr, mo = map(int, path.stem.split("_"))
    text = soup.get_text(" ", strip=True)
    url = receipt["url"]
    table, = soup.select("table.gv-table")
    require(soup.select_one('link[rel="canonical"]')["href"] == url and
            soup.h1.get_text(strip=True) == f"Giá vàng SJC tháng {mo:02d}/{yr}" and
            f"Sản phẩm theo dõi: {PRODUCT}" in text and UNITS in text and
            [x.get_text(strip=True) for x in table.select("thead th")] == COLUMNS,
            f"Unexpected archive identity or units: {path}")
    rows = []
    for tr in table.select("tbody tr"):
        day_cell, bid_cell, ask_cell = tr.find_all("td", recursive=False)
        anchor = day_cell.select_one("a[href]")
        d = datetime.strptime(anchor.get_text(strip=True), "%d/%m/%Y").date()
        day_url = urljoin(url, anchor["href"])
        require((d.year, d.month) == (yr, mo) and day_url == f"{url}/{d.day}",
                f"Inconsistent row date or daily link: {d}")
        bid, ask = price(bid_cell), price(ask_cell.select_one(".gv-row__price"))
        label = ask_cell.select_one(".gv-row__chg").get_text(strip=True)
        require(0 < bid <= ask and
                (label in {"không đổi", "ngày đầu kỳ"} or label.startswith(("▲", "▼"))),
                f"Unexpected quote or change label: {d}")
        rows.append(dict(date=pd.Timestamp(d), archive_bid=bid, archive_ask=ask,
                         provider_carry_flag=label == "không đổi", source_file=path.name,
                         provider_ask_change_label=label, source_url=url, day_url=day_url))
    require(rows and len({r["date"] for r in rows}) == len(rows), f"Empty or duplicate dates: {path}")
    return rows


def flat_runs(panel, prefix, sessions):
    prices = panel[[prefix + "_bid", prefix + "_ask"]]
    group = prices.ne(prices.shift()).any(axis=1).cumsum()
    rows = []
    for _, run in prices.dropna().groupby(group):
        start, end = run.index[[0, -1]]
        if len(run) < 2:
            continue
        rows.append(dict(vintage=prefix, start=start.date(), end=end.date(), calendar_days=len(run),
                         sessions=len(sessions.intersection(run.index)), bid=run.iloc[0, 0], ask=run.iloc[0, 1]))
    return pd.DataFrame(rows).sort_values(["calendar_days", "start"], ascending=[False, True])


def reconstruct():
    receipts = json.loads((OUT / "receipts.json").read_text())
    require({r["file"] for r in receipts} == {f"{m.year}_{m.month}.html" for m in MONTHS}
            and len(receipts) == len(MONTHS), "Incomplete month list")
    parsed = pd.DataFrame(row for receipt in receipts for row in parse_month(receipt)).set_index("date").sort_index()
    require(parsed.index.is_unique, "Duplicate dates across months")
    cols = ["archive_bid", "archive_ask", "provider_carry_flag", "source_file"]
    parsed[cols].to_csv(OUT / "archive.csv")
    days = pd.date_range(MONTHS[0].start_time, MONTHS[-1].end_time.normalize(), name="date")
    sessions = pd.DatetimeIndex(pd.read_csv(CALENDAR, usecols=["date"], parse_dates=["date"]).date)
    frozen_source = json.loads((ROOT / "extensions_C_v1/inputs/availability_policy.json").read_text())
    pinned = next(r["sha256"] for r in frozen_source["source_rows"] if r["asset"] == "GOLD")
    require(sha(ORIGINAL.read_bytes()) == pinned, "Frozen day series failed its pinned digest")
    frozen = pd.read_csv(ORIGINAL, parse_dates=["date"]).set_index("date").rename(columns={
        "sjc_buy": "frozen_bid", "sjc_sell": "frozen_ask", "provider_carry_flag": "frozen_provider_carry_flag"})
    orig_receipts = {r["file"]: r for r in json.loads((READY / "gold_archive_manifest.json").read_text())["records"]}
    for r in orig_receipts.values():
        require(sha((READY / "gold_archive_raw" / r["file"]).read_bytes()) == r["sha256"],
                f"Frozen original response failed digest: {r['file']}")
    require(frozen.index.is_unique, "Duplicate frozen dates")
    panel = parsed.reindex(days).join(frozen[["frozen_bid", "frozen_ask", "frozen_provider_carry_flag"]])
    panel["is_market_session"] = panel.index.isin(sessions)
    panel["frozen_source_sha256"] = frozen.source_file.map(lambda name: orig_receipts[name]["sha256"])
    panel["revised_source_sha256"] = panel.source_file.map({r["file"]: r["sha256"] for r in receipts})
    panel["bid_revision"] = panel.archive_bid - panel.frozen_bid
    panel["ask_revision"] = panel.archive_ask - panel.frozen_ask
    present = panel.archive_bid.notna()
    common = present & panel.frozen_bid.notna()
    differ = common & (panel.bid_revision.ne(0) | panel.ask_revision.ne(0))
    panel["revision_status"] = "missing_both"
    panel.loc[~present & panel.frozen_bid.notna(), "revision_status"] = "revised_row_missing"
    panel.loc[present & ~panel.frozen_bid.notna(), "revision_status"] = "newly_covered"
    panel.loc[common, "revision_status"] = "same_prices"
    panel.loc[differ, "revision_status"] = "revised_prices"
    panel["provider_flag_revised"] = (panel.provider_carry_flag != panel.frozen_provider_carry_flag).where(common)
    panel["pair_flat_vs_previous_calendar_day"] = panel.archive_bid.eq(panel.archive_bid.shift()) & panel.archive_ask.eq(panel.archive_ask.shift())
    panel["quote_status"] = panel.provider_ask_change_label.map(
        lambda label: ("missing_source_row" if pd.isna(label) else
                       "month_open_change_unreported" if label == "ngày đầu kỳ" else
                       "provider_ask_unchanged_possible_carry" if label == "không đổi" else
                       "provider_ask_changed"))
    panel.loc[panel.provider_carry_flag.eq(True) & ~panel.pair_flat_vs_previous_calendar_day
              & panel.archive_bid.shift().notna(), "quote_status"] = "provider_ask_unchanged_pair_changed"
    runs = pd.concat([flat_runs(panel, prefix, sessions) for prefix in ["frozen", "archive"]])
    runs.to_csv(OUT / "flat_periods.csv", index=False)
    monthly = []
    for r in receipts:
        chunk = panel.loc[panel.index.to_period("M") == pd.Period(r["file"].replace("_", "-")[:-5], freq="M")]
        f = orig_receipts[r["file"]]
        monthly.append(dict(source_file=r["file"], source_url=r["url"], received_at_utc=r["received_at_utc"],
                            sha256=r["sha256"], frozen_sha256=f["sha256"], frozen_received_at_utc=f["received_at_utc"],
                            product=PRODUCT, column_labels=" | ".join(COLUMNS), source_unit=UNITS,
                            first=chunk.index.min().date(), last=chunk.index.max().date(),
                            expected_rows=len(chunk), revised_rows=int(chunk.archive_ask.count()),
                            revised_missing=int(chunk.archive_ask.isna().sum()),
                            price_revisions=int((chunk.revision_status == "revised_prices").sum()),
                            flagged_ask_unchanged=int(chunk.provider_carry_flag.eq(True).sum()),
                            revised_flags=int(chunk.provider_flag_revised.eq(True).sum())))
    pd.DataFrame(monthly).to_csv(OUT / "months.csv", index=False)
    return panel, runs


def detail_jobs(runs):
    days = set(pd.to_datetime(["2024-06-22", "2025-01-22", "2025-03-22", "2025-09-14",
                               "2025-09-15", "2025-09-30", "2026-02-23", "2026-02-24"]))
    for run in runs.query("vintage == 'archive' and calendar_days >= 12").itertuples():
        days.update(pd.date_range(run.start, pd.Timestamp(run.end) + pd.Timedelta(days=1)))
    return [(f"{d.date()}.html", f"https://giavang.tv/lich-su/{d.year}/{d.month}/{d.day}") for d in sorted(days)]


def parse_detail(receipt, panel):
    path = OUT / "daily_raw" / receipt["file"]
    data = path.read_bytes()
    require(sha(data) == receipt["sha256"], f"Digest mismatch: {path}")
    soup = BeautifulSoup(data, "html.parser")
    d = pd.Timestamp(path.stem)
    require(soup.select_one('link[rel="canonical"]')["href"] == receipt["url"] == panel.at[d, "day_url"]
            and soup.h1.get_text(strip=True) == d.strftime("Giá vàng ngày %d/%m/%Y"), f"Unexpected detail date: {d}")
    table = soup.select_one("table.gv-table--regions")
    rows = [] if table is None else table.select("tbody tr")
    if table:
        require([x.get_text(strip=True) for x in table.select("thead th")] == ["Thương hiệu", "Mua vào", "Bán ra"],
                f"Unrecognized day table: {d}")
    brands = [row.th.get_text(" ", strip=True) for row in rows]
    detail = dict(date=d, detail_url=receipt["url"], detail_sha256=receipt["sha256"],
                  detail_brands="|".join(brands), detail_status="SJC_absent_from_daily_table",
                  detail_bid=None, detail_ask=None, detail_ask_change_label=None, detail_intraday_unchanged_note=None)
    if "SJC" in brands:
        matched = [el.get_text(" ", strip=True) for el in soup.select("li")
                   if el.get_text(" ", strip=True).startswith(d.strftime("Giá vàng SJC ngày %d/%m/%Y:"))]
        require(len(matched) == 1 and f"Sản phẩm: {PRODUCT}" in matched[0] and brands.count("SJC") == 1,
                f"Daily quote product unconfirmed: {d}")
        bid, ask = rows[brands.index("SJC")].select("td")
        bid_value, ask_value = price(bid), price(ask.select_one(".gv-row__price"))
        require(0 < bid_value <= ask_value, f"Invalid detailed quote on {d}")
        rounded_pair = [int(Decimal(v).quantize(Decimal("1E2"), rounding=ROUND_HALF_UP)) for v in [bid_value, ask_value]]
        agrees = rounded_pair == panel.loc[d, ["archive_bid", "archive_ask"]].tolist()
        detail.update(detail_status="SJC_pair_agrees_at_monthly_precision" if agrees else "SJC_pair_disagrees",
                      detail_bid=bid_value, detail_ask=ask_value, detail_ask_change_label=ask.select_one(".gv-row__chg").get_text(strip=True),
                      detail_intraday_unchanged_note="không đổi giá trong ngày" in matched[0])
    return detail


def assess_details(panel, runs):
    records = json.loads((OUT / "daily_receipts.json").read_text())
    require({r["file"] for r in records} == {filename for filename, _ in detail_jobs(runs)}
            and len({r["file"] for r in records}) == len(records), "Incomplete targeted daily evidence")
    detail = pd.DataFrame(parse_detail(r, panel) for r in records).set_index("date").sort_index()
    detail.to_csv(OUT / "daily_detail_checks.csv")
    panel = panel.join(detail)
    panel["detail_status"] = panel.detail_status.fillna("daily_detail_unexamined")
    # The PNJ vendor sells SJC bars and the repository's legacy series is calendar-filled.
    legacy_path = ROOT / "datasets/gold/gold_full.csv"
    legacy = pd.read_csv(legacy_path, parse_dates=["date"]).set_index("date")[["sjc_buy", "sjc_sell"]]
    require(legacy.index.is_unique, "Duplicate PNJ-feed dates")
    panel = panel.join(legacy.rename(columns={"sjc_buy": "legacy_pnj_sjc_bid", "sjc_sell": "legacy_pnj_sjc_ask"}))
    panel["legacy_pnj_ask_minus_monthly"] = panel.legacy_pnj_sjc_ask - panel.archive_ask
    panel.to_csv(OUT / "day_comparison.csv")
    long_runs = []
    for run in runs.query("vintage == 'archive' and calendar_days >= 12").itertuples():
        part = panel.loc[run.start:run.end]
        next_day = pd.Timestamp(run.end) + pd.Timedelta(days=1)
        before = panel.loc[pd.Timestamp(run.end), ["archive_bid", "archive_ask"]].to_numpy(float)
        after = panel.loc[next_day, ["archive_bid", "archive_ask"]].to_numpy(float)
        long_runs.append(dict(start=run.start, end=run.end, calendar_days=run.calendar_days,
                              market_sessions=int(part.is_market_session.sum()),
                              detail_with_sjc=int(part.detail_bid.count()),
                              detail_without_sjc=int(part.detail_status.eq("SJC_absent_from_daily_table").sum()),
                              sessions_without_sjc=int((part.is_market_session & part.detail_bid.isna()).sum()),
                              detail_disagrees=int(part.detail_status.eq("SJC_pair_disagrees").sum()),
                              legacy_pnj_distinct_asks=int(part.legacy_pnj_sjc_ask.nunique()),
                              legacy_pnj_low=part.legacy_pnj_sjc_ask.min(), legacy_pnj_high=part.legacy_pnj_sjc_ask.max(),
                              next_day=next_day.date(), next_mid_change=after.sum() / before.sum() - 1))
    pd.DataFrame(long_runs).to_csv(OUT / "residual_flat_period_checks.csv", index=False)
    original_spells = []
    for run in runs.query("vintage == 'frozen' and calendar_days >= 12").itertuples():
        part = panel.loc[run.start:run.end]
        next_day = pd.Timestamp(run.end) + pd.Timedelta(days=1)
        boundary = panel.loc[[pd.Timestamp(run.end), next_day]]
        mids = {key: boundary[[key + "_bid", key + "_ask"]].mean(axis=1) for key in ("archive", "frozen")}
        original_spells.append(dict(start=run.start, end=run.end, calendar_days=run.calendar_days,
                                    revised_pairs=part[["archive_bid", "archive_ask"]].drop_duplicates().shape[0],
                                    revised_calendar_rows=int(part.revision_status.eq("revised_prices").sum()),
                                    revised_market_sessions=int((part.revision_status.eq("revised_prices") & part.is_market_session).sum()),
                                    repricing_date=next_day.date(),
                                    frozen_next_mid_return=mids["frozen"].iloc[1] / mids["frozen"].iloc[0] - 1,
                                    revised_next_mid_return=mids["archive"].iloc[1] / mids["archive"].iloc[0] - 1))
    pd.DataFrame(original_spells).to_csv(OUT / "frozen_flat_run_revisions.csv", index=False)
    summary = dict(
        provider="GiaVang.TV", product=PRODUCT, monthly_source_unit=UNITS,
        normalized_unit="thousand VND per luong", monthly_precision="one decimal million VND per luong",
        period=[str(panel.index[0].date()), str(panel.index[-1].date())], revised_months=len(MONTHS),
        expected_calendar_days=len(panel), monthly_pairs=int(panel.archive_ask.count()),
        missing_monthly_days=int(panel.archive_ask.isna().sum()), session_days=int(panel.is_market_session.sum()),
        changed_price_pairs=int(panel.revision_status.eq("revised_prices").sum()),
        changed_session_pairs=int((panel.revision_status.eq("revised_prices") & panel.is_market_session).sum()),
        provider_ask_unchanged=int(panel.provider_carry_flag.eq(True).sum()),
        revised_ask_change_flags=int(panel.provider_flag_revised.eq(True).sum()),
        flagged_but_pair_changed=int(panel.quote_status.eq("provider_ask_unchanged_pair_changed").sum()),
        month_opener=int(panel.quote_status.eq("month_open_change_unreported").sum()),
        detail_checks=len(detail), detail_status_counts={str(k):int(v) for k,v in detail.detail_status.value_counts().items()},
        detail_sampling="Every day and following boundary of revised two-sided constant periods of 12+ calendar days, plus selected boundary and ask-change examples.",
        limitations=["Monthly tables describe closing prices and explicitly carry absent source observations.",
                     "The unchanged badge concerns the ask. It can accompany a bid change. Month-opening rows lack prior-day comparison.",
                     "Daily detail without an SJC row leaves that date's monthly SJC pair unconfirmed. A dated daily detail does not prove transactable size, time or point-in-time availability.",
                     "The PNJ-vendor legacy panel is a calendar-filled contextual comparison, never a source of replacement quotes."],
        frozen_daily_sha256=sha(ORIGINAL.read_bytes()), legacy_pnj_sha256=sha(legacy_path.read_bytes()),
        parser_sha256=sha(Path(__file__).read_bytes()),
        market_calendar_sha256=sha(CALENDAR.read_bytes()),
        normalized_artifacts={p.name:sha(p.read_bytes()) for p in sorted(OUT.iterdir())
                              if p.is_file() and p.name != "manifest.json"})
    write_json(OUT / "manifest.json", summary)


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--fetch", action="store_true", help="Acquire missing source pages. Otherwise replay frozen downloads offline.")
    args = cli.parse_args()
    if args.fetch:
        capture_pages([(f"{m.year}_{m.month}.html", f"https://giavang.tv/lich-su/{m.year}/{m.month}")
                       for m in MONTHS], "raw", "receipts.json")
    panel, runs = reconstruct()
    if args.fetch:
        capture_pages(detail_jobs(runs), "daily_raw", "daily_receipts.json")
    assess_details(panel, runs)
    print(panel.revision_status.value_counts())
    print(runs.groupby("vintage").head(3).to_string(index=False))


if __name__ == "__main__":
    main()
