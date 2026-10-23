"""Render every Mermaid connection in linked domain/HTTP/integration views."""
from pathlib import Path
from html import escape
import json
import re

out = Path(__file__).parent
source = (out.parent / 'ARCHITECTURE_OVERVIEW.md').read_text()
mermaid = re.search(r'```mermaid\n(.*?)```', source, re.S).group(1)
expected = {(a, b, op) for a, op, b in re.findall(
    r'^\s+(\w+)\s+(-->|<-->)(?:\|[^\n]+?\|)?\s*(\w+)\s*$', mermaid, re.M)}
seen = set()
p = ['''<svg xmlns="http://www.w3.org/2000/svg" width="3200" height="2890" viewBox="0 0 3200 2890">
<defs>
<marker id="http" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto-start-reverse"><path d="M0,0 L8,4 L0,8" fill="#526B89"/></marker>
<marker id="event" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto-start-reverse"><path d="M0,0 L8,4 L0,8" fill="#B45309"/></marker>
</defs><rect width="3200" height="2890" fill="#F8FAFC"/>
<style>text{font-family:Arial,Helvetica,sans-serif}</style>''']

colors = {
 'Web':('#DCFCE7','#15803D'), 'Chat':('#DBEAFE','#2563EB'),
 'Portfolio':('#DBEAFE','#1D4ED8'), 'Market':('#CCFBF1','#0F766E'),
 'Knowledge':('#CCFBF1','#0F766E'), 'Quant':('#EDE9FE','#7C3AED'),
 'ML':('#EDE9FE','#7C3AED'), 'Research':('#EDE9FE','#7C3AED'),
 'S3':('#FEF3C7','#A16207'), 'Redis':('#FEF3C7','#A16207'),
 'Sources':('#E2E8F0','#475569'), 'LLM':('#E2E8F0','#475569'),
 'MQ':('#FFEDD5','#C2410C')
}
names = {'Web':'Frontend / BFF','Chat':'Chat Service','Portfolio':'Portfolio Service',
 'Market':'Market Data','Knowledge':'Knowledge Service','Quant':'Quant Serving',
 'ML':'ML Platform','Research':'Research Service','S3':'S3','Redis':'Redis',
 'Sources':'Sources','LLM':'LLM / Embedding','MQ':'RabbitMQ'}

def box(x,y,w,h,fill='#FFFFFF',stroke='#D5DFEB',rx=15,sw=2):
    p.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')

