"""Finite approved claims only; independent from quantitative facts and their hashes."""

import hashlib
import json
import re
from datetime import datetime
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID
from pydantic import Field, model_validator
from portfolio_contracts import StrictModel, canonical_hash, utcnow
from portfolio_contracts.assets import EQUITY_IDS
from sqlalchemy import update
from .allocation_status import previous_turn
from .explanation import plain
from .models import Job


class Passage(StrictModel):
    chunk_id: UUID
    document_version_id: UUID
    document_version: int = Field(ge=1)
    document_title: str = Field(min_length=1, max_length=300)
    claim_id: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=1, max_length=2000)
    text_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_title: str = Field(min_length=1, max_length=300)
    source_url: str = Field(max_length=2048)
    locator: str = Field(min_length=1, max_length=300)
    available_at: datetime
    published_at: datetime | None = None

    @model_validator(mode="after")
    def integrity(self):
        u = urlsplit(self.source_url)
        if (
            u.scheme != "https"
            or not u.hostname
            or u.username
            or u.password
            or any(ord(c) < 33 for c in self.source_url)
        ):
            raise ValueError("unsafe citation")
        if (
            hashlib.sha256(self.text.encode()).hexdigest() != self.text_hash
            or self.available_at.tzinfo is None
        ):
            raise ValueError("evidence mismatch")
        return self


class Retrieval(StrictModel):
    corpus_id: UUID | None
    corpus_version: str | None
    corpus_hash: str | None = Field(pattern=r"^[a-f0-9]{64}$")
    index_version: Literal["openai-small-1536-v1"]
    retrieval_version: Literal[
        "knowledge-retrieval-v1",
        "knowledge-retrieval-v2",
        "knowledge-retrieval-v3",
        "knowledge-retrieval-v4", "knowledge-retrieval-v5", "knowledge-retrieval-v6",
    ]
    mode: Literal["LEXICAL", "HYBRID"]
    reason: str = Field(max_length=80)
    passages: list[Passage] = Field(max_length=5)


def previous_knowledge_topic(sessions, job):
    card = previous_turn(sessions, job)
    if not card or card.get("type") != "knowledge":
        return None
    topics = {c["document_title"] for c in card["knowledge"]["citations"]}
    return next(iter(topics)) if len(topics) == 1 else None


class ClaimPlan(StrictModel):
    selected_chunk_ids: list[str] = Field(max_length=3)
    candidate_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class QuotedPassage(StrictModel):
    chunk_id: str = Field(min_length=36, max_length=36)
    quote: str = Field(min_length=12, max_length=240)


class QuotedSelection(StrictModel):
    candidate_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    coverage: Literal["SUPPORTED", "PARTIAL", "MISSING"]
    supports: list[QuotedPassage] = Field(max_length=3)


class ClauseAnswer(StrictModel):
    index: int = Field(ge=0, le=5)
    chunk_id: str | None
    quote: str | None


class ClauseSelection(StrictModel):
    candidate_hash: str
    parts: list[ClauseAnswer] = Field(min_length=1, max_length=6)


def question_parts(question):
    normalized = plain(question)
    boundaries = list(_SPLIT_QUESTIONS.finditer(normalized)) if len(normalized) == len(question) else []
    starts = [0, *(m.end() for m in boundaries)]
    ends = [*(m.start() for m in boundaries), len(question)]
    return [question[a:b].strip() for a, b in zip(starts, ends) if question[a:b].strip()]


