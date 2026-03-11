import os
import subprocess
from datetime import datetime, timedelta
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

import requests
from bs4 import BeautifulSoup

# Đường dẫn thư mục & file CSV (cùng folder với script này)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(BASE_DIR, "datasets/pnj_sjc_price.csv")

##Crawler
def parse_price(text):
    try:
        # Loại bỏ dấu chấm, chuyển về int rồi chia cho 1000
        clean = text.replace('.', '').strip()
        value = int(clean)
        return round(value / 1000, 2)
    except:
        return None

def get_gold_data_for_date(date_obj):
    day = date_obj.strftime("%d")
    month = date_obj.strftime("%m")
    year = date_obj.strftime("%Y")
    url = f"https://giavang.pnj.com.vn/history?gold_history_day={day}&gold_history_month={month}&gold_history_year={year}"
    resp = requests.get(url)
    if resp.status_code != 200:
        return None
    soup = BeautifulSoup(resp.text, 'lxml')
    table = soup.select_one(
        "#portlet_com_pnj_gold_price_web_SearchGoldPriceResultPortlet_INSTANCE_3WGHuiSEaY89 > div > div > div > table:nth-child(1)"
    )
    if not table:
        # Trả về NaN cho các cột nếu không tìm thấy bảng
        return {"PNJ_gia_mua": None, "PNJ_gia_ban": None, "SJC_gia_mua": None, "SJC_gia_ban": None}
    try:
        pnj_row = table.select_one("tbody > tr:nth-child(2)")
        sjc_row = table.select_one("tbody > tr:nth-child(4)")
        pnj_gia_mua = parse_price(pnj_row.select_one("td:nth-child(2)").get_text())
        pnj_gia_ban = parse_price(pnj_row.select_one("td:nth-child(3)").get_text())
        sjc_gia_mua = parse_price(sjc_row.select_one("td:nth-child(2)").get_text())
        # Lấy SJC_gia_ban theo thứ tự ưu tiên:
        sjc_gia_ban = None
        # 1) tr[5] td[3]
        cell = table.select_one("tbody > tr:nth-child(5) > td:nth-child(3)")
        if cell and cell.get_text().strip():
            sjc_gia_ban = parse_price(cell.get_text())
        else:
            # 2) tr[6] td[2]
            cell = table.select_one("tbody > tr:nth-child(6) > td:nth-child(2)")
            if cell and cell.get_text().strip():
                sjc_gia_ban = parse_price(cell.get_text())
            else:
                # 3) sang table thứ hai: tr[7] td[2]
                table2 = soup.select_one(
                    "#portlet_com_pnj_gold_price_web_SearchGoldPriceResultPortlet_INSTANCE_3WGHuiSEaY89 "
                    "> div > div > div > table:nth-child(2)"
                )
                if table2:
                    cell = table2.select_one("tbody > tr:nth-child(7) > td:nth-child(2)")
                    if cell and cell.get_text().strip():
                        sjc_gia_ban = parse_price(cell.get_text())
        return {"PNJ_gia_mua": pnj_gia_mua, "PNJ_gia_ban": pnj_gia_ban, "SJC_gia_mua": sjc_gia_mua, "SJC_gia_ban": sjc_gia_ban}
    except:
        return {"PNJ_gia_mua": None, "PNJ_gia_ban": None, "SJC_gia_mua": None, "SJC_gia_ban": None}

