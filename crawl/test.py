from vnstock import Vnstock, Fund

# # Khởi tạo đối tượng stock với mã 'ACB' và nguồn dữ liệu 'VCI'
# stock = Vnstock().stock(symbol='ACB', source='VCI')

# # Lấy dữ liệu lịch sử giá cổ phiếu trong 1 năm qua
# df = stock.quote.history(start='2024-01-01', end='2025-01-01', interval='1D')

# # In 5 dòng đầu tiên của dữ liệu
# print(df.head())

# # Lưu dữ liệu ra file Excel
# df.to_excel('gia_lich_su_ACB.xlsx', index=False)
# print("Đã lưu dữ liệu vào file 'gia_lich_su_ACB.xlsx'")


fund = Fund()
