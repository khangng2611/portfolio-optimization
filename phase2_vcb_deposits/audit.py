"""Rebuild the deposit source audit from frozen evidence, without network access."""
import csv
import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from itertools import groupby
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
EVIDENCE = ROOT / "evidence"
START, END, OOS = "2020-01-01", "2026-04-30", "2023-10-02"
TENORS = {"demand": "33284", "1m": "33285", "12m": "33290"}
CALENDAR = ROOT.parent / "extensions_C_v1/inputs/prices_valuation.csv"


def write_csv(name, rows):
    with (ROOT / name).open("w", newline="", encoding="utf-8") as out:
        writer = csv.DictWriter(out, fieldnames=rows[0], lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def build():
    manifest = json.loads((EVIDENCE / "manifest.json").read_text())
    for source in manifest.values():
        assert hashlib.sha256((EVIDENCE / source["file"]).read_bytes()).hexdigest() == source["sha256"], source["file"]
    assert hashlib.sha256(CALENDAR.read_bytes()).hexdigest() == "c6789fb99526608cc0e5426de2b8ff59bee14148d908828bd72ed0d3e5814c84"
    with CALENDAR.open() as f:
        sessions = [r["date"] for r in csv.DictReader(f) if START <= r["date"] <= END]
    assert sessions == sorted(set(sessions))
    rates = []

    def record(source, day, tenor, value, kind, locator, known="", publication=""):
        assert tenor in TENORS and date.fromisoformat(day) and source in manifest
        value = Decimal(str(value))
        assert value.is_finite() and 0 <= value < 100
        assert not known or datetime.fromisoformat(known).date().isoformat() >= day
        rates.append(dict(bank="VCB", client="personal", currency="VND", product="savings_counter",
                          tenor=tenor, observed_date=day, rate_pct_pa=f"{value:.2f}", effective_from="",
                          known_by_local=known, publication_local=publication, kind=kind,
                          source_id=source, locator=locator))

    with (ROOT / "observations.csv").open() as f:
        for row in csv.DictReader(f):
            for tenor in TENORS:
                if row[tenor]:
                    record(row["source_id"], row["observed_date"], tenor, row[tenor], row["kind"],
                           row["locator"], row["known_by_local"], row["publication_local"])

    table = BeautifulSoup((EVIDENCE / "expanded.html").read_bytes(), "html.parser")
    headers = table.select("thead th")
    # The final column contains the collapse button. It has no observation date.
    assert headers[-1].get_text(strip=True) == "Thu gọn"
    dates = [datetime.strptime(h.get_text(strip=True), "%d-%m-%Y").date().isoformat() for h in headers[2:-1]]
    assert len(set(dates)) == len(dates)
    for tenor, row_id in TENORS.items():
        cells = table.select_one(f"tr[data-row-id='{row_id}']").find_all(["td", "th"], recursive=False)
        assert len(cells) == len(headers)
        for day, cell in zip(dates, cells[2:-1]):
            raw = cell.get_text(strip=True)
            if raw and "2019-12-01" <= day <= END:
                record("expanded", day, tenor, raw.replace(",", "."), "reconstruction", f"row {row_id}")

    live = BeautifulSoup((EVIDENCE / "vcb.html").read_bytes(), "html.parser")
    payload = json.loads(live.select_one("#currentDataInterestRate")["value"])
    assert payload["AccountType"] == "Personal"
    keys = {"Demand": "demand", "1-months": "1m", "12-months": "12m"}
    for r in payload["Data"]:
        if r["currencyCode"] == "VND" and r["tenorType"] == "Savings" and r["tenor"] in keys:
            record("vcb", payload["UpdatedDate"][:10], keys[r["tenor"]], Decimal(str(r["rates"])) * 100,
                   "live_control", "currentDataInterestRate", payload["UpdatedDate"])
    assert len([r for r in rates if r["kind"] == "live_control"]) == 3
    assert not any(r["kind"] == "reconstruction" and r["observed_date"] == "2020-10-01" and
                   r["tenor"] == "12m" for r in rates)
    write_csv("rates.csv", sorted(rates, key=lambda r: (r["observed_date"], r["tenor"], r["source_id"])))

    coverage, gaps = [], []
    for tenor in TENORS:
        subset = [r for r in rates if r["tenor"] == tenor]
        captures = {}
        for r in subset:
            day = r["observed_date"]
            if r["kind"] == "bank_capture" and r["known_by_local"][:10] == day:
                captures.setdefault(day, set()).add(r["rate_pct_pa"])
        verified = {day for day, values in captures.items() if len(values) == 1}
        for sample, start in [("full", START), ("oos", OOS)]:
            trading_days = [day for day in sessions if day >= start]
            hits = sorted(verified.intersection(trading_days))
            blocks = []
            for covered, group in groupby(trading_days, key=lambda day: day in hits):
                block = list(group)
                if not covered:
                    blocks.append(len(block))
                    gaps.append(dict(tenor=tenor, sample=sample, first=block[0], last=block[-1], sessions=len(block)))
            assert len(hits) + sum(blocks) == len(trading_days)
            reconstructed = {r["observed_date"] for r in subset if r["kind"] == "reconstruction"
                             and start <= r["observed_date"] <= END}
            coverage.append(dict(tenor=tenor, sample=sample, sessions=len(trading_days),
                                 bank_capture_sessions=len(hits), missing_sessions=sum(blocks),
                                 longest_gap_sessions=max(blocks, default=0), first_capture=next(iter(hits), ""),
                                 last_capture=hits[-1] if hits else "", reconstruction_dates=len(reconstructed)))
    write_csv("coverage.csv", coverage)
    write_csv("gaps.csv", gaps)


if __name__ == "__main__":
    build()
