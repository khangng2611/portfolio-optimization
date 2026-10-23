"""Create native editable draw.io shapes/connectors, with explicit routes."""
from pathlib import Path
import xml.etree.ElementTree as E
import re
from html import escape

OUT = Path(__file__).parent
mermaid = re.search(r'```mermaid\n(.*?)```', (OUT.parent/'ARCHITECTURE_OVERVIEW.md').read_text(), re.S).group(1)
expected={(a,b,op) for a,op,b in re.findall(r'^\s+(\w+)\s+(-->|<-->)(?:\|[^\n]+?\|)?\s*(\w+)\s*$',mermaid,re.M)}
seen=set()
mx=E.Element('mxfile',host='app.diagrams.net',agent='Architecture native XML',version='24.7.17')
palette={'Web':('#D4EDDA','#15803D'),'Chat':('#CCE5FF','#2563EB'),'Portfolio':('#CCE5FF','#1D4ED8'),'Market':('#CCFBF1','#0F766E'),'Knowledge':('#CCFBF1','#0F766E'),'Quant':('#EDE9FE','#7C3AED'),'ML':('#EDE9FE','#7C3AED'),'Research':('#EDE9FE','#7C3AED'),'MQ':('#FFEDD5','#C2410C'),'DB':('#FFF3CD','#A16207'),'S3':('#FFF3CD','#A16207'),'Redis':('#FFF3CD','#A16207'),'Sources':('#F1F5F9','#64748B'),'LLM':('#F1F5F9','#64748B')}
names={'Web':'Frontend / BFF','Chat':'Chat Service','Portfolio':'Portfolio Service','Market':'Market Data','Knowledge':'Knowledge Service','Quant':'Quant Serving','ML':'ML Platform','Research':'Research Service','MQ':'RabbitMQ','S3':'S3','Redis':'Redis','Sources':'Sources','LLM':'LLM / Embedding'}

class Page:
    def __init__(self,name,w,h):
        d=E.SubElement(mx,'diagram',id=f'page-{len(mx)}',name=name)
        g=E.SubElement(d,'mxGraphModel',dx='1500',dy='1000',grid='0',gridSize='10',guides='1',tooltips='1',connect='1',arrows='1',fold='1',page='0',pageScale='1',pageWidth=str(w),pageHeight=str(h),math='0',shadow='0')
        self.root=E.SubElement(g,'root')
        E.SubElement(self.root,'mxCell',id='0')
        E.SubElement(self.root,'mxCell',id='1',parent='0')
        self.n=1; self.geo={}; self.edges=[]
    def ident(self):
        self.n+=1; return f'c{self.n}'
    def v(self,x,y,w,h,value='',style='',parent='1',meta=None):
        id=self.ident()
        a={'id':id,'value':value,'style':style,'vertex':'1','parent':parent}
        if meta: a.update(meta)
        c=E.SubElement(self.root,'mxCell',a)
        px,py=self.geo[parent][:2] if parent in self.geo else (0,0)
        E.SubElement(c,'mxGeometry',x=str(x-px),y=str(y-py),width=str(w),height=str(h),**{'as':'geometry'})
        self.geo[id]=(x,y,w,h)
        return id
    def group(self,x,y,w,h,fill='#FFFFFF',stroke='#CBD5E1',sw=2):
        return self.v(x,y,w,h,style=f'rounded=1;arcSize=8;html=1;fillColor={fill};strokeColor={stroke};strokeWidth={sw};container=1;collapsible=0;recursiveResize=0;connectable=0;')
    def text(self,x,y,w,h,s,size=24,color='#172B43',bold=False,parent='1'):
        return self.v(x,y,w,h,escape(s),f'text;html=1;whiteSpace=wrap;align=left;verticalAlign=middle;fillColor=none;strokeColor=none;fontFamily=Helvetica;fontSize={size};fontColor={color};fontStyle={1 if bold else 0};spacing=0;connectable=0;',parent)
    def node(self,x,y,w,h,key,subtitle=None,parent='1',title=None):
        fill,color=palette[key]
        label=f'<b>{escape(title or names.get(key,key))}</b>'
        if subtitle: label+='<br><font style="font-size:21px">'+escape(subtitle).replace('\n','<br>')+'</font>'
        style=f'rounded=1;arcSize=10;html=1;whiteSpace=wrap;align=left;verticalAlign=middle;spacing=16;fillColor={fill};strokeColor={color};strokeWidth=2;fontSize=26;fontFamily=Helvetica;fontColor={color};'
        return self.v(x,y,w,h,label,style,parent,{'domainRef':key})
    def edge(self,a,b,label='',pts=(),async_=False,both=False,exit=(1,.5),entry=(0,.5)):
        id=self.ident(); color='#B45309' if async_ else '#526B89'
        style=f'edgeStyle=none;rounded=0;html=1;endArrow=block;endFill=1;endSize=9;startArrow={"block" if both else "none"};startFill=1;strokeColor={color};strokeWidth=2;dashed={1 if async_ else 0};fontColor={color};fontFamily=Helvetica;fontSize=21;labelBackgroundColor=#FFFFFF;labelBorderColor=none;exitX={exit[0]};exitY={exit[1]};entryX={entry[0]};entryY={entry[1]};exitPerimeter=1;entryPerimeter=1;jumpStyle=arc;jumpSize=8;'
        c=E.SubElement(self.root,'mxCell',id=id,value=escape(label),style=style,edge='1',parent='1',source=a,target=b)
        g=E.SubElement(c,'mxGeometry',relative='1',y='-17',**{'as':'geometry'})
        if pts:
            arr=E.SubElement(g,'Array',**{'as':'points'})
            for x,y in pts: E.SubElement(arr,'mxPoint',x=str(x),y=str(y))
        self.edges.append(id)
        return id

