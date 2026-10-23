"""Generate an editable vector architecture overview; render with Sharp separately."""
from pathlib import Path
from html import escape

OUT = Path(__file__).parent
parts = ['''<svg xmlns="http://www.w3.org/2000/svg" width="2400" height="2040" viewBox="0 0 2400 2040">
<defs>
 <marker id="arrow" markerWidth="9" markerHeight="9" refX="7" refY="4.5" orient="auto-start-reverse"><path d="M0,0 L8,4.5 L0,9" fill="none" stroke="#61748B" stroke-width="1.5"/></marker>
 <marker id="async" markerWidth="9" markerHeight="9" refX="7" refY="4.5" orient="auto-start-reverse"><path d="M0,0 L8,4.5 L0,9" fill="none" stroke="#D97706" stroke-width="1.5"/></marker>
</defs>
<rect width="2400" height="2040" fill="#F8FAFC"/>
<style>text{font-family:Arial,Helvetica,sans-serif;fill:#172B43} .muted{fill:#61748B}</style>''']

def rect(x,y,w,h,fill,stroke='none',rx=18,sw=2):
    parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')

def text(x,y,s,size=24,color='#172B43',weight=400):
    parts.append(f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" style="fill:{color}">{escape(s)}</text>')

def lines(x,y,items,size=23,color='#52647B',gap=32):
    for i,s in enumerate(items): text(x,y+i*gap,s,size,color)

def path(d,async_=False,bidir=False):
    color='#D97706' if async_ else '#61748B'
    marker='async' if async_ else 'arrow'
    dash='stroke-dasharray="9 8"' if async_ else ''
    start=f'marker-start="url(#{marker})"' if bidir else ''
    parts.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="2.5" {dash} {start} marker-end="url(#{marker})"/>')

def label(x,y,s,size=21):
    w=len(s)*size*.53+20
    rect(x-8,y-size,w,size+12,'#F8FAFC',rx=5)
    text(x,y,s,size,'#52647B')

def card(x,y,w,title,body,fill,stroke,h=110):
    rect(x,y,w,h,fill,stroke,12)
    text(x+20,y+37,title,27,stroke,700)
    lines(x+20,y+70,body,21,gap=28)

text(60,72,'KIẾN TRÚC HỆ THỐNG',46,weight=700)
text(60,115,'Ứng dụng tư vấn phân bổ danh mục • Microservices + Event-driven',27,'#52647B')
text(2040,65,'GIAI ĐOẠN 2',23,'#52647B',700)
text(2040,101,'Thiết kế đề xuất',22,'#52647B')

# Layer 1: UI + server-side BFF, deliberately combined as in source.
rect(60,160,1740,165,'#EFF8F1','#C9E4D1')
text(85,203,'01  GIAO DIỆN',23,'#166534',700)
card(520,183,855,'Frontend · Next.js UI + server BFF',
     ['Chat • hồ sơ rủi ro • danh mục • biểu đồ • backtest'], '#D4EDDA','#228B4B',117)
path('M 945 325 V 373 H 460 V 450')
path('M 945 373 H 990 V 450')
path('M 990 373 H 1530 V 450')
label(630,360,'HTTPS · REST / SSE',23)
label(400,430,'Portfolio, Chat')
label(926,430,'Market')
label(1460,430,'Research')

# Main service layer; each card is an independent domain service.
rect(60,450,1740,480,'#FFFFFF','#D9E2ED')
text(85,492,'02  DỊCH VỤ ĐỘC LẬP',24,weight=700)
rect(85,515,535,388,'#EFF6FF','#BFDBFE',14)
rect(640,515,535,388,'#F0FDFA','#99E4D8',14)
rect(1195,515,580,388,'#F5F3FF','#DDD6FE',14)
text(105,553,'NGHIỆP VỤ & HỘI THOẠI',23,'#1D4ED8',700)
text(660,553,'DỮ LIỆU & TRI THỨC',23,'#0F766E',700)
text(1215,553,'TÍNH TOÁN & MÔ HÌNH',23,'#6D28D9',700)
card(105,576,495,'Portfolio Service',['Profile • ledger • allocation saga'], '#CCE5FF','#2563EB')
card(105,728,495,'Chat Service',['Intent • tools • giải thích • SSE'], '#CCE5FF','#2563EB')
card(660,576,495,'Market Data Service',['Ingestion • kiểm định • snapshots'], '#CCFBF1','#0F766E')
card(660,728,495,'Knowledge Service',['Tài liệu • embeddings • RAG'], '#CCFBF1','#0F766E')
card(1215,569,540,'Quant Serving',['Forecasts • views • BL optimization'], '#EDE9FE','#7C3AED',99)
card(1215,681,540,'ML Platform',['Training • validation • model registry'], '#EDE9FE','#7C3AED',99)
card(1215,793,540,'Research Service',['Backtest • experiments • thesis evidence'], '#EDE9FE','#7C3AED',99)
text(108,880,'HTTPS giữa service: xem bảng kết nối bên dưới.',20,'#52647B')

# Async bus: endpoint membership explicit, Knowledge excluded.
path('M 350 935 V 1030',True,True)
path('M 900 935 V 1030',True)
path('M 1480 935 V 1030',True,True)
label(260,981,'Portfolio, Chat')
label(810,981,'Market → event')
label(1325,981,'Quant, ML, Research')
rect(60,1035,1740,137,'#FFF7ED','#FDBA74')
text(85,1078,'03  BẤT ĐỒNG BỘ',23,'#9A3412',700)
text(520,1080,'RabbitMQ',32,'#9A3412',700)
text(750,1080,'AMQPS · commands / domain events',25,'#9A3412')
text(520,1125,'Outbox → queue → consumer • retry / deduplication • kết quả qua events',23,'#9A3412')

# Owned persistence. Side rail starts at service boundary, bypasses RabbitMQ.
path('M 60 905 H 30 V 1240 H 305 V 1270')
path('M 30 1240 H 905 V 1270')
path('M 905 1240 H 1490 V 1270')
label(360,1225,'Truy cập lưu trữ từ service sở hữu / BFF · không đi qua RabbitMQ',22)
rect(60,1275,1740,242,'#FFFCF0','#ECD8A4')
text(85,1315,'04  LƯU TRỮ',23,'#854D0E',700)
card(85,1340,540,'PostgreSQL databases',[
    'SQL/TLS · database riêng mỗi service',
    'Knowledge database có pgvector',
    'Không truy vấn chéo database'
], '#FFF3CD','#A16207',153)
card(650,1340,555,'S3 · artifacts có version',[
    'HTTPS · datasets / models / results',
    'Market, ML, Quant, Research, Knowledge',
    'Owner scope • manifest • checksum'
], '#FFF3CD','#A16207',153)
card(1230,1340,545,'Redis',[
    'RESP/TLS · BFF: session',
    'Chat: SSE hints · Quant: forecast cache',
    'Trình duyệt không kết nối Redis'
], '#FFF3CD','#A16207',153)

# External sources / model providers, grouped as a separate boundary.
rect(1870,160,470,1012,'#F1F5F9','#CBD5E1')
text(1895,207,'BÊN NGOÀI HỆ THỐNG',24,'#475569',700)
card(1895,249,420,'Nguồn giá / NAV',[
    'và tài liệu',
    'Giá tài sản • NAV quỹ',
    'Tài liệu được cho phép'
], '#E2E8F0','#475569',165)
card(1895,470,420,'LLM / embedding',[
    'Hosted provider APIs',
    'Hiểu ý định • diễn giải',
    'Vector hóa văn bản'
], '#E2E8F0','#475569',165)
path('M 1800 700 H 1835 V 342 H 1889')
path('M 1835 700 V 560 H 1889')
label(1888,731,'HTTPS',23)
lines(1895,779,[
    'Market → Sources',
    'Giá / NAV qua source adapters',
    '',
    'Knowledge → Sources',
    'Nhập tài liệu theo allowlist',
    '',
    'Chat → LLM',
    'Intent / giải thích kết quả',
    '',
    'Knowledge → Embedding',
    'Tạo vectors cho RAG'
],21,gap=31)

rect(1870,1203,470,314,'#FFFFFF','#D9E2ED')
text(1895,1247,'CÁCH ĐỌC',24,weight=700)
path('M 1898 1288 H 1970')
text(1988,1296,'HTTPS / storage',21)
path('M 1898 1343 H 1970',True,True)
text(1988,1351,'AMQPS / events',21)
lines(1895,1401,[
    'Màu = nhóm trách nhiệm.',
    'Khung lớn = lớp / ranh giới.',
    'Đường chung gộp nhiều kết nối.'
],21,gap=33)

# Exact synchronous call map avoids a spaghetti diagram.
rect(60,1560,2280,367,'#FFFFFF','#D9E2ED')
text(85,1605,'KẾT NỐI HTTPS GIỮA CÁC SERVICE',26,weight=700)
text(85,1640,'Mỗi dòng ghi rõ bên gọi, bên nhận và dữ liệu trao đổi; response trả về trên cùng kết nối.',22,'#61748B')
rows_left=[
 ('Chat → Portfolio','Scoped tools: hồ sơ / danh mục / yêu cầu phân bổ'),
 ('Chat → Market','Facts: dữ liệu thị trường có nguồn và thời điểm'),
 ('Chat → Knowledge','Retrieval: đoạn tài liệu và citations'),
 ('Portfolio → Market','Pin metadata của data snapshot'),
 ('Portfolio → Quant','Resolve model / forecast đã READY'),
]
rows_right=[
 ('Quant → ML','Đọc model manifest và phiên bản đã duyệt'),
 ('Research → Market','Đọc metadata của dataset đã pin'),
 ('Research → ML','Đọc historical model manifest'),
]
for x,rows in [(85,rows_left),(1255,rows_right)]:
    for i,(a,b) in enumerate(rows):
        yy=1687+i*46
        text(x,yy,a,22,'#172B43',700)
        text(x+295,yy,b,20,'#52647B')
lines(1255,1842,[
    'Forecast có thể dùng chung; final weights theo từng danh mục.',
    'Mỗi service sở hữu dữ liệu và có thể triển khai độc lập.'
],21,gap=33)

text(60,1980,'Góc nhìn rút gọn: Identity, ingress và monitoring được lược khỏi hình; vẫn thuộc kiến trúc production.',23,'#61748B')
text(60,2017,'Nguồn: ARCHITECTURE_OVERVIEW.md • 14 thành phần • Các kết nối hạ tầng được gom và ghi rõ phạm vi sử dụng.',21,'#61748B')
parts.append('</svg>')
(OUT/'architecture-layered.svg').write_text('\n'.join(parts))
print(OUT/'architecture-layered.svg')
