# ===================================================================
# CRAWL PNJ/SJC GOLD PRICES (buy/sell) FROM THE PNJ EDGE API
# - Full mode (default): rebuild gold_full/train/test.csv from
#   TRAIN_START_DATE to today, split at SPLIT_DATE (from config.py).
# - Update mode (--update): crawl only a given time frame and merge it
#   into the existing gold CSVs. Decoupled from the train/test split:
#   each file only absorbs the window dates that belong to its coverage.
# ===================================================================

import argparse
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import requests

# Import fixed date constants from project config
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))
from config import TRAIN_START_DATE, SPLIT_DATE

PNJ_API_BASE_URL = "https://edge-cf-api.pnj.io"

ROOT_DIR = PROJECT_ROOT
GOLD_DIR = ROOT_DIR / "datasets" / "gold"
FULL_CSV_PATH = GOLD_DIR / "gold_full.csv"
TRAIN_CSV_PATH = GOLD_DIR / "gold_train.csv"
TEST_CSV_PATH = GOLD_DIR / "gold_test.csv"

# Crawl uses "today" as end date (not the fixed backtest date)
TEST_END_DATE = datetime.now().strftime("%Y-%m-%d")

COLUMNS = ["date", "pnj_buy", "pnj_sell", "sjc_buy", "sjc_sell"]

# Update-mode targets: (path, extend_forward). train is a closed segment
# (it ends at the split), so it only refreshes dates already inside it;
# full and test are open-ended towards the present and may be extended.
UPDATE_TARGETS = (
    (FULL_CSV_PATH, True),
    (TEST_CSV_PATH, True),
    (TRAIN_CSV_PATH, False),
)


## Crawler
def parse_price(text):
    try:
        # Remove thousand separators and cast to int
        clean = text.replace(".", "").strip()
        value = int(clean)
        return value
    except:
        return None


def _extract_buy_sell(gold_type):
    gia_mua = parse_price(gold_type.get("gia_mua", ""))
    gia_ban = parse_price(gold_type.get("gia_ban", ""))

    if gia_mua is not None and gia_ban is not None:
        return gia_mua, gia_ban

    data = gold_type.get("data") or []
    if data:
        first = data[0] or {}
        if gia_mua is None:
            gia_mua = parse_price(first.get("gia_mua", ""))
        if gia_ban is None:
            gia_ban = parse_price(first.get("gia_ban", ""))

    return gia_mua, gia_ban


def get_gold_data_for_date(date_obj):
    date_param = date_obj.strftime("%Y%m%d")
    url = (
        f"{PNJ_API_BASE_URL}/ecom-frontend/v1/get-gold-price-history?date={date_param}"
    )

    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        payload = resp.json()
    except requests.RequestException:
        return None
    except ValueError:
        return None

    locations = payload.get("locations") if isinstance(payload, dict) else None
    if not locations:
        return {"pnj_buy": None, "pnj_sell": None, "sjc_buy": None, "sjc_sell": None}

    pnj_buy = pnj_sell = None
    sjc_buy = sjc_sell = None

    for location in locations:
        if location.get("name") != "TPHCM":
            continue
        for gold_type in location.get("gold_type", []):
            name = (gold_type.get("name") or "").strip().upper()
            gia_mua, gia_ban = _extract_buy_sell(gold_type)

            if name == "PNJ" and (pnj_buy is None or pnj_sell is None):
                pnj_buy = gia_mua if pnj_buy is None else pnj_buy
                pnj_sell = gia_ban if pnj_sell is None else pnj_sell

            if "PNJ" in name and (pnj_buy is None or pnj_sell is None):
                pnj_buy = gia_mua if pnj_buy is None else pnj_buy
                pnj_sell = gia_ban if pnj_sell is None else pnj_sell

            if name == "SJC" and (sjc_buy is None or sjc_sell is None):
                sjc_buy = gia_mua if sjc_buy is None else sjc_buy
                sjc_sell = gia_ban if sjc_sell is None else sjc_sell

        if None not in (pnj_buy, pnj_sell, sjc_buy, sjc_sell):
            break

    return {
        "pnj_buy": pnj_buy,
        "pnj_sell": pnj_sell,
        "sjc_buy": sjc_buy,
        "sjc_sell": sjc_sell,
    }