def code_update_gia_vang(start_date, end_date):
    # Thư mục chứa file và đường dẫn file CSV
    folder = BASE_DIR                            
    filepath = CSV_PATH                          
    os.makedirs(folder, exist_ok=True)    

    # Đọc dữ liệu đã có (nếu file tồn tại và không rỗng)
    if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
        df_existing = pd.read_csv(filepath, dtype=str)
        df_existing['Ngày'] = pd.to_datetime(df_existing['Ngày'], format="%d/%m/%Y")
        existing_dates = set(df_existing['Ngày'].dt.strftime("%d/%m/%Y"))
    else:
        df_existing = pd.DataFrame(columns=["Ngày", "PNJ_gia_mua", "PNJ_gia_ban", "SJC_gia_mua", "SJC_gia_ban"])
        existing_dates = set()

    rows = []
    current_date = start_date
    while current_date <= end_date:
        date_str = current_date.strftime("%d/%m/%Y")
        if date_str not in existing_dates:
            print(f"Crawling {date_str}...")
            data = get_gold_data_for_date(current_date)
            if data is None:
                # Lỗi khi request
                row = {"Ngày": date_str, "PNJ_gia_mua": None, "PNJ_gia_ban": None, "SJC_gia_mua": None, "SJC_gia_ban": None}
            else:
                row = {"Ngày": date_str,
                       "PNJ_gia_mua": data["PNJ_gia_mua"],
                       "PNJ_gia_ban": data["PNJ_gia_ban"],
                       "SJC_gia_mua": data["SJC_gia_mua"],
                       "SJC_gia_ban": data["SJC_gia_ban"]}
            rows.append(row)
        current_date += timedelta(days=1)

    # Ghi vào CSV và sắp xếp
    if rows:
        df_new = pd.DataFrame(rows)
        df_new['Ngày'] = pd.to_datetime(df_new['Ngày'], format="%d/%m/%Y")
        df_all = pd.concat([df_existing, df_new], ignore_index=True)
        df_all = df_all.drop_duplicates(subset=['Ngày'], keep='first')
        df_all = df_all.sort_values(by='Ngày', ascending=False)
        df_all['Ngày'] = df_all['Ngày'].dt.strftime("%d/%m/%Y")
        df_all.to_csv(filepath, index=False)
        print(f"Saved {len(df_new)} new records to {filepath}")
    else:
        print("No new dates to crawl.")

def update_missing_data(start_date, end_date):
    """
    Gọi batch crawl để đảm bảo CSV đã đầy đủ dữ liệu từ start_date đến end_date.
    """
    code_update_gia_vang(start_date, end_date)
    print(f"Đã cập nhật dữ liệu từ {start_date.strftime('%d/%m/%Y')} đến {end_date.strftime('%d/%m/%Y')}.")


def visualize(start_date, end_date, columns):
    """
    Đọc CSV, lọc, vẽ đồ thị giá vàng cho các cột trong `columns`
    """
    df = pd.read_csv(CSV_PATH, parse_dates=["Ngày"], dayfirst=True)
    mask = (df['Ngày'].dt.date >= start_date) & (df['Ngày'].dt.date <= end_date)
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
            df['Ngày'],
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
        for year, group in df.groupby(df['Ngày'].dt.year):
            dates = group['Ngày']
            mid = dates.iloc[len(dates)//2]
            ax.text(mid, ymin, str(year), ha='center', va='bottom')

    plt.title(f"Giá vàng từ {start_date.strftime('%d/%m/%Y')} đến {end_date.strftime('%d/%m/%Y')}")
    plt.legend()
    plt.tight_layout()
    plt.show()

def main():
    # start_str = input("Enter start date (dd/mm/yyyy): ")
    # end_str   = input("Enter end date (dd/mm/yyyy): ")
    start_str = "01/01/2024"
    end_str   = "10/01/2024"
    sd = datetime.strptime(start_str, "%d/%m/%Y").date()
    ed = datetime.strptime(end_str, "%d/%m/%Y").date()

    # Cập nhật dữ liệu thiếu
    update_missing_data(sd, ed)

    # # Chọn cột để hiển thị
    # print("Chọn cột để hiển thị:")
    # print(" 1: PNJ_gia_mua")
    # print(" 2: PNJ_gia_ban")
    # print(" 3: SJC_gia_mua")
    # print(" 4: SJC_gia_ban")
    # nums = input("Nhập các số (cách nhau bởi dấu phẩy) hoặc 'all' để chọn tất cả: ")
    # if nums.strip().lower() == 'all':
    #     cols = ["PNJ_gia_mua", "PNJ_gia_ban", "SJC_gia_mua", "SJC_gia_ban"]
    # else:
    #     mapping = {'1': 'PNJ_gia_mua', '2': 'PNJ_gia_ban', '3': 'SJC_gia_mua', '4': 'SJC_gia_ban'}
    #     cols = [mapping[n.strip()] for n in nums.split(',') if n.strip() in mapping]
    #     if not cols:
    #         print("Không có lựa chọn hợp lệ, sử dụng mặc định cả 4 cột.")
    #         cols = ["PNJ_gia_mua", "PNJ_gia_ban", "SJC_gia_mua", "SJC_gia_ban"]

    cols = ["PNJ_gia_mua", "PNJ_gia_ban", "SJC_gia_mua", "SJC_gia_ban"]
    if not cols:
        print("Không có lựa chọn hợp lệ, sử dụng mặc định cả 4 cột.")
        cols = ["PNJ_gia_mua", "PNJ_gia_ban", "SJC_gia_mua", "SJC_gia_ban"]

    # Vẽ biểu đồ với cột đã chọn
    visualize(sd, ed, cols)

if __name__ == '__main__':
    main()