# The searchable concepts distinguish what the question is about from what
# it asks the paragraph to establish. Both are derived from the quoted text.
_CONCEPTS = {
    "ew": r"equal weight|chia deu(?: ty trong)?|chia (?:tien|von)(?: bang nhau)?|phan bo deu",
    "mlview": r"views? ml|ml views?|views? (?:tu|do) (?:mo hinh |may hoc )?ml|bl[_ ]ml",
    "blacklitterman": r"black[\W_]+litterman",
    "covariance": r"(?:ma tran )?(?:hiep phuong sai|dong bien)",
    "diversification": r"da dang(?: hoa)?|phan tan rui ro",
    "portfoliorisk": r"(?:rui ro|bien dong|phuong sai) (?:cua )?danh muc",
    "assetrisk": r"(?:rui ro|(?:do )?bien dong) (?:cua )?(?:rieng |tung |moi )tai san",
    "freshness": r"du lieu freshness|(?:tuoi|do moi) (?:cua )?du lieu|do moi(?= nav)|tuoi(?= (?:tu ngay |nav))",
    "modelreview": r"(?:xet |phe )?duyet (?:mot )?(?:mo hinh|model)|model approval",
    "riskprofile": r"ho so(?= (?:cua )?(?:minh|toi))|ho so rui ro|khau vi rui ro|risk profile",
    "holdings": r"(?:tai san )?(?:dang |thuc su )?nam giu(?: co phieu)?|so huu (?:tai san|co phieu)",
    "target": r"(?:phan bo )?muc tieu|target",
    "order": r"lenh (?:mua ban|mua|ban)|(?:dat|khop|gui) lenh(?: (?:mua ban|giao dich))?",
    "acceptance": r"(?:chap nhan|dong y(?: voi)?) (?:mot )?(?:de xuat|phan bo|target)|luu de xuat",
    "slippage": r"truot gia|slippage",
    "inputs": r"dau vao|phu thuoc(?: vao)?",
    "uncertainty": r"chac chan dung|luon dung|luc nao sai|co the sai|sai so|du bao sai",
    "assurance": r"bao dam|dam bao|cam ket|hua hen|loi hua|chac(?: chan)?(?= (?:co lai|loi|lai|sinh loi))",
    "tradeoff": r"danh doi|trade.?off",
    "profit": r"kiem (?:duoc )?(?:tien|loi)|loi suat|loi nhuan|(?:ty suat )?sinh loi|co lai|lai tot|ket qua dau tu|sinh lai",
    "future": r"tuong lai|sau nay",
    "eliminate": r"(?:loai(?: bo)?|xoa bo|tranh)(?: duoc)? (?:het|moi|tat ca|toan bo)",
    "loss": r"mat tien|thua lo|bi lo|co the lo",
    "reviewer": r"reviewer|trach nhiem cua ai|ai co quyen|thuoc ve ai",
    "prior": r"prior|loi suat can bang",
    "confidence": r"(?:muc|diem|do) tin cay",
    "proof": r"chung minh|bang chung|xac nhan rang",
    "pinned": r"(?:da |duoc )?ghim",
    "history": r"lich su|(?:da )?luu|cu|goc",
    "change": r"thay(?= ho so)|thay doi|sua doi|lam (?:giam|tang)",
    "daybasis": r"tinh tu ngay|tu ngay (?:nav|quan sat)|theo ngay lich tu ngay|tu ngay nao",
    "expired": r"(?:da |moi )?(?:het han|qua han)",
    "weight": r"ty trong|trong so",
    "risk": r"rui ro",
    "cost": r"(?:chi )?phi(?: giao dich)?",
    "constraint": r"rang buoc|gioi han dau tu",
    "limitation": r"nhuoc diem|han che|gioi han",
}
_SUBJECTS = set(
    "ew mvo mlview blacklitterman covariance diversification portfoliorisk turnover backtest vff freshness modelreview riskprofile holdings target acceptance slippage".split()
)
_FACETS = set(_CONCEPTS) - _SUBJECTS
# Conversational framing carries no claim of its own. Preserve other residual
# terms (e.g. an unknown instrument, horizon, tax or jurisdiction) as anchors.
_FILLER = re.compile(
    r"\b(?:la gi|nghia la gi|co y nghia gi|y nghia|thuat ngu|khai niem|cho toi biet|ban co the|"
    r"giai thich|nhu the nao|the nao|tai sao(?: can)?|vi sao|duoc khong|co the tang|co the|"
    r"cang cao thi|trong he thong|he thong|redacted|quy tac|hoat dong|lam cho|"
    r"tac dong(?: den)?|anh huong(?: den)?|chuyen(?: doi)?|bien dich|sau chi phi|chac chan)\b"
)
_STOP = set(
    "la co khong gi cua thi vay no nay do ban toi ve den cho cach dung hay the va duoc sao chi luon trong lam thanh tot rang lieu da ung dung nao".split()
)
_CONCEPT_PATTERNS = {
    key: re.compile(r"\b(?:" + pattern + r")\b") for key, pattern in _CONCEPTS.items()
}
_INSTRUMENT = re.compile(
    r"\b(?:" + "|".join(EQUITY_IDS).lower() + r"|bitcoin|ether|btc|eth)\b"
)
_PERSONAL_STATE = re.compile(
    r"\b(?:danh muc|tai khoan|de xuat|ro tai san|nguon du lieu|vff|nav) (?:cua )?(?:toi|minh|em)\b|"
    r"\b(?:hom nay|hien tai|bay gio)\b.*\b(?:da|chua|het han|qua han|gia)\b"
)


