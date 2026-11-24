"""Read-only status replies and the previous turn to which a short question refers."""
import re
from sqlalchemy import select
from portfolio_contracts import aware
from .models import Conversation, Event, Job, Message


PAUSED_TEXT = "Tính năng tạo đề xuất mới đang tạm dừng. Bạn vẫn có thể xem các đề xuất đã lưu."
REASONS = {
    "SYSTEM_PAUSED": PAUSED_TEXT,
    "INPUT_UNAVAILABLE": "Chưa kiểm tra được trạng thái tạo đề xuất. Bạn có thể thử lại.",
    "PORTFOLIO_REQUIRED": "Hãy chọn danh mục để kiểm tra rổ tài sản của bạn.",
    "ASSET_SELECTION_REQUIRED": "Danh mục cần có rổ tài sản trước khi tạo đề xuất.",
    "RISK_PROFILE_REQUIRED": "Hãy xác nhận hồ sơ rủi ro của danh mục trước khi tạo đề xuất.",
    "VFF_STALE": "NAV VFF đủ điều kiện của rổ đã quá giới hạn 7 ngày.",
    "GOLD_STALE": "Giá vàng đủ điều kiện của rổ đã quá giới hạn 7 ngày.",
    "ASSET_DATA_STALE": "Dữ liệu đủ điều kiện của rổ đã quá giới hạn 7 ngày.",
    "INPUT_EXPIRED": "Dữ liệu đầu vào của danh mục đã hết hạn.",
    "MODEL_REVIEW_PENDING": "Mô hình cần cho rổ tài sản này đang chờ duyệt.",
    "MODEL_UNAVAILABLE": "Chưa có mô hình phù hợp cho rổ tài sản này.",
    "MODEL_EPOCH_MISMATCH": "Mô hình và kỳ dữ liệu của rổ chưa khớp.",
    "MODEL_COVERAGE_MISSING": "Mô hình chưa bao phủ đủ cổ phiếu của rổ.",
    "ASSET_DATA_MISSING": "Một tài sản trong rổ đang thiếu dữ liệu.",
    "DEFENSIVE_ASSET_REQUIRED": "Rổ cần có VFF để đáp ứng giới hạn phòng thủ.",
    "CONSTRAINTS_INFEASIBLE": "Rổ tài sản chưa đáp ứng được các giới hạn phân bổ.",
    "INSUFFICIENT_ASSETS": "Cần chọn ít nhất hai tài sản trong rổ.",
    "HISTORY_INSUFFICIENT": "Lịch sử giá của rổ chưa đủ để tính đề xuất.",
    "NO_VALID_ML_VIEWS": "Rổ chưa có đủ tín hiệu dự báo để tính đề xuất.",
    "READY": "Danh mục đủ điều kiện tạo đề xuất tại thời điểm kiểm tra.",
}


