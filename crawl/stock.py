# ===================================================================
# FETCH OHLCV DATA FOR 30 VN30 SYMBOLS + ETF E1VFVN30
# - Automatically fetch the 30 VN30 symbols from vnstock (dynamic)
# - Save the symbol list to a txt file (vn30_stocks.txt)
# - For each symbol (stock + ETF), fetch full OHLCV data
# - Save each symbol to its own CSV file
# ===================================================================

import sys
import pandas as pd
from vnstock import Quote, Listing
from datetime import datetime
from pathlib import Path
import time

# ====================== SETTINGS ======================
# Import fixed date constants from project config
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))
from config import TRAIN_START_DATE, SPLIT_DATE

# Crawl uses "today" as end date (not the fixed backtest date)
TEST_END_DATE = datetime.now().strftime("%Y-%m-%d")

start_date = TRAIN_START_DATE
end_date = TEST_END_DATE
ROOT_DIR = Path(__file__).resolve().parents[1]
DATASETS_DIR = ROOT_DIR / "datasets"
LIST_FILE = DATASETS_DIR / "vn30_list.txt"
OUTPUT_DIR = DATASETS_DIR / "stocks"

START_INDEX = 20  # Starting index in the list (for batch runs)
BATCH_SIZE = 10  # Number of symbols to process per run


# ====================== STEP 1: FETCH 30 VN30 SYMBOLS ======================
def retrieve_vn30_list():
    print("Fetching 30 VN30 symbols from vnstock...")
    listing = Listing()
    vn30_list = listing.symbols_by_group(group_name="VN30")
    # vn30_symbols = vn30_list['symbol'].tolist()
    print(f"Fetched {len(vn30_list)} VN30 symbols.")

    # Save the symbol list to a txt file
    DATASETS_DIR.mkdir(parents=True, exist_ok=True)
    with open(LIST_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(vn30_list))
    print(f"Saved 30 VN30 symbols to file: {LIST_FILE}")


# ====================== STEP 3: FETCH OHLCV AND SAVE EACH FILE ======================
def split_train_test(df):
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = (
        df.dropna(subset=["date"])
        .drop_duplicates(subset=["date"], keep="last")
        .sort_values("date")
    )

    train_start = pd.Timestamp(TRAIN_START_DATE)
    split_date = pd.Timestamp(SPLIT_DATE)
    test_end = pd.Timestamp(TEST_END_DATE)

    full_df = df[(df["date"] >= train_start) & (df["date"] <= test_end)].copy()
    train_df = full_df[full_df["date"] <= split_date].copy()
    test_df = full_df[full_df["date"] >= split_date].copy()

    for frame in (full_df, train_df, test_df):
        frame["date"] = frame["date"].dt.strftime("%Y-%m-%d")

    return full_df, train_df, test_df


def fetch_and_save(symbol):
    try:
        quote = Quote(symbol=symbol, source="VCI")
        df = quote.history(
            symbol=symbol,
            start=start_date,
            interval="1D",
        )

        # Keep standard columns
        df = df[["time", "open", "high", "low", "close", "volume"]].copy()
        df.rename(columns={"time": "date"}, inplace=True)
        df["symbol"] = symbol
        full_df, train_df, test_df = split_train_test(df)

        if full_df.empty:
            print(
                f"No data in configured range ({TRAIN_START_DATE} -> {TEST_END_DATE}) for {symbol}."
            )
            return False

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        (OUTPUT_DIR / "train").mkdir(parents=True, exist_ok=True)
        (OUTPUT_DIR / "test").mkdir(parents=True, exist_ok=True)
        full_path = OUTPUT_DIR / "full" / f"{symbol}.csv"
        train_path = OUTPUT_DIR / "train" / f"{symbol}_train.csv"
        test_path = OUTPUT_DIR / "test" / f"{symbol}_test.csv"

        full_df.to_csv(full_path, index=False, encoding="utf-8-sig")
        train_df.to_csv(train_path, index=False, encoding="utf-8-sig")
        test_df.to_csv(test_path, index=False, encoding="utf-8-sig")

        print(
            f"Saved {symbol} -> full:{len(full_df)} train:{len(train_df)} test:{len(test_df)}"
        )
        return True

    except Exception as e:
        print(f"Error while fetching {symbol}: {e}")
        return False


def retrieve_ohlcv_for_vn30_symbols():
    # Read symbol list from file
    with open(LIST_FILE, "r", encoding="utf-8") as f:
        symbols = [line.strip() for line in f.readlines() if line.strip()]

    print(f"Total symbols to fetch: {len(symbols)} (30 VN30)")

    # Select <BATCH_SIZE> symbols based on START_INDEX
    symbols_batch = symbols[START_INDEX : START_INDEX + BATCH_SIZE]

    if not symbols_batch:
        print(
            f"No symbols left to process (START_INDEX={START_INDEX} exceeds the list length)."
        )
        return
    print(
        f"Processing symbols from index {START_INDEX} to {START_INDEX + len(symbols_batch) - 1}:"
    )
    print(f"Symbol batch: {symbols_batch}")

    # Fetch OHLCV for each symbol and save separately
    success_count = 0
    for symbol in symbols_batch:
        if fetch_and_save(symbol):
            success_count += 1
        time.sleep(1.2)  # Delay to avoid rate limits

    print("\n" + "=" * 60)
    print(f"DONE! Successfully processed {success_count}/{len(symbols)} symbols.")
    print(f"All files were saved in directory: {OUTPUT_DIR}")
    print(
        "Each file contains full columns: date, open, high, low, close, volume, symbol"
    )
    next_index = START_INDEX + BATCH_SIZE
    if next_index < len(symbols):
        print(f"For the next run, set START_INDEX = {next_index}")


if __name__ == "__main__":
    # Step 1: Fetch VN30 symbols and save to file once (uncomment if file is missing)
    # retrieve_vn30_list()

    # retrieve_ohlcv_for_vn30_symbols()

    # Fetch data for ETF E1VFVN30
    fetch_and_save("VPL")
