import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

import service_observability as obs


@pytest.fixture
def exporter(monkeypatch):
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(obs, "_tracer", provider.get_tracer("portfolio-services"))
    monkeypatch.setattr(obs, "_enabled", True)
    monkeypatch.setenv("TRACE_VIEWER_URL", "http://localhost:16686")
    yield exporter
    provider.shutdown()


def test_persisted_context_continues_after_unrelated_request(exporter):
    with obs.span("submit"):
        saved = obs.capture_context()
        origin = obs.trace_id()
    with obs.span("unrelated"):
        with obs.span("dispatch", carrier=saved):
            assert obs.trace_id() == origin
        assert obs.trace_id() != origin
    assert obs.trace_fields(saved)["job_trace_url"].endswith("/trace/" + origin)
    assert obs.trace_fields(None) == {"job_trace_id": None, "job_trace_url": None}


def test_http_propagates_without_exporting_credentials_or_payload(exporter):
    app = FastAPI()
    obs.install_http_tracing(app)

    @app.post("/api/v1/jobs/{job_id}")
    def submit(job_id: str):
        return {"trace": obs.trace_id()}

    headers = {
        "traceparent": "00-" + "1" * 32 + "-" + "2" * 16 + "-01",
        "baggage": "password=secret",
        "authorization": "Bearer secret",
    }
    response = TestClient(app).post(
        "/api/v1/jobs/PRIVATE?token=secret", json={"capital": "secret"}, headers=headers
    )
    assert response.headers["x-trace-id"] == "1" * 32
    data = exporter.get_finished_spans()
    assert data[0].name == "POST /api/v1/jobs/{job_id}"
    assert "secret" not in str(data[0].attributes)
    assert "PRIVATE" not in str(data[0].attributes)


def test_malformed_context_and_exception_are_safe(exporter):
    with pytest.raises(ValueError):
        with obs.span(
            "failure",
            carrier={"traceparent": "garbage", "baggage": "secret"},
            attributes={"authorization": "secret"},
        ):
            raise ValueError("password=secret")
    completed = exporter.get_finished_spans()[0]
    assert completed.status.description == "ValueError"
    assert "secret" not in str(completed.attributes)
    assert not completed.events
    assert (
        obs.trace_id({"traceparent": "00-" + "0" * 32 + "-" + "2" * 16 + "-01"}) is None
    )


def test_poll_is_new_trace_with_origin_link(exporter):
    with obs.span("submit"):
        saved = obs.capture_context()
        origin = obs.trace_id()
    with obs.span("poll"):
        obs.link_job(saved, "job-123")
        assert obs.trace_id() != origin
    poll = exporter.get_finished_spans()[1]
    assert len(poll.links) == 1
    assert format(poll.links[0].context.trace_id, "032x") == origin


def test_disabled_no_dead_links_and_unsafe_viewer_rejected(monkeypatch):
    monkeypatch.setattr(obs, "_enabled", False)
    with obs.span("disabled"):
        assert obs.capture_context() is None
    monkeypatch.setenv("TRACE_VIEWER_URL", "http://attacker.example")
    assert (
        obs.trace_fields({"traceparent": "00-" + "1" * 32 + "-" + "2" * 16 + "-01"})[
            "job_trace_url"
        ]
        is None
    )


def test_logs_only_allowlisted_metadata(exporter, caplog):
    caplog.set_level("INFO", logger="portfolio.trace")
    with obs.span("worker"):
        obs.log_event(
            "job.completed",
            job_id="123",
            outcome="duplicate_delivery",
            password="secret",
            capital=999,
        )
    record = next(
        record for record in caplog.records if record.name == "portfolio.trace"
    )
    fields = record.trace_fields
    assert fields["job_id"] == "123"
    assert "password" not in fields and "capital" not in fields
    assert fields["trace_id"]
    assert (
        exporter.get_finished_spans()[0].attributes["outcome"] == "duplicate_delivery"
    )


def test_invalid_viewer_never_fails_job_metadata(monkeypatch):
    monkeypatch.setenv("TRACE_VIEWER_URL", "http://[invalid")
    fields = obs.trace_fields(
        {"traceparent": "00-" + "1" * 32 + "-" + "2" * 16 + "-01"}
    )
    assert fields == {"job_trace_id": "1" * 32, "job_trace_url": None}


def test_invalid_tracestate_silently_dropped_while_disabled(monkeypatch, caplog):
    monkeypatch.setattr(obs, "_enabled", False)
    assert (
        obs.trace_id(
            {
                "traceparent": "00-" + "1" * 32 + "-" + "2" * 16 + "-01",
                "tracestate": "private-invalid-value",
            }
        )
        == "1" * 32
    )
    assert "private" not in caplog.text


def test_uvicorn_error_handler_never_formats_private_exception(monkeypatch):
    import logging
    from io import StringIO
    from uvicorn.config import LOGGING_CONFIG
    from logging.config import dictConfig

    dictConfig(LOGGING_CONFIG)
    handler = logging.getLogger("uvicorn").handlers[0]
    output = StringIO()
    monkeypatch.setattr(handler, "stream", output)
    monkeypatch.setenv("OTEL_TRACES_ENABLED", "true")
    monkeypatch.setattr(obs, "_provider", None)
    monkeypatch.setattr(obs, "_tracer", obs._tracer)
    monkeypatch.setattr(obs, "_enabled", False)
    obs.configure("privacy-test")
    try:
        raise ValueError("private-database-parameter")
    except ValueError:
        logging.getLogger("uvicorn.error").exception("private-request-body")
    assert "private" not in output.getvalue()
    assert "ValueError" in output.getvalue()
    obs._provider.shutdown()


def test_exporter_failure_preserves_business_result_and_context(monkeypatch):
    from opentelemetry.sdk.trace.export import SpanExporter

    class BrokenExporter(SpanExporter):
        def export(self, spans):
            raise ConnectionError("collector unavailable")

        def shutdown(self):
            pass

    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(BrokenExporter()))
    monkeypatch.setattr(obs, "_tracer", provider.get_tracer("portfolio-services"))
    monkeypatch.setattr(obs, "_enabled", True)
    with obs.span("business"):
        result = {"status": "SUCCEEDED"}
    assert result["status"] == "SUCCEEDED"
    assert obs.trace_id() is None
    provider.shutdown()
