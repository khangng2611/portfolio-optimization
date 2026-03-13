import os
import subprocess
from datetime import datetime, timedelta
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

import requests
# Đường dẫn thư mục & file CSV (cùng folder với script này)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(BASE_DIR, "datasets/gold/pnj_sjc_price.csv")
PNJ_API_BASE_URL = "https://edge-cf-api.pnj.io"

##Crawler
def parse_price(text):
    try:
        # Loại bỏ dấu chấm, chuyển về int rồi chia cho 1000
        clean = text.replace('.', '').strip()
        value = int(clean)
        return round(value / 1000, 2)
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
    url = f"{PNJ_API_BASE_URL}/ecom-frontend/v1/get-gold-price-history?date={date_param}"

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

def batch_gold_price_update(start_date, end_date):
    # Thư mục chứa file và đường dẫn file CSV
    folder = BASE_DIR                            
    filepath = CSV_PATH                          
    os.makedirs(folder, exist_ok=True)    

    # Đọc dữ liệu đã có (nếu file tồn tại)
    if os.path.exists(filepath):
        df_existing = pd.read_csv(filepath, dtype=str)
        df_existing['date'] = pd.to_datetime(df_existing['date'], errors='coerce', dayfirst=True)
        df_existing = df_existing.dropna(subset=['date'])
        existing_dates = set(df_existing['date'].dt.strftime("%Y-%m-%d"))
    else:
        df_existing = pd.DataFrame(columns=["date", "pnj_buy", "pnj_sell", "sjc_buy", "sjc_sell"])
        existing_dates = set()

    rows = []
    current_date = start_date
    while current_date <= end_date:
        date_str = current_date.strftime("%Y-%m-%d")
        if date_str not in existing_dates:
            print(f"Crawling {date_str}...")
            data = get_gold_data_for_date(current_date)
            if data is None:
                # Lỗi khi request
                row = {"date": date_str, "pnj_buy": None, "pnj_sell": None, "sjc_buy": None, "sjc_sell": None}
            else:
                row = {"date": date_str,
                       "pnj_buy": data["pnj_buy"],
                       "pnj_sell": data["pnj_sell"],
                       "sjc_buy": data["sjc_buy"],
                       "sjc_sell": data["sjc_sell"]}
            rows.append(row)
        current_date += timedelta(days=1)

    # Ghi vào CSV và sắp xếp
    if rows:
        df_new = pd.DataFrame(rows)
        df_new['date'] = pd.to_datetime(df_new['date'], errors='coerce')
        df_all = pd.concat([df_existing, df_new], ignore_index=True)
        df_all['date'] = pd.to_datetime(df_all['date'], errors='coerce')
        df_all = df_all.dropna(subset=['date'])
        df_all = df_all.drop_duplicates(subset=['date'], keep='first')
        df_all = df_all.sort_values(by='date', ascending=True)
        df_all['date'] = df_all['date'].dt.strftime("%Y-%m-%d")
        df_all.to_csv(filepath, index=False)
        print(f"Saved {len(df_new)} new records to {filepath}")
    else:
        print("No new dates to crawl.")

def update_missing_data(start_date, end_date):
    """
    Gọi batch crawl để đảm bảo CSV đã đầy đủ dữ liệu từ start_date đến end_date.
    """
    batch_gold_price_update(start_date, end_date)
    print(f"Đã cập nhật dữ liệu từ {start_date.strftime('%d/%m/%Y')} đến {end_date.strftime('%d/%m/%Y')}.")


def visualize(start_date, end_date, columns):
    """
    Đọc CSV, lọc, vẽ đồ thị giá vàng cho các cột trong `columns`
    """
    df = pd.read_csv(CSV_PATH, parse_dates=["date"], dayfirst=True)
    mask = (df['date'].dt.date >= start_date) & (df['date'].dt.date <= end_date)
    df = df.loc[mask].copy()
    df.dropna(subset=columns, how='all', inplace=True)
    if df.empty:
        print("Không có dữ liệu để hiển thị sau khi loại NaN.")
        return

    # Giới hạn trục Y
    vals = df[columns]
    ymin, ymax = vals.min().min(), vals.max().max()

    fig, ax = plt.subplots(figsize=(10, 6))
    marker_map = {
        "PNJ_gia_mua": "o", "PNJ_gia_ban": "o",
        "SJC_gia_mua": "x", "SJC_gia_ban": "x"
    }
    for col in columns:
        ax.plot(
            df['date'],
            df[col],
            marker=marker_map.get(col, 'o'),
            label=col
        )

    ax.set_ylim(ymin * 0.99, ymax * 1.01)
    ax.set_ylabel('Giá (triệu đồng/lượng)')

    # Định dạng trục X (giữ nguyên logic cũ)
    days = (end_date - start_date).days
    if days <= 10:
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%d/%m/%y'))
        ax.xaxis.set_major_locator(mdates.DayLocator())
    else:
        ax.xaxis.set_major_locator(mdates.MonthLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
        for year, group in df.groupby(df['date'].dt.year):
            dates = group['date']
            mid = dates.iloc[len(dates)//2]
            ax.text(mid, ymin, str(year), ha='center', va='bottom')

    plt.title(f"Giá vàng từ {start_date.strftime('%d/%m/%Y')} đến {end_date.strftime('%d/%m/%Y')}")
    plt.legend()
    plt.tight_layout()
    plt.show()

def main():
    start_str = "01/01/2023"
    end_str   = "10/03/2026"
    sd = datetime.strptime(start_str, "%d/%m/%Y").date()
    ed = datetime.strptime(end_str, "%d/%m/%Y").date()

    # Cập nhật dữ liệu thiếu
    update_missing_data(sd, ed)

    cols = ["pnj_buy", "pnj_sell", "sjc_buy", "sjc_sell"]
    if not cols:
        print("Không có lựa chọn hợp lệ, sử dụng mặc định cả 4 cột.")
        cols = ["pnj_buy", "pnj_sell", "sjc_buy", "sjc_sell"]

    # Vẽ biểu đồ với cột đã chọn
    # visualize(sd, ed, cols)

if __name__ == '__main__':
    main()
