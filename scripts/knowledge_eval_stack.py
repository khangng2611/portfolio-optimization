"""Run the regular owner services on local Docker with separate empty PostgreSQL databases."""

import importlib.util
import json
import os
from contextlib import contextmanager
from pathlib import Path
import secrets
import subprocess
import time
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parents[1]
PROJECT = "portfolio-auth-demo"


def docker(*args, env=None, data=None):
    result = subprocess.run(
        ["docker", *args],
        input=data,
        text=True,
        capture_output=True,
        timeout=90,
        env=os.environ | (env or {}),
    )
    if result.returncode:
        # Docker arguments, migration traces and driver error details can contain credentials.
        raise RuntimeError(
            f"Docker {args[0]} failed (exit {result.returncode}); inspect the isolated service locally"
        )
    return result.stdout.strip()


def inspect(name):
    return json.loads(docker("inspect", name))[0]


def base(service):
    return inspect(f"{PROJECT}-{service}-1")


def api_url(name):
    port = inspect(name)["NetworkSettings"]["Ports"]["8000/tcp"][0]["HostPort"]
    return f"http://127.0.0.1:{port}"


def wait_ready(probe):
    for _ in range(45):
        try:
            if probe():
                return
        except (httpx.HTTPError, RuntimeError):
            pass
        time.sleep(0.5)
    raise RuntimeError("Isolated owner-service readiness timeout")


