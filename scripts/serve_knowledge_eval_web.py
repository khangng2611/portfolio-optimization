"""Serve the normal Web/BFF on loopback with the provider-off RAG owner stack."""

import argparse
import json
import os
from pathlib import Path
import signal
from threading import Event
from time import monotonic

import httpx

from accept_knowledge_paid import save_receipt
from eval_knowledge_openai import CORPUS, ROOT, index_candidate
from knowledge_eval_stack import base, docker, owner_stack, wait_ready


def serve(source_root, image, metadata):
    if ROOT / "output" not in metadata.resolve().parents:
        raise ValueError("Select an ignored output path for the QA receipt")
    stop_file = metadata.with_suffix(".stop")
    if stop_file.exists():
        raise ValueError("Select a fresh QA receipt path")
    docker("image", "inspect", "--format", "{{.Id}}", image)
    metadata.parent.mkdir(parents=True, exist_ok=True)
    with metadata.open("x") as receipt:
        os.fchmod(receipt.fileno(), 0o600)
        json.dump({"status": "STARTING"}, receipt)
    stop = Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    with owner_stack(
        paid=False, approval="", cap=0, limit=0, semantic=True, source_root=source_root
    ) as (_, knowledge, worker):
        corpus = index_candidate(knowledge, source_root / CORPUS.relative_to(ROOT))
        tag = worker.removesuffix("-chat-worker")
        web, redis = tag + "-web", tag + "-redis"
        config = base("web")
        (network,) = config["NetworkSettings"]["Networks"]
        env = dict(v.split("=", 1) for v in config["Config"]["Env"])
        origin = "http://127.0.0.1:3138"
        env.update(
            APP_ORIGIN=origin,
            CHAT_API_URL=f"http://{tag}-chat-api:8000",
            PORTFOLIO_API_URL=f"http://{tag}-portfolio-api:8000",
            KNOWLEDGE_API_URL=f"http://{tag}-knowledge-api:8000",
            REDIS_URL=f"redis://{redis}:6379/0",
        )
        containers = []
        try:
            containers.append(
                docker(
                    "run",
                    "-d",
                    "--name",
                    redis,
                    "--network",
                    network,
                    "--tmpfs",
                    "/data:rw,size=16m",
                    base("redis")["Image"],
                    "redis-server",
                    "--save",
                    "",
                    "--appendonly",
                    "no",
                )
            )
            containers.append(
                docker(
                    "run",
                    "-d",
                    "--name",
                    web,
                    "--network",
                    network,
                    "--publish",
                    "127.0.0.1:3138:3000",
                    *(v for key in env for v in ("--env", key)),
                    image,
                    env=env,
                )
            )
            wait_ready(lambda: httpx.get(origin + "/health/live", timeout=2).is_success)
            save_receipt(
                metadata,
                {
                    "status": "READY",
                    "origin": origin,
                    "web": web,
                    "chat_api": tag + "-chat-api",
                    "worker": worker,
                    "corpus_hash": corpus["hash"],
                },
            )
            print(f"Ready at {origin}/#chat", flush=True)
            deadline = monotonic() + 20 * 60
            while (
                monotonic() < deadline and not stop_file.exists() and not stop.wait(1)
            ):
                pass
        finally:
            for container in reversed(containers):
                docker("rm", "--force", "--volumes", container)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=ROOT)
    parser.add_argument("--image", required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    args = parser.parse_args()
    serve(args.source_root.resolve(), args.image, args.metadata)
