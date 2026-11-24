"""Compose the evidence-prioritized alternate SJC feed and audit TradeSao separately."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import time
import os
import re
import shutil
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup
import pandas as pd
import requests

HERE = Path(__file__).resolve().parent
STORE = HERE / "alternate"
MONTHS = pd.period_range("2019-12","2026-04",freq="M")
SPEC = "giá vàng miếng SJC 1L, 10L, 1KG tại TP.HCM"


def parse(content, month):
    doc = BeautifulSoup(content, "html.parser")
    text = doc.get_text(" ",strip=True)
    if SPEC not in text or "Giá đóng cửa từng ngày" not in text:
        raise ValueError(f"Missing product or closing price evidence {month}")
    table = next(t for t in doc.select("table") if [n.get_text(strip=True) for n in t.select("th")][:3]==["Ngày","Mua vào","Bán ra"])
    records = []
    for row in table.select("tr"):
        cells = row.select("td")
        if not cells:
            continue
        anchor = cells[0].select_one("a[href]")
        date = parse_qs(urlparse(anchor["href"]).query)["ngay"][0]
        if not date.startswith(str(month)):
            raise ValueError(f"Date outside {month}")
        values = [float(c.get_text(strip=True).replace(",", "."))*1000 for c in cells[1:3]]
        if not 0 < values[0] <= values[1]:
            raise ValueError(f"Crossed quote {date}")
        pill = cells[3].select_one(".tsgh-pill")
        if pill is None:
            raise ValueError(f"Missing quote change marker {date}")
        records.append((date,*values,"is-flat" in pill.get("class",[]),f"{month}.html.gz"))
    if len({r[0] for r in records}) != len(records):
        raise ValueError(f"Duplicate TradeSao date in {month}")
    return records


def acquire(month):
    name = str(month)
    url = f"https://tradesao.com/sjc-gold-price/?nam={month.year}&thang={month.month}"
    raw, receipt = STORE / f"{name}.html.gz", STORE / f"{name}.json"
    if receipt.exists():
        content = gzip.decompress(raw.read_bytes())
        if hashlib.sha256(content).hexdigest() != json.loads(receipt.read_text())["sha256"]:
            raise ValueError(f"Snapshot integrity {month}")
    else:
        for attempt in range(3):
            try:
                response = requests.get(url,timeout=30)
                response.raise_for_status()
                break
            except requests.RequestException:
                if attempt == 2:
                    raise
                time.sleep(1+attempt)
        content = response.content
        raw.write_bytes(gzip.compress(content,mtime=0))
        receipt.write_text(json.dumps(dict(url=response.url,captured=datetime.now(timezone.utc).isoformat(),
                                           sha256=hashlib.sha256(content).hexdigest(),bytes=len(content)),indent=2))
    return parse(content,month)


def tradesao():
    STORE.mkdir(exist_ok=True)
    with ThreadPoolExecutor(max_workers=3) as pool:
        records = [row for batch in pool.map(acquire, MONTHS) for row in batch]
    columns = ["date", "tradesao_bid", "tradesao_ask", "tradesao_flat_flag", "tradesao_file"]
    data = pd.DataFrame(records, columns=columns)
    gia = pd.read_csv(HERE / "snapshot/archive.csv")
    values = gia.merge(data, how="left", on="date", validate="one_to_one")
    values["status"] = "pair_differs"
    values.loc[values.archive_bid.eq(values.tradesao_bid) & values.archive_ask.eq(values.tradesao_ask),
               "status"] = "pair_matches_giavang"
    values.loc[values.tradesao_file.isna(), "status"] = "missing_tradesao_date"
    values.to_csv(STORE / "tradesao_comparison.csv", index=False)
    print(values.status.value_counts())


def read_igold():
    raw = HERE / "verification/raw/igold.csv"
    meta = json.loads(raw.with_suffix(".json").read_text())
    if hashlib.sha256(raw.read_bytes()).hexdigest() != meta["sha256_response"]:
        raise ValueError("iGold CSV receipt mismatch")
    data = pd.read_csv(raw)
    identity = {"Thương hiệu": "SJC", "Sản phẩm": "Miếng 1 lượng · cả loại 10 lượng, 1 kg",
                "Khu vực": "Hồ Chí Minh", "Đơn vị (VND)": "LUONG"}
    if not all(data[column].eq(expected).all() for column, expected in identity.items()):
        raise ValueError("Unexpected iGold product, branch or units")
    data = data.rename(columns={"Ngày (giờ Việt Nam)": "date", "Giá mua chốt ngày": "bid", "Giá bán chốt ngày": "ask"})
    dates = pd.date_range("2024-12-31", "2026-04-30").strftime("%Y-%m-%d").tolist()
    if data.date.tolist() != dates:
        raise ValueError("Incomplete iGold close series")
    for side, label in (("bid", "mua"), ("ask", "bán")):
        if not data[side].between(data[f"Giá {label} thấp nhất ngày"], data[f"Giá {label} cao nhất ngày"]).all():
            raise ValueError(f"iGold {side} outside the published daily range")
        data[side] = data[side] / 1000
    data["source_url"] = meta["url"]
    return data.set_index("date")


def compose(anchor, overrides, igold, conflicting_dates=()):
    """Select the dated observation or carry its price, never its eligibility for execution."""
    rows = []
    last_gia = None
    disputed = False
    for gia in anchor.itertuples():
        date = gia.date
        gia_pair = (gia.archive_bid, gia.archive_ask)
        base = dict(date=date, gia_bid=gia.archive_bid, gia_ask=gia.archive_ask, gia_provider_flag=gia.provider_carry_flag,
                    anchor_file=gia.source_file, reference_date=date, reference_age_days=0, evidence_file_2="",
                    corroborating_url="", webgia_time_ict="", news_published_ict="", news_quote_time_ict="",
                    evidence="published rounded daily pair", source_url=gia.source_url)
        if date in igold.index:
            value = igold.loc[date]
            bid, ask = value.bid, value.ask
            base.update(source="iGold", source_file="igold.csv", source_url=value.source_url,
                        evidence="published same-product daily closing pair")
            disputed = False
        elif date in overrides.index:
            value = overrides.loc[date]
            bid, ask = value.bid, value.ask
            article = re.search(r"-(\d+)\.html$", value.news_url)
            if article is None:
                raise ValueError(f"Unknown supporting article {value.news_url}")
            base.update(source="Webgia+VietnamNet", source_file=f"wg_{date}.html.gz",
                        evidence_file_2=f"vn_{article[1]}.html.gz", evidence=value.evidence,
                        source_url=value.webgia_url, corroborating_url=value.news_url,
                        webgia_time_ict=value.webgia_time_ict, news_published_ict=value.news_published_ict,
                        news_quote_time_ict=value.news_quote_time_ict)
            disputed = (bid, ask) != gia_pair
        elif date in conflicting_dates or (disputed and gia_pair == last_gia):
            prev = rows[-1]
            bid, ask = prev["archive_bid"], prev["archive_ask"]
            for col in ("reference_date", "source_file", "evidence_file_2", "source_url", "corroborating_url",
                        "webgia_time_ict", "news_published_ict", "news_quote_time_ict"):
                base[col] = prev[col]
            reason = ("conflicting dated published quotes" if date in conflicting_dates
                      else "unresolved unchanged base after dated contradiction")
            base.update(source="last corroborated mark", evidence=reason,
                        reference_age_days=(pd.Timestamp(date) - pd.Timestamp(base["reference_date"])).days)
            disputed = True
        else:
            bid, ask = gia_pair
            disputed = False
            base.update(source="GiaVang.TV", source_file=gia.source_file)
        mark_only = base["reference_date"] != date
        if base["source"] == "GiaVang.TV":
            flag = gia.provider_carry_flag
        else:
            flag = mark_only or (bool(rows) and ask == rows[-1]["archive_ask"])
        if not 0 < bid <= ask or not pd.notna(ask) or ask == float("inf"):
            raise ValueError(f"Invalid composite quote {date}")
        base.update(archive_bid=bid, archive_ask=ask, provider_carry_flag=flag,
                    primary_fill_allowed=not flag, permissive_fill_allowed=not mark_only)
        rows.append(base)
        last_gia = gia_pair
    return pd.DataFrame(rows)


def build():
    anchor = pd.read_csv(HERE / "snapshot/day_comparison.csv")
    overrides = pd.read_csv(HERE / "verification/overrides.csv", keep_default_na=False).set_index("date", verify_integrity=True)
    igold = read_igold()
    days = pd.date_range("2019-12-01", "2026-04-30").strftime("%Y-%m-%d").tolist()
    if (anchor.date.tolist() != days or not overrides.index.isin(anchor.date).all()
            or overrides.index.intersection(igold.index).size):
        raise ValueError("Composite source dates overlap or do not cover the locked calendar")
    for date, row in overrides.iterrows():
        if not pd.Timestamp(row.webgia_time_ict).date().isoformat() == date:
            raise ValueError(f"Webgia observation outside its assigned day: {date}")
        article = re.search(r"-(\d+)\.html$", row.news_url)
        for name, expected in ((f"wg_{date}", row.webgia_sha256),
                               (f"vn_{article[1]}", row.news_sha256)):
            receipt = json.loads((HERE / "verification/raw" / (name + ".json")).read_text())
            if receipt["sha256_response"] != expected:
                raise ValueError(f"Verification table hash differs from its receipt for {name}")
    conflicts = pd.read_csv(HERE / "verification/manual_conflicts.csv").set_index("date", verify_integrity=True)
    if (not conflicts.index.isin(anchor.date.iloc[1:]).all() or conflicts.index.isin(overrides.index).any()
            or conflicts.index.isin(igold.index).any()):
        raise ValueError("Conflicting dates cannot be accepted overrides")
    data = compose(anchor, overrides, igold, conflicts.index)
    dest = STORE / "raw"
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(HERE / "verification/manual_conflicts.csv", dest / "manual_conflicts.csv")
    refs = {}
    supporting_recaps = {Path(f).name for f in conflicts.recap_raw_file}
    for file in sorted((set(data.source_file) | set(data.evidence_file_2) | supporting_recaps) - {""}):
        source = HERE / ("snapshot/raw" if file.endswith(".html") else "verification/raw") / file
        if file.endswith(".gz"):
            payload = gzip.decompress(source.read_bytes())
            receipt = json.loads(source.with_suffix("").with_suffix(".json").read_text())
            if hashlib.sha256(payload).hexdigest() != receipt["sha256_response"]:
                raise ValueError(f"Corroborating page hash changed: {file}")
        shutil.copyfile(source, dest / file)
        refs[file] = hashlib.sha256(source.read_bytes()).hexdigest()
    data["source_file_sha256"] = data.source_file.map(refs)
    gia_rows = data.source.eq("GiaVang.TV")
    if not data.loc[gia_rows, "source_file_sha256"].eq(anchor.loc[gia_rows, "revised_source_sha256"]).all():
        raise ValueError("GiaVang anchor response differs from the verified monthly source")
    data["corroborating_file_sha256"] = data.evidence_file_2.map(refs)
    data.to_csv(STORE / "provenance.csv", index=False)
    data[["date", "archive_bid", "archive_ask", "provider_carry_flag", "source_file"]].to_csv(
        STORE / "archive.csv", index=False)
    print(data.groupby("source").size())


def alternate_sensitivity(out):
    """Accept dated flat pairs, while a synthetic mark can never execute a new order."""
    from phase2_gold_k5.portfolio import portfolios
    from phase2_gold_k5.score import score
    alt = out / "dated_quotes"
    alt.mkdir()
    os.link(out / "forecasts.csv", alt / "forecasts.csv")
    quotes = pd.read_csv(out / "gold_quotes.csv").set_index("date", verify_integrity=True)
    provenance = pd.read_csv(STORE / "provenance.csv").set_index("date", verify_integrity=True).loc[quotes.index]
    for col in ("archive_bid", "archive_ask", "source_file", "provider_carry_flag"):
        if not quotes[col].eq(provenance[col]).all():
            raise ValueError(f"Alternate run quotes differ from source evidence in {col}")
    permit = provenance.permissive_fill_allowed
    if permit.isna().any() or not permit.eq(provenance.reference_date.eq(provenance.index.to_series())).all():
        raise ValueError("Invalid synthetic-mark eligibility")
    quotes["bid"], quotes["ask"] = quotes.archive_bid.where(permit), quotes.archive_ask.where(permit)
    quotes.rename(columns={"execution_status": "primary_execution_status"}, inplace=True)
    quotes["execution_status"] = permit.map({True: "dated_two_sided", False: "synthetic_mark_only"})
    quotes.to_csv(alt / "gold_quotes.csv")
    portfolios(alt)
    score(alt)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["build", "tradesao"])
    if parser.parse_args().action == "build":
        build()
    else:
        tradesao()