def mark(a,b,op='-->'):
    assert (a,b,op) in expected and (a,b,op) not in seen,(a,b,op)
    seen.add((a,b,op))

p=Page('01 - Architecture detail',3200,2900)
p.text(60,30,2300,70,'MICROSERVICES THEO DOMAIN',49,bold=True)
p.text(60,100,2500,60,'+ EVENT-DRIVEN ORCHESTRATION',39,'#1D4ED8',True)
p.text(60,170,3000,50,'Ba góc nhìn của cùng hệ thống • 37 kết nối gốc • Node và connector native, chỉnh sửa trực tiếp được trong draw.io.',27,'#52647B')
p.text(60,225,3050,45,'A  DOMAIN BOUNDARIES + DATA OWNERSHIP + EVENT BUS',29,bold=True)
domains=[('Chat','HỘI THOẠI','Intent • tools\nExplanations • SSE','chat_db','Continuation events'),('Portfolio','DANH MỤC','Profile • ledger\nAllocation saga','portfolio_db','Commands / result events\nqua transactional outbox'),('Quant','TỐI ƯU','Forecasts • views\nBlack–Litterman optimization','quant_db','Optimize / forecast\nReady / result events'),('Market','THỊ TRƯỜNG','Ingestion • data quality\nImmutable snapshots','market_db','dataset.published'),('ML','MÔ HÌNH','Training • validation\nModel registry','ml_db','Training commands\nmodel.published'),('Knowledge','TRI THỨC','Documents • embeddings\nRAG retrieval','knowledge_db + pgvector','HTTPS retrieval; không nối MQ'),('Research','THỰC NGHIỆM','Backtest • experiments\nThesis evidence','research_db','Research commands\nCompletion events')]
service_ids={}; route=[]
for i,(key,title,body,db,events) in enumerate(domains):
    x=60+i*443; color=palette[key][1]
    group=p.group(x,280,422,450,stroke=color,sw=4 if key=='Portfolio' else 2)
    p.text(x+20,300,380,40,title,26,color,True,group)
    p.text(x+20,345,380,35,'WORKFLOW ORCHESTRATOR' if key=='Portfolio' else 'API / worker • deploy độc lập',22,color,key=='Portfolio',group)
    sid=p.node(x+18,395,386,111,key,body,group); service_ids[key]=sid
    did=p.node(x+18,565,386,65,'DB',parent=group,title=db)
    p.edge(sid,did,'SQL/TLS',exit=(.5,1),entry=(.5,0))
    p.text(x+20,650,378,40,'Chỉ service sở hữu đọc / ghi DB.',20,'#52647B',parent=group)
    p.text(x+20,688,378,35,'API / schema / migrations có version.',20,'#52647B',parent=group)
    mark(key,'DB')
    if key!='Knowledge': route.append((key,x,sid))
    p.text(x+5,747,394,77,events,20,'#9A3412' if key!='Knowledge' else color)
