from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import requests

PNJ_API_BASE_URL = "https://edge-cf-api.pnj.io"

ROOT_DIR = Path(__file__).resolve().parents[1]
GOLD_DIR = ROOT_DIR / "datasets" / "gold"
TRAIN_CSV_PATH = GOLD_DIR / "gold_train.csv"
TEST_CSV_PATH = GOLD_DIR / "gold_test.csv"

TRAIN_START_STR = "01/01/2020"
SPLIT_DATE_STR = "01/10/2023"
TEST_END_STR = datetime.now().strftime("%d/%m/%Y")

COLUMNS = ["date", "pnj_buy", "pnj_sell", "sjc_buy", "sjc_sell"]


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
    train_start = datetime.strptime(TRAIN_START_STR, "%d/%m/%Y").date()
    split_date = datetime.strptime(SPLIT_DATE_STR, "%d/%m/%Y").date()
    test_end = datetime.strptime(TEST_END_STR, "%d/%m/%Y").date()

    seed_start = train_start - timedelta(days=1)
    df_raw = crawl_gold_range(seed_start, test_end)
    df_filled = fill_missing_with_previous_day(df_raw, seed_start, test_end)

    df_filled["date"] = pd.to_datetime(df_filled["date"]).dt.date

    train_df = df_filled[
        (df_filled["date"] >= train_start) & (df_filled["date"] <= split_date)
    ].copy()
    test_df = df_filled[
        (df_filled["date"] >= split_date) & (df_filled["date"] <= test_end)
    ].copy()

    train_df["date"] = pd.to_datetime(train_df["date"]).dt.strftime("%Y-%m-%d")
    test_df["date"] = pd.to_datetime(test_df["date"]).dt.strftime("%Y-%m-%d")

    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    train_df[COLUMNS].to_csv(TRAIN_CSV_PATH, index=False)
    test_df[COLUMNS].to_csv(TEST_CSV_PATH, index=False)

    print(f"Saved train data to: {TRAIN_CSV_PATH} ({len(train_df)} rows)")
    print(f"Saved test data to: {TEST_CSV_PATH} ({len(test_df)} rows)")


def main():
    build_and_save_train_test()


if __name__ == "__main__":
    main()
