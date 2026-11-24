from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select

from chat_service.models import Event, Job, ProviderInvocation, ToolCall
from chat_service.workflow import Worker
from portfolio_contracts import utcnow
from test_chat import chat as chat_fixture, conversation, headers

chat = chat_fixture


@pytest.fixture
def status_chat(chat, monkeypatch):
    c, db, tools = chat
    pid = tools.summary["id"]
    cid = conversation(c, pid)
    monkeypatch.setenv("SYSTEM_HYBRID_ENABLED", "true")
    monkeypatch.setenv("CHAT_CONTEXTUAL_REPLIES", "1")
    state = {"reason_code": "SYSTEM_PAUSED"}
    original = tools.call
    def call(job, name, args):
        if name != "get_allocation_status":
            return original(job, name, args)
        code = state["reason_code"]
        if code == "OUTAGE":
            raise httpx.ConnectError("fixture")
        return {"status": "READY" if code == "READY" else "BLOCKED", **state,
                "scope": "system" if code == "SYSTEM_PAUSED" else "portfolio",
                "checked_at": utcnow().isoformat(), "portfolio_id": job.request["portfolio_id"]}
    monkeypatch.setattr(tools, "call", call)
    def turn(text, **changes):
        key = str(uuid4())
        response = c.post(f"/api/v1/conversations/{cid}/messages", headers=headers(key=key),
                          json={"content": text, "client_message_id": key, **changes})
        assert response.status_code == 202
        assert Worker(db, tools).tick()
        messages = c.get(f"/api/v1/conversations/{cid}/messages", headers=headers()).json()
        return messages[-1]
    return turn, state, db, tools


def test_pause_then_why_then_reopened_with_no_mutation(status_chat):
    turn, state, db, tools = status_chat
    paused = turn("Tạo đề xuất phân bổ")
    assert paused["structured"]["reason_code"] == "SYSTEM_PAUSED"
    state["reason_code"] = "READY"
    why = turn("Vì sao vậy?")
    assert why["structured"]["checked_at"] == paused["structured"]["checked_at"]
    assert "lý do chi tiết" in why["content"]
    current = turn("Bây giờ tạo được chưa?")
    assert current["structured"]["status"] == "READY"
    assert current["structured"]["checked_at"] != paused["structured"]["checked_at"]
    with db() as s:
        assert not s.scalars(select(ProviderInvocation)).all()
        assert {t.tool for t in s.scalars(select(ToolCall))} <= {"get_profile", "get_allocation_status"}
        assert all(j.status == "SUCCEEDED" and not j.dependency_id for j in s.scalars(select(Job)))
    assert not tools.allocations
    assert turn("Tạo đề xuất phân bổ")["structured"]["type"] == "confirmation"


def test_previous_failure_is_scoped_even_after_switch(status_chat):
    turn, _, db, _ = status_chat
    turn("Tạo đề xuất phân bổ")
    with db.begin() as s:
        old = s.scalar(select(Job))
        old.status, old.result_message_id, old.error = "FAILED", None, "SYSTEM_PAUSED"
        s.add(Event(job_id=old.id, sequence=99, type="failed", payload={"code":old.error}))
    assert turn("Tai sao chua tao duoc de xuat?")["structured"]["reason_code"] == "SYSTEM_PAUSED"
    assert turn("Vi sao vay?", portfolio_id=str(uuid4()))["structured"]["type"] == "input_required"


def test_current_basket_outage_and_vff_are_distinct(status_chat):
    turn, state, _, tools = status_chat
    state.update(reason_code="VFF_STALE", details={"asset_id":"VFF", "observation_date":"2026-11-01", "age_days":9, "max_age_days":7})
    assert "2026-11-01" in turn("Tại sao dữ liệu VFF của tôi chưa dùng được?")["content"]
    state["reason_code"] = "OUTAGE"
    answer = turn("Bây giờ tạo được chưa?")
    assert answer["structured"]["status"] == "UNKNOWN" and "thử lại" in answer["content"]
    assert not tools.allocations


@pytest.mark.parametrize("text", [
    "ML views", "Target và holdings", "Dữ liệu freshness", "Phê duyệt mô hình",
    "Quy tắc tạm dừng tạo đề xuất là gì?", "Chính sách độ mới NAV VFF là gì?",
])
def test_standalone_educational_topic(text):
    from chat_service.workflow import intent_of
    assert intent_of({"content": text}) == "knowledge"


def test_out_of_scope_write_does_not_read_or_call_model(status_chat):
    turn, _, db, tools = status_chat
    result = turn("Xóa dữ liệu danh mục của Bob")
    assert result["structured"]["type"] == "help"
    with db() as s:
        assert not s.scalars(select(ToolCall)).all()
        assert not s.scalars(select(ProviderInvocation)).all()
    assert not tools.allocations


