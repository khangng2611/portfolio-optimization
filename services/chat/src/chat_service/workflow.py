from datetime import date, datetime, timedelta
from decimal import Decimal
import re
import unicodedata
import hashlib
import os
import time
from uuid import uuid4
from zoneinfo import ZoneInfo
import httpx
from service_observability import log_event
from sqlalchemy import delete
from portfolio_contracts import aware, canonical_hash, system_hybrid_enabled, system_hybrid_managed, utcnow
from portfolio_contracts.assets import EQUITY_IDS
from .models import ToolCall, Event
from .provider import Provider, render
from .queue import Queue
from .allocation_status import previous_turn, status_question, status_text
from .tools import ALLOCATION_INPUT_ERRORS, ToolError
from .llm import Dialogue, allocation_request
from .knowledge import (
    Retrieval,
    knowledge_answer,
    previous_knowledge_topic,
    render_evidence,
    save_checkpoint,
)
from .openai_provider import redact


BLOCKED_INTENT = re.compile(
    r"bo qua .*huong dan|ignore .*instructions|system prompt|api key|bearer |tu .*chap nhan|tu .*promote"
)


UNSUPPORTED_DATA_CHANGE = re.compile(r"\b(?:xoa|ghi de) (?:du lieu|danh muc|ho so|de xuat)\b")


def normalize_intent(text):
    return "".join(
        c
        for c in unicodedata.normalize("NFKD", text.casefold().replace("đ", "d"))
        if not unicodedata.combining(c)
    )


def is_knowledge_followup(text):
    text = normalize_intent(text).strip()
    return bool(re.match(
        r"(?:(?:vay|the|con)\s+)?(?:no|cai nay|cai do|phuong phap (?:nay|do)|cach (?:nay|do))\b"
        r"|(?:con|the con) (?:nhuoc diem|uu diem|han che|rui ro|loi ich)\b", text,
    ))


def is_evidence_followup(text):
    value = normalize_intent(text)
    if BLOCKED_INTENT.search(value) or re.search(r"(?:tao|tinh|hay) (?:de xuat|phan bo)|lap phuong an|toi uu|chay (?:ew|mvo|bl)", value):
        return False
    linked = bool(re.search(r"de xuat|phan bo|ty trong|cua ro|anh huong|lien quan",value))
    if "thi truong" in value and (not linked or re.search(r"hom nay|hien tai|moi nhat", value)):
        return False
    if "ho so" in value and not linked:
        return False
    if re.search(r"la gi|nghia la|khai niem",value) and not linked:
        if not any(re.search(r"\b"+a.lower()+r"\b",value) for a in EQUITY_IDS):
            return False
    if "rui ro" in value and "ho so" not in value:
        return True
    return bool(re.search(r"\b(?:views?|du bao|tin hieu|rsi(?:\d+)?|macd|momentum|dac trung|xu huong|bien dong|drawdown|k5|confidence|q)\b", value) or ("ho so" in value and re.search(r"anh huong|lien quan|phan bo|de xuat", value)))


# Match a current SJC sell-price lookup without capturing forecasts, other products or past dates.
GOLD_QUOTE = re.compile(
    r"(?:(?:cho (?:toi|minh)|ban cho (?:toi|minh)) (?:biet |hoi |xem )?)?"
    r"(?:gia (?:ban )?(?:vang(?: mieng)?(?: sjc)?|sjc)|vang(?: sjc)?(?= .*bao nhieu))"
    r"(?: (?:hom nay|hien tai|moi nhat|bay gio|la bao nhieu|gia bao nhieu|bao nhieu|the nao|vay|a))*"
)


EQUITY_QUOTE = re.compile(
    r"(?:(?:cho (?:toi|minh)|ban cho (?:toi|minh)) (?:biet |hoi |xem )?)?"
    r"gia (?:co phieu |ma )?(" + "|".join(asset.lower() for asset in EQUITY_IDS) + r")"
    r"(?: (?:hom nay|hien tai|moi nhat|bay gio)| (?:ngay )?(?P<date>\d{1,2}/\d{1,2}/\d{4}|\d{4}-\d{2}-\d{2}))?"
    r"(?: (?:la bao nhieu|bao nhieu|the nao|vay|a))*"
)


def equity_quote_query(question):
    match = EQUITY_QUOTE.fullmatch(" ".join(normalize_intent(question).strip(" ?!.").split()))
    if not match:
        return None
    query = {"asset_id": match[1].upper()}
    if value := match["date"]:
        try:
            requested = datetime.strptime(value, "%d/%m/%Y").date() if "/" in value else date.fromisoformat(value)
        except ValueError:
            return None
        if requested > utcnow().astimezone(ZoneInfo("Asia/Ho_Chi_Minh")).date():
            return None
        query["requested_date"] = requested.isoformat()
    return query


def quote_amount(price_vnd):
    price = format(Decimal(price_vnd), ",f")
    whole, _, fraction = price.partition(".")
    amount = whole.replace(",", ".")
    if fraction.rstrip("0"):
        amount += "," + fraction.rstrip("0")
    return amount


def equity_quote_answer(facts):
    asset = facts["asset_id"]
    requested = facts.get("requested_date")
    row = next((item for item in facts["observations"] if not requested or item["observation_date"] == requested), None)
    if row is None:
        if requested:
            day = date.fromisoformat(requested)
            return f"Chưa có giá {asset} đã xác minh cho ngày {day:%d/%m/%Y}."
        return f"Chưa có dữ liệu giá đã xác minh cho {asset}."
    day = date.fromisoformat(row["observation_date"])
    amount = quote_amount(row["price_vnd"])
    latest = f"Giá {asset} ghi nhận ngày {day:%d/%m/%Y} là {amount} đồng/cổ phiếu."
    return latest if requested or row["observation_date"] == facts["local_date"] else f"Chưa xác minh được giá hôm nay. {latest}"


def gold_quote_answer(facts):
    today = date.fromisoformat(facts["local_date"])
    rows = facts["observations"]
    if not rows:
        return f"Chưa có dữ liệu giá bán vàng miếng SJC tại TP.HCM tính đến {today:%d/%m/%Y}."
    row = rows[0]
    observed = date.fromisoformat(row["observation_date"])
    amount = quote_amount(row["price_vnd"])
    prefix = "" if observed == today else f"Chưa có giá ngày {today:%d/%m/%Y}. "
    return f"{prefix}Giá bán vàng miếng SJC tại TP.HCM ngày {observed:%d/%m/%Y} là {amount} đồng/lượng. Nguồn Giavang.tv."


def description_asset(question):
    words = " ".join(normalize_intent(question).strip(" .?!").split())
    match = re.fullmatch(
        r"(?:(?:ma |co phieu )?([a-z0-9]+) la (?:ma |co phieu |cong ty )?gi"
        r"|(?:mo ta|gioi thieu|thong tin) (?:ve )?(?:ma |co phieu )?([a-z0-9]+))", words,
    )
    if match:
        asset = (match[1] or match[2]).upper()
        if asset in EQUITY_IDS:
            return asset
    return None