mq=p.node(60,845,3080,130,'MQ','AMQPS • commands / events • outbox / inbox • retry / deduplication. Portfolio giữ trạng thái và quyết định bước nghiệp vụ.')
for key,x,sid in route:
    p.edge(sid,mq,pts=[(x+411,450.5),(x+411,828)],async_=True,both=key!='Market',entry=((x+411-60)/3080,0))
    mark(key,'MQ','-->' if key=='Market' else '<-->')

bgroup=p.group(60,1005,1520,1325)
cgroup=p.group(1620,1005,1520,1325)
p.text(85,1020,1460,47,'B  HTTPS — ĐIỂM VÀO & LỜI GỌI LIÊN SERVICE',27,bold=True,parent=bgroup)
p.text(85,1070,1460,35,'Mũi tên chỉ bên gọi; response trả trên cùng kết nối.',23,'#52647B',parent=bgroup)
p.text(1645,1020,1460,47,'C  ARTIFACTS, CACHE & PROVIDERS',27,bold=True,parent=cgroup)
p.text(1645,1070,1460,35,'Tách từng cụm kết nối để nhãn không chồng lên service.',23,'#52647B',parent=cgroup)

def fanout(x,y,key,targets,h,parent):
    group=p.group(x,y,1470,h,'#F8FAFC','#E2E8F0')
    yy=[y+26+i*65 for i in range(len(targets))]
    mid=(yy[0]+yy[-1])/2+23
    sid=p.node(x+16,mid-38,295,76,key,parent=group)
    for row,(dst,label) in zip(yy,targets):
        tid=p.node(x+1135,row,315,47,dst,parent=group)
        p.edge(sid,tid,label,[(x+337,mid),(x+337,row+23.5)])
        mark(key,dst)

fanout(85,1120,'Web',[('Portfolio','HTTPS: portfolio API'),('Chat','HTTPS: REST + SSE'),('Market','HTTPS: market reads'),('Research','HTTPS: backtest jobs')],295,bgroup)
fanout(85,1430,'Chat',[('Portfolio','HTTPS: scoped tools'),('Market','HTTPS: facts'),('Knowledge','HTTPS: retrieve citations')],230,bgroup)
fanout(85,1675,'Portfolio',[('Market','HTTPS: pin snapshot metadata'),('Quant','HTTPS: resolve ready model version')],165,bgroup)
fanout(85,1855,'Quant',[('ML','HTTPS: model manifest')],115,bgroup)
fanout(85,1985,'Research',[('Market','HTTPS: pinned dataset metadata'),('ML','HTTPS: historical model manifest')],165,bgroup)
p.text(100,2180,1440,118,'Frontend = Next.js UI + server BFF. Chỉ BFF truy cập Redis session.\nService lặp ở B/C là cùng service tại A, không phải deployment mới.\nCác API bổ sung cho workflow bất đồng bộ qua RabbitMQ.',23,'#52647B',parent=bgroup)

def fanin(x,y,key,callers,h,sub):
    group=p.group(x,y,1470,h,'#F8FAFC','#E2E8F0')
    yy=[y+22+i*62 for i in range(len(callers))]
    mid=(yy[0]+yy[-1])/2+24
    tid=p.node(x+1170,mid-49,280,98,key,sub,parent=group)
    for row,(src,label) in zip(yy,callers):
        sid=p.node(x+15,row,290,48,src,parent=group)
        p.edge(sid,tid,label,[(x+1110,row+24),(x+1110,mid)])
        mark(src,key)

fanin(1645,1120,'S3',[('Market','HTTPS: dataset artifacts'),('ML','HTTPS: model artifacts'),('Quant','HTTPS: scoped reads / own run writes'),('Research','HTTPS: scoped reads / experiment writes'),('Knowledge','HTTPS: source documents')],347,'Owner + version')
fanin(1645,1482,'Redis',[('Web','RESP/TLS: session — chỉ BFF'),('Chat','RESP/TLS: SSE hints'),('Quant','RESP/TLS: derived forecast cache')],223,'Session / cache')
fanin(1645,1720,'Sources',[('Market','HTTPS: source adapters'),('Knowledge','HTTPS: allowlisted document ingestion')],161,'Giá / NAV / tài liệu')
fanin(1645,1896,'LLM',[('Chat','HTTPS: structured intent / explanation'),('Knowledge','HTTPS: embedding batches')],161,'Hosted provider')
p.text(1660,2095,1440,197,'PostgreSQL: mỗi domain sở hữu database riêng, đã vẽ tại A.\nS3: quyền truy cập theo owner và artifact manifest.\nRedis cache / hints không thay thế trạng thái bền vững.\nNguồn và LLM không truy cập trực tiếp database nội bộ.\nIdentity, ingress, monitoring nằm ngoài phạm vi sơ đồ này.',23,'#52647B',parent=cgroup)