@contextmanager
def owner_stack(
    *, paid, approval, cap, limit, semantic=False, source_root=ROOT, embeddings=False, saved_portfolio=False, chat_flags=(), staged_portfolio=False
):
    known_flags = {"CHAT_CONTEXT_FOLLOWUPS", "CHAT_KNOWLEDGE_CLAUSES", "CHAT_KNOWLEDGE_REWRITE"}
    if not set(chat_flags) <= known_flags:
        raise ValueError("Unknown QA feature")
    if embeddings and not paid:
        raise ValueError(
            "Embedding diagnostic requires a scoped paid approval"
        )
    spec = importlib.util.spec_from_file_location(
        "local_bootstrap", ROOT / "infra/local/bootstrap.py"
    )
    bootstrap = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bootstrap)
    tag = "rag-qa-" + uuid4().hex[:12]
    pg = tag + "-postgres"
    (network,) = base("chat-worker")["NetworkSettings"]["Networks"]
    names = []

    def launch(name, image, *, env, args=(), cmd=(), stdin=None, one_shot=False):
        name = tag + "-" + name
        flags = ["--rm"] if one_shot else ["--detach"]
        result = docker(
            "run",
            *flags,
            "--name",
            name,
            "--network",
            network,
            *(x for key in env for x in ("--env", key)),
            *args,
            image,
            *cmd,
            env=env,
            data=stdin,
        )
        if not one_shot:
            names.append(name)
        return result

    def owner(
        service,
        package,
        *,
        extras=None,
        cmd=(),
        container=None,
        one_shot=False,
        publish=False,
    ):
        prototype = base(service)
        env = dict(pair.split("=", 1) for pair in prototype["Config"]["Env"])
        env.update(
            DATABASE_URL=url(package, "runtime"),
            PYTHONDONTWRITEBYTECODE="1",
            PYTHONPYCACHEPREFIX="/tmp/qa-pycache",
            PYTHONPATH=f"/qa/services/{package}/src:/qa/packages/contracts/src",
        )
        env.update(extras or {})
        # Only source packages and migration files are mounted. The original repository and volumes stay private.
        args = [
            "--volume",
            f"{source_root}/services/{package}:/qa/services/{package}:ro",
            "--volume",
            f"{source_root}/packages/contracts/src:/qa/packages/contracts/src:ro",
        ]
        if publish:
            args += ["--publish", "127.0.0.1::8000"]
        launch(
            container or service,
            prototype["Image"],
            env=env,
            args=args,
            cmd=cmd or prototype["Config"]["Cmd"],
            one_shot=one_shot,
        )

    def url(package, role):
        password = credentials[f"{package.upper()}_{role.upper()}_PASSWORD"]
        return (
            f"postgresql+psycopg://{package}_{role}:{password}@{pg}:5432/{package}_db"
        )

    packages = ["chat", "knowledge", "portfolio"]
    credentials = {
        f"{p.upper()}_{r}_PASSWORD": secrets.token_urlsafe(20)
        for p in packages
        for r in ["RUNTIME", "MIGRATOR"]
    }
    try:
        launch(
            "postgres",
            base("knowledge-postgres")["Image"],
            env={
                "POSTGRES_PASSWORD": secrets.token_urlsafe(20),
                "POSTGRES_INITDB_ARGS": "--auth-host=scram-sha-256",
            },
            args=["--tmpfs", "/var/lib/postgresql/data:rw,size=256m"],
        )
        wait_ready(
            lambda: "accepting connections"
            in docker("exec", pg, "pg_isready", "-U", "postgres")
        )
        sql = (
            bootstrap.make_database_sql(credentials, names=packages)
            + "\\connect knowledge_db\nCREATE EXTENSION vector;\n"
        )
        docker(
            "exec",
            "-i",
            pg,
            "psql",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            "postgres",
            "-d",
            "postgres",
            data=sql,
        )
        for package in packages:
            owner(
                package + "-api",
                package,
                container=package + "-migrate",
                one_shot=True,
                extras={"MIGRATION_DATABASE_URL": url(package, "migrator")},
                cmd=[
                    "alembic",
                    "-c",
                    f"/qa/services/{package}/alembic.ini",
                    "upgrade",
                    "head",
                ],
            )
        # Stage the owner read contract against an existing receipt. Only the normal
        # job-bound grants are issued there; the eval submits no confirmations.
        portfolio_env = {}
        if staged_portfolio:
            if saved_portfolio:
                raise ValueError("Select one Portfolio endpoint")
            config = dict(pair.split("=", 1) for pair in base("portfolio-api")["Config"]["Env"])
            portfolio_env["DATABASE_URL"] = config["DATABASE_URL"]
        owner("portfolio-api", "portfolio", extras=portfolio_env)
        owner("knowledge-api", "knowledge", publish=True)
        embedding_env = {"OPENAI_API_KEY": "", "KNOWLEDGE_PAID_APPROVAL": ""}
        if embeddings:
            key = dict(
                v.split("=", 1) for v in base("chat-worker")["Config"]["Env"]
            ).get("OPENAI_API_KEY", "")
            if not key.strip():
                raise ValueError("Scoped embedding connection is unavailable")
            embedding_env.update(
                OPENAI_API_KEY=key,
                KNOWLEDGE_PAID_APPROVAL=approval,
                KNOWLEDGE_BUDGET_USD=str(cap),
            )
        owner("knowledge-worker", "knowledge", extras=embedding_env)
        urls = {
            "PORTFOLIO_API_URL": "http://portfolio-api:8000" if saved_portfolio else f"http://{tag}-portfolio-api:8000",
            "KNOWLEDGE_API_URL": f"http://{tag}-knowledge-api:8000",
        }
        owner("chat-api", "chat", extras=urls, publish=True)
        owner(
            "chat-worker",
            "chat",
            extras=urls
            | {k: "1" if k in chat_flags else "0" for k in known_flags}
            | ({} if paid else {"OPENAI_API_KEY": ""})
            | {
                "CHAT_LLM_ENABLED": "1" if paid else "0",
                "CHAT_LLM_PROVIDER": "openai",
                "CHAT_OPENAI_MODEL": "gpt-6-luna",
                "CHAT_CONTEXTUAL_REPLIES": "0",
                "CHAT_PROVIDER_URL": "",
                "CHAT_QUERY_EMBEDDINGS_ENABLED": "1" if embeddings else "0",
                "CHAT_KNOWLEDGE_SEMANTIC_SELECTION": "1" if semantic else "0",
                "CHAT_LLM_APPROVAL_CALL_LIMIT": str(limit),
                "CHAT_LLM_DAILY_CALL_LIMIT": str(limit),
                "KNOWLEDGE_PAID_APPROVAL": approval,
                "KNOWLEDGE_BUDGET_USD": str(cap),
            },
        )
        chat, knowledge = api_url(tag + "-chat-api"), api_url(tag + "-knowledge-api")
        for endpoint in [chat, knowledge]:
            wait_ready(
                lambda: httpx.get(endpoint + "/health/ready", timeout=2).is_success
            )
        yield chat, knowledge, tag + "-chat-worker"
    finally:
        for name in reversed(names):
            docker("rm", "--force", name)
