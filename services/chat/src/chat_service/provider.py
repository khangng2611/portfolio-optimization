"""Bounded provider adapter. Only validated fact/template references can be published.

The MVP deliberately exposes a finite language to the provider. Free prose, numeric
claims and tool instructions cannot pass this schema and fall back to templates.
"""

import asyncio
import json
import os
import time
from typing import Literal
import httpx
from pydantic import Field
from portfolio_contracts import StrictModel


class ExplanationPlan(StrictModel):
    sections: list[Literal["weights", "constraints", "provenance", "risk"]] = Field(
        min_length=1, max_length=4
    )
    facts_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    input_tokens: int = Field(ge=0, le=1600)
    output_tokens: int = Field(ge=0, le=448)


class Provider:
    timeout_seconds = 5

    async def _request(self, url, payload):
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            async with client.stream(
                "POST",
                url,
                headers={
                    "Authorization": "Bearer " + os.environ.get("CHAT_PROVIDER_KEY", "")
                },
                json=payload,
            ) as response:
                response.raise_for_status()
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(body) + len(chunk) > 8192:
                        raise ValueError("response budget")
                    body.extend(chunk)
                return json.loads(body)

    async def _bounded(self, url, payload):
        return await asyncio.wait_for(
            self._request(url, payload), timeout=self.timeout_seconds
        )

    def explain(self, facts, facts_hash):
        url = os.environ.get("CHAT_PROVIDER_URL")
        if not url:
            return None, {"reason": "NOT_CONFIGURED"}
        # No PII, chat history or user prompt leaves this boundary. Budget is one
        # call/turn, <=2048 tokens, <=5s, never an autonomous tool loop.
        start = time.monotonic()
        try:
            payload = {
                "model": os.environ.get("CHAT_PROVIDER_MODEL", "configured"),
                "schema_version": "fact-plan-v1",
                "facts_hash": facts_hash,
                "facts": {
                    k: facts[k]
                    for k in (
                        "asset_ids",
                        "weights",
                        "constraints",
                        "core_version",
                        "policy_version_id",
                    )
                    if k in facts
                },
                "response_schema": ExplanationPlan.model_json_schema(),
                "max_output_tokens": 448,
            }
            if len(json.dumps(payload).encode()) > 6400:
                raise ValueError("input budget")
            plan = ExplanationPlan.model_validate(
                asyncio.run(self._bounded(url, payload))
            )
            if plan.facts_hash != facts_hash or len(set(plan.sections)) != len(
                plan.sections
            ):
                raise ValueError("grounding mismatch")
            return plan.sections, {
                "reason": "VERIFIED",
                "model": os.environ.get("CHAT_PROVIDER_MODEL", "configured"),
                "input_tokens": plan.input_tokens,
                "output_tokens": plan.output_tokens,
                "latency_ms": int((time.monotonic() - start) * 1000),
            }
        except (httpx.TimeoutException, TimeoutError):
            return None, {"reason": "TIMEOUT"}
        except httpx.HTTPError:
            return None, {"reason": "PROVIDER_UNAVAILABLE"}
        except (ValueError, KeyError, TypeError):
            return None, {"reason": "UNVERIFIED_OUTPUT"}


def render(facts, sections=None):
    # Every value comes from canonical APIs; provider output contains no text.
    parts = []
    for section in sections or ["weights", "constraints", "provenance", "risk"]:
        if section == "weights" and facts.get("asset_ids") and facts.get("weights"):
            parts.append(
                "Tỷ trọng từ kết quả định lượng: "
                + ", ".join(
                    f"{a}: {float(w) * 100:.2f}%"
                    for a, w in zip(facts["asset_ids"], facts["weights"], strict=True)
                )
                + "."
            )
        elif section == "constraints" and facts.get("constraints"):
            constraints = facts["constraints"]
            limits = []
            if "max_position_weight" in constraints:
                limits.append(
                    f"mỗi tài sản tối đa {float(constraints['max_position_weight']) * 100:.2f}%"
                )
            if constraints.get("min_defensive_weight", 0) > 0:
                limits.append(
                    f"nhóm phòng thủ tối thiểu {float(constraints['min_defensive_weight']) * 100:.2f}%"
                )
            if limits:
                parts.append(
                    "Giới hạn theo hồ sơ đã xác nhận: " + "; ".join(limits) + "."
                )
            parts.append(
                "Các ràng buộc và chiến lược được giữ nguyên theo đầu vào bạn đã xem lại."
            )
        elif section == "provenance":
            source = []
            if facts.get("as_of_date"):
                source.append("dữ liệu đến " + str(facts["as_of_date"]))
            if facts.get("core_version"):
                source.append("core " + str(facts["core_version"]))
            if source:
                parts.append(
                    "Kết quả sử dụng "
                    + ", ".join(source)
                    + ". Mã đầu vào và các phiên bản được lưu trong phần nguồn đối chiếu của đề xuất."
                )
        elif section == "risk":
            parts.append(
                "Đây là đề xuất phân bổ. Lợi nhuận thực tế không được bảo đảm; chỉ lưu target sau khi bạn xác nhận trên màn hình đề xuất."
            )
    return "\n\n".join(parts)