def saga(page,start):
    for i,(src,dst,event,a,b) in enumerate([
        ('Portfolio','Quant','COMMAND: optimize.requested','Lưu saga + input + outbox','Chạy BL / solver; lưu result + outbox'),
        ('Quant','Portfolio','EVENT: optimization.succeeded','Phát kết quả đã commit','Kiểm tra version / constraints; lưu recommendation'),
        ('Portfolio','Chat','EVENT: recommendation.ready','Phát đề xuất READY','Canonical facts → LLM → kiểm tra → SSE')]):
        y=start+i*130
        frame=page.group(60,y,3080,115)
        page.text(80,y+25,60,55,f'{i+1:02}',29,'#1D4ED8',True,frame)
        left=page.node(155,y+30,390,60,src,parent=frame)
        broker=page.node(1400,y+30,280,60,'MQ',parent=frame)
        right=page.node(1940,y+30,390,60,dst,parent=frame)
        page.edge(left,broker,event,async_=True)
        page.edge(broker,right,'AMQPS',async_=True)
        page.text(575,y+78,760,30,a,19,'#52647B',parent=frame)
        page.text(2360,y+20,740,85,b,24,'#52647B',parent=frame)

p.text(60,2360,3060,50,'D  PHÓNG TO ALLOCATION SAGA — PORTFOLIO ĐIỀU PHỐI, RABBITMQ CHUYỂN THÔNG ĐIỆP',29,bold=True)
saga(p,2425)
p.text(60,2820,3050,60,'Đủ 37/37 kết nối gốc tại A–C. Các cạnh tại D phóng to cùng workflow. Mỗi shape, nhãn và connector đều chỉnh sửa được.',24,'#52647B')

assert seen==expected,(expected-seen,seen-expected)
assert len(seen)==37
# A second, presentation-friendly page isolates orchestration without crossing lines.
q=Page('02 - Allocation orchestration',3200,1050)
q.text(60,40,3000,70,'EVENT-DRIVEN ORCHESTRATION — ALLOCATION SAGA',43,bold=True)
q.text(60,120,3000,60,'Các input đã xác nhận. Workflow bắt đầu tại Portfolio; mọi bước có trạng thái lưu bền vững.',29,'#52647B')
saga(q,235)
for x,key,heading,body in [(60,'Portfolio','ORCHESTRATOR','Sở hữu state machine, kiểm tra kết quả và quyết định bước tiếp theo.'),(1120,'MQ','BROKER','Chuyển command/event; hỗ trợ delivery, retry và deduplication.'),(2180,'Quant','EXECUTORS: QUANT / CHAT','Thực thi tác vụ; ghi kết quả và phát event qua outbox.')]:
    group=q.group(x,695,960,195,palette[key][0],palette[key][1])
    q.text(x+25,718,910,50,heading,29,palette[key][1],True,group)
    q.text(x+25,780,900,87,body,28,'#52647B',parent=group)
q.text(60,936,3020,60,'Luồng accept target / PAPER execution là hành động riêng; recommendation READY chưa phải giao dịch đã thực hiện.',26,'#52647B')

path=OUT/'architecture-editable.drawio'
E.indent(mx,space='  ')
E.ElementTree(mx).write(path,encoding='utf-8',xml_declaration=True)
# Referential integrity and native-object assertions.
for diagram in mx:
    cells=diagram.findall('./mxGraphModel/root/mxCell')
    ids={c.attrib['id'] for c in cells}
    assert len(ids)==len(cells)
    for c in cells:
        for field in ['parent','source','target']:
            if field in c.attrib: assert c.attrib[field] in ids
    assert not any('image=' in c.attrib.get('style','') for c in cells)
print(f'{path}: 2 pages, 37/37 source relationships; all nodes/edges native; XML references validated.')