def allocation_definition(question):
    term = r"(?:phan bo tai san|asset allocation)"
    words = " ".join(normalize_intent(question).strip(" ?!.").split())
    return bool(re.fullmatch(
        rf"(?:{term} (?:la gi|nghia la gi)|(?:khai niem|dinh nghia|the nao la|giai thich) {term})", words
    ))


def allocation_lookup(words):
    """Resolve completed selections before broad definition and allocation shortcuts."""
    if not re.search(r"\b(?:muc tieu|phan bo|co cau|phuong an|ty trong|de xuat|target)\b", words):
        return None
    if re.search(r"^(?:hay |giup (?:toi|minh) )?(?:tao|lap|chay|cap nhat|sua|doi|xoa|luu|chap nhan)\b", words):
        return None
    if "muc tieu" in words and re.search(r"\b(?:khac gi|phan biet)\b", words) and re.search(r"nam giu|holdings", words):
        return "knowledge"
    if re.search(r"\b(?:da luu|cua (?:toi|minh)) trong ho so\b", words):
        return "profile"
    if re.search(r"\b(?:neu|gia su|quy tac|quy dinh|khai niem|dinh nghia|nghia la|co che|tai sao|vi sao|tai lieu|so voi|khac nhau|co phai|thay doi|ghi de|tao moi|hay tao)\b", words):
        return None
    completed = re.search(r"\b(?:(?:da|vua) (?:duoc )?(?:luu|chap nhan|chot|dong y)|(?:toi|minh) (?:da )?luu)\b", words)
    if "ban nhap" in words:
        return "source_choice"
    if completed and re.search(r"\b(?:de xuat|phuong an)\b", words) and "luu" in words and "chap nhan" not in words:
        return None  # A saved proposal may still be awaiting acceptance.
    if completed and not re.search(r"\b(?:chua|khong|co the|neu|se|truoc khi|sau khi|khi nao|luc nao|bao gio|thuc te|dang nam|holdings)\b", words):
        return "saved_target"
    reference = re.search(r"\b(?:nay|do|day|cua toi|cua minh|dang chon|dang xem|dang noi|lan truoc|bam dong y)\b", words)
    if reference and re.search(r"\b(?:muc tieu|phan bo|co cau|target)\b", words) and re.search(r"\b(?:gi|nao|xem lai)\b", words):
        return "source_choice"
    return None


def intent_of(request):
    if request.get("confirmation"):
        return "allocation"
    if request.get("intent") in (None, "market", "help", "explain", "knowledge") and description_asset(request["content"]):
        return "asset_description"
    if request.get("intent") in (None, "market") and GOLD_QUOTE.fullmatch(
        " ".join(normalize_intent(request["content"]).strip(" ?!.").split())
    ):
        return "gold_quote"
    if request.get("intent") in (None, "market") and equity_quote_query(request["content"]):
        return "equity_quote"
    if request.get("intent") in (None, "knowledge") and allocation_definition(request["content"]):
        return "knowledge"
    if request.get("intent"):
        return request["intent"]
    text = request["content"].casefold()
    normalized = normalize_intent(text)
    if BLOCKED_INTENT.search(normalized) or UNSUPPORTED_DATA_CHANGE.search(normalized):
        return "help"
    topic = normalized.strip(" ?!.")
    lookup = allocation_lookup(topic)
    if lookup in {"saved_target", "knowledge", "profile"}:
        return lookup
    pinned_proposal = re.search(
        r"\b(?:de xuat|phuong an|lan phan bo|khuyen nghi|recommendation) "
        r"(?:(?:minh|toi|ban) )?(?:nay|do|tren|cu|da |vua |hom truoc|lan truoc|truoc do|dang (?:chon|xem|mo)|cua (?:toi|minh))", topic,
    )
    question = "?" in text or re.search(
        r"\b(?:sao|tai sao|vi sao|the nao|ra sao|nhu nao|khong|chua|"
        r"gi|nao|ai|chu|bao nhieu|dau|chac|bao dam|anh huong|phu thuoc|khac nhau|y nghia|giai thich)\b", topic,
    )
    tries_to_create = re.search(r"\b(?:tao|lap|gui) (?:duoc )?(?:de xuat|phuong an|yeu cau)", topic)
    if pinned_proposal and not tries_to_create and (question or request.get("recommendation_id")):
        return "explain"

    # A policy or hypothetical question can mention the same asset and timeout as a live basket.
    policy = re.search(r"^(?:neu|gia su)\b|\b(?:quy tac|quy dinh|chinh sach|nguyen tac|khai niem)\b", topic)
    personal = re.search(r"\b(?:cua (?:toi|minh)|(?:danh muc|ro) (?:nay|dang chon))\b", topic)
    if policy and question and (not personal or topic.startswith(("neu ", "gia su "))):
        return "knowledge"
    if question and re.search(r"\b(?:ty trong|phan bo|ket qua) (?:vua |duoc )?(?:neu|nhac|noi|hien thi)\b", topic):
        return "previous_turn"
    if question and re.search(r"\b(?:chi hoi|hoi trong chat|neu hoi|hoi ve)\b", topic) and re.search(
        r"\b(?:tu doi|thay doi|cap nhat|tu sua|ghi de)\b", topic,
    ):
        return "knowledge"
    # Keep the past marker distinct from “lúc này” when removing diacritics.
    status_words = normalize_intent(unicodedata.normalize("NFC", text).replace("lúc nãy", "lúc trước"))
    query = status_question(status_words)
    if query:
        return query
    if lookup == "source_choice":
        return lookup
    educational_topic = re.search(
        r"\b(?:ew|mvo|bl_ml|views?|chia deu|freshness|holdings|target|backtest|"
        r"black.?litterman|turnover|covariance|hiep phuong sai|tuong quan|"
        r"truot gia|chi phi|da dang hoa|rui ro danh muc|ho so rui ro|khau vi rui ro|rang buoc|"
        r"duyet mo hinh|duyet model|model candidate|phe duyet|do moi|du lieu het han|chap nhan de xuat|"
        r"phan bo muc tieu|lenh (?:mua|ban|giao dich)|dat lenh|rui ro thi truong|da dang|tai lieu|ml|du bao|"
        r"nav|do tin cay|bien dong|trong so|ty trong muc tieu)\b", topic,
    )
    if re.search(r"la gi|nghia la|kien thuc|khai niem", topic):
        return "knowledge"
    if educational_topic and question and not personal and not re.search(
        r"\b(?:tao|lap|chay) (?:giup |cho )?(?:de xuat|phan bo|phuong an)|"
        r"^(?:xem|hien thi|tom tat|kiem tra|cho (?:toi|minh) xem) (?:ho so|danh muc)|"
        r"\b(?:chon|dung) (?:ew|mvo|bl_ml)\b", topic,
    ):
        return "knowledge"
    if re.fullmatch(
        r"(?:ml views?|views? ml|(?:phan bo muc tieu|target) va holdings|(?:du lieu )?freshness|(?:phe )?duyet mo hinh)",
        topic,
    ) or re.search(r"da dang hoa|hiep phuong sai|covariance|black.?litterman|backtest|turnover", topic):
        return "knowledge"
    if (
        "giai thich" in normalized
        or "explain" in normalized
        or re.search(r"\b(?:dang noi (?:toi|den|ve) )?de xuat nao(?: vay| the)?$", topic)
        or normalized.strip(" ?!.")
        in {"de xuat nao", "de xuat nao vay", "ban dang noi de xuat nao", "y toi la de xuat nao vay"}
        or (
            re.search(r"\b(vi sao|tai sao)\b", normalized)
            and re.search(r"phan bo|ty trong|quyet dinh|de xuat", normalized)
        )
    ):
        return "explain"
    if question and not personal and re.search(
        r"\b(?:tai lieu|ly thuyet|trong ung dung|cong thuc|co che|y nghia|khai niem|dinh nghia|"
        r"dinh gia|nguyen ly|chien luoc|phuong sai|danh doi|giao dich|sinh loi|loi suat|dong bien)\b", topic,
    ) and not allocation_request(topic):
        return "knowledge"
    if allocation_request(topic):
        return "allocation"
    if any(s in normalized for s in ("thi truong", "market")):
        return "market"
    if "ho so" in normalized:
        return "profile"
    if "danh muc" in normalized:
        return "portfolio"
    return "help"


