# This is a sample Python script to fetch historical stock data for popular Vietnamese stocks, ETFs, and CCQ (mutual funds).
# Prioritizes popular stocks in recent years (e.g., blue-chips like VCB, VNM), ETFs like E1VFVN30 (VN30 ETF), and popular CCQ like VCBF-BCF.
# Uses 'vnstock' library (install via: pip install vnstock3) for easy access to Vietnamese market data.
# Time range: Last 3 years (from 2023-01-01 to current date).
# Output: Saves data to CSV files for each asset type.

import pandas as pd
from datetime import datetime
from vnstock import Vnstock  # Import Vnstock from vnstock3 package

# Define the list of assets
# Popular stocks (blue-chips/mid-caps recent years): VCB (Vietcombank), VNM (Vinamilk), HPG (Hoa Phat), FPT, MWG (Mobile World), SSI, BID, CTG, etc.
stocks = ['VCB', 'VNM', 'HPG', 'FPT', 'MWG', 'SSI', 'BID', 'CTG']

# ETFs: E1VFVN30 (VN30 ETF), add more if needed like VFMVND (Diamond ETF)
etfs = ['E1VFVN30']

# CCQ (mutual funds): VCBF-BCF (bond fund), TCBS-IBOND (bond), add more like VCBF-FIF (equity)
ccq = ['VCBF-BCF', 'TCBS-IBOND']

# Combine all symbols for fetching
all_symbols = stocks + etfs + ccq

# Set time range: Last 3 years to current date (adjust as needed)
start_date = '2024-01-01'
end_date = '2026-01-01'
# end_date = datetime.now().strftime('%Y-%m-%d')  # Current date

# Initialize Vnstock client (for HOSE/HNX data)
stock_client = Vnstock().stock(symbol='VCB', source='VCI')  # Initialize with any symbol, source='VCI' for reliable data

# Function to fetch historical data for a symbol
def fetch_historical_data(symbol, start, end):
    try:
        df = stock_client.quote.history(symbol=symbol, start=start, end=end)
        df = df[['time', 'close', 'volume']] 
        df.rename(columns={'time': 'date'}, inplace=True)
        df['symbol'] = symbol
        return df
    except Exception as e:
        print(f"Error fetching data for {symbol}: {e}")
        return pd.DataFrame()

# Fetch data for all symbols
all_data = pd.DataFrame()
for symbol in all_symbols:
    df = fetch_historical_data(symbol, start_date, end_date)
    if not df.empty:
        all_data = pd.concat([all_data, df], ignore_index=True)

# Save to CSV (or process further for MPT/Black-Litterman)
all_data.to_csv('vietnam_stock_data.csv', index=False)
print("Data saved to 'vietnam_stock_data.csv'. Preview:")
print(all_data.head())

# Further processing example: Compute daily returns for MPT
# Group by symbol and compute returns
def compute_returns(df):
    df = df.sort_values('date')
    df['return'] = df['close'].pct_change()  # Daily return = (close_t - close_{t-1}) / close_{t-1}
    return df

all_data_with_returns = all_data.groupby('symbol').apply(compute_returns).reset_index(drop=True)
all_data_with_returns.to_csv('vietnam_stock_data_with_returns.csv', index=False)
print("Data with returns saved to 'vietnam_stock_data_with_returns.csv'.")