def support_terms(text):
    value = plain(text)
    if re.search(r"\bml\b", value) and re.search(r"\bviews?\b|\bdu bao\b", value):
        value += " mlview"
    for term, aliases in _CONCEPT_PATTERNS.items():
        value = aliases.sub(term, value)
    return set(re.findall(r"\w+", _FILLER.sub(" ", value))) - _STOP


def _word_pairs(value):
    words = [w for w in re.findall(r"\w+", plain(value)) if w not in _STOP]
    return set(zip(words, words[1:]))


# Concrete scope constraints apply to both offline and provider-backed selection.
_UNSUPPORTED_DETAIL = re.compile(
    r"\b(?:cong thuc|thue|quyen chon|ty gia|trai phieu|yield|gamma|bitcoin|blockchain|"
    r"tac gia|phat minh|sang lap|sinh nam|thanh lap|quoc gia|mo lai luc|khi nao mo lai|"
    r"bao gio mo lai|ngay mai|thu nhap|so du|tai khoan|dia chi|top may|bao nhieu tien)\b"
)
_QUANTITY = re.compile(r"\b\d+(?:[.,]\d+)?\s*(?:%|ngay|phien|tuan|thang|nam|gio|dong)?")
_ENTITY = re.compile(
    r"\b(?:ma co phieu|co phieu|ma|quy|tai nuoc|doi voi ma|cho ma)\s+([a-z0-9_]+)"
)
_GENERAL_ENTITY = set(
    "cua da dau dinh trong trinh muc co nay nam tai thi duoc chung tac moi che mo xu do".split()
)
_SPLIT_QUESTIONS = re.compile(
    r"[?;!\n]+|,\s*con\s+|(?<=la gi)\s+va\s+|\s+(?:va|nhung)\s+(?=(?:ngay mai|khi nao|bao gio|bao nhieu|ai la|tai sao|vi sao|lieu|co (?:bao dam|chac)|loi nhuan nam|gia cua|danh muc cua toi))"
)


def knowledge_scope_allows(question, passages):
    """Whether these passages could cover the question's named entities and values."""
    value = plain(question)
    if (
        not passages
        or _PERSONAL_STATE.search(value)
        or _INSTRUMENT.search(value)
        or _UNSUPPORTED_DETAIL.search(value)
    ):
        return False
    if re.search(r"\b(?:dang|hien tai|bay gio|hom nay)\b", value) and re.search(
        r"\b(?:gia|qua han|het han|stale|duyet chua|mo lai|tam dung|san sang|du lieu cua toi)\b",
        value,
    ):
        return False
    body = plain(" ".join(p.text for p in passages))
    titles = plain(" ".join(p.document_title for p in passages))
    body_words = set(re.findall(r"\w+", body + " " + titles))
    terms = support_terms(value)
    subjects = terms & _SUBJECTS
    passage_terms = [
        support_terms(p.text) | support_terms(p.document_title) for p in passages
    ]
    if subjects and not subjects <= set.union(*passage_terms):
        return False
    if subjects and any(not subjects & words for words in passage_terms):
        return False
    if "assurance" in terms and not terms & {
        "profit",
        "future",
        "risk",
        "assetrisk",
        "portfoliorisk",
        "loss",
        "uncertainty",
    }:
        return False
    # Upper-case identifiers, explicit instruments and units are binding even
    # if an otherwise relevant paragraph discusses the same investment method.
    for tag in re.findall(r"(?<!\w)[A-Z][A-Z0-9_]{1,12}(?!\w)", question):
        if tag.lower() not in body_words and not (
            support_terms(tag) & _SUBJECTS & set.union(*passage_terms)
        ):
            return False
    for entity in _ENTITY.findall(value):
        if entity not in _GENERAL_ENTITY and entity not in body_words:
            return False
    quantities = [x.strip() for x in _QUANTITY.findall(value)]
    if any(
        not re.search(r"(?<!\w)" + re.escape(x) + r"(?!\w)", body) for x in quantities
    ):
        return False
    amount = re.search(
        r"\b(?:bao nhieu|may (?:ngay|phien|phan tram|gio)|muc nao)\b", value
    )
    if amount and not (
        re.search(r"\b(?:freshness|do moi|tuoi du lieu|nav|vff|bo dem)\b", value)
        and re.search(r"\b\d+ (?:ngay|phien)\b", body)
    ):
        return False
    return True


def _paragraph_terms(p):
    words = support_terms(p.text)
    body = plain(p.text)
    if {"proof", "profit", "future"} <= words:
        words.add("assurance")
    if {"pinned", "history", "weight"} <= words:
        words.add("change")
    if "ngay nav" in body or "ngay quan sat" in body:
        words.add("daybasis")
    if re.search(
        r"\b(?:khong|sai so|bat dinh|lam giam|uoc luong)\b", body
    ) and p.claim_id.endswith(("-limit", "-uncertainty", "-estimation", "-boundary")):
        words.add("limitation")
    return words


# These relationships must be evidenced in the paragraph itself. Remaining
# conversational wording contributes to ranking without being a pass/fail test.
_RELATIONSHIPS = {
    "tradeoff",
    "assurance",
    "uncertainty",
    "eliminate",
    "confidence",
    "proof",
    "pinned",
    "daybasis",
    "expired",
    "order",
    "constraint",
    "limitation",
    "loss",
    "reviewer",
    "prior",
}


def _assurance_parts(clause):
    """Expand a shared guarantee predicate for lists of subjects or objects."""
    norm = plain(clause)
    promise = _CONCEPT_PATTERNS["assurance"].search(norm)
    if not promise or len(norm) != len(clause):
        return [clause]
    join = re.compile(r"\s*(?:,|\bva\b|\bcung nhu\b|\bdong thoi\b)\s*")
    before = list(join.finditer(norm, 0, promise.start()))
    if before:
        starts = [0] + [m.end() for m in before]
        ends = [m.start() for m in before] + [promise.start()]
        names = [clause[a:b].strip() for a, b in zip(starts, ends)]
        if all(
            support_terms(name) & _SUBJECTS and support_terms(name) <= _SUBJECTS
            for name in names
        ):
            return [
                part
                for name in names
                for part in _assurance_parts(name + " " + clause[promise.start() :])
            ]
    after = list(join.finditer(norm, promise.end()))
    if not after:
        return [clause]
    parts = [clause[: after[0].start()]]
    prefix = clause[: promise.end()]
    for a, b in zip(
        [m.end() for m in after], [m.start() for m in after[1:]] + [len(clause)]
    ):
        part = clause[a:b]
        parts.append(
            part if "assurance" in support_terms(part) else prefix + " " + part
        )
    return parts


def supported_passages(question, passages, preferred):
    selected, missing, last_subject = [], False, set()
    evidence = [
        (
            p,
            _paragraph_terms(p),
            support_terms(p.document_title) & _SUBJECTS,
            _word_pairs(p.text),
        )
        for p in passages
    ]
    clauses = [part for clause in question_parts(question) for part in _assurance_parts(clause)]
    for clause in clauses:
        raw = plain(clause)
        terms = support_terms(raw)
        if not terms:
            continue
        subject = (terms & _SUBJECTS) or last_subject
        last_subject = subject
        required = terms & _RELATIONSHIPS
        # An order question asks about accepting the proposal and trading, even
        # when the question calls the proposed allocation a target.
        if "order" in required and "acceptance" in subject:
            subject = {"acceptance"}
        if "reviewer" in required:
            subject = subject | {"modelreview"}
        definition = (
            bool(re.search(r"\b(?:la gi|dinh nghia|khai niem|nghia la|mo ta|bieu thi|noi len|duoc hieu|dung de lam gi)\b", raw))
            or terms <= subject
        )
        pairs = _word_pairs(raw)
        eligible = []
        for p, words, topics, paragraph_pairs in evidence:
            if (
                not knowledge_scope_allows(clause, [p])
                or not subject <= words | topics
                or not required <= words
            ):
                continue
            overlap = terms & words
            facets = (terms & _FACETS) - required
            # A subject match proves neither a specific risk nor the effect on a fee.
            if facets and not facets & words:
                continue
            if not subject:
                if not (len(overlap) >= 2 and (required or pairs & paragraph_pairs)):
                    continue
            elif not (
                required
                or facets & words
                or definition
                or pairs & paragraph_pairs
                or len(overlap - subject) >= 2
            ):
                continue
            priority = (
                bool(
                    definition and not required and p.claim_id.endswith("-definition")
                ),
                len(required & words),
                len(subject & topics),
                -len((words & _SUBJECTS) - subject),
                len(facets & words),
                len(overlap - subject),
                len(pairs & paragraph_pairs),
                len(overlap),
                str(p.chunk_id) in preferred,
                -len(words & _FACETS),
            )
            eligible.append((priority, p))
        if not eligible:
            missing = True
            continue
        chosen = max(eligible, key=lambda entry: entry[0])[1]
        chosen_ids = [str(chosen.chunk_id)]
        if definition and subject == {"mlview"} and not required:
            # The operational definition describes the approved model, while the
            # companion paragraph defines a view as an uncertain return forecast.
            chosen_ids += [
                str(p.chunk_id)
                for p, words, _, _ in evidence
                if p.claim_id == "ml-views-limit" and "uncertainty" in words
            ]
        for cid in chosen_ids:
            if cid not in selected:
                if len(selected) == 3:
                    missing = True
                else:
                    selected.append(cid)
    return selected, missing


