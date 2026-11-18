"""Real pgvector storage with synthetic vectors in an isolated schema; NOT provider hybrid evidence."""

import os
from pathlib import Path
import subprocess
import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.skipif(
    os.environ.get("KNOWLEDGE_POSTGRES_TEST") != "1",
    reason="Requires local Knowledge PostgreSQL storage probe",
)
def test_exact_cosine_and_scoping_precede_ranking_on_postgres():
    code = """
from uuid import uuid4
from datetime import timedelta
from sqlalchemy import create_engine,text
from sqlalchemy.orm import Session
import os
from portfolio_contracts import utcnow
from knowledge_service.models import Base,Corpus,ActiveCorpus,Document,Membership,Chunk
from knowledge_service.corpus import sha,normalize,MODEL,INDEX
from knowledge_service.retrieval import Query,retrieve
engine=create_engine(os.environ['MIGRATION_DATABASE_URL'])
schema='knowledge_probe_'+uuid4().hex
with engine.begin() as db:db.execute(text('CREATE SCHEMA '+schema))
try:
 scoped=engine.execution_options(schema_translate_map={None:schema})
 Base.metadata.create_all(scoped)
 now=utcnow();vector=[1.0]+[0.0]*1535
 with Session(scoped) as s,s.begin():
  s.execute(text('SET LOCAL search_path TO '+schema+',public'))
  corpus=Corpus(name='synthetic storage probe',body_hash='a'*64,status='READY',manifest={});s.add(corpus);s.flush()
  s.add(ActiveCorpus(id=1,corpus_id=corpus.id,epoch=0))
  for key,visibility,available,embedding,model in [('public','PUBLIC',now-timedelta(days=1),vector,MODEL),('private','PRIVATE',now-timedelta(days=1),vector,MODEL),('future','PUBLIC',now+timedelta(days=1),vector,MODEL),('weak','PUBLIC',now-timedelta(days=1),[0.0,1.0]+[0.0]*1534,MODEL),('wrong-model','PUBLIC',now-timedelta(days=1),vector,'wrong')]:
   doc=Document(document_key=key,version=1,content_hash='b'*64,metadata_hash='c'*64,title=key,visibility=visibility,available_at=available);s.add(doc);s.flush()
   s.add(Membership(corpus_id=corpus.id,document_id=doc.id))
   s.add(Chunk(document_id=doc.id,claim_id=key,text='covariance '+key,text_hash=sha('covariance '+key),search_text=normalize('covariance '+key),source_title='synthetic unit fixture',source_url='https://example.org/unit',locator='unit',embedding=embedding,embedding_model=model,index_version=INDEX))
  s.flush()
  q=Query(query='no-lexical-match',as_of=now,embedding=vector,embedding_model=MODEL)
  result=retrieve(s,q)
  assert [p['claim_id'] for p in result['passages']]==['public']
  assert 'embedding' not in str(result)
  assert retrieve(s,Query(query='zxqvnomatch',as_of=now))['passages']==[]
  lexical=retrieve(s,Query(query='covariance',as_of=now))
  assert {p['claim_id'] for p in lexical['passages']}=={'public','weak','wrong-model'}
  paraphrase=retrieve(s,Query(query='Bạn diễn giải cách dùng ma trận đồng biến được không?',as_of=now))
  assert paraphrase['retrieval_version']=='knowledge-retrieval-v2'
  assert {p['claim_id'] for p in paraphrase['passages']}=={'public','weak','wrong-model'}
  unaccented=retrieve(s,Query(query='ban dien giai cach dung ma tran dong bien duoc khong',as_of=now))
  assert unaccented['passages']==paraphrase['passages']
  assert not retrieve(s,Query(query='Giá của ma trận LED hôm nay?',as_of=now))['passages']
  assert not retrieve(s,Query(query='ma trận đồng biến dùng làm gì?',as_of=now-timedelta(days=2)))['passages']
  corpus.status='DRAFT';s.flush()
  assert retrieve(s,q)['passages']==[]
 # HTTP owner handler must keep one snapshot even when an activation commits mid-read.
 from sqlalchemy import event
 from sqlalchemy.orm import sessionmaker
 from fastapi.testclient import TestClient
 from knowledge_service.api import create_app
 from service_auth import Principal
 with engine.begin() as db:db.execute(text('UPDATE '+schema+".corpus SET status='READY'"))
 read_engine=create_engine(os.environ['MIGRATION_DATABASE_URL'],connect_args={'options':'-csearch_path='+schema+',public'})
 swapped=[]
 def swap_after_ranking(conn,cursor,statement,parameters,context,executemany):
  if 'SELECT id FROM eligible' in statement and not swapped:
   swapped.append(True)
   with engine.begin() as writer:writer.execute(text('UPDATE '+schema+'.active_corpus SET corpus_id=NULL WHERE id=1'))
 event.listen(read_engine,'after_cursor_execute',swap_after_ranking)
 class Verifier:
  def verify(self,token):return Principal('issuer','machine',frozenset(),frozenset({'knowledge:retrieve'}),'chat-service')
 with TestClient(create_app(sessions=sessionmaker(read_engine),verifier=Verifier()),raise_server_exceptions=False) as client:
  response=client.post('/internal/v1/knowledge/retrieve',json={'query':'covariance','as_of':now.isoformat()},headers={'Authorization':'Bearer unit-storage-token'})
  assert response.status_code==200, 'pointer swap broke the retrieval snapshot'
  assert len(response.json()['passages'])==3 and response.json()['corpus_hash']=='a'*64
 assert swapped
 read_engine.dispose()
 print('PASS: isolated PostgreSQL1536 exact cosine, threshold, model, PUBLIC, cutoff, draft and no-match filters')
finally:
 with engine.begin() as db:db.execute(text('DROP SCHEMA '+schema+' CASCADE'))
"""
    command = [
        "docker",
        "compose",
        "--env-file",
        str(ROOT / "infra/local/.generated/.env"),
        "-f",
        str(ROOT / "infra/local/compose.yaml"),
        "run",
        "--rm",
        "-T",
        "--no-deps",
        "knowledge-migrate",
        "python",
        "-",
    ]
    result = subprocess.run(
        command, input=code, text=True, capture_output=True, timeout=45
    )
    assert result.returncode == 0, (
        "Knowledge isolated PostgreSQL storage probe failed; no raw credentials logged"
    )
