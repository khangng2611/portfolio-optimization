"""Bounded OpenAI embeddings transport. Caller must durably reserve before I/O."""

import asyncio
import json
import math
import os
from decimal import Decimal, InvalidOperation
import time
import httpx

MODEL = "text-embedding-3-small"
DIMENSIONS = 1536
INDEX = "openai-small-1536-v1"
PRICE_VERSION = "2026-11-07"
PRICE_SOURCE = "https://developers.openai.com/api/docs/models/text-embedding-3-small"


def approved_budget():
    try:
        amount = Decimal(os.environ.get("KNOWLEDGE_BUDGET_USD", "0"))
        if (
            not os.environ.get("KNOWLEDGE_PAID_APPROVAL")
            or not amount.is_finite()
            or not 0 < amount <= 1
        ):
            return None
        return os.environ["KNOWLEDGE_PAID_APPROVAL"], amount
    except InvalidOperation:
        return None


class Embeddings:
    async def _request(self, text):
        async with httpx.AsyncClient(timeout=5, follow_redirects=False) as c:
            async with c.stream(
                "POST",
                "https://api.openai.com/v1/embeddings",
                headers={"Authorization": "Bearer " + os.environ["OPENAI_API_KEY"]},
                json={
                    "model": MODEL,
                    "input": text,
                    "dimensions": DIMENSIONS,
                    "encoding_format": "float",
                },
            ) as r:
                r.raise_for_status()
                body = bytearray()
                async for chunk in r.aiter_bytes():
                    if len(body) + len(chunk) > 100000:
                        raise ValueError("response budget")
                    body.extend(chunk)
                return json.loads(body)

    def embed(self, text):
        meta = {
            "model": MODEL,
            "dimensions": DIMENSIONS,
            "price_version": PRICE_VERSION,
            "reason": "BUDGET_NOT_APPROVED",
        }
        if not approved_budget():
            return None, meta
        if not text.strip() or len(text.encode()) > 8000:
            return None, meta | {"reason": "INPUT_BUDGET_EXCEEDED"}
        started = time.monotonic()
        try:
            data = asyncio.run(asyncio.wait_for(self._request(text), timeout=5))
            rows = data["data"]
            v = rows[0]["embedding"]
            usage = data["usage"]["total_tokens"]
            if (
                data["model"] != MODEL
                or len(rows) != 1
                or rows[0]["index"] != 0
                or len(v) != DIMENSIONS
                or any(type(x) not in (int, float) or not math.isfinite(x) for x in v)
                or not any(v)
                or type(usage) is not int
                or not 0 <= usage <= 8000
            ):
                raise ValueError("embedding contract")
            return {"embedding": v}, meta | {
                "reason": "VERIFIED",
                "input_tokens": usage,
                "output_tokens": 0,
                "estimated_cost_usd": str(Decimal(usage) * Decimal("0.02") / 1000000),
                "latency_ms": int((time.monotonic() - started) * 1000),
            }
        except (
            httpx.HTTPError,
            TimeoutError,
            ValueError,
            KeyError,
            TypeError,
            IndexError,
        ):
            return None, meta | {
                "reason": "EMBEDDING_UNAVAILABLE",
                "latency_ms": int((time.monotonic() - started) * 1000),
            }
