"""Real Knowledge runtime grants and exact pgvector arithmetic; no business result writes."""

from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
COMMAND = [
    "docker",
    "compose",
    "--env-file",
    str(ROOT / "infra/local/.generated/.env"),
    "-f",
    str(ROOT / "infra/local/compose.yaml"),
]


def verify():
    code = """
from knowledge_service.runtime import sessions_from_env
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
engine=sessions_from_env().kw['bind']
with engine.connect() as db:
    assert db.scalar(text('SELECT current_user'))=='knowledge_runtime'
    assert db.scalar(text("SELECT extversion FROM pg_extension WHERE extname='vector'"))=='0.8.1'
    assert db.scalar(text("SELECT 1-('[1,0]'::vector <=> '[1,0]'::vector)"))==1
    assert db.scalar(text("SELECT 1-('[1,0]'::vector <=> '[0,1]'::vector)"))==0
for query in ('CREATE TABLE public.forbidden_knowledge_probe(id integer)', 'SET ROLE knowledge_owner', "UPDATE document_version SET visibility='PRIVATE' WHERE false", 'DELETE FROM lifecycle_audit WHERE false', 'DELETE FROM document_chunk WHERE false'):
    with engine.connect() as db:
        try:db.execute(text(query))
        except DBAPIError as e:assert getattr(e.orig,'sqlstate',None)=='42501'
        else:raise AssertionError('runtime permission allowed')
print('PASS: Knowledge runtime DDL/owner/immutable-row denial; pgvector exact cosine')
"""
    r = subprocess.run(
        COMMAND + ["exec", "-T", "knowledge-api", "python", "-"],
        input=code,
        text=True,
        capture_output=True,
        timeout=25,
    )
    if r.returncode:
        raise SystemExit("FAIL: Knowledge boundary check (raw DB output suppressed)")
    print(r.stdout.strip())


if __name__ == "__main__":
    verify()