def crawl_gold_range(start_date, end_date):
    rows = []
    current_date = start_date

    while current_date <= end_date:
        date_str = current_date.strftime("%Y-%m-%d")
        print(f"Crawling {date_str}...")
        data = get_gold_data_for_date(current_date)

        if data is None:
            row = {
                "date": date_str,
                "pnj_buy": None,
                "pnj_sell": None,
                "sjc_buy": None,
                "sjc_sell": None,
            }
        else:
            row = {
                "date": date_str,
                "pnj_buy": data["pnj_buy"],
                "pnj_sell": data["pnj_sell"],
                "sjc_buy": data["sjc_buy"],
                "sjc_sell": data["sjc_sell"],
            }

        rows.append(row)
        current_date += timedelta(days=1)

    return pd.DataFrame(rows, columns=COLUMNS)


def fill_missing_with_previous_day(df, start_date, end_date):
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])

    for col in COLUMNS[1:]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    full_index = pd.date_range(start=start_date, end=end_date, freq="D")
    df = (
        df.drop_duplicates(subset=["date"], keep="last")
        .set_index("date")
        .reindex(full_index)
        .sort_index()
        .ffill()
        .reset_index()
        .rename(columns={"index": "date"})
    )

    df["date"] = df["date"].dt.strftime("%Y-%m-%d")
    return df[COLUMNS]


def build_and_save_train_test():
    train_start = date.fromisoformat(TRAIN_START_DATE)
    split_date = date.fromisoformat(SPLIT_DATE)
    test_end = date.fromisoformat(TEST_END_DATE)

    seed_start = train_start - timedelta(days=1)
    df_raw = crawl_gold_range(seed_start, test_end)
    df_filled = fill_missing_with_previous_day(df_raw, seed_start, test_end)

    df_filled["date"] = pd.to_datetime(df_filled["date"]).dt.date

    full_df = df_filled[
        (df_filled["date"] >= train_start) & (df_filled["date"] <= test_end)
    ].copy()
    train_df = full_df[full_df["date"] <= split_date].copy()
    test_df = full_df[full_df["date"] >= split_date].copy()

    for frame in (full_df, train_df, test_df):
        frame["date"] = pd.to_datetime(frame["date"]).dt.strftime("%Y-%m-%d")

    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    full_df[COLUMNS].to_csv(FULL_CSV_PATH, index=False)
    train_df[COLUMNS].to_csv(TRAIN_CSV_PATH, index=False)
    test_df[COLUMNS].to_csv(TEST_CSV_PATH, index=False)

    print(f"Saved full data to: {FULL_CSV_PATH} ({len(full_df)} rows)")
    print(f"Saved train data to: {TRAIN_CSV_PATH} ({len(train_df)} rows)")
    print(f"Saved test data to: {TEST_CSV_PATH} ({len(test_df)} rows)")


## Update mode
def parse_date_arg(text):
    """Parse a CLI date given as YYYY-MM-DD or DD/MM/YYYY."""
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise argparse.ArgumentTypeError(
        f"invalid date {text!r}: expected YYYY-MM-DD or DD/MM/YYYY"
    )


def load_gold_csv(path):
    """Load a gold CSV with normalized date and price columns."""
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])
    for col in COLUMNS[1:]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return (
        df.drop_duplicates(subset=["date"], keep="last")
        .sort_values("date")
        .reset_index(drop=True)
    )


def get_latest_saved_date():
    """Return the most recent date saved across the gold CSVs (or None)."""
    latest = None
    for path, _ in UPDATE_TARGETS:
        if not path.exists():
            continue
        df = load_gold_csv(path)
        if df.empty:
            continue
        file_max = df["date"].max()
        if latest is None or file_max > latest:
            latest = file_max
    return latest


