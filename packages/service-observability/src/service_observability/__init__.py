"""Manual, privacy-limited tracing shared by HTTP and durable workers."""

import atexit
import json
import logging
import os
import re
from contextlib import contextmanager
from urllib.parse import urlsplit

from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.trace import SpanKind, Status, StatusCode
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

_enabled = False
_service_name = "portfolio-service"
_provider = None
_tracer = trace.get_tracer("portfolio-services")
_propagator = TraceContextTextMapPropagator()
_parent = re.compile(r"00-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}\Z")
_state_key = re.compile(
    r"(?:[a-z][a-z0-9_*/-]{0,255}|[a-z0-9][a-z0-9_*/-]{0,240}@[a-z][a-z0-9_*/-]{0,13})\Z"
)
_attrs = {
    "job.id",
    "event.id",
    "event.type",
    "strategy",
    "job.strategy",
    "core.version",
    "status",
    "job.status",
    "outcome",
    "error.type",
    "error.code",
    "stage",
    "messaging.system",
    "messaging.destination.name",
    "messaging.rabbitmq.exchange",
    "messaging.rabbitmq.routing_key",
    "messaging.operation.type",
    "messaging.message.id",
    "messaging.message.redelivered",
    "messaging.delivery.count",
    "http.request.method",
    "http.route",
    "http.response.status_code",
}
_log_fields = {
    "job_id",
    "event_id",
    "event_type",
    "queue",
    "status",
    "outcome",
    "duration_ms",
    "error_type",
    "error_code",
    "strategy",
    "core_version",
}


def _valid_state(state):
    if not isinstance(state, str) or len(state) > 512 or len(state.split(",")) > 32:
        return False
    seen = set()
    for member in state.split(","):
        parts = member.strip().split("=")
        if len(parts) != 2:
            return False
        key, value = parts
        if (
            not _state_key.fullmatch(key)
            or key in seen
            or not 1 <= len(value) <= 256
            or value != value.strip()
            or not all(
                32 <= ord(char) <= 126 and char not in {",", "="} for char in value
            )
        ):
            return False
        seen.add(key)
    return True


def _carrier(carrier):
    if not isinstance(carrier, dict):
        return {}
    parent = carrier.get("traceparent")
    if not isinstance(parent, str) or not _parent.fullmatch(parent):
        return {}
    if int(parent[3:35], 16) == 0 or int(parent[36:52], 16) == 0:
        return {}
    result = {"traceparent": parent}
    state = carrier.get("tracestate")
    if _valid_state(state):
        parsed = trace.TraceState.from_header([state])
        if parsed:
            result["tracestate"] = parsed.to_header()
    return result


class _SafeFormatter(logging.Formatter):
    def format(self, record):
        fields = getattr(record, "trace_fields", None)
        if fields is None:
            fields = {
                "stage": "runtime",
                "logger": record.name,
                "level": record.levelname,
                "trace_id": trace_id(),
            }
            if record.exc_info:
                fields["error_type"] = record.exc_info[0].__name__
        return json.dumps(fields, separators=(",", ":"))


def configure(service_name: str) -> None:
    global _enabled, _provider, _tracer, _service_name
    if os.environ.get("OTEL_TRACES_ENABLED", "false").lower() != "true":
        return
    if _provider is not None:
        return
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

    try:
        _service_name = os.environ.get("OTEL_SERVICE_NAME", service_name)
        endpoint = os.environ.get(
            "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "http://localhost:4318/v1/traces"
        )
        provider = TracerProvider(
            resource=Resource.create({"service.name": _service_name})
        )
        provider.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(endpoint=endpoint, timeout=2),
                max_queue_size=2048,
                max_export_batch_size=512,
                schedule_delay_millis=500,
                export_timeout_millis=2000,
            )
        )
        _provider = provider
        _tracer = provider.get_tracer("portfolio-services")
        _enabled = True
        atexit.register(provider.shutdown)
        root = logging.getLogger()
        if not root.handlers:
            root.addHandler(logging.StreamHandler())
        handlers = set(root.handlers)
        for logger in logging.Logger.manager.loggerDict.values():
            if isinstance(logger, logging.Logger):
                handlers.update(logger.handlers)
        for handler in handlers:
            handler.setFormatter(_SafeFormatter())
        logging.getLogger("portfolio.trace").setLevel(logging.INFO)
        logging.getLogger("uvicorn.access").disabled = True
    except Exception:
        # Observability setup cannot prevent business startup.
        _enabled = False


