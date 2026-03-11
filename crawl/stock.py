# ===================================================================
# LẤY DỮ LIỆU OHLCV CHO 30 MÃ VN30 + ETF E1VFVN30
# - Tự động lấy danh sách 30 mã VN30 từ vnstock (dynamic)
# - Lưu danh sách vào file txt (vn30_stocks.txt)
# - Với mỗi mã (cổ phiếu + ETF) → lấy đầy đủ OHLCV
# - Mỗi mã lưu thành 1 file CSV riêng
# ===================================================================

import pandas as pd
from vnstock import Quote, Listing
from datetime import datetime
import time
import os

# ====================== CÀI ĐẶT ======================
# Thời gian lấy dữ liệu (3 năm gần nhất)
start_date = '2023-01-01'
end_date   = datetime.now().strftime('%Y-%m-%d')
LIST_FILE = 'datasets/vn30_list.txt'
OUTPUT_DIR = 'datasets/stocks'
START_INDEX =  29 # Chỉ số bắt đầu trong danh sách (dùng để chạy theo batch)
BATCH_SIZE = 10   # Số mã xử lý mỗi lần chạy


# ====================== BƯỚC 1: LẤY DANH SÁCH 30 MÃ VN30 ======================
def retrieve_vn30_list():
    print("Đang lấy danh sách 30 mã VN30 từ vnstock...")
    listing = Listing()
    vn30_list = listing.symbols_by_group(group_name='VN30')
    # vn30_symbols = vn30_list['symbol'].tolist()
    print(f"Đã lấy được {len(vn30_list)} mã VN30.")

    # Lưu danh sách vào file txt
    with open(LIST_FILE, 'w', encoding='utf-8') as f:
        f.write('\n'.join(vn30_list))
    print(f"Đã lưu danh sách 30 mã VN30 vào file: {LIST_FILE}")

# ====================== BƯỚC 3: LẤY OHLCV VÀ LƯU RIÊNG TỪNG FILE ======================
def fetch_and_save(symbol):
    try:
        quote = Quote(symbol='VCI', source='VCI')

        df = quote.history(
            symbol=symbol,
            start=start_date,
            interval='1D',
        )

        # Đảm bảo các cột chuẩn
        df = df[['time', 'open', 'high', 'low', 'close', 'volume']].copy()
        df.rename(columns={'time': 'date'}, inplace=True)
        df['symbol'] = symbol

        # Tên file: <symbol>.csv
        file_path = f"{OUTPUT_DIR}/{symbol}.csv"
        df.to_csv(file_path, index=False, encoding='utf-8-sig')

        print(f"Đã lưu {symbol} → {file_path} ({len(df)} dòng)")
        return True

    except Exception as e:
        print(f"Lỗi khi lấy {symbol}: {e}")
        return False

def retrieve_ohlcv_for_vn30_symbols():
    # Đọc lại danh sách từ file
    with open(LIST_FILE, 'r', encoding='utf-8') as f:
        symbols = [line.strip() for line in f.readlines() if line.strip()]

    print(f"Tổng số mã sẽ lấy dữ liệu: {len(symbols)} (30 VN30)")

    # Lấy batch <BATCH_SIZE> mã theo START_INDEX
    symbols_batch = symbols[START_INDEX:START_INDEX + BATCH_SIZE]

    if not symbols_batch:
        print(f"Không còn mã nào để xử lý (START_INDEX={START_INDEX} vượt quá danh sách).")
        return
    print(f"Xử lý quỹ từ index {START_INDEX} đến {START_INDEX + len(symbols_batch) - 1}:")
    print(f"Danh sách: {symbols_batch}")

    # Lấy OHLCV cho từng mã và lưu riêng
    success_count = 0
    for symbol in symbols_batch:
        if fetch_and_save(symbol):
            success_count += 1
        time.sleep(1.2)  # Delay tránh rate limit

    print("\n" + "="*60)
    print(f"HOÀN TẤT! Đã xử lý thành công {success_count}/{len(symbols)} mã.")
    print(f"Tất cả file được lưu trong thư mục: {OUTPUT_DIR}")
    print("Mỗi file có đầy đủ cột: date, open, high, low, close, volume, symbol")
    next_index = START_INDEX + BATCH_SIZE
    if next_index < len(symbols):
        print(f"Lần chạy tiếp theo, đặt START_INDEX = {next_index}")

if __name__ == "__main__":
    # Bước 1: Lấy danh sách VN30 và lưu vào file, 1 lần duy nhất (bỏ comment nếu đã có file)
    # retrieve_vn30_list()

    retrieve_ohlcv_for_vn30_symbols()

    # Lay dữ liệu cho ETF E1VFVN30
    fetch_and_save('E1VFVN30')