def text(x,y,s,size=25,color='#182C44',bold=False):
    p.append(f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" font-weight="{700 if bold else 400}">{escape(s)}</text>')

def lines(x,y,items,size=24,color='#52647B',gap=32):
    for i,s in enumerate(items): text(x,y+i*gap,s,size,color)

def arrow(d,kind='http',both=False):
    color='#B45309' if kind=='event' else '#526B89'
    dash='stroke-dasharray="10 7"' if kind=='event' else ''
    start=f'marker-start="url(#{kind})"' if both else ''
    p.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="2.5" {dash} marker-end="url(#{kind})" {start}/>')

def wire(d):
    p.append(f'<path d="{d}" fill="none" stroke="#526B89" stroke-width="2.5"/>')

def node(x,y,w,h,key,subtitle=None):
    fill,stroke=colors[key]
    box(x,y,w,h,fill,stroke,10)
    text(x+17,y+(36 if subtitle else h/2+9),names[key],26,stroke,True)
    if subtitle: text(x+17,y+68,subtitle,22,stroke)

def mark(a,b,op='-->'):
    key=(a,b,op)
    assert key in expected, key
    assert key not in seen, ('duplicate source connection',key)
    seen.add(key)

text(60,75,'MICROSERVICES THEO DOMAIN',50,bold=True)
text(60,130,'+ EVENT-DRIVEN ORCHESTRATION',41,'#1D4ED8',True)
text(2220,73,'PORTFOLIO OPTIMIZATION',30,'#52647B',True)
text(2220,119,'Kiến trúc chi tiết • Giai đoạn 2',27,'#52647B')
text(60,184,'Ba góc nhìn của cùng một hệ thống — giữ đầy đủ các kết nối từ bản Mermaid, bố trí lại để giảm giao cắt.',27,'#52647B')

# A: seven owned domain boundaries and the asynchronous integration plane.
text(60,244,'A  DOMAIN BOUNDARIES + DATA OWNERSHIP + EVENT BUS',30,bold=True)
domains = [
 ('Chat','HỘI THOẠI',['Intent • scoped tools','Explanations • SSE'],'chat_db',['Continuation events']),
 ('Portfolio','DANH MỤC',['Profile • ledger','Allocation saga'],'portfolio_db',['Commands / result events','qua transactional outbox']),
 ('Quant','TỐI ƯU',['Forecasts • views','Black–Litterman optimization'],'quant_db',['Optimize / forecast','Ready / result events']),
 ('Market','THỊ TRƯỜNG',['Ingestion • data quality','Immutable snapshots'],'market_db',['dataset.published']),
 ('ML','MÔ HÌNH',['Training • validation','Model registry'],'ml_db',['Training commands','model.published']),
 ('Knowledge','TRI THỨC',['Documents • embeddings','RAG retrieval'],'knowledge_db + pgvector',['HTTPS retrieval; không nối MQ']),
 ('Research','THỰC NGHIỆM',['Backtest • experiments','Evaluation / thesis evidence'],'research_db',['Research commands','Completion events'])
]
for i,(key,title,body,db,events) in enumerate(domains):
    x=60+i*443
    fill,color=colors[key]
    box(x,275,422,450,'#FFFFFF',color,sw=4 if key=='Portfolio' else 2)
    text(x+20,315,title,26,color,True)
    if key=='Portfolio':
        box(x+18,331,386,35,'#1D4ED8','#1D4ED8',rx=6)
        text(x+34,356,'WORKFLOW ORCHESTRATOR',23,'#FFFFFF',True)
    else: text(x+20,356,'API / worker • deploy độc lập',22,'#52647B')
    box(x+18,389,386,111,fill,color,rx=10)
    text(x+35,425,names[key],29,color,True)
    lines(x+35,454,body,22,color,29)
    arrow(f'M {x+208} 503 V 548')
    text(x+226,534,'SQL/TLS',20,'#52647B')
    box(x+18,558,386,65,'#FEF3C7','#A16207',rx=10)
    text(x+32,599,db,24,'#854D0E',True)
    text(x+20,658,'Chỉ service sở hữu được đọc / ghi DB.',20,'#52647B')
    text(x+20,695,'API / schema / migrations có version.',20,'#52647B')
    mark(key,'DB')
    if key!='Knowledge':
        # Explicit side port belongs to API/worker, bypassing its database.
        route_x=x+411
        arrow(f'M {x+405} 454 H {route_x} V 827','event',key!='Market')
        lines(x+12,767,events,20,'#9A3412',gap=28)
        mark(key,'MQ','-->' if key=='Market' else '<-->')
    else: text(x+12,776,events[0],20,'#0F766E')

box(60,840,3080,130,'#FFF7ED','#F59E0B')
text(85,890,'RabbitMQ',37,'#9A3412',True)
text(395,890,'AMQPS · Commands & Domain Events',31,'#9A3412',True)
text(85,938,'Outbox / inbox • delivery ít nhất một lần • retry / deduplication • broker chuyển thông điệp; Portfolio giữ trạng thái và quyết định bước nghiệp vụ.',27,'#9A3412')

# B/C linked views. Repeated boxes reference the same deployed service.
box(60,1005,1520,1325)
box(1620,1005,1520,1325)
text(85,1051,'B  HTTPS — ĐIỂM VÀO & LỜI GỌI LIÊN SERVICE',27,bold=True)
text(85,1090,'Mũi tên chỉ bên khởi tạo request; response trả trên cùng kết nối.',23,'#52647B')
text(1645,1051,'C  ARTIFACTS, CACHE & NHÀ CUNG CẤP NGOÀI',27,bold=True)
text(1645,1090,'Mỗi nhánh giữ rõ service sử dụng, giao thức và mục đích.',23,'#52647B')

def fanout(x,y,source_key,targets,h):
    """One source, individually labeled outgoing calls; all source edges retained."""
    w=1470
    box(x,y,w,h,'#F8FAFC','#E2E8F0',rx=12)
    rows_y=[y+26+i*65 for i in range(len(targets))]
    middle=(rows_y[0]+rows_y[-1])/2+23
    node(x+16,middle-38,295,76,source_key)
    branch=x+337
    wire(f'M {x+311} {middle} H {branch} M {branch} {rows_y[0]+23} V {rows_y[-1]+23}')
    for yy,(target,label) in zip(rows_y,targets):
        arrow(f'M {branch} {yy+23} H {x+1120}')
        text(x+355,yy+13,label,22,'#52647B')
        node(x+1135,yy,315,47,target)
        mark(source_key,target)

fanout(85,1120,'Web',[
 ('Portfolio','HTTPS: portfolio API'),('Chat','HTTPS: REST + SSE'),
 ('Market','HTTPS: market reads'),('Research','HTTPS: backtest jobs')],295)
fanout(85,1430,'Chat',[
 ('Portfolio','HTTPS: scoped tools'),('Market','HTTPS: market facts'),
 ('Knowledge','HTTPS: retrieve citations')],230)
fanout(85,1675,'Portfolio',[
 ('Market','HTTPS: pin snapshot metadata'),('Quant','HTTPS: resolve ready model version')],165)
fanout(85,1855,'Quant',[('ML','HTTPS: model manifest')],115)
fanout(85,1985,'Research',[
 ('Market','HTTPS: pinned dataset metadata'),('ML','HTTPS: historical model manifest')],165)
lines(100,2197,[
 'Frontend = Next.js UI + server BFF. Chỉ BFF dùng Redis session.',
 'Các tên service lặp ở B/C là cùng service tại A, không phải bản deploy mới.',
 'Các API này bổ sung cho luồng bất đồng bộ, không thay thế event bus.'
],23,gap=38)

def fanin(x,y,target,callers,h,sub):
    """Individually labeled calls into a shared endpoint; no permissions inferred."""
    box(x,y,1470,h,'#F8FAFC','#E2E8F0',rx=12)
    rows_y=[y+22+i*62 for i in range(len(callers))]
    mid=(rows_y[0]+rows_y[-1])/2+24
    branch=x+1110
    wire(f'M {branch} {rows_y[0]+24} V {rows_y[-1]+24}')
    arrow(f'M {branch} {mid} H {x+1158}')
    node(x+1170,mid-49,280,98,target,sub)
    for yy,(caller,label) in zip(rows_y,callers):
        node(x+15,yy,290,48,caller)
        wire(f'M {x+310} {yy+24} H {branch}')
        text(x+335,yy+14,label,22,'#52647B')
        mark(caller,target)

fanin(1645,1120,'S3',[
 ('Market','HTTPS: dataset artifacts'),('ML','HTTPS: model artifacts'),
 ('Quant','HTTPS: scoped reads / own run writes'),
 ('Research','HTTPS: scoped reads / experiment writes'),
 ('Knowledge','HTTPS: source documents')],347,'Owner + version')
fanin(1645,1482,'Redis',[
 ('Web','RESP/TLS: session — chỉ server BFF'),
 ('Chat','RESP/TLS: SSE hints'),('Quant','RESP/TLS: derived forecast cache')],223,'Session / cache')
fanin(1645,1720,'Sources',[
 ('Market','HTTPS: source adapters'),
 ('Knowledge','HTTPS: allowlisted document ingestion')],161,'Giá / NAV / tài liệu')
fanin(1645,1896,'LLM',[
 ('Chat','HTTPS: structured intent / explanation'),
 ('Knowledge','HTTPS: embedding batches')],161,'Hosted provider')
lines(1660,2110,[
 'PostgreSQL: 7 owned databases đã vẽ trực tiếp trong từng domain tại A.',
 'S3: quyền đọc / ghi giới hạn theo owner và artifact manifest.',
 'Redis: cache / hints không thay thế trạng thái nghiệp vụ bền vững.',
 'Nguồn / LLM là external providers, không có quyền truy cập DB nội bộ.',
 'Identity, ingress và monitoring nằm ngoài phạm vi bản Mermaid này.'
],23,gap=38)

# Orchestration close-up, retaining the same services and broker.
text(60,2396,'D  PHÓNG TO ALLOCATION SAGA — PORTFOLIO ĐIỀU PHỐI QUA COMMAND / EVENT',29,bold=True)
rows=[
 ('01','Portfolio','Quant','COMMAND: optimize.requested','Lưu saga + input + outbox','Chạy BL / solver; lưu result + outbox'),
 ('02','Quant','Portfolio','EVENT: optimization.succeeded','Phát kết quả đã commit','Kiểm tra version / constraints; lưu recommendation'),
 ('03','Portfolio','Chat','EVENT: recommendation.ready','Phát đề xuất đã sẵn sàng','Canonical facts → LLM → kiểm tra → SSE'),
]
for i,(number,src,dst,msg,before,after) in enumerate(rows):
    y=2423+i*105
    box(60,y,3080,93)
    text(80,y+56,number,29,'#1D4ED8',True)
    node(150,y+18,330,57,src)
    text(500,y+34,before,21,'#52647B')
    arrow(f'M 490 {y+66} H 1372','event')
    text(920,y+34,msg,21,'#9A3412',True)
    node(1385,y+18,260,57,'MQ')
    arrow(f'M 1658 {y+46} H 1855','event')
    node(1870,y+18,350,57,dst)
    text(2245,y+55,after,24,'#52647B')

text(60,2785,'Quyền sở hữu DB ≠ một máy chủ riêng cho mỗi DB. Saga là state machine bền vững trong Portfolio; RabbitMQ không thay vai trò orchestrator.',25,'#52647B')
text(60,2830,'Khung = domain / ranh giới triển khai   •   Xanh dương = nghiệp vụ   •   Xanh ngọc = dữ liệu / tri thức   •   Tím = quant / ML   •   Vàng = storage   •   Cam = messaging',24,'#52647B')
text(60,2870,'37/37 kết nối gốc được đối chiếu trong A–C. Các mũi tên tại D phóng to cùng luồng, không bổ sung service hoặc thay đổi quyền sở hữu.',23,'#64748B')

assert seen==expected, {'missing':sorted(expected-seen),'extra':sorted(seen-expected)}
assert len(seen)==37, len(seen)
p.append('</svg>')
(out/'architecture-detailed-domains.svg').write_text('\n'.join(p))
(out/'architecture-detailed-connections.json').write_text(json.dumps({
    'source':'docs/ARCHITECTURE_OVERVIEW.md',
    'source_connections':len(expected),'visualized_connections':len(seen),
    'connections':[{'from':a,'to':b,'direction':op} for a,b,op in sorted(seen)]
},indent=2))
print(f'Validated {len(seen)}/{len(expected)} Mermaid connections; generated detailed SVG.')
