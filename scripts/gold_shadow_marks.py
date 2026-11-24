"""Point-in-time economic marks for the GOLD–K5 paper observer."""

from bisect import bisect_left, bisect_right
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path

from market_service.hybrid_forward_capture import DECISION_TIME, HISTORY_START, VIETNAM
from market_service.phase1_sources import normalize_fmarket, normalize_gold_archive, verify_vff_identity
from scripts.hybrid_forward_panel import _Batch


class CaptureUnavailable(ValueError):
    pass


class Captures:
    def __init__(self, root, as_of):
        self.root = Path(root)
        if not self.root.is_dir():
            raise ValueError(f"Capture archive not found: {self.root}")
        self.as_of = as_of
        self.paths = {}
        self.provenance = {}
        for phase in ("evaluation", "settlement", "gold_shadow"):
            for summary in sorted((self.root / phase).glob("*/*/summary.json")):
                day = summary.parent.parent.name
                if day <= as_of.astimezone(VIETNAM).date().isoformat():
                    self.paths.setdefault(day, []).append(summary.parent)
        self.sessions = []
        self.calendar_errors = {}
        for day in sorted(self.paths, reverse=True):
            try:
                self.sessions = self._read(day, "calendar", lambda batch: batch.calendar())
                break
            except CaptureUnavailable as exc:
                self.calendar_errors[day] = str(exc)

    @lru_cache(maxsize=24)
    def _batch(self, path, day):
        cutoff = min(self.as_of, datetime.combine(date.fromisoformat(day), DECISION_TIME, VIETNAM))
        batch = _Batch(self.root, path, cutoff, False, gold_shadow=True)
        if (batch.finished > cutoff or batch.started.astimezone(VIETNAM).date().isoformat() != day
                or batch.started.astimezone(VIETNAM).hour < 15):
            raise ValueError("Capture not completed by cutoff")
        return batch

    def _read(self, day, source, get):
        errors = []
        for path in self.paths.get(day, []):
            try:
                batch = self._batch(path, day)
                result = get(batch)
                provenance = self.provenance.setdefault(str(path.relative_to(self.root)), batch.provenance | {"receipts": {}})
                provenance["receipts"].update(batch.provenance["receipts"])
                return result
            except (ValueError, OSError, ArithmeticError, KeyError, TypeError, IndexError) as exc:
                errors.append(str(exc))
        raise CaptureUnavailable(f"{day} {source}: " + (" | ".join(errors) or "no contemporaneous capture"))

    @lru_cache(maxsize=1024)
    def _check_calendar(self, day):
        expected = self.sessions[bisect_left(self.sessions, "2026-11-24"):bisect_right(self.sessions, day)]
        def check(batch):
            actual = batch.calendar()
            if actual[bisect_left(actual, "2026-11-24"):] != expected or not expected or expected[-1] != day:
                raise ValueError("VNINDEX session vintage mismatch")
        self._read(day, "calendar", check)

    @lru_cache(maxsize=4096)
    def _stock(self, day, asset, basis_day):
        def get(batch):
            rows = dict(batch.stock(asset))
            close = float(rows[date.fromisoformat(day)])
            basis = float(rows[date.fromisoformat(basis_day)]) if basis_day else close
            return close, basis
        return self._read(day, asset, get)

    @lru_cache(maxsize=512)
    def _quote(self, day):
        from quant_service.gold_shadow_quotes import parse_month

        stamp = date.fromisoformat(day)
        name = f"GOLD-{stamp:%Y-%m}"

        def get(batch):
            def parse(raw):
                rows, _ = normalize_gold_archive(raw, stamp.year, stamp.month)
                quote = parse_month(raw, stamp.year, stamp.month)[day]
                if quote["ask"] != dict(rows)[stamp]:
                    raise ValueError("Two-sided quote and captured ask disagree")
                return [(d, p) for d, p in rows if d <= stamp], quote
            return batch.source(name, f"https://giavang.tv/lich-su/{stamp.year}/{stamp.month}", "GET", parse)[1]
        return self._read(day, name, get)

    @lru_cache(maxsize=512)
    def _nav(self, day, settlement):
        mark_day = date.fromisoformat(day)

        def get(batch):
            batch.source("VFF-identity", "https://api.fmarket.vn/res/products/filter", "POST",
                         lambda raw: (verify_vff_identity(raw), {}),
                         payload={"searchField": "VFF", "types": ["NEW_FUND", "TRADING_FUND"], "pageSize": 100})
            rows, _ = batch.source("VFF", "https://api.fmarket.vn/res/product/get-nav-history", "POST",
                                   lambda raw: normalize_fmarket(raw, HISTORY_START, batch.day),
                                   payload={"isAllData": 1, "productId": 21, "fromDate": None,
                                            "toDate": batch.day.strftime("%Y%m%d")})
            eligible = [(d, p) for d, p in rows if 0 <= (mark_day - d).days <= 7]
            if not eligible:
                raise ValueError(f"No genuine VFF NAV within seven days of {day}")
            observed, nav = eligible[-1]
            return float(nav), observed.isoformat()
        return self._read(settlement, "VFF", get)

    def mark(self, i, assets, previous=None):
        day = self.sessions[i]
        # This study fixes the VFF valuation vintage five exchange sessions after each close.
        self._check_calendar(day)
        quote = self._quote(day)
        prices, share_factors = {}, {}
        for asset in sorted(assets):
            if asset in ("VFF", "GOLD"):
                continue
            prior = previous is not None and asset in previous["prices"]
            close, revised_basis = self._stock(day, asset, previous["day"] if prior else None)
            prices[asset] = close
            # KBS adjusts its history. Convert prior share-equivalents into this vintage's units.
            share_factors[asset] = previous["prices"][asset] / revised_basis if prior else 1.
        prices["GOLD"] = (quote["bid"] + quote["ask"]) / 2
        observed = settlement = None
        if "VFF" in assets:
            settlement = self.sessions[i + 5]
            self._check_calendar(settlement)
            prices["VFF"], observed = self._nav(day, settlement)
        return dict(prices=prices, share_factors=share_factors, **quote, day=day, nav_date=observed, nav_vintage=settlement)