def update_gold_range(start_date, end_date):
    """Crawl [start_date, end_date] and merge it into the existing gold CSVs.

    Decoupled from the train/test split: each output file only absorbs the
    window dates that belong to its own coverage. full/test also accept dates
    after their last saved day (they run up to the present), while train only
    refreshes dates already inside its closed range.
    """
    targets = []
    for path, extend_forward in UPDATE_TARGETS:
        if path.exists():
            targets.append((path, extend_forward, load_gold_csv(path)))

    if not targets:
        print(
            "No existing gold CSVs found. Run a full crawl first: python crawl/gold.py"
        )
        return

    print(f"Crawling gold price updates: {start_date} -> {end_date}")
    new_df = crawl_gold_range(start_date, end_date)
    new_df["date"] = pd.to_datetime(new_df["date"], errors="coerce")
    new_df = new_df.dropna(subset=["date"])
    for col in COLUMNS[1:]:
        new_df[col] = pd.to_numeric(new_df[col], errors="coerce")

    dataset_start = min(df["date"].min() for _, _, df in targets)
    dropped_before = new_df[new_df["date"] < dataset_start]
    if not dropped_before.empty:
        print(
            f"Note: {len(dropped_before)} window day(s) before "
            f"{dataset_start:%Y-%m-%d} are outside the dataset range and were ignored."
        )

    updated_any = False
    for path, extend_forward, old_df in targets:
        file_min = old_df["date"].min()
        file_max = old_df["date"].max()

        window = new_df[new_df["date"] >= file_min]
        if not extend_forward:
            window = window[window["date"] <= file_max]

        if window.empty:
            print(
                f"Skipped {path.name}: window is outside its coverage "
                f"({file_min:%Y-%m-%d} -> {file_max:%Y-%m-%d})."
            )
            continue

        window_start = window["date"].min()
        if window_start > file_max:
            gap_days = (window_start - file_max).days - 1
            gap_note = f" (leaving a gap of {gap_days} day(s))" if gap_days > 0 else ""
            print(f"Extending {path.name} beyond {file_max:%Y-%m-%d}{gap_note}.")

        combined = pd.concat([old_df, window], ignore_index=True)
        # Per date, keep the last non-null price: freshly crawled values win,
        # but a null crawl (holiday, API outage) never wipes a saved price.
        combined = combined.groupby("date", as_index=False)[COLUMNS[1:]].last()
        combined[COLUMNS[1:]] = combined[COLUMNS[1:]].ffill()
        combined["date"] = combined["date"].dt.strftime("%Y-%m-%d")

        combined[COLUMNS].to_csv(path, index=False)
        updated_any = True
        print(
            f"Updated {path.name}: {len(old_df)} -> {len(combined)} rows "
            f"({combined['date'].iloc[0]} -> {combined['date'].iloc[-1]})"
        )

    if not updated_any:
        print("No gold CSVs were updated for the requested window.")


## CLI
def main():
    parser = argparse.ArgumentParser(
        description=(
            "Crawl PNJ/SJC gold prices. Default: full rebuild of "
            "gold_full/train/test.csv. With --update: crawl only the given "
            "time frame and merge it into the existing CSVs."
        )
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help=(
            "update mode: crawl the given time frame (decoupled from the "
            "train/test split) and merge it into the existing gold CSVs"
        ),
    )
    parser.add_argument(
        "--start",
        type=parse_date_arg,
        default=None,
        help="update window start (YYYY-MM-DD or DD/MM/YYYY); "
        "default: the day after the last saved date",
    )
    parser.add_argument(
        "--end",
        type=parse_date_arg,
        default=None,
        help="update window end (YYYY-MM-DD or DD/MM/YYYY); default: today",
    )
    args = parser.parse_args()

    if not args.update:
        if args.start is not None or args.end is not None:
            parser.error("--start/--end require --update")
        build_and_save_train_test()
        return

    end_date = args.end if args.end is not None else date.today()
    if args.start is not None:
        start_date = args.start
    else:
        latest = get_latest_saved_date()
        if latest is None:
            parser.error(
                "no existing gold CSVs to update; run a full crawl first (without --update)"
            )
        start_date = (latest + timedelta(days=1)).date()
        if start_date > end_date:
            print(
                f"Gold data already up to date (last saved date: {latest:%Y-%m-%d})."
            )
            return

    if start_date > end_date:
        print(f"Nothing to crawl: start {start_date} is after end {end_date}.")
        return

    update_gold_range(start_date, end_date)


if __name__ == "__main__":
    main()