class Worker:
    def __init__(
        self, sessions, tools, provider=None, clock=utcnow, *, query_rewriter=None
    ):
        self.sessions, self.tools, self.clock = sessions, tools, clock
        self.q, self.provider = Queue(sessions), provider or Provider()
        self.dialogue = Dialogue(sessions)
        # In-process experiment only. The adapter owns its one-second deadline.
        self.query_rewriter = query_rewriter
        self.started, self.tool_count = time.monotonic(), 0

    def has_time(self, seconds, *, reserve=7):
        # Reserve the final 3s corpus recheck and 4s owner authorization read.
        return 20 - (time.monotonic() - self.started) >= seconds + reserve

    def call(self, job, name, args):
        if time.monotonic() - self.started > 20 or self.tool_count >= 7:
            raise ToolError("TOOL_BUDGET_EXCEEDED", permanent=True)
        self.tool_count += 1
        started = time.monotonic()
        try:
            result = self.tools.call(job, name, args)
        except (httpx.HTTPError, ToolError):
            with self.sessions.begin() as s:
                s.add(
                    ToolCall(
                        job_id=job.id,
                        tool=name,
                        arguments_hash=canonical_hash(args),
                        status="FAILED",
                    )
                )
            raise
        with self.sessions.begin() as s:
            s.add(
                ToolCall(
                    job_id=job.id,
                    tool=name,
                    arguments_hash=canonical_hash(args),
                    result_hash=canonical_hash(result),
                    result_reference=result.get("id") or result.get("job_id"),
                    status="SUCCEEDED",
                )
            )
        log_event("chat.tool." + name, job_id=job.id, duration_ms=round((time.monotonic() - started) * 1000))
        return result

    def reply(
        self,
        job,
        text,
        structured,
        *,
        status="SUCCEEDED",
        events=(),
        stage="COMPLETE",
        error=None,
        use_dialogue=True,
    ):
        mid = str(uuid4())
        if (
            use_dialogue and self.dialogue.contextual
            and self.query_rewriter is None
            and not (system_hybrid_managed() and structured.get("type") in {"help", "input_required"})
            and structured.get("type")
            in {"help", "input_required", "knowledge", "profile", "portfolio", "market"}
            and self.has_time(9, reserve=1)
        ):
            # Authorization is refreshed before even a conversational model call.
            self.call(job, "get_profile", {})
            generated, response_meta = self.dialogue.respond(job, structured)
            structured["response"] = response_meta
            if generated and (
                structured.get("fields") != ["strategy"]
                or all(label in generated for label in ("EW", "MVO", "ML"))
            ):
                text = generated
        if getattr(self, "dialogue_metadata", None):
            structured["dialogue"] = self.dialogue_metadata
        if structured.get("type") == "confirmation":
            structured["confirmation_message_id"] = mid
        ending = (
            "input_required" if status == "WAITING_INPUT" else "completed",
            {"message_id": mid, "status": status},
        )
        return self.q.finish(
            job,
            status=status,
            stage=stage,
            error=error,
            message={"id": mid, "content": text, "structured": structured},
            events=[*events, ending],
            now=self.clock(),
        )

    def saved_target(self, job, portfolio_id, named_portfolio):
        prompt = {"type": "input_required", "fields": ["portfolio_id"], "pending_lookup": "saved_target"}
        if not portfolio_id:
            return self.reply(job, "Hãy chọn danh mục để xem mục tiêu phân bổ đã lưu.", prompt,
                              status="WAITING_INPUT", stage="COLLECT", use_dialogue=False)
        if re.search(r"\b(?:\d{1,4}[-/]\d{1,2}|ngay \d+|thang (?:truoc|\d+)|nam (?:ngoai|\d{4})|lan (?:dau|ap chot))\b",
                     normalize_intent(job.request["content"])):
            return self.reply(job, "Hãy mở đúng đề xuất trong lịch sử danh mục để xem phân bổ của lần đó.",
                              {"type": "input_required", "fields": ["recommendation_id"]},
                              status="WAITING_INPUT", stage="COLLECT", use_dialogue=False)
        facts = self.call(job, "get_portfolio_summary", {"portfolio_id": portfolio_id, "include_saved_target": True})
        if facts.get("scope") != "saved_target" or facts.get("id") != portfolio_id or "accepted_target" not in facts:
            raise ToolError("TOOL_UNAVAILABLE", permanent=True)
        name = facts["name"]
        if named_portfolio and named_portfolio != normalize_intent(name):
            return self.reply(job, "Hãy chọn đúng danh mục bạn vừa nhắc đến để xem mục tiêu đã lưu.", prompt,
                              status="WAITING_INPUT", stage="COLLECT", use_dialogue=False)
        target = facts["accepted_target"]
        if target is None:
            text = f"Danh mục {name} chưa có mục tiêu phân bổ đã chấp nhận."
        else:
            from .explanation import percent
            accepted = datetime.fromisoformat(target["accepted_at"]).astimezone(ZoneInfo("Asia/Ho_Chi_Minh"))
            allocation = sorted(zip(target["asset_ids"], map(Decimal, target["weights"]), strict=True),
                                key=lambda item: item[1], reverse=True)
            parts = [f"{asset} {percent(weight)}" for asset, weight in allocation if weight > 0]
            text = f"Mục tiêu phân bổ của {name} đã lưu ngày {accepted:%d/%m/%Y} gồm " + ", ".join(parts) + "."
        return self.reply(job, text, {"type": "portfolio", "facts": facts, "facts_hash": canonical_hash(facts)},
                          use_dialogue=False)

    def read_status(self, job):
        pid = job.request.get("portfolio_id")
        try:
            facts = self.call(job, "get_allocation_status", {})
            if facts.get("portfolio_id") != pid or facts.get("status") not in {"READY", "BLOCKED", "UNKNOWN"}:
                raise ValueError("Invalid readiness scope")
            if facts.get("scope") not in {"portfolio", "system"} or datetime.fromisoformat(facts["checked_at"]).tzinfo is None:
                raise ValueError("Invalid readiness metadata")
            if (facts["status"] == "READY") != (facts.get("reason_code") == "READY"):
                raise ValueError("Inconsistent readiness")
            if system_hybrid_managed() and not system_hybrid_enabled() and facts["reason_code"] != "SYSTEM_PAUSED":
                return {"type": "allocation_status", "portfolio_id": pid, "scope": "system", "status": "BLOCKED",
                        "reason_code": "SYSTEM_PAUSED", "checked_at": self.clock().isoformat(), "source": "chat_release"}
            return facts | {"type": "allocation_status", "source": "portfolio_readiness"}
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            return {"type": "allocation_status", "portfolio_id": pid, "scope": "portfolio", "status": "UNKNOWN",
                    "reason_code": "INPUT_UNAVAILABLE", "checked_at": self.clock().isoformat(), "source": "read_attempt"}

    def confirmation(self, job, p, strategy, reason="CONFIRM_INPUT"):
        inputs = {"portfolio": p, "strategy": strategy}
        return self.reply(
            job,
            "Vui lòng kiểm tra danh mục, hồ sơ rủi ro và ràng buộc trước khi tạo đề xuất."
            if strategy == "HYBRID" else
            "Vui lòng kiểm tra danh mục, hồ sơ rủi ro, chiến lược và ràng buộc trước khi tạo đề xuất.",
            {
                "type": "confirmation",
                "reason": reason,
                "input": inputs,
                "facts_hash": canonical_hash(inputs),
            },
            status="WAITING_INPUT",
            stage="CONFIRMATION",
        )

    def tick(self):
        job = self.q.claim(now=self.clock())
        if not job:
            return False
        self.started, self.tool_count = time.monotonic(), 0
        self.dialogue_metadata = None
        try:
            if aware(job.deadline) <= self.clock():
                return self.q.finish(
                    job,
                    status="FAILED",
                    error="DEADLINE_EXCEEDED",
                    events=[("failed", {"code": "DEADLINE_EXCEEDED"})],
                    now=self.clock(),
                )
            if aware(job.grant_expires_at) <= self.clock():
                raise ToolError("AUTHORIZATION_REQUIRED", permanent=True)
            if job.attempts >= job.max_attempts:
                raise ToolError("RETRY_EXHAUSTED", permanent=True)
            r = job.request
            if job.stage == "WAIT_ALLOCATION":
                status = self.call(
                    job, "get_allocation_job", {"resource_id": job.dependency_id}
                )
                if status["status"] in ("QUEUED", "RUNNING", "RETRY"):
                    return self.q.finish(
                        job,
                        status="WAITING_DEPENDENCY",
                        stage="WAIT_ALLOCATION",
                        delay=1,
                        now=self.clock(),
                    )
                if status["status"] != "SUCCEEDED" or not status.get(
                    "recommendation_id"
                ):
                    code = (status.get("error") or {}).get("code")
                    raise ToolError(code if code in ALLOCATION_INPUT_ERRORS else "ALLOCATION_FAILED", permanent=True)
                facts = self.call(
                    job,
                    "get_recommendation",
                    {"resource_id": status["recommendation_id"]},
                )
                return self.explain(job, facts)
            if job.stage == "SUBMIT":
                pin = r["confirmed_input"]
                result = self.call(
                    job,
                    "request_allocation",
                    {
                        "portfolio_id": pin["portfolio"]["id"],
                        **({"strategy": pin["strategy"]} if pin["strategy"] != "HYBRID" else {}),
                        "expected_version": pin["portfolio"]["version"],
                        "expected_policy_version": pin["portfolio"][
                            "policy_version_id"
                        ],
                    },
                )
                return self.q.finish(
                    job,
                    status="WAITING_DEPENDENCY",
                    stage="WAIT_ALLOCATION",
                    dependency_id=result["job_id"],
                    events=[
                        (
                            "stage_changed",
                            {
                                "stage": "WAIT_ALLOCATION",
                                "allocation_job_id": result["job_id"],
                            },
                        )
                    ],
                    now=self.clock(),
                )
            if not r.get("confirmation") and UNSUPPORTED_DATA_CHANGE.search(normalize_intent(r["content"])):
                return self.reply(job, "Chat chỉ hỗ trợ xem thông tin và chuẩn bị đề xuất cho danh mục của bạn.",
                                  {"type": "help"}, use_dialogue=False)
            deterministic = intent_of(r)
            named_portfolio = None
            if deterministic == "portfolio" and not r.get("intent"):
                name = re.fullmatch(r"danh muc (.+)", normalize_intent(r["content"]).strip(" ?!."))
                if name and (previous_turn(self.sessions, job) or {}).get("pending_lookup") == "saved_target":
                    deterministic, named_portfolio = "saved_target", name[1]
            profile = None
            glossary_choice = False
            # Short answers are meaningful only immediately after our source question.
            choice = normalize_intent(r["content"]).strip(" ?!.")
            choice = re.sub(r"^(?:(?:y (?:toi|minh) la|(?:toi|minh) muon|muon) )?(?:xem |tim hieu )?", "", choice)
            choices = {"ban da luu": "saved_target", "phan bo da luu": "saved_target",
                       "de xuat dang mo": "explain", "khai niem": "knowledge",
                       "khai niem phan bo tai san": "knowledge"}
            if not r.get("intent") and not r.get("confirmation") and choice in choices:
                if (previous_turn(self.sessions, job) or {}).get("fields") == ["source"]:
                    deterministic = choices[choice]
                    glossary_choice = deterministic == "knowledge"
            if deterministic == "source_choice":
                source = None
                if self.dialogue.enabled:
                    profile = self.call(job, "get_profile", {})
                    pending = (previous_turn(self.sessions, job) or {}).get("pending_lookup") == "saved_target"
                    # Leave seven seconds of the worker tool budget for the selected owner reads.
                    if self.has_time(1):
                        plan, self.dialogue_metadata = self.dialogue.allocation_source(job, pending, self.started + 20 - 7)
                    else:
                        plan, self.dialogue_metadata = None, {"reason": "TURN_BUDGET_EXHAUSTED"}
                    source = plan["source"] if plan else None
                if source not in {"saved_target", "explain", "knowledge", "market"}:
                    return self.reply(job, "Bạn muốn xem bản đã lưu, đề xuất đang mở hay tìm hiểu khái niệm phân bổ tài sản?",
                                      {"type": "input_required", "fields": ["source"]},
                                      status="WAITING_INPUT", stage="COLLECT", use_dialogue=False)
                deterministic = source
                r = r | {"intent": source}
            if deterministic == "saved_target":
                return self.saved_target(job, r.get("portfolio_id"), named_portfolio)
            readiness_checked = False
            if deterministic in ("previous_turn", "previous_status", "recheck_previous"):
                profile = self.call(job, "get_profile", {})
                prior = previous_turn(self.sessions, job)
                if prior and prior.get("type") == "allocation_status":
                    if deterministic != "recheck_previous":
                        return self.reply(job, status_text(prior, historical=True), prior)
                    deterministic = "current_status"
                elif prior and prior.get("type") == "recommendation" and deterministic == "previous_turn":
                    r = r | {"intent": "explain", "recommendation_id": prior["recommendation_id"]}
                    deterministic = "explain"
                else:
                    return self.reply(job, "Bạn muốn hỏi về lần tạo đề xuất hay một đề xuất đã lưu?",
                                      {"type": "input_required", "fields": ["reference"]}, use_dialogue=False)
            if deterministic == "current_status" or (deterministic == "allocation" and system_hybrid_managed()):
                facts = self.read_status(job)
                readiness_checked = True
                if deterministic == "current_status" or facts["status"] != "READY":
                    return self.reply(job, status_text(facts), facts)
            if deterministic == "asset_description":
                asset = description_asset(r["content"])
                self.call(job, "get_profile", {})
                facts = self.call(job, "get_market_facts", {"asset_id": asset, "description": True})
                if facts.get("scope") != "asset_description" or facts.get("asset_id") != asset:
                    raise ToolError("TOOL_UNAVAILABLE", permanent=True)
                name = facts.get("display_name")
                text = f"{asset} là mã cổ phiếu của {name}." if name and name != asset else f"{asset} là mã cổ phiếu trong danh mục tài sản."
                text += " " + (facts.get("description") or "Danh mục chưa có mô tả doanh nghiệp cho mã này.")
                return self.reply(job, text, {"type": "market", "facts": facts, "facts_hash": canonical_hash(facts)}, use_dialogue=False)
            if deterministic in ("gold_quote", "equity_quote"):
                self.call(job, "get_profile", {})
                query = {"asset_id": "GOLD"} if deterministic == "gold_quote" else equity_quote_query(r["content"])
                asset = query["asset_id"]
                facts = self.call(job, "get_market_facts", query)
                if (facts.get("scope") != deterministic or any(row.get("asset_id") != asset for row in facts.get("observations", []))
                    or (deterministic == "equity_quote" and (facts.get("asset_id") != asset or facts.get("requested_date") != query.get("requested_date")))):
                    raise ToolError("TOOL_UNAVAILABLE", permanent=True)
                return self.reply(
                    job, gold_quote_answer(facts) if deterministic == "gold_quote" else equity_quote_answer(facts),
                    {"type": "market", "facts": facts, "facts_hash": canonical_hash(facts)},
                    use_dialogue=False,
                )
            from .explanation import method_requested

            focused = self.saved_asset_reply(job, r, deterministic)
            if focused is not None:
                return focused
            linked_method_question = method_requested(r["content"]) and (
                deterministic != "knowledge"
                or re.search(r"(?:de xuat|phan bo|danh muc) (?:nay|do|vua roi)", normalize_intent(r["content"]))
            )
            question_text = normalize_intent(r["content"])
            named_metric = (
                bool(set(EQUITY_IDS) & set(re.findall(r"\b\w+\b", question_text.upper())))
                and bool(re.search(r"\b(?:du bao|views?|tin hieu|rsi|macd|momentum)\b", question_text))
                and not re.search(r"\b(?:hom nay|ngay mai|hien tai|bao dam)\b", question_text)
            )
            if (not r.get("intent") and not r.get("confirmation")
                and not BLOCKED_INTENT.search(normalize_intent(r["content"]))
                and (((deterministic != "knowledge" or named_metric) and is_evidence_followup(r["content"])) or linked_method_question
                     or (r.get("recommendation_id") and is_evidence_followup(r["content"])))
                and (r.get("recommendation_id") or self.dialogue.recommendation_reference(job))):
                deterministic = "explain"
            if deterministic == "explain" and not r.get("confirmation"):
                r = r | {"intent": "explain"}
            topic = None
            if (
                (
                    deterministic == "knowledge"
                    or (deterministic == "help" and not r.get("intent"))
                )
                and is_knowledge_followup(r["content"])
                and not BLOCKED_INTENT.search(normalize_intent(r["content"]))
            ):
                topic = previous_knowledge_topic(self.sessions, job)
            if (
                profile is None and self.dialogue.enabled
                and not r.get("intent")
                and not r.get("confirmation")
                and self.dialogue.context(job)[0] is not None
            ):
                # Validate current account/role/grant at its owner before sending
                # even bounded prior conversation context to an external model.
                profile = self.call(job, "get_profile", {})
            if deterministic == "knowledge" or topic:
                r = r | {"intent": "knowledge"}
            elif not r.get("intent") and deterministic != "explain" and not readiness_checked:
                r, self.dialogue_metadata = self.dialogue.interpret(job)
            intent = intent_of(r)
            if intent == "saved_target":
                return self.saved_target(job, r.get("portfolio_id"), None)
            if intent == "knowledge":
                if profile is None:
                    self.call(job, "get_profile", {})
                evidence = self.knowledge(job, previous_topic=topic, glossary_choice=glossary_choice)
                return self.reply(
                    job,
                    knowledge_answer(evidence),
                    {"type": "knowledge", "knowledge": evidence},
                    use_dialogue=False,
                )
            if intent in ("help", "clarify", "unsupported"):
                return self.reply(
                    job,
                    "Bạn muốn xem hồ sơ, tóm tắt danh mục, dữ liệu thị trường, tạo đề xuất hay giải thích đề xuất? Tôi không tự chấp nhận target, giao dịch hoặc thay ràng buộc.",
                    {"type": "help"},
                )
            if intent == "market":
                facts = self.call(job, "get_market_facts", {})
                return self.reply(
                    job,
                    "Facts thị trường do Market Service cung cấp, kèm nguồn và thời điểm trong thẻ dữ liệu.",
                    {
                        "type": "market",
                        "facts": facts,
                        "facts_hash": canonical_hash(facts),
                    },
                )
            if not r.get("portfolio_id"):
                return self.reply(
                    job,
                    "Chọn danh mục trước khi tiếp tục. Bạn có thể tạo danh mục và xác nhận hồ sơ trong mục Danh mục.",
                    {"type": "input_required", "fields": ["portfolio_id"]},
                    status="WAITING_INPUT",
                    stage="COLLECT",
                )
            if profile is None:
                profile = self.call(job, "get_profile", {})
            if intent == "explain":
                r = r | {
                    "recommendation_id": r.get("recommendation_id")
                    or self.dialogue.recommendation_reference(job),
                }
                if not r.get("recommendation_id"):
                    return self.reply(
                        job,
                        "Mình chưa tìm thấy đề xuất của danh mục đang chọn trong cuộc trao đổi này. Bạn muốn mở một đề xuất đã có hay chuẩn bị đề xuất mới?",
                        {"type": "input_required", "fields": ["recommendation_id"]},
                        status="WAITING_INPUT",
                        stage="COLLECT",
                    )
                return self.explain(
                    job,
                    self.call(
                        job,
                        "get_recommendation",
                        {"resource_id": r["recommendation_id"]},
                    ),
                    requested=True,
                )
            p = self.call(
                job, "get_portfolio_summary", {"portfolio_id": r["portfolio_id"]}
            )
            if intent == "profile":
                return self.reply(
                    job,
                    "Hồ sơ đã xác nhận từ Portfolio Service.",
                    {
                        "type": "profile",
                        "facts": profile,
                        "facts_hash": canonical_hash(profile),
                    },
                )
            if intent == "portfolio":
                return self.reply(
                    job,
                    "Tóm tắt danh mục từ Portfolio Service.",
                    {"type": "portfolio", "facts": p, "facts_hash": canonical_hash(p)},
                )
            if system_hybrid_managed() and not readiness_checked:
                facts = self.read_status(job)
                if facts["status"] != "READY":
                    return self.reply(job, status_text(facts), facts)
            if not p.get("risk_profile") or not p["risk_profile"].get("version_id"):
                return self.reply(
                    job,
                    "Cần xác nhận hồ sơ rủi ro trước khi tạo đề xuất qua Chat.",
                    {
                        "type": "input_required",
                        "fields": ["confirmed_risk_profile"],
                        "portfolio_id": p["id"],
                    },
                    status="WAITING_INPUT",
                    stage="COLLECT",
                )
            if not system_hybrid_managed() and not r.get("strategy") and not r.get("confirmed_input"):
                return self.reply(
                    job,
                    "Chọn chiến lược EW, MVO hoặc BL_ML; hệ thống không tự chuyển chiến lược khi có lỗi.",
                    {"type": "input_required", "fields": ["strategy"]},
                    status="WAITING_INPUT",
                    stage="COLLECT",
                )
            if not r.get("confirmation"):
                return self.confirmation(job, p, "HYBRID" if system_hybrid_managed() else r["strategy"])
            pin = r["confirmed_input"]
            if system_hybrid_managed() and pin["strategy"] != "HYBRID":
                return self.confirmation(job, p, "HYBRID", "STALE_CONFIRMATION")
            if (
                canonical_hash({"portfolio": p, "strategy": pin["strategy"]})
                != r["confirmation"]["facts_hash"]
            ):
                return self.confirmation(job, p, pin["strategy"], "STALE_CONFIRMATION")
            # The dependency intent is committed before the HTTP mutation; stable job
            # identity is the downstream business key, including after a hard crash.
            return self.q.finish(
                job,
                status="QUEUED",
                stage="SUBMIT",
                events=[("stage_changed", {"stage": "TOOL_AUTHORIZED"})],
                now=self.clock(),
            )
        except ToolError as exc:
            if job.stage == "SUBMIT" and exc.code == "SYSTEM_PAUSED":
                facts = {"type": "allocation_status", "portfolio_id": job.request.get("portfolio_id"),
                         "scope": "system", "status": "BLOCKED", "reason_code": exc.code,
                         "checked_at": self.clock().isoformat(), "source": "portfolio_submit"}
                return self.reply(job, status_text(facts), facts)
            attempts = job.attempts + 1
            status = (
                "AUTHORIZATION_REQUIRED"
                if exc.code == "AUTHORIZATION_REQUIRED"
                else "FAILED"
                if exc.permanent or attempts >= job.max_attempts
                else "RETRY"
            )
            return self.q.finish(
                job,
                status=status,
                error=exc.code,
                attempts=attempts,
                delay=min(16, 2**attempts),
                events=[
                    (
                        "input_required"
                        if status == "AUTHORIZATION_REQUIRED"
                        else "failed"
                        if status == "FAILED"
                        else "stage_changed",
                        {"code": exc.code, "status": status},
                    )
                ],
                now=self.clock(),
            )
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            attempts = job.attempts + 1
            final = attempts >= job.max_attempts
            return self.q.finish(
                job,
                status="FAILED" if final else "RETRY",
                error="DEPENDENCY_UNAVAILABLE",
                attempts=attempts,
                delay=min(16, 2**attempts),
                events=[
                    (
                        "failed" if final else "stage_changed",
                        {"code": "DEPENDENCY_UNAVAILABLE"},
                    )
                ],
                now=self.clock(),
            )

    def saved_asset_reply(self, job, request, intent):
        if (intent not in {"help", "explain", "knowledge", "portfolio"}
            or request.get("intent") not in (None, "explain") or request.get("confirmation")
            or not request.get("portfolio_id")):
            return None
        words = normalize_intent(request["content"])
        if (BLOCKED_INTENT.search(words) or allocation_request(words) or is_evidence_followup(words)
            or re.search(r"\b(?:la gi|nghia la|hom nay|ngay mai|du bao|ho so|bao dam|loi nhuan|gia|nav|neu|gia su|mua|ban het|giao dich)\b", words)):
            return None
        named = set(re.findall(r"\b\w+\b", words.upper())) & {*EQUITY_IDS, "VFF", "GOLD"}
        refers = re.search(r"\b(?:(?:quy|ma|tai san|co phieu) (?:nay|do|ay)|no)\b", words)
        contextual = os.getenv("CHAT_CONTEXT_FOLLOWUPS") == "1"
        words = words.strip(" .?!")
        amount = bool(re.search(r"bao nhieu (?:tien|dong)|so tien|quy ra tien", words))
        implicit_reason = bool(re.fullmatch(r"(?:tai |vi )?sao (?:lai )?(?:cao|thap|nhieu|it)(?: (?:the|vay))?", words))
        switch_asset = bool(re.fullmatch(r"(?:the |vay )?con (?:ma )?[a-z0-9]+(?: thi sao)?", words))
        if not (named or refers or contextual and (implicit_reason or amount)):
            return None
        weight_cue = re.search(r"ty trong|chiem|bao nhieu %|phan tram|qua nhieu|qua it|danh nhieu|phan von|sao (?:lai )?chon", words)
        if not weight_cue and not (contextual and (amount or implicit_reason or switch_asset)) and (
            not self.dialogue.enabled or intent not in {"help", "explain"}
        ):
            return None
        rid = request.get("recommendation_id") or self.dialogue.recommendation_reference(job)
        if not rid:
            return None
        previous = previous_turn(self.sessions, job) or {}
        prior = (previous.get("focus") or {}) if previous.get("recommendation_id") == rid else {}
        last_asset = prior.get("asset")
        inherits_asset = refers or contextual and (implicit_reason or amount)
        allowed = named or ({last_asset} if inherits_asset and last_asset else set())
        asset = next(iter(allowed)) if len(allowed) == 1 else None
        self.call(job, "get_profile", {})
        field = "reason" if re.search(r"sao|ly do|qua nhieu|qua it", words) else "weight"
        metadata = {"reason": "CANONICAL_ROUTE"}
        named_tokens = set(re.findall(r"(?<!\w)[A-Z]{2,5}(?!\w)", request["content"]))
        unknown_ticker = bool(named_tokens - {*EQUITY_IDS, "VFF", "GOLD", "VND", "VNĐ"})
        explicit_symbols = set(re.findall(r"\bma (\w+)", words)) - {"nay", "do", "ay"}
        unknown_ticker |= any(tag.upper() not in {*EQUITY_IDS, "VFF", "GOLD"} for tag in explicit_symbols)
        if amount and not named and not refers and not re.match(
            r"^(?:(?:vay|the) )?(?:tuong ung|quy ra|so tien|la bao nhieu|bao nhieu|tinh ra)\b", words
        ):
            unknown_ticker = True
        mentions_holdings = re.search(r"nam giu|dang giu|so huu|so du|thuc te", words)
        if contextual and ((amount and unknown_ticker) or (mentions_holdings and (amount or weight_cue))):
            return self.reply(job, "Bạn muốn xem tài sản đang nắm giữ hay phân bổ mục tiêu của một mã trong đề xuất?",
                              {"type": "input_required", "fields": ["reference"]},
                              status="WAITING_INPUT", stage="COLLECT", use_dialogue=False)
        explicit_amount = amount and (last_asset or named) and re.search(r"tuong ung|muc tieu|de xuat|quy ra", words)
        if contextual and amount and not explicit_amount:
            return self.reply(job, "Bạn muốn xem số tiền theo đề xuất hay giá trị đang nắm giữ?",
                              {"type": "input_required", "fields": ["reference"]},
                              status="WAITING_INPUT", stage="COLLECT", use_dialogue=False)
        if contextual and explicit_amount:
            field = "amount"
        elif contextual and switch_asset and named and last_asset:
            field = prior.get("field", "clarify")
        elif not (contextual and weight_cue and asset):
            plan, metadata = self.dialogue.proposal_focus(job, last_asset)
            if plan and plan["field"] == "other" and not contextual:
                return None
            if plan:
                field = plan["field"]
                if asset != plan["asset"]:
                    asset = None
            elif implicit_reason and last_asset:
                field = "reason"
            elif not weight_cue:
                field = "clarify"
        self.dialogue_metadata = metadata
        if not asset or field not in {"weight", "reason", "amount"}:
            return self.reply(job, "Bạn muốn hỏi tỷ trọng hay lý do phân bổ của mã nào trong đề xuất?",
                              {"type": "input_required", "fields": ["reference"]},
                              status="WAITING_INPUT", stage="COLLECT", use_dialogue=False)
        facts = self.call(job, "get_recommendation", {"resource_id": rid})
        if facts["id"] != rid or facts["portfolio_id"] != request["portfolio_id"]:
            raise ToolError("TOOL_UNAVAILABLE", permanent=True)
        if asset not in facts["asset_ids"]:
            return self.reply(job, "Chưa tìm thấy mã này trong đề xuất của danh mục đang chọn.",
                              {"type": "input_required", "fields": ["reference"]},
                              status="WAITING_INPUT", stage="COLLECT", use_dialogue=False)
        if field == "amount" and facts.get("capital_vnd") is None:
            return self.reply(job, "Đề xuất này thiếu vốn tại thời điểm tính để quy đổi sang đồng. Bạn muốn xem tỷ trọng hay chọn đề xuất khác?",
                              {"type": "input_required", "fields": ["reference"]},
                              status="WAITING_INPUT", stage="COLLECT", use_dialogue=False)
        return self.explain(job, facts, requested=True, focus={"asset": asset, "field": field})

    def explain(self, job, facts, *, requested=False, focus=None):
        digest = canonical_hash(facts)
        evidence, claims, selected_claim_ids = None, None, None
        from .explanation import allocation_method, build_claims, default_ids, detail_requested, method_requested, render_claims, validate_plan

        question = job.request["content"]
        detail = detail_requested(question)

        try:
            candidate = self.call(job, "get_recommendation_evidence", {"resource_id": facts["id"]})
            claims = build_claims(facts, candidate)
            evidence = candidate
        except (ValueError, KeyError, TypeError, AttributeError, ToolError, httpx.HTTPError):
            # Older grants/services can still explain the canonical facts already read.
            # Final owner authorization below remains mandatory.
            pass
        knowledge = None if focus else self.knowledge(
            job, select_claims=False, strategy=facts.get("strategy")
        )
        if focus:
            from .explanation import focused_weight
            claim = focused_weight(facts, focus)
            if claims is not None:
                claims.append(claim)
            selected_claim_ids = [claim.id]
            sections, metadata = None, {"reason": "CANONICAL_FACTS"}
        elif not self.has_time(3 if evidence is not None else 8):
            sections, metadata = None, {"reason": "TURN_BUDGET_EXHAUSTED"}
        elif evidence is not None:
            plan, metadata = self.dialogue.explain_claims(
                job, digest, evidence, claims, deadline=self.started + 20 - 7
            )
            sections = None
            if plan:
                try:
                    selected_claim_ids = validate_plan(plan, facts, evidence, claims, question)
                    sections = selected_claim_ids
                except ValueError:
                    metadata = metadata | {"reason": "UNVERIFIED_OUTPUT"}
        elif self.dialogue.enabled:
            sections, metadata = self.dialogue.explain(
                job, facts, digest, self.knowledge_data
            )
        elif self.q.reserve_provider(job, now=self.clock()):
            sections, metadata = self.provider.explain(facts, digest)
        else:
            sections, metadata = None, {"reason": "PROVIDER_BUDGET_EXHAUSTED"}
        if evidence is not None:
            selected_claim_ids = selected_claim_ids or default_ids(claims, question)
            text = render_claims(claims, selected_claim_ids, concise=not detail)
            metadata = metadata | {"schema_version": "explanation-claims-v1", "prompt_version": "allocation-explanation-v2"}
        else:
            text = claim.text if focus else render(facts, sections)
        if metadata.get("knowledge_plan"):
            knowledge = render_evidence(
                self.knowledge_data,
                metadata["knowledge_plan"],
                query_hash=knowledge["query_hash"],
                metadata={k: v for k, v in metadata.items() if k != "knowledge_plan"},
            )
        if focus:
            self.call(job, "get_profile", {})
        else:
            knowledge = self.validate_knowledge(job, knowledge)
        if requested and evidence is None and not focus:
            method = "\n\n".join(p["text"] for p in knowledge["citations"])
            text = "\n\n".join(
                part
                for part in (
                    "Mình đang giải thích đề xuất này dựa trên kết quả định lượng và hồ sơ đã xác nhận.",
                    method,
                    text,
                )
                if part
            )
        if requested and method_requested(question):
            text = allocation_method(facts) + "\n\n" + text
        rid = facts["id"]
        mid = str(uuid4())
        return self.q.finish(
            job,
            status="SUCCEEDED",
            stage="COMPLETE",
            recommendation_id=rid,
            message={
                "id": mid,
                "content": text,
                "structured": {
                    "type": "recommendation",
                    "recommendation_id": rid,
                    "facts": facts,
                    "facts_hash": digest,
                    **({"explanation_evidence": evidence, "selected_claim_ids": selected_claim_ids,
                        "explanation_claims": [c.model_dump(mode="json") for c in claims],
                        "renderer_version": "allocation-explanation-v2",
                        "explanation_detail_level": "detail" if detail else "concise"} if evidence is not None else {}),
                    **({"focus": focus, "dialogue": self.dialogue_metadata,
                        "selected_claim_ids": selected_claim_ids,
                        "explanation_claims": [c.model_dump(mode="json") for c in (claims or [claim])]}
                       if focus else {"knowledge": knowledge}),
                    "explanation_status": "VERIFIED" if sections else "TEMPLATE",
                    "explanation_requested": requested,
                    "provider": metadata,
                    "schema_version": metadata.get("schema_version", "fact-plan-v1"),
                    "prompt_version": metadata.get("prompt_version", "chat-v1"),
                    "template_version": "chat-template-v2",
                },
            },
            events=[
                ("artifact_ready", {"type": "recommendation", "id": rid}),
                ("text_delta", {"text": text}),
                (
                    "completed",
                    {
                        "message_id": mid,
                        "explanation_status": "VERIFIED" if sections else "TEMPLATE",
                    },
                ),
            ],
            now=self.clock(),
        )

    def rewrite_knowledge(self, job, args, baseline, topic):
        query = args["query"]
        if (
            not baseline.corpus_id
            or not baseline.corpus_hash
            or baseline.mode != "LEXICAL"
            or "embedding" in args
            or baseline.reason != "NO_EVIDENCE"
            or BLOCKED_INTENT.search(normalize_intent(job.request["content"]))
            or (is_knowledge_followup(query) and not topic)
            or not self.has_time(4)
        ):
            return None
        try:
            question = redact(job.request["content"])
            if len(question) > 800 or re.search(
                r"\b(?:so du|so tai khoan|von cua toi|ho so cua toi|dang nam giu)\b", normalize_intent(question)
            ):
                return None
            public_topic = redact(topic) if topic else None
            if self.query_rewriter is not None:
                rewritten = self.query_rewriter(question, public_topic)
            elif self.has_time(8):
                rewritten = self.dialogue.rewrite_knowledge(job, question, public_topic)
            else:
                return None
            if not isinstance(rewritten, str):
                return None
            rewritten = rewritten.strip()
            tickers = {*EQUITY_IDS, "VFF", "GOLD"}
            added = set(re.findall(r"\w+", rewritten.upper())) - set(re.findall(r"\w+", query.upper()))
            if (
                not re.fullmatch(r"[^\W\d_][\w -]{0,159}", rewritten)
                or bool(added & tickers) or any(c.isdigit() for c in rewritten)
                or rewritten.casefold() == query.strip().casefold()
                or redact(rewritten) != rewritten
                or not self.has_time(3)
            ):
                return None
            result = self.call(
                job,
                "retrieve_knowledge",
                args | {"query": rewritten, "corpus_id": str(baseline.corpus_id)},
            )
            parsed = Retrieval.model_validate(result)
            if (
                parsed.corpus_id == baseline.corpus_id
                and parsed.corpus_hash == baseline.corpus_hash
                and parsed.retrieval_version == baseline.retrieval_version
                and parsed.mode == "LEXICAL"
                and parsed.reason == "MATCH"
                and parsed.passages
                and all(
                    p.available_at <= aware(job.created_at) for p in parsed.passages
                )
            ):
                return result | {
                    "rewritten_query_hash": hashlib.sha256(
                        rewritten.encode()
                    ).hexdigest()
                }
        except (TimeoutError, httpx.HTTPError, ValueError, ToolError):
            pass
        return None

    def knowledge(self, job, select_claims=True, *, previous_topic=None, strategy=None, glossary_choice=False):
        # Never retry a paid call or switch corpora after the first checkpoint.
        query = redact(job.request["content"])
        if strategy in ("EW", "MVO", "BL_ML"):
            query = f"{query} {strategy}"
        glossary = select_claims and (glossary_choice or allocation_definition(query))
        query_hash = hashlib.sha256(query.encode()).hexdigest()
        paid_rewrite = os.getenv("CHAT_KNOWLEDGE_REWRITE") == "1"
        clauses = os.getenv("CHAT_KNOWLEDGE_CLAUSES") == "1"
        # Only a public, previously cited title disambiguates an elliptical lexical lookup.
        lexical = f"{previous_topic} {query}" if previous_topic and self.query_rewriter is None else query
        if len(lexical) > 4000:
            lexical = query  # Preserve the complete question, including a trailing qualification.
        args = {"query": lexical, "as_of": aware(job.created_at).isoformat()}
        if glossary:
            args["query"] = "Phân bổ tài sản"
        try:
            data = job.knowledge_checkpoint
            if data is None:
                if not self.has_time(3):
                    raise ValueError("retrieval deadline budget")
                vector, embedding_meta = (
                    self.dialogue.embed_query(job, query)
                    if not glossary and self.query_rewriter is None and not paid_rewrite and self.has_time(8)
                    else (None, {"reason": "TURN_BUDGET_EXHAUSTED"})
                )
                if vector:
                    args |= {
                        "embedding": vector["embedding"],
                        "embedding_model": "text-embedding-3-small",
                        "index_version": "openai-small-1536-v1",
                    }
                data = self.call(job, "retrieve_knowledge", args)
                parsed = Retrieval.model_validate(data)
                if any(p.available_at > aware(job.created_at) for p in parsed.passages):
                    raise ValueError("cutoff mismatch")
                if (
                    (self.query_rewriter is not None or paid_rewrite)
                    and select_claims
                    and not glossary
                    and not parsed.passages
                ):
                    data = (
                        self.rewrite_knowledge(job, args, parsed, previous_topic)
                        or data
                    )
                if lexical != query and "rewritten_query_hash" not in data:
                    data = data | {"rewritten_query_hash": hashlib.sha256(lexical.encode()).hexdigest()}
                data = save_checkpoint(self.sessions, job, data)
            plan, metadata = None, None
            if glossary:
                ids = [p["chunk_id"] for p in data["passages"] if p["claim_id"] == "asset-allocation-definition"]
                plan = {"candidate_hash": canonical_hash(data), "selected_chunk_ids": ids[:1]}
                metadata = {"reason": "GLOSSARY_LOOKUP"}
            elif (
                select_claims
                and self.query_rewriter is None
                and (clauses or "rewritten_query_hash" not in data)
                and data["passages"]
                and self.has_time(8)
            ):
                plan, metadata = self.dialogue.select_knowledge(job, data, previous_topic=previous_topic if clauses else None)
            evidence = render_evidence(
                data, plan, query_hash=query_hash, metadata=metadata,
                question=(query if clauses else f"{previous_topic or ''} {query}") if select_claims else None,
            )
        except (httpx.HTTPError, ValueError, KeyError, TypeError, ToolError):
            data = {
                "corpus_id": None,
                "corpus_version": None,
                "corpus_hash": None,
                "index_version": "openai-small-1536-v1",
                "retrieval_version": "knowledge-retrieval-v1",
                "mode": "LEXICAL",
                "reason": "KNOWLEDGE_UNAVAILABLE",
                "passages": [],
            }
            evidence = render_evidence(data, None, query_hash=query_hash)
        self.knowledge_data = data
        return self.validate_knowledge(job, evidence) if select_claims else evidence

    def validate_knowledge(self, job, evidence):
        try:
            if evidence.get("corpus_id"):
                active = self.call(
                    job,
                    "retrieve_knowledge",
                    {
                        "query": redact(job.request["content"]),
                        "as_of": aware(job.created_at).isoformat(),
                        "corpus_id": evidence["corpus_id"],
                    },
                )
                if active.get("corpus_hash") != evidence.get("corpus_hash"):
                    raise ValueError("deactivated corpus")
        except (httpx.HTTPError, ValueError, ToolError, KeyError):
            data = self.knowledge_data | {
                "passages": [],
                "reason": "CORPUS_UNAVAILABLE",
            }
            evidence = render_evidence(data, None, query_hash=evidence["query_hash"])
        self.call(job, "get_profile", {})
        return evidence

    def prune_events(self):
        with self.sessions.begin() as s:
            s.execute(
                delete(Event).where(Event.created_at < self.clock() - timedelta(days=7))
            )