@pytest.mark.parametrize(("question", "source"), [
    ("Theo quy định thì NAV VFF được xem là đủ mới khi nào?", "knowledge"),
    ("NAV VFF trong rổ của tôi còn dùng được không?", "current_status"),
    ("Giờ danh mục này tạo được đề xuất chưa?", "current_status"),
    ("Kiểm tra xem hiện tại có tạo được đề xuất không?", "current_status"),
    ("Tỷ trọng VFF trong đề xuất hôm trước dựa vào đâu?", "explain"),
    ("Vì sao đề xuất đã lưu lại giữ VFF khi NAV hôm nay hết hạn?", "explain"),
    ("Trượt giá ảnh hưởng thế nào tới kết quả sau phí?", "knowledge"),
    ("Chấp nhận đề xuất có đặt lệnh mua bán luôn không?", "knowledge"),
    ("Hồ sơ rủi ro được chuyển thành ràng buộc đầu tư ra sao?", "knowledge"),
    ("Cho mình hỏi chia đều vốn có chắc lãi không?", "knowledge"),
    ("Giải thích vì sao rủi ro danh mục còn phụ thuộc tương quan?", "knowledge"),
    ("Cho mình xem hồ sơ rủi ro hiện tại", "profile"),
    ("Tạo đề xuất cho tôi ngay bây giờ", "allocation"),
])
def test_source_depends_on_question_scope_and_time(question, source):
    from chat_service.workflow import intent_of
    assert intent_of({"content": question}) == source


def test_hypothetical_eligibility_never_reads_a_live_basket(status_chat):
    turn, _, db, tools = status_chat
    card = turn("Nếu dữ liệu hết hạn thì có tạo đề xuất được không?")["structured"]
    assert card["type"] == "knowledge"
    with db() as s:
        assert "get_allocation_status" not in {t.tool for t in s.scalars(select(ToolCall))}
    assert not tools.allocations


@pytest.mark.parametrize(("text", "source"), [
    ("Chia đều có chắc sinh lời?", "knowledge"),
    ("Vì sao lần trước chưa tạo được đề xuất này?", "previous_status"),
    ("Đề xuất mới đang bật chưa?", "current_status"),
    ("Có thể gửi yêu cầu phân bổ lúc này chưa?", "current_status"),
    ("Cho mình biết hiện tại hệ thống có đang nhận yêu cầu phân bổ không?", "current_status"),
    ("Bây giờ tạo đề xuất của tôi được chưa?", "current_status"),
    ("Vì sao danh mục không cho tôi tạo đề xuất ở lượt trước?", "previous_status"),
    ("Làm thế nào để đa dạng hóa danh mục?", "knowledge"),
])
def test_question_variants_preserve_intent(text, source):
    from chat_service.workflow import intent_of
    assert intent_of({"content": text}) == source


def test_elliptical_now_rechecks_only_if_previous_scope_is_status(status_chat):
    turn, state, _, _ = status_chat
    assert turn("Còn bây giờ thì sao?")["structured"]["type"] == "input_required"
    previous = turn("Tạo đề xuất phân bổ")["structured"]
    state["reason_code"] = "READY"
    current = turn("Còn bây giờ thì sao?")["structured"]
    assert current["reason_code"] == "READY"
    assert current["checked_at"] != previous["checked_at"]


@pytest.mark.parametrize(("question", "expected"), [
    ("Khi tôi chấp nhận một phân bổ mục tiêu thì ứng dụng có tự đặt lệnh mua chứng khoán không?", "knowledge"),
    ("Rủi ro thị trường ảnh hưởng tới đa dạng hóa ra sao?", "knowledge"),
    ("Lúc nãy hệ thống từ chối tạo đề xuất vì lý do gì?", "previous_status"),
    ("Vì sao lần đó lại như thế?", "previous_turn"),
    ("Đang nói tới đề xuất nào vậy?", "explain"),
    ("Đề xuất đang chọn dùng cách phân bổ nào?", "explain"),
])
def test_read_questions_preserve_scope_and_time(question, expected):
    from chat_service.workflow import intent_of
    assert intent_of({"content": question}) == expected


@pytest.mark.parametrize(("question", "expected"), [
    ("Tạo cho mình đề xuất phân bổ mới", "allocation"),
    ("Lập một đề xuất cho danh mục này", "allocation"),
    ("Kiểm tra trạng thái xét duyệt model trong rổ này", "current_status"),
    ("Lệnh mua có tự chạy khi tôi đồng ý với đề xuất không?", "knowledge"),
    ("Nếu tôi hỏi về rủi ro thì hồ sơ của mình có thay đổi không?", "knowledge"),
    ("Tài liệu có công thức tính rho của quyền chọn không?", "knowledge"),
    ("Một dự báo sinh lời từ ML có thể sai chứ?", "knowledge"),
    ("Phần tỷ trọng vừa nhắc đến dựa vào đâu nhỉ?", "previous_turn"),
])
def test_public_question_and_personal_read_or_create_request(question, expected):
    from chat_service.workflow import intent_of
    assert intent_of({"content": question}) == expected
