from types import SimpleNamespace

from portfolio_contracts.broker import handle_delivery, publish
import service_observability as obs
from test_observability import exporter  # noqa: F401


class Producer:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def publish(self, body, **kwargs):
        self.body, self.kwargs = body, kwargs


def test_publish_and_consume_continue_trace_and_ack_after_callback(exporter):  # noqa: F811
    producer = Producer()
    connection = SimpleNamespace(Producer=lambda **kwargs: producer)
    payload = {
        "event_id": "event-1",
        "correlation_id": "job-1",
        "payload": {"secret": "private"},
    }
    with obs.span("submit"):
        origin = obs.trace_id()
        publish(connection, "portfolio", payload)
    calls = []
    message = SimpleNamespace(
        headers={**producer.kwargs["headers"], "baggage": "secret"},
        delivery_info={},
        ack=lambda: calls.append("ack"),
    )

    def callback(body):
        assert body is payload
        assert obs.trace_id() == origin
        calls.append("callback")

    handle_delivery(payload, message, "quant-serving", callback)
    assert calls == ["callback", "ack"]
    assert producer.kwargs["delivery_mode"] == 2
    assert set(producer.kwargs["headers"]) == {"traceparent"}
    assert "private" not in str(
        [item.attributes for item in exporter.get_finished_spans()]
    )
    assert obs.trace_id() is None


def test_reject_outcomes_preserve_existing_retry_semantics(exporter):  # noqa: F811
    for error, requeue in [
        (ValueError("secret"), False),
        (RuntimeError("secret"), True),
    ]:
        rejected = []
        message = SimpleNamespace(
            headers={},
            delivery_info={},
            reject=lambda **kwargs: rejected.append(kwargs),
        )

        def callback(body):
            raise error

        handle_delivery({}, message, "portfolio", callback)
        assert rejected == [{"requeue": requeue}]
    spans = exporter.get_finished_spans()
    assert all(item.status.is_ok is False for item in spans)
    assert all(not item.events for item in spans)


def test_invalid_envelope_identifiers_are_not_exported(exporter, caplog):  # noqa: F811
    caplog.set_level("INFO", logger="portfolio.trace")
    message = SimpleNamespace(
        headers={}, delivery_info={}, reject=lambda **kwargs: None
    )

    def callback(body):
        raise ValueError("invalid envelope")

    handle_delivery(
        {"event_id": "private-name", "correlation_id": "private-capital"},
        message,
        "portfolio",
        callback,
    )
    assert "private" not in str(
        [item.attributes for item in exporter.get_finished_spans()]
    )
    assert "private" not in str(
        [getattr(record, "trace_fields", {}) for record in caplog.records]
    )
