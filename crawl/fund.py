# CODE: Retrieve historical NAV from vnstock (Fmarket integration)
# - Read fund symbols from fund_list.txt
# - Process only 5 funds per run (configurable via START_INDEX)
# - For each fund, fetch NAV history using nav_report()
# - Build a DataFrame with columns: date, price (nav_per_unit), fund_name
# - SAVE EACH FUND TO A SEPARATE CSV FILE (filename: <fund_name>_nav_history.csv)

import pandas as pd
from vnstock import Fund
from datetime import datetime
from pathlib import Path
import time  # Delay to avoid rate limits when needed

# ====== CONFIGURATION ======
START_INDEX = 60  # Starting index in the list
BATCH_SIZE = 5  # Number of funds to process per run
TRAIN_START_DATE = "2020-01-01"
SPLIT_DATE = "2023-10-01"
TEST_END_DATE = datetime.now().strftime("%Y-%m-%d")
ROOT_DIR = Path(__file__).resolve().parents[1]
DATASETS_DIR = ROOT_DIR / "datasets"
LIST_FILE = DATASETS_DIR / "fund_list.txt"
BOND_LIST_FILE = DATASETS_DIR / "bond_list.txt"
OUTPUT_DIR = DATASETS_DIR / "funds"
# ========================

# Initialize Fund object
fund = Fund()


def retrieve_fund_list():
    short_names = fund.listing()["short_name"].tolist()
    DATASETS_DIR.mkdir(parents=True, exist_ok=True)
    with open(LIST_FILE, "w") as f:
        for name in short_names:
            f.write(name + "\n")
    print(f"Saved {len(short_names)} fund short_names to fund_list.txt")


def retrieve_bond_list():
    df_all_funds = fund.listing()
    df_bond = df_all_funds[
        df_all_funds["fund_type"].str.contains(
            "Trái phiếu|Bond|Fixed Income", case=False, na=False
        )
    ]
    short_names = df_bond["short_name"].tolist()
    DATASETS_DIR.mkdir(parents=True, exist_ok=True)
    with open(BOND_LIST_FILE, "w") as f:
        for name in short_names:
            f.write(name + "\n")
    print(f"Saved {len(short_names)} bond short_names to bond_list.txt")


def get_nav_and_return(symbol):
    max_retries = 3
    attempt = 0

    while attempt < max_retries:
        try:
            # Fetch NAV report
            nav_df = fund.details.nav_report(symbol)

            # Validate required columns
            if "nav_per_unit" not in nav_df.columns or "date" not in nav_df.columns:
                print(f"Fund {symbol} is missing nav_per_unit or date columns.")
                return pd.DataFrame()

            # Prepare DataFrame
            df = nav_df[["date", "nav_per_unit"]].copy()
            df = df.sort_values("date")  # Ensure chronological order
            df["symbol"] = symbol
            df["price"] = (df["nav_per_unit"] / 1000).round(
                2
            )  # Divide by 1000 and round to 2 decimals

            # Keep only the 3 required columns
            df_final = df[["date", "price", "symbol"]]

            print(f"Processed fund {symbol} ({len(df_final)} rows)")

            return df_final

        except Exception as e:
            error_message = str(e)
            if "RateLimitExceeded" in error_message:
                attempt += 1
                print(
                    f"RateLimitExceeded while fetching fund {symbol}. Waiting 60 seconds before retry ({attempt}/{max_retries})..."
                )
                time.sleep(60)
                continue

            print(f"Error while fetching NAV for fund {symbol}: {e}")
            return pd.DataFrame()

    print(f"Exceeded maximum retries for fund {symbol} due to RateLimitExceeded.")
    return pd.DataFrame()


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


def crawl_fund_nav_history():
    # Step 1: Read fund symbols from file
    with open(LIST_FILE, "r") as f:
        all_fund_names = [line.strip() for line in f if line.strip()]

    print(f"Total funds in list file: {len(all_fund_names)}")

    # Step 2: Select a <BATCH_SIZE> batch based on START_INDEX
    fund_names_batch = all_fund_names[START_INDEX : START_INDEX + BATCH_SIZE]

    if not fund_names_batch:
        print(
            f"No funds left to process (START_INDEX={START_INDEX} exceeds the list length)."
        )
        return

    print(
        f"Processing funds from index {START_INDEX} to {START_INDEX + len(fund_names_batch) - 1}:"
    )
    print(f"Fund batch: {fund_names_batch}")
    # Step 3: Iterate through each fund and save each to a separate file
    processed_count = 0

    for fund_name in fund_names_batch:
        # Get NAV history and returns for one fund
        df_quy = get_nav_and_return(fund_name)

        if not df_quy.empty:
            # Output filename for each fund
            full_df, train_df, test_df = split_train_test(df_quy)
            if full_df.empty:
                print(
                    f"No data in configured range ({TRAIN_START_DATE} -> {TEST_END_DATE}) for {fund_name}."
                )
                continue

            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            (OUTPUT_DIR / "train").mkdir(parents=True, exist_ok=True)
            (OUTPUT_DIR / "test").mkdir(parents=True, exist_ok=True)
            full_path = OUTPUT_DIR / f"{fund_name}.csv"
            train_path = OUTPUT_DIR / "train" / f"{fund_name}_train.csv"
            test_path = OUTPUT_DIR / "test" / f"{fund_name}_test.csv"

            full_df.to_csv(full_path, index=False, encoding="utf-8-sig")
            train_df.to_csv(train_path, index=False, encoding="utf-8-sig")
            test_df.to_csv(test_path, index=False, encoding="utf-8-sig")

            print(
                f"Saved {fund_name} -> full:{len(full_df)} train:{len(train_df)} test:{len(test_df)}"
            )
            processed_count += 1

        # Delay to avoid Fmarket rate limits
        time.sleep(1.5)  # 1.5 seconds between requests

    # Step 4: Summary report
    print(f"\nDone! Successfully processed and saved {processed_count} funds.")
    print(f"All files were saved in directory: {OUTPUT_DIR}")
    next_index = START_INDEX + BATCH_SIZE
    if next_index < len(all_fund_names):
        print(f"For the next run, set START_INDEX = {next_index}")


if __name__ == "__main__":
    # retrieve_bond_list()
    crawl_fund_nav_history()
