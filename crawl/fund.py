# CODE: Lấy NAV lịch sử từ vnstock (Fmarket integration)
# - Đọc danh sách quỹ từ file fund_list.txt
# - Mỗi lần chạy chỉ xử lý 5 quỹ (có thể set START_INDEX)
# - Với từng quỹ, lấy NAV history qua nav_report()
# - Tạo DataFrame với các cột: date, price (nav_per_unit), fund_name
# - LƯU RIÊNG TỪNG FILE CSV cho mỗi mã quỹ (tên file: <fund_name>_nav_history.csv)

import pandas as pd
from vnstock import Fund
from datetime import datetime
import time  # Để delay tránh rate limit nếu cần

# ====== CẤU HÌNH ======
START_INDEX = 60   # Chỉ số bắt đầu trong danh sách
BATCH_SIZE = 5    # Số quỹ xử lý mỗi lần chạy
OUTPUT_DIR = 'datasets/funds'
# ========================

# Khởi tạo Fund object
fund = Fund()

def retrieve_fund_list():
    short_names = fund.listing()['short_name'].tolist()
    with open('fund_list.txt', 'w') as f:
        for name in short_names:
            f.write(name + '\n')
    print(f"Saved {len(short_names)} fund short_names to fund_list.txt")

def get_nav_and_return(fund_name):
    max_retries = 3
    attempt = 0

    while attempt < max_retries:
        try:
            # Lấy báo cáo NAV
            nav_df = fund.details.nav_report(fund_name)

            # Kiểm tra cột cần thiết
            if 'nav_per_unit' not in nav_df.columns or 'date' not in nav_df.columns:
                print(f"Quỹ {fund_name} thiếu cột nav_per_unit hoặc date.")
                return pd.DataFrame()

            # Chuẩn bị DataFrame
            df = nav_df[['date', 'nav_per_unit']].copy()
            df = df.sort_values('date')  # Đảm bảo theo thứ tự thời gian
            df['fund_name'] = fund_name
            df['price'] = df['nav_per_unit']  # Đổi tên thành price cho thống nhất

            # Chỉ giữ 3 cột theo yêu cầu
            df_final = df[['date', 'price', 'fund_name']]

            print(f"Đã xử lý quỹ {fund_name} ({len(df_final)} dòng)")

            return df_final

        except Exception as e:
            error_message = str(e)
            if 'RateLimitExceeded' in error_message:
                attempt += 1
                print(f"RateLimitExceeded khi lấy quỹ {fund_name}. Chờ 60 giây rồi thử lại ({attempt}/{max_retries})...")
                time.sleep(60)
                continue

            print(f"Lỗi khi lấy NAV cho quỹ {fund_name}: {e}")
            return pd.DataFrame()

    print(f"Vượt quá số lần thử lại cho quỹ {fund_name} do RateLimitExceeded.")
    return pd.DataFrame()

def crawl_fund_nav_history():
    # Bước 1: Đọc danh sách quỹ từ file
    fund_list_file = 'fund_list.txt'
    with open(fund_list_file, 'r') as f:
        all_fund_names = [line.strip() for line in f if line.strip()]

    print(f"Tổng số quỹ trong file: {len(all_fund_names)}")

    # Bước 2: Lấy batch <BATCH_SIZE> quỹ theo START_INDEX
    fund_names_batch = all_fund_names[START_INDEX:START_INDEX + BATCH_SIZE]

    if not fund_names_batch:
        print(f"Không còn quỹ nào để xử lý (START_INDEX={START_INDEX} vượt quá danh sách).")
        return

    print(f"Xử lý quỹ từ index {START_INDEX} đến {START_INDEX + len(fund_names_batch) - 1}:")
    print(f"Danh sách: {fund_names_batch}")
    # Bước 3: Lặp qua từng quỹ và lưu RIÊNG từng file
    processed_count = 0

    for fund_name in fund_names_batch:
        
        # Hàm lấy NAV history và tính return cho một quỹ
        df_quy = get_nav_and_return(fund_name)

        if not df_quy.empty:
            # Tên file riêng cho từng quỹ
            file_name = f"{OUTPUT_DIR}/{fund_name}_nav_history.csv"
            df_quy.to_csv(file_name, index=False, encoding='utf-8-sig')
            print(f"Đã lưu file riêng: {file_name}")
            processed_count += 1

        # Delay để tránh rate limit từ Fmarket
        time.sleep(1.5)  # 1.5 giây giữa các request

    # Bước 4: Báo cáo tổng kết
    print(f"\nHoàn tất! Đã xử lý và lưu thành công {processed_count} quỹ.")
    print(f"Tất cả file được lưu trong thư mục: {OUTPUT_DIR}")
    next_index = START_INDEX + BATCH_SIZE
    if next_index < len(all_fund_names):
        print(f"Lần chạy tiếp theo, đặt START_INDEX = {next_index}")

if __name__ == "__main__":
    crawl_fund_nav_history()