def clause_references(question, data, parsed, plan, metadata):
    selection = ClauseSelection.model_validate(plan)
    parts = question_parts(question)
    if (not parts or metadata.get("reason") != "VERIFIED" or selection.candidate_hash != canonical_hash(data)
        or [p.index for p in selection.parts] != list(range(len(parts)))):
        raise ValueError("Incomplete clause map")
    candidates = {str(p.chunk_id): p for p in parsed.passages}
    mapping, selected = [], []
    for clause, item in zip(parts, selection.parts):
        if item.chunk_id is None and item.quote is None:
            mapping.append({"question": clause, "chunk_id": None})
            continue
        ref = QuotedPassage.model_validate({"chunk_id": item.chunk_id, "quote": item.quote})
        passage = candidates.get(ref.chunk_id)
        if (not passage or ref.quote != ref.quote.strip() or ref.quote not in passage.text
            or not knowledge_scope_allows(clause, [passage])):
            raise ValueError("Unsupported clause")
        prefix = plain(passage.text[:passage.text.index(ref.quote)])
        if re.search(r"\b(?:khong|chua)(?: (?:phai|the|he|duoc))?\s*$", prefix):
            raise ValueError("Quotation omitted negation")
        requested_relations = support_terms(clause) & _RELATIONSHIPS
        if requested_relations - _paragraph_terms(passage):
            raise ValueError("Passage does not establish the requested relationship")
        if "assurance" in requested_relations:
            supported, missing = supported_passages(clause, [passage.model_copy(update={"text":ref.quote})], [ref.chunk_id])
            if not supported or missing:
                raise ValueError("Unsupported guarantee")
        mapping.append({"question":clause,"chunk_id":ref.chunk_id,"quote":ref.quote})
        if ref.chunk_id not in selected:
            selected.append(ref.chunk_id)
    if len(selected) > 3:
        raise ValueError("Citation budget exceeded")
    return mapping, selected


def knowledge_answer(evidence):
    passages = [p["text"] for p in evidence["citations"]]
    if not passages:
        return "Chưa có nguồn phù hợp trong tài liệu đã duyệt để trả lời câu hỏi này."
    if evidence.get("coverage") == "PARTIAL":
        missing = [p["question"] for p in evidence.get("clause_evidence", []) if p["chunk_id"] is None]
        passages.append("Tài liệu đã duyệt chưa đủ căn cứ cho phần “" + "”; “".join(missing) + "”."
                        if missing else "Tài liệu đã duyệt chưa đủ căn cứ để trả lời phần còn lại của câu hỏi.")
    return "\n\n".join(passages)