@contextmanager
def span(name, *, carrier=None, kind=None, attributes=None):
    if not _enabled:
        yield trace.INVALID_SPAN
        return
    context = (
        None
        if carrier is None
        else _propagator.extract(_carrier(carrier), context=Context())
    )
    safe = {
        key: value
        for key, value in (attributes or {}).items()
        if key in _attrs and isinstance(value, (str, bool, int, float))
    }
    with _tracer.start_as_current_span(
        name,
        context=context,
        kind=kind or SpanKind.INTERNAL,
        attributes=safe,
        record_exception=False,
        set_status_on_exception=False,
    ) as current:
        try:
            yield current
        except BaseException as error:
            current.set_attribute("error.type", type(error).__name__)
            current.set_status(Status(StatusCode.ERROR, type(error).__name__))
            raise


def capture_context():
    if not _enabled:
        return None
    headers = {}
    _propagator.inject(headers)
    return _carrier(headers) or None


def trace_id(carrier=None):
    context = (
        trace.get_current_span().get_span_context()
        if carrier is None
        else trace.get_current_span(
            _propagator.extract(_carrier(carrier), context=Context())
        ).get_span_context()
    )
    return format(context.trace_id, "032x") if context.is_valid else None


def trace_fields(carrier):
    identity = trace_id(carrier) if carrier else None
    base = os.environ.get("TRACE_VIEWER_URL", "http://localhost:16686").rstrip("/")
    try:
        parsed = urlsplit(base)
        safe = (
            not parsed.username
            and not parsed.password
            and not parsed.query
            and not parsed.fragment
            and (
                (
                    parsed.scheme == "http"
                    and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
                    and parsed.port == 16686
                )
                or (parsed.scheme == "https" and bool(parsed.hostname))
            )
        )
    except ValueError:
        safe = False
    return {
        "job_trace_id": identity,
        "job_trace_url": base + "/trace/" + identity if identity and safe else None,
    }


def inject_headers(headers=None):
    result = dict(headers or {})
    result.update(capture_context() or {})
    return result


def link_job(carrier, job_id):
    current = trace.get_current_span()
    current.set_attribute("job.id", str(job_id))
    if carrier:
        context = trace.get_current_span(
            _propagator.extract(_carrier(carrier), context=Context())
        ).get_span_context()
        if context.is_valid:
            current.add_link(context)


def log_event(stage, **safe_fields):
    active = trace.get_current_span()
    current = active.get_span_context()
    fields = {
        key: value
        for key, value in safe_fields.items()
        if key in _log_fields and isinstance(value, (str, bool, int, float))
    }
    for key, attribute in {
        "job_id": "job.id",
        "event_id": "event.id",
        "outcome": "outcome",
        "status": "status",
        "error_type": "error.type",
        "error_code": "error.code",
    }.items():
        if key in fields:
            active.set_attribute(attribute, fields[key])
    fields.update(
        service=_service_name,
        stage=stage,
        trace_id=trace_id(),
        span_id=format(current.span_id, "016x") if current.is_valid else None,
    )
    logging.getLogger("portfolio.trace").info(
        "trace event", extra={"trace_fields": fields}
    )


class _HTTPTracing:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope.get("path", "").startswith(
            ("/api/v1", "/internal/v1")
        ):
            return await self.app(scope, receive, send)
        headers = {
            key.decode("latin1").lower(): value.decode("latin1")
            for key, value in scope.get("headers", [])
            if key.lower() in {b"traceparent", b"tracestate"}
        }
        method = scope.get("method", "HTTP")
        with span(
            method + " request",
            carrier=headers,
            kind=SpanKind.SERVER,
            attributes={"http.request.method": method},
        ) as current:

            async def traced_send(message):
                if message["type"] == "http.response.start":
                    route = getattr(scope.get("route"), "path", "/unmatched")
                    current.update_name(method + " " + route)
                    current.set_attribute("http.route", route)
                    current.set_attribute(
                        "http.response.status_code", message["status"]
                    )
                    if message["status"] >= 500:
                        current.set_status(Status(StatusCode.ERROR))
                    identity = trace_id()
                    if identity:
                        message = {
                            **message,
                            "headers": [
                                (key, value)
                                for key, value in message.get("headers", [])
                                if key.lower() != b"x-trace-id"
                            ]
                            + [(b"x-trace-id", identity.encode())],
                        }
                await send(message)

            await self.app(scope, receive, traced_send)


def install_http_tracing(app):
    app.add_middleware(_HTTPTracing)