def status_question(text):
    text = text.strip(" ?!.,")
    reason = re.search(r"\b(?:vi sao|tai sao|do dau|ly do|nguyen nhan|sao)\b", text)
    now = re.search(r"\b(?:bay gio|gio|hien tai|hom nay|luc nay|kiem tra lai)\b", text)
    action = re.search(r"\b(?:tao|lap|tinh|de xuat|phan bo|mo lai|tam dung)\b", text)
    basket = re.search(r"\b(?:vff|nav|model|mo hinh|du lieu|ro|danh muc)\b", text)
    eligibility = re.search(
        r"chua (?:du|dung)|dung duoc|su dung duoc|qua han|qua cu|het han|con han|"
        r"du moi|du dieu kien|san sang|cho (?:reviewer |phe )?duyet|da duoc duyet|bi chan|bi khoa|stale|thieu du lieu",
        text,
    )
    if reason and re.search(r"\b(?:he thong tu choi|da tu choi|bi tu choi)\b", text) and not re.search(r"\b(?:hien tai|bay gio|dang)\b", text):
        return "previous_status"
    if reason and re.search(r"\b(?:luc truoc|luc do|lan do|vua bi|lan truoc)\b", text) and action:
        return "previous_status"
    if reason and now and action and eligibility:
        return "current_status"
    if reason and not now and re.search(
        r"tam dung|bi (?:chan|tu choi|khoa)|(?:chua|khong) (?:the )?tao|"
        r"tao .*that bai|(?:lan|luot) (?:truoc|vua)|vua roi", text,
    ):
        return "previous_status"
    if re.fullmatch(r"(?:tai sao|vi sao|ly do|sao|do dau|nguyen nhan)(?: (?:lan do|lai|the|vay|la gi|nhu vay|nhu the|the a|a))*", text):
        return "previous_turn"
    if re.fullmatch(r"(?:(?:con|the|vay) )?(?:bay gio|gio|luc nay|hien tai)(?: thi)?(?: sao| the nao| duoc chua)?", text):
        return "recheck_previous"
    scoped = re.search(r"\b(?:cua (?:toi|minh)|(?:ro|danh muc) (?:nay|moi|dang chon)|chua|dang)\b", text)
    model_state = re.search(r"\b(?:trang thai|tinh trang|kiem tra)\b.*\b(?:duyet|phe duyet)\b", text)
    if basket and (eligibility or model_state) and (scoped or now):
        return "current_status"
    if action and (
        re.search(r"bao gio|khi nao|duoc chua|duoc khong|san sang chua|trang thai|du dieu kien|con .*dung|(?:bat|mo|khoa) (?:khong|chua)", text)
        or (re.search(r"\b(?:tao|lap|mo lai|(?:gui|nhan) yeu cau)\b", text) and re.search(r"\b(?:khong|chua)\b", text))
        or ("tam dung" in text and (now or "con " in text))
    ):
        return "current_status"
    return None


def previous_turn(sessions, job):
    """Only the immediately preceding job can resolve an implicit reference."""
    with sessions() as s:
        prior = s.scalar(select(Job).join(Conversation, Conversation.id == Job.conversation_id).where(
            Job.conversation_id == job.conversation_id, Job.owner_key == job.owner_key,
            Conversation.owner_key == job.owner_key, Job.created_at < job.created_at,
        ).order_by(Job.created_at.desc(), Job.id.desc()).limit(1))
        if not prior:
            return None
        if prior.result_message_id:
            msg = s.get(Message, prior.result_message_id)
            if msg and msg.conversation_id == job.conversation_id and msg.role == "assistant" and aware(msg.created_at) < aware(job.created_at):
                if prior.request.get("portfolio_id") == job.request.get("portfolio_id"):
                    return msg.structured
                # Only the empty selection prompt may follow the user into a selected portfolio.
                if not prior.request.get("portfolio_id") and (msg.structured or {}).get("pending_lookup") == "saved_target":
                    return {"pending_lookup": "saved_target"}
        if prior.request.get("portfolio_id") != job.request.get("portfolio_id"):
            return None
        if prior.status == "FAILED" and prior.error in REASONS and prior.error != "READY":
            at = s.scalar(select(Event.created_at).where(
                Event.job_id == prior.id, Event.type == "failed", Event.created_at < job.created_at,
            ).order_by(Event.sequence.desc()).limit(1))
            if at:
                return {"type": "allocation_status", "status": "UNKNOWN" if prior.error == "INPUT_UNAVAILABLE" else "BLOCKED",
                        "scope": "system" if prior.error == "SYSTEM_PAUSED" else "portfolio",
                        "portfolio_id": prior.request.get("portfolio_id"), "reason_code": prior.error,
                        "checked_at": aware(at).isoformat(), "source": "previous_job"}
    return None


def status_text(card, historical=False):
    reason = card["reason_code"]
    if historical and reason == "SYSTEM_PAUSED":
        return "Ở lượt trước, hệ thống đã tạm dừng tạo đề xuất mới. Hệ thống chưa cung cấp lý do chi tiết hoặc thời điểm mở lại."
    text = REASONS.get(reason, "Rổ tài sản chưa đủ điều kiện tạo đề xuất.")
    details = card.get("details") or {}
    if details.get("observation_date"):
        text += f" Ngày dữ liệu đủ điều kiện gần nhất: {details['observation_date']}."
    if details.get("available_at"):
        text += f" Dữ liệu có thể sử dụng từ {details['available_at']}."
    return ("Theo lần kiểm tra trước: " + text) if historical else text
