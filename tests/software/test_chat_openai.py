"""Offline adapter contract tests. MockTransport is never live-provider evidence."""

import json
import httpx
import pytest


def provider(monkeypatch, handler):
    from chat_service.openai_provider import OpenAIProvider

    monkeypatch.setenv("OPENAI_API_KEY", "private-test-key")
    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kw: original(transport=httpx.MockTransport(handler), **kw),
    )
    return OpenAIProvider()


def response(value, **changes):
    return {
        "id": "resp-test",
        "model": "gpt-6-luna",
        "status": "completed",
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": json.dumps(value)}],
            }
        ],
        "usage": {"input_tokens": 123, "output_tokens": 42},
    } | changes


def test_openai_interprets_structured_plan_without_authorizing_tools(monkeypatch):
    plan = {"intent": "allocation", "strategy": "MVO", "reference": "none"}

    def serve(request):
        assert str(request.url) == "https://api.openai.com/v1/responses"
        assert request.headers["authorization"] == "Bearer private-test-key"
        body = json.loads(request.content)
        assert body["store"] is False
        assert body["reasoning"] == {"effort": "none"}
        assert body["max_output_tokens"] == 384
        assert body["text"]["format"]["strict"] is True
        assert "tools" not in body and "previous_response_id" not in body
        return httpx.Response(200, json=response(plan))

    result, meta = provider(monkeypatch, serve).interpret(
        {"content": "Chia vốn tối ưu giúp tôi"}
    )
    assert result == plan
    assert meta["reason"] == "VERIFIED" and meta["input_tokens"] == 123
    assert meta["output_tokens"] == 42 and meta["model"] == "gpt-6-luna"
    assert "private-test-key" not in json.dumps(meta)


@pytest.mark.parametrize(
    "value",
    [
        {"intent": "accept", "strategy": None, "reference": "none"},
        {"intent": "allocation", "strategy": "AUTO", "reference": "none"},
        {
            "intent": "allocation",
            "strategy": "MVO",
            "reference": "none",
            "confirmed": True,
        },
        {
            "intent": "explain",
            "strategy": None,
            "reference": "none",
            "resource_id": "another-owner",
        },
        {
            "intent": "allocation",
            "strategy": "MVO",
            "reference": "none",
            "weights": [1],
        },
    ],
)
def test_untrusted_model_cannot_expand_contract(monkeypatch, value):
    result, meta = provider(
        monkeypatch, lambda _: httpx.Response(200, json=response(value))
    ).interpret({"content": "test"})
    assert result is None and meta["reason"] == "UNVERIFIED_OUTPUT"
    assert (
        meta["input_tokens"] == 123
    )  # charged usage is retained even on validation failure


@pytest.mark.parametrize(
    "status,code",
    [
        (401, "PROVIDER_AUTH_ERROR"),
        (429, "PROVIDER_QUOTA"),
        (503, "PROVIDER_UNAVAILABLE"),
    ],
)
def test_provider_errors_never_retry_or_expose_response(monkeypatch, status, code):
    calls = []

    def serve(request):
        calls.append(request)
        return httpx.Response(status, text="sensitive provider error private-test-key")

    result, meta = provider(monkeypatch, serve).interpret({"content": "test"})
    assert result is None and meta["reason"] == code
    assert len(calls) == 1 and "sensitive" not in json.dumps(meta)


@pytest.mark.parametrize(
    "changes",
    [
        {"status": "incomplete"},
        {
            "output": [
                {"type": "message", "content": [{"type": "refusal", "refusal": "No"}]}
            ]
        },
        {"usage": None},
        {"output": [{"type": "function_call", "name": "accept"}]},
    ],
)
def test_incomplete_refusal_or_missing_usage_falls_back(monkeypatch, changes):
    value = response(
        {"intent": "help", "strategy": None, "reference": "none"}, **changes
    )
    assert (
        provider(monkeypatch, lambda _: httpx.Response(200, json=value)).interpret(
            {"content": "test"}
        )[0]
        is None
    )


def test_explanation_uses_fact_plan_and_keeps_usage_outside_generated_schema(
    monkeypatch,
):
    digest = "a" * 64

    def serve(request):
        body = json.loads(request.content)
        schema = body["text"]["format"]["schema"]
        assert "input_tokens" not in schema["properties"]
        assert "secret-owner" not in request.content.decode()
        return httpx.Response(
            200, json=response({"sections": ["risk", "weights"], "facts_hash": digest})
        )

    sections, meta = provider(monkeypatch, serve).explain(
        {"owner_user_id": "secret-owner", "weights": ["0.5"], "asset_ids": ["FPT"]},
        digest,
    )
    assert sections == ["risk", "weights"] and meta["input_tokens"] == 123


def test_missing_key_and_oversize_input_cost_nothing(monkeypatch):
    from chat_service.openai_provider import OpenAIProvider

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert (
        OpenAIProvider().interpret({"content": "test"})[1]["reason"] == "NOT_CONFIGURED"
    )
    p = provider(
        monkeypatch, lambda _: pytest.fail("oversize request must not leave process")
    )
    assert p.interpret({"content": "x" * 20000})[1]["reason"] == "INPUT_BUDGET_EXCEEDED"


def test_wall_deadline_and_stream_limit(monkeypatch):
    import asyncio

    class Slow(httpx.AsyncByteStream):
        async def __aiter__(self):
            await asyncio.sleep(0.2)
            yield b"{}"

    p = provider(
        monkeypatch, lambda request: httpx.Response(200, stream=Slow(), request=request)
    )
    p.timeout_seconds = 0.02
    assert p.interpret({"content": "test"})[1]["reason"] == "TIMEOUT"


def test_redaction_removes_keys_identity_and_bearers():
    from chat_service.openai_provider import redact

    text = redact(
        "email alice@example.com Bearer eyJhbGci.abc.def sk-proj-abcdefghijklmnop 0e7c7617-c5e5-4062-b576-499fdeafc8a4"
    )
    assert "alice@" not in text and "eyJ" not in text and "sk-proj" not in text
    assert "0e7c7617" not in text


def test_explanation_plan_receives_redacted_current_question(monkeypatch):
    def serve(request):
        context = json.loads(json.loads(request.content)["input"])
        assert "rủi ro" in context["question"]
        assert "alice@example.com" not in context["question"]
        return httpx.Response(
            200, json=response({"sections": ["risk"], "facts_hash": "a" * 64})
        )

    sections, meta = provider(monkeypatch, serve).explain(
        {}, "a" * 64, question="Nói rõ rủi ro, email alice@example.com"
    )
    assert sections == ["risk"] and meta["reason"] == "VERIFIED"
