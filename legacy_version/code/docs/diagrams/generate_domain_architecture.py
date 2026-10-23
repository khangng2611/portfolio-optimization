"""Domain ownership overview plus one concrete event-driven orchestration flow."""
from pathlib import Path
from html import escape

out = Path(__file__).parent
p = ['''<svg xmlns="http://www.w3.org/2000/svg" width="2600" height="1960" viewBox="0 0 2600 1960">
<defs>
<marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto-start-reverse"><path d="M0,0 L8,4 L0,8" fill="#64748B"/></marker>
<marker id="command" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto-start-reverse"><path d="M0,0 L8,4 L0,8" fill="#D97706"/></marker>
<marker id="event" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto-start-reverse"><path d="M0,0 L8,4 L0,8" fill="#7C3AED"/></marker>
</defs><rect width="2600" height="1960" fill="#F8FAFC"/>
<style>text{font-family:Arial,Helvetica,sans-serif}</style>''']

def box(x,y,w,h,fill='#FFFFFF',stroke='#CBD5E1',sw=2,rx=16):
    p.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')

def txt(x,y,s,size=24,color='#172B43',bold=False):
    p.append(f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{700 if bold else 400}" fill="{color}">{escape(s)}</text>')

def lines(x,y,items,size=22,color='#52647B',gap=30):
    for i,s in enumerate(items): txt(x,y+i*gap,s,size,color)

def line(d,kind='arrow',both=False):
    color={'arrow':'#64748B','command':'#D97706','event':'#7C3AED'}[kind]
    dash='stroke-dasharray="10 7"' if kind=='event' else ''
    start=f'marker-start="url(#{kind})"' if both else ''
    p.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="3" {dash} marker-end="url(#{kind})" {start}/>')

txt(60,76,'MICROSERVICES THEO DOMAIN',47,bold=True)
txt(60,124,'+ EVENT-DRIVEN ORCHESTRATION',38,'#2563EB',True)
txt(1850,76,'PORTFOLIO OPTIMIZATION',25,'#52647B',True)
txt(1850,116,'Kiến trúc đề xuất · Giai đoạn 2',25,'#52647B')
txt(60,186,'A. RANH GIỚI DOMAIN — SERVICE, DỮ LIỆU VÀ DEPLOYMENT RIÊNG',27,bold=True)

box(60,215,2480,91,'#EFF8F1','#A7D7B7')
txt(85,252,'Frontend · Next.js UI + BFF',28,'#166534',True)
txt(85,285,'HTTPS tới Chat / Portfolio / Market / Research · SSE trả kết quả về UI',23,'#166534')
txt(1675,252,'BFF quản lý session; browser không đọc Redis.',23,'#166534')
txt(1675,285,'Các domain còn lại phục vụ qua API / worker nội bộ.',23,'#166534')

domains=[
 ('HỘI THOẠI','Chat Service',['Intent • tools','Giải thích • SSE'],'chat_db','#CCE5FF','#2563EB','Continuation events'),
 ('DANH MỤC','Portfolio Service',['Profile • ledger','Allocation saga'],'portfolio_db','#DBEAFE','#1D4ED8','Command / result / ready'),
 ('TỐI ƯU','Quant Serving',['Forecasts • views','Black–Litterman'],'quant_db','#EDE9FE','#7C3AED','Optimize / result'),
 ('THỊ TRƯỜNG','Market Data',['Ingestion • quality','Immutable snapshots'],'market_db','#CCFBF1','#0F766E','dataset.published'),
 ('MÔ HÌNH','ML Platform',['Training • validation','Model registry'],'ml_db','#EDE9FE','#7C3AED','Training / model events'),
 ('TRI THỨC','Knowledge Service',['Documents • embeddings','RAG retrieval'],'knowledge_db','#CCFBF1','#0F766E','HTTPS retrieval'),
 ('THỰC NGHIỆM','Research Service',['Backtest • experiments','Evaluation evidence'],'research_db','#EDE9FE','#7C3AED','Research jobs / events'),
]
for i,(domain,name,body,db,fill,color,event) in enumerate(domains):
    x=60+i*357
    if i in [0,1,3,6]:
        line(f'M {x+165} 307 V 346')
    box(x,350,338,405,'#FFFFFF',color,4 if i==1 else 2)
    txt(x+18,390,domain,23,color,True)
    if i==1:
        box(x+17,405,304,30,'#1D4ED8','#1D4ED8',rx=7)
        txt(x+34,427,'WORKFLOW ORCHESTRATOR',18,'#FFFFFF',True)
    else:
        txt(x+18,429,'Domain API + worker runtime',19,'#64748B')
    box(x+17,453,304,111,fill,color,rx=10)
    txt(x+30,487,name,25,color,True)
    lines(x+30,517,body,21,color,gap=27)
    line(f'M {x+170} 565 V 613')
    txt(x+183,596,'SQL/TLS',18,'#64748B')
    box(x+17,622,304,61,'#FFF3CD','#A16207',rx=10)
    txt(x+30,660,db+(' + vector' if i==5 else ''),21,'#854D0E',True)
    txt(x+18,716,'Own DB • API / schema có version',18,'#52647B')
    txt(x+18,742,event,20,color)
    if i!=5:
        # Connect the domain's integration boundary, not its database.
        line(f'M {x+170} 760 V 841','event',i!=3)

box(60,848,2480,118,'#FFF7ED','#F59E0B',2)
txt(85,892,'RabbitMQ',33,'#9A3412',True)
txt(345,892,'AMQPS · Commands & Domain Events',29,'#9A3412',True)
txt(85,936,'Chuyển thông điệp giữa domain • outbox / inbox • retry / deduplication • không quyết định bước nghiệp vụ tiếp theo',25,'#9A3412')
box(60,989,2480,92,'#FFFFFF','#D9E2ED')
txt(85,1024,'HẠ TẦNG / TÍCH HỢP ĐƯỢC LƯỢC KHỎI LUỒNG CHÍNH',21,'#52647B',True)
txt(85,1057,'S3: artifacts theo owner  |  Redis: BFF session / Chat hints / Quant cache  |  Nguồn giá, tài liệu  |  LLM / embedding provider',25,'#52647B')

txt(60,1140,'B. MỘT WORKFLOW CỤ THỂ — AI ĐIỀU PHỐI, AI THỰC THI?',29,bold=True)
txt(60,1180,'Ví dụ: input đã xác nhận → tối ưu danh mục → lưu recommendation → sinh giải thích.',25,'#52647B')

def workflow(y,number,title,left,left_lines,right,right_lines,message,kind):
    box(60,y,2480,163,'#FFFFFF','#D9E2ED')
    txt(85,y+48,number,34,'#2563EB',True)
    lines(85,y+85,title,23,'#172B43',gap=31)
    left_color='#1D4ED8' if left=='Portfolio' else '#7C3AED'
    right_color='#1D4ED8' if right in ['Portfolio','Chat'] else '#7C3AED'
    box(365,y+25,455,112,'#EFF6FF' if left=='Portfolio' else '#F5F3FF',left_color,rx=12)
    txt(386,y+61,left,29,left_color,True)
    lines(386,y+92,left_lines,21,gap=29)
    box(1260,y+38,235,88,'#FFF7ED','#F59E0B',rx=12)
    txt(1286,y+91,'RabbitMQ',28,'#9A3412',True)
    box(1935,y+25,575,112,'#EFF6FF' if right in ['Portfolio','Chat'] else '#F5F3FF',right_color,rx=12)
    txt(1956,y+61,right,29,right_color,True)
    lines(1956,y+92,right_lines,21,gap=29)
    line(f'M 825 {y+98} H 1253',kind)
    line(f'M 1500 {y+98} H 1927',kind)
    txt(843,y+71,message,20,'#D97706' if kind=='command' else '#7C3AED',True)
    txt(1530,y+71,'AMQPS delivery',22,'#52647B')

workflow(1215,'01',['Gửi lệnh','tính toán'],'Portfolio',
 ['Lưu saga = WAITING_QUANT','Commit input + outbox'],
 'Quant',['Kiểm tra input • chạy BL / solver','Lưu run + result + outbox'],
 'COMMAND: optimize.requested','command')
workflow(1396,'02',['Nhận kết quả','và chuyển bước'],'Quant',
 ['Công bố kết quả đã tính','Không tự sửa dữ liệu Portfolio'],
 'Portfolio',['Đối chiếu request / version / constraints','Lưu recommendation + ready-event outbox'],
 'EVENT: optimization.succeeded','event')
workflow(1577,'03',['Tiếp tục','giải thích'],'Portfolio',
 ['Công bố recommendation READY','Trạng thái saga lưu tại portfolio_db'],
 'Chat',['Đọc canonical facts • gọi LLM • kiểm tra','Lưu giải thích → SSE tới Frontend'],
 'EVENT: recommendation.ready','event')

box(60,1770,2480,106,'#EFF6FF','#BFDBFE')
txt(85,1813,'ORCHESTRATOR = PORTFOLIO',27,'#1D4ED8',True)
txt(765,1813,'BROKER = RABBITMQ',27,'#9A3412',True)
txt(1450,1813,'EXECUTORS = QUANT / CHAT',27,'#6D28D9',True)
txt(85,1850,'Giữ state, kiểm tra kết quả, chuyển bước.',23,'#52647B')
txt(765,1850,'Chuyển và giao lại command / event.',23,'#52647B')
txt(1450,1850,'Thực hiện tác vụ trong domain được giao.',23,'#52647B')
txt(60,1925,'Các database là quyền sở hữu logic riêng; không bắt buộc mỗi DB là một máy chủ. HTTPS liên service và các workflow khác được lược để làm rõ kiến trúc.',22,'#64748B')
p.append('</svg>')
(out/'architecture-domain-orchestration.svg').write_text('\n'.join(p))
print(out/'architecture-domain-orchestration.svg')
