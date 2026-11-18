"""Keep approved stale-input reasons without forwarding arbitrary upstream text."""

import httpx
import pytest
from chat_service.tools import Tools, ToolError
from chat_service.workflow import Worker
from test_chat import chat as chat_fixture, conversation, headers, send

chat = chat_fixture


@pytest.mark.parametrize(
    "code", ["INPUT_EXPIRED", "VFF_STALE", "GOLD_STALE", "ASSET_DATA_STALE"]
)
def test_stale_input_reason_survives_tool_boundary(code):
    response = httpx.Response(
        409,
        json={"detail": {"code": code, "message": "untrusted secret upstream text"}},
        request=httpx.Request("POST", "http://portfolio/internal"),
    )
    with pytest.raises(ToolError) as error:
        Tools.checked(response)
    assert error.value.code == code
    assert error.value.permanent
    assert "secret" not in str(error.value)


@pytest.mark.parametrize(
    "body",
    [
        {"detail": {"code": "sk-secret-key", "message": "secret"}},
        {"detail": "secret"},
        {"detail": {"code": ["INPUT_EXPIRED"]}},
        {"error": {"code": "unknown"}},
    ],
)
def test_unknown_or_malformed_errors_remain_generic(body):
    response = httpx.Response(
        409, json=body, request=httpx.Request("POST", "http://portfolio/internal")
    )
    with pytest.raises(ToolError) as error:
        Tools.checked(response)
    assert error.value.code == "STALE_OR_INVALID_INPUT"


def test_expiry_reason_persists_in_job_and_failed_event(chat, monkeypatch):
    c, sessions, tools = chat
    cid = conversation(c, tools.summary["id"])
    original = tools.call

    def call(job, name, args):
        if name == "request_allocation":
            raise ToolError("INPUT_EXPIRED", permanent=True)
        return original(job, name, args)

    monkeypatch.setattr(tools, "call", call)
    send(c, cid)
    assert Worker(sessions, tools).tick()
    card = c.get(f"/api/v1/conversations/{cid}/messages", headers=headers()).json()[-1][
        "structured"
    ]
    queued = send(
        c,
        cid,
        confirmation={
            "message_id": card["confirmation_message_id"],
            "facts_hash": card["facts_hash"],
        },
    ).json()
    assert Worker(sessions, tools).tick()
    assert Worker(sessions, tools).tick()
    job = c.get(queued["status_url"], headers=headers()).json()
    assert job["status"] == "FAILED" and job["error"] == "INPUT_EXPIRED"
    assert not tools.allocations


def test_legacy_expired_string_is_mapped_without_publishing_raw_text():
    response = httpx.Response(
        409,
        json={"detail": "Dữ liệu đầu vào đã hết hạn."},
        request=httpx.Request("POST", "http://portfolio/internal"),
    )
    with pytest.raises(ToolError) as error:
        Tools.checked(response)
    assert error.value.code == "INPUT_EXPIRED"


@pytest.mark.parametrize(
    "code", ["INPUT_EXPIRED", "VFF_STALE", "GOLD_STALE", "ASSET_DATA_STALE"]
)
def test_portfolio_error_envelope_preserves_approved_codes(code):
    response = httpx.Response(
        409,
        json={
            "error": {
                "code": code,
                "message": "untrusted raw detail",
                "details": {"private": "hidden"},
            }
        },
        request=httpx.Request("POST", "http://portfolio/internal"),
    )
    with pytest.raises(ToolError) as error:
        Tools.checked(response)
    assert error.value.code == code
    assert "hidden" not in str(error.value)


def test_legacy_expired_error_envelope_maps_to_typed_code():
    response = httpx.Response(
        409,
        json={"error": {"code": "CONFLICT", "message": "Dữ liệu đầu vào đã hết hạn."}},
        request=httpx.Request("POST", "http://portfolio/internal"),
    )
    with pytest.raises(ToolError) as error:
        Tools.checked(response)
    assert error.value.code == "INPUT_EXPIRED"
