# ===================================================================
# FETCH OHLCV DATA FOR 30 VN30 SYMBOLS + ETF E1VFVN30
# - Automatically fetch the 30 VN30 symbols from vnstock (dynamic)
# - Save the symbol list to a txt file (vn30_stocks.txt)
# - For each symbol (stock + ETF), fetch full OHLCV data
# - Save each symbol to its own CSV file
# ===================================================================

import pandas as pd
from vnstock import Quote, Listing
from datetime import datetime
import time
import os

# ====================== SETTINGS ======================
# Data time range (latest 3 years)
start_date = '2023-01-01'
end_date   = datetime.now().strftime('%Y-%m-%d')
LIST_FILE = 'datasets/vn30_list.txt'
OUTPUT_DIR = 'datasets/stocks'
START_INDEX =  29 # Starting index in the list (for batch runs)
BATCH_SIZE = 10   # Number of symbols to process per run


# ====================== STEP 1: FETCH 30 VN30 SYMBOLS ======================
def retrieve_vn30_list():
    print("Fetching 30 VN30 symbols from vnstock...")
    listing = Listing()
    vn30_list = listing.symbols_by_group(group_name='VN30')
    # vn30_symbols = vn30_list['symbol'].tolist()
    print(f"Fetched {len(vn30_list)} VN30 symbols.")

    # Save the symbol list to a txt file
    with open(LIST_FILE, 'w', encoding='utf-8') as f:
        f.write('\n'.join(vn30_list))
    print(f"Saved 30 VN30 symbols to file: {LIST_FILE}")

# ====================== STEP 3: FETCH OHLCV AND SAVE EACH FILE ======================
def fetch_and_save(symbol):
    try:
        quote = Quote(symbol='VCI', source='VCI')

        df = quote.history(
            symbol=symbol,
            start=start_date,
            interval='1D',
        )

        # Keep standard columns
        df = df[['time', 'open', 'high', 'low', 'close', 'volume']].copy()
        df.rename(columns={'time': 'date'}, inplace=True)
        df['symbol'] = symbol

        # Filename: <symbol>.csv
        file_path = f"{OUTPUT_DIR}/{symbol}.csv"
        df.to_csv(file_path, index=False, encoding='utf-8-sig')

        print(f"Saved {symbol} → {file_path} ({len(df)} rows)")
        return True

    except Exception as e:
        print(f"Error while fetching {symbol}: {e}")
        return False

def retrieve_ohlcv_for_vn30_symbols():
    # Read symbol list from file
    with open(LIST_FILE, 'r', encoding='utf-8') as f:
        symbols = [line.strip() for line in f.readlines() if line.strip()]

    print(f"Total symbols to fetch: {len(symbols)} (30 VN30)")

    # Select <BATCH_SIZE> symbols based on START_INDEX
    symbols_batch = symbols[START_INDEX:START_INDEX + BATCH_SIZE]

    if not symbols_batch:
        print(f"No symbols left to process (START_INDEX={START_INDEX} exceeds the list length).")
        return
    print(f"Processing symbols from index {START_INDEX} to {START_INDEX + len(symbols_batch) - 1}:")
    print(f"Symbol batch: {symbols_batch}")

    # Fetch OHLCV for each symbol and save separately
    success_count = 0
    for symbol in symbols_batch:
        if fetch_and_save(symbol):
            success_count += 1
        time.sleep(1.2)  # Delay to avoid rate limits

    print("\n" + "="*60)
    print(f"DONE! Successfully processed {success_count}/{len(symbols)} symbols.")
    print(f"All files were saved in directory: {OUTPUT_DIR}")
    print("Each file contains full columns: date, open, high, low, close, volume, symbol")
    next_index = START_INDEX + BATCH_SIZE
    if next_index < len(symbols):
        print(f"For the next run, set START_INDEX = {next_index}")

if __name__ == "__main__":
    # Step 1: Fetch VN30 symbols and save to file once (uncomment if file is missing)
    # retrieve_vn30_list()

    retrieve_ohlcv_for_vn30_symbols()

    # Fetch data for ETF E1VFVN30
    fetch_and_save('E1VFVN30')