"""Read the SJC bid and ask from the exact source vintage pinned by a proposal."""
import csv
from datetime import date, datetime, timezone
from decimal import Decimal
from hashlib import sha256
from html.parser import HTMLParser
import io
from pathlib import Path
import re

from .full import TZ

WARMUP_HASH = "42ee952f6a6e0486464c5e39e84cbb66f2a857d723cc15b39a46870bb9c58275"
WARMUP_END = date(2026, 4, 30)
WARMUP_VERIFIED_AT = "2026-11-24T09:04:19.416910+00:00"
MAX_BYTES = 8 * 1024 * 1024


class _MonthlyTable(HTMLParser):
    def __init__(self):
        super().__init__()
        self.inside = False
        self.count = 0
        self.rows = []
        self.row = self.cell = None

    def handle_starttag(self, tag, attrs):
        if tag == "table" and "gv-table" in dict(attrs).get("class", "").split():
            self.inside = True
            self.count += 1
        if self.inside:
            if tag == "tr":
                self.row = []
            elif tag in ("th", "td") and self.row is not None:
                self.cell = []

    def handle_endtag(self, tag):
        if not self.inside:
            return
        if tag in ("td", "th") and self.cell is not None:
            self.row.append(" ".join(self.cell))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None
        elif tag == "table":
            self.inside = False

    def handle_data(self, data):
        if self.cell is not None and data.strip():
            self.cell.append(data.strip())


def parse_month(raw, year, month):
    if len(raw) > MAX_BYTES:
        raise ValueError("Oversized SJC archive")
    html = raw.decode("utf-8")
    if "Vàng SJC 1L, 10L, 1KG · Hồ Chí Minh" not in html or "triệu đồng / lượng" not in html:
        raise ValueError("Unexpected SJC product or unit")
    table = _MonthlyTable()
    table.feed(html)
    if table.count != 1 or table.rows[:1] != [["Ngày", "Mua lại", "Bạn trả"]]:
        raise ValueError("Unexpected SJC quote table")
    result = {}
    for stamp, buy, sell in table.rows[1:]:
        day = datetime.strptime(stamp.split()[0], "%d/%m/%Y").date()
        if (day.year, day.month) != (year, month) or str(day) in result:
            raise ValueError("Inconsistent SJC quote date")
        sell_parts = sell.split(maxsplit=1)
        if len(sell_parts) != 2:
            raise ValueError("Missing SJC quote change status")
        amount, label = sell_parts
        if label not in {"không đổi", "ngày đầu kỳ"} and not label.startswith(("▲", "▼")):
            raise ValueError("Unknown SJC quote change status")
        amounts = [buy.strip(), amount]
        if not all(re.fullmatch(r"\d+(?:,\d{1,6})?", amount) for amount in amounts):
            raise ValueError("Unexpected SJC quote precision")
        bid, ask = [int(Decimal(v.replace(",", ".")) * 1_000_000) for v in amounts]
        if not 0 < bid <= ask:
            raise ValueError("Invalid SJC bid/ask")
        result[str(day)] = dict(bid=bid, ask=ask, provider_carry_flag=label == "không đổi")
    if not result:
        raise ValueError("Empty SJC quote table")
    return result


def _aware(stamp):
    value = datetime.fromisoformat(stamp) if isinstance(stamp, str) else stamp
    if value.utcoffset() is None:
        raise ValueError("Missing source timezone")
    return value


def load_capture(panel, decision_session, decision_at, directory, warmup_path):
    day = date.fromisoformat(str(decision_session))
    cutoff = _aware(decision_at)
    if cutoff < max(_aware(WARMUP_VERIFIED_AT), _aware(panel.snapshot["created_at"])):
        raise ValueError("SJC vintage unavailable at proposal cutoff")
    root = Path(directory).resolve()
    raw = Path(warmup_path).read_bytes()
    if sha256(raw).hexdigest() != WARMUP_HASH:
        raise ValueError("Revised SJC warm-up hash differs")
    quotes = {}
    for record in csv.DictReader(io.StringIO(raw.decode())):
        stamp = record["date"]
        if stamp <= str(day):
            quotes[stamp] = dict(bid=int(Decimal(record["archive_bid"]) * 1000),
                                 ask=int(Decimal(record["archive_ask"]) * 1000),
                                 provider_carry_flag=record["provider_carry_flag"] == "True",
                                 source_sha256=WARMUP_HASH, received_at=WARMUP_VERIFIED_AT)
    coverage = panel.snapshot["asset_coverage"]["GOLD"]
    for ref in coverage["raw_artifact_refs"]:
        if ref.get("role") == "frozen-canonical-through-2026-04-30":
            continue
        url = ref["url"]
        match = re.fullmatch(r"https://giavang\.tv/lich-su/(\d{4})/([1-9]|1[012])", url)
        if not match or ref.get("asset_id") != "GOLD" or ref.get("method") != "GET" or ref.get("status") != 200:
            raise ValueError("Unexpected pinned SJC source")
        year, month = map(int, match.groups())
        if date(year, month, 1) > day:
            continue
        received = _aware(ref["received_at"])
        if not _aware(ref["requested_at"]) <= received <= min(cutoff, _aware(panel.snapshot["created_at"])):
            raise ValueError("SJC receipt outside snapshot cutoff")
        pin = ref["raw"]
        digest = pin["sha256"]
        if (not re.fullmatch(r"[a-f0-9]{64}", digest) or pin["file"] != f"{digest}.json"
                or pin["path"] != f"refresh/full-phase1/{digest}.json"):
            raise ValueError("Invalid SJC file reference")
        path = root / pin["path"]
        if path.resolve() != path or not 0 < pin["bytes"] == path.stat().st_size <= MAX_BYTES:
            raise ValueError("Invalid pinned SJC file")
        blob = path.read_bytes()
        if sha256(blob).hexdigest() != digest:
            raise ValueError("Pinned SJC archive content changed")
        for stamp, pair in parse_month(blob, year, month).items():
            if stamp <= str(WARMUP_END) or stamp > str(min(day, received.astimezone(TZ).date())):
                continue
            if stamp in quotes:
                raise ValueError("Conflicting SJC source months")
            quotes[stamp] = dict(pair, source_sha256=digest, source_url=url, received_at=received.isoformat())
    i, j = panel.dates.index(day), panel.ids.index("GOLD")
    observed = date.fromordinal(int(panel.observation_days[i, j]))
    quote = quotes.get(str(observed))
    if (not panel.valid[i, j] or not quote or observed >= day
            or (day - observed).days > 7 or coverage["status"] != "AVAILABLE"
            or panel.prices[i, j] != quote["ask"]
            or max(panel.known_seconds[i, j], panel.policy_seconds[i, j]) > cutoff.timestamp()):
        raise ValueError("Research quote and eligible proposal GOLD observation disagree")
    return dict(gold_quotes=quotes, cutoff_at=cutoff.astimezone(timezone.utc).isoformat(),
                warmup_sha256=WARMUP_HASH, observed_quote=dict(quote, date=str(observed), unit="VND/tael"))