def render_evidence(data, plan, *, query_hash, metadata=None, question=None):
    original = {
        key: value for key, value in data.items() if key != "rewritten_query_hash"
    }
    parsed = Retrieval.model_validate(original)
    if len(json.dumps(data["passages"], ensure_ascii=False).encode()) > 8000:
        raise ValueError("context budget")
    ids = [str(p.chunk_id) for p in parsed.passages]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate chunk")
    reason = "PROVIDER_DISABLED"
    selected = ids[:3]
    status = "REFERENCE" if selected else "MISSING"
    coverage = None
    semantic = isinstance(plan, dict) and "supports" in plan
    mapping = None
    if isinstance(plan, dict) and "parts" in plan:
        try:
            mapping, selected = clause_references(question or "", data, parsed, plan, metadata or {})
            coverage = "MISSING" if not selected else "PARTIAL" if any(p["chunk_id"] is None for p in mapping) else "SUPPORTED"
            status = "VERIFIED_REFERENCES" if selected else "MISSING"
            reason = "VERIFIED_CLAUSES"
        except ValueError:
            reason = "INVALID_REFERENCES"
    elif semantic:
        try:
            selection = QuotedSelection.model_validate(plan)
            passages = {str(p.chunk_id): p for p in parsed.passages}
            chosen = [p.chunk_id for p in selection.supports]
            if (
                not question or (metadata or {}).get("reason") != "VERIFIED"
                or selection.candidate_hash != canonical_hash(data)
                or (selection.coverage == "MISSING") != (not chosen)
                or len(set(chosen)) != len(chosen)
                or any(ref.chunk_id not in passages or ref.quote.strip() != ref.quote
                       or ref.quote not in passages[ref.chunk_id].text for ref in selection.supports)
            ):
                raise ValueError("unsupported quotation")
            quoted = [passages[i] for i in chosen]
            if chosen and not knowledge_scope_allows(question, quoted):
                raise ValueError("outside public evidence")
            if chosen and "assurance" in support_terms(question):
                # A promise must be supported for that subject and object in
                # the selected quote, not elsewhere in a different paragraph.
                spans = []
                for p, ref in zip(quoted, selection.supports):
                    prefix = plain(p.text[:p.text.index(ref.quote)])
                    if re.search(r"\b(?:khong|chua)(?: (?:phai|the|he|duoc))?\s*$", prefix):
                        raise ValueError("quotation omitted negation")
                    spans.append(p.model_copy(update={"text": ref.quote}))
                covered, missing = supported_passages(question, spans, chosen)
                if set(covered) != set(chosen) or (missing and selection.coverage == "SUPPORTED"):
                    raise ValueError("no support for assurance")
            selected, coverage = chosen, selection.coverage
            status = "VERIFIED_REFERENCES" if chosen else "MISSING"
            reason = "VERIFIED_QUOTES"
        except ValueError:
            reason = "INVALID_REFERENCES"
    elif plan is not None:
        try:
            p = ClaimPlan.model_validate(plan)
            if (
                p.candidate_hash != canonical_hash(data)
                or len(set(p.selected_chunk_ids)) != len(p.selected_chunk_ids)
                or not set(p.selected_chunk_ids) <= set(ids)
            ):
                raise ValueError("references")
            selected = p.selected_chunk_ids
            status = "VERIFIED_REFERENCES" if selected else "MISSING"
            reason = "VALID_REFERENCES"
        except ValueError:
            reason = "INVALID_REFERENCES"
    if reason == "VALID_REFERENCES" and (metadata or {}).get("reason") == "GLOSSARY_LOOKUP":
        coverage = "SUPPORTED" if selected else "MISSING"
    if question is not None and coverage is None:
        # A validated empty selection is an explicit abstention.
        passages = parsed.passages if selected else []
        preferred = selected
        selected, missing = supported_passages(question, passages, preferred)
        if not selected:
            status = "MISSING"
        elif status == "VERIFIED_REFERENCES" and not set(selected) <= set(preferred):
            status = "REFERENCE"
        coverage = "MISSING" if not selected else "PARTIAL" if missing else "SUPPORTED"
    result = {
        k: data[k]
        for k in (
            "corpus_id",
            "corpus_version",
            "corpus_hash",
            "index_version",
            "retrieval_version",
            "mode",
        )
    }
    result.update(
        status=status,
        reason=data["reason"],
        selection_reason=reason,
        query_hash=query_hash,
        schema_version="knowledge-claims-v1",
        prompt_version="knowledge-quotes-v1" if semantic else "knowledge-selection-v1",
        retrieved_chunk_ids=ids,
        selected_chunk_ids=selected,
        citations=[
            p.model_dump(mode="json")
            for p in parsed.passages
            if str(p.chunk_id) in selected
        ],
        provider=metadata or {"reason": "NOT_CONFIGURED"},
    )
    if "rewritten_query_hash" in data:
        result["rewritten_query_hash"] = data["rewritten_query_hash"]
    if coverage is not None:
        result["coverage"] = coverage
        result["selection_version"] = "verified-quotes-v1" if reason == "VERIFIED_QUOTES" else "vietnamese-claim-intents-v3"
    if mapping is not None:
        result.update(clause_evidence=mapping, selection_version="clauses-v1", prompt_version="knowledge-clauses-v1")
    result["evidence_hash"] = canonical_hash(result)
    return result


def save_checkpoint(sessions, job, data):
    now = utcnow()
    with sessions.begin() as s:
        result = s.execute(
            update(Job)
            .where(
                Job.id == job.id,
                Job.status == "RUNNING",
                Job.lease_token == job.lease_token,
                Job.lease_until > now,
                Job.knowledge_checkpoint.is_(None),
            )
            .values(knowledge_checkpoint=data)
        )
        if result.rowcount == 1:
            return data
        return s.get(Job, job.id).knowledge_checkpoint
