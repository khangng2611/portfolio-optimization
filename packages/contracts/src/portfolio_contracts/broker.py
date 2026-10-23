"""Shared transport topology; only JSON wire contracts cross the boundary."""

import logging
import os
import ssl
from urllib.parse import urlsplit
from uuid import UUID

from kombu import Connection, Exchange, Queue
from opentelemetry.trace import SpanKind, Status, StatusCode
from service_observability import capture_context, log_event, span

COMMANDS = Exchange("portfolio.commands", type="direct", durable=True)
EVENTS = Exchange("portfolio.events", type="direct", durable=True)
MARKET_COMMANDS = Exchange("market.commands", type="direct", durable=True)
DEAD = Exchange("portfolio.dead", type="direct", durable=True)
ARGS = {
    "x-queue-type": "quorum",
    "x-delivery-limit": 3,
    "x-dead-letter-exchange": DEAD.name,
}
QUANT_QUEUE = Queue(
    "quant.optimize.v1",
    COMMANDS,
    routing_key="quant.optimize.v1",
    durable=True,
    queue_arguments=ARGS,
)
PORTFOLIO_QUEUE = Queue(
    "portfolio.results.v1",
    EVENTS,
    routing_key="portfolio.results.v1",
    durable=True,
    queue_arguments=ARGS,
)
MARKET_QUEUE = Queue(
    "market.ingest.v1",
    MARKET_COMMANDS,
    routing_key="market.ingest.v1",
    durable=True,
    queue_arguments=ARGS,
)


def connection_from_url(url, *, heartbeat=30):
    parsed = urlsplit(url)
    tls = None
    if parsed.scheme == "amqps":
        tls = {"cert_reqs": ssl.CERT_REQUIRED, "server_hostname": parsed.hostname}
        ca_file = os.environ.get("BROKER_CA_FILE")
        if ca_file:
            tls["ca_certs"] = ca_file
    elif parsed.scheme != "amqp":
        raise ValueError("Broker URL must use amqp or amqps")
    return Connection(
        url,
        ssl=tls,
        heartbeat=heartbeat,
        connect_timeout=5,
        transport_options={"confirm_publish": True},
    )


def _identifier(payload, key):
    try:
        value = payload.get(key)
        return str(UUID(value)) if isinstance(value, str) else None
    except (ValueError, AttributeError):
        return None


def publish(connection, owner, payload):
    exchange, route = {
        "portfolio": (COMMANDS, "quant.optimize.v1"),
        "quant-serving": (EVENTS, "portfolio.results.v1"),
        "market-data": (MARKET_COMMANDS, "market.ingest.v1"),
    }[owner]
    with span(
        "rabbitmq.publish",
        kind=SpanKind.PRODUCER,
        attributes={
            "messaging.system": "rabbitmq",
            "messaging.destination.name": route,
            "messaging.rabbitmq.exchange": exchange.name,
            "messaging.rabbitmq.routing_key": route,
            "messaging.operation.type": "publish",
            "event.id": _identifier(payload, "event_id"),
            "job.id": _identifier(payload, "correlation_id"),
        },
    ):
        with connection.Producer(serializer="json", auto_declare=False) as producer:
            producer.publish(
                payload,
                exchange=exchange,
                routing_key=route,
                delivery_mode=2,
                retry=False,
                mandatory=True,
                timeout=5,
                headers=capture_context() or {},
            )
        log_event(
            "broker.published",
            queue=route,
            event_id=_identifier(payload, "event_id"),
            job_id=_identifier(payload, "correlation_id"),
        )


def handle_delivery(body, message, owner, callback):
    queue = {
        "quant-serving": QUANT_QUEUE,
        "portfolio": PORTFOLIO_QUEUE,
        "market-data": MARKET_QUEUE,
    }[owner]
    payload = body if isinstance(body, dict) else {}
    with span(
        "rabbitmq.consume",
        carrier=getattr(message, "headers", None) or {},
        kind=SpanKind.CONSUMER,
        attributes={
            "messaging.system": "rabbitmq",
            "messaging.destination.name": queue.name,
            "messaging.operation.type": "process",
            "event.id": _identifier(payload, "event_id"),
            "job.id": _identifier(payload, "correlation_id"),
            "messaging.message.redelivered": bool(
                getattr(message, "delivery_info", {}).get("redelivered", False)
            ),
        },
    ) as current:
        try:
            callback(body)
        except ValueError as error:
            current.set_attribute("error.type", type(error).__name__)
            current.set_status(Status(StatusCode.ERROR, type(error).__name__))
            logging.exception("Rejecting invalid event")
            message.reject(requeue=False)
            log_event(
                "broker.rejected",
                queue=queue.name,
                error_type=type(error).__name__,
                outcome="invalid",
            )
        except Exception as error:
            current.set_attribute("error.type", type(error).__name__)
            current.set_status(Status(StatusCode.ERROR, type(error).__name__))
            logging.exception(
                "Transient consumer error; quorum delivery limit bounds retries"
            )
            message.reject(requeue=True)
            log_event(
                "broker.rejected",
                queue=queue.name,
                error_type=type(error).__name__,
                outcome="retry",
            )
        else:
            message.ack()
            log_event(
                "broker.acknowledged",
                queue=queue.name,
                job_id=_identifier(payload, "correlation_id"),
                event_id=_identifier(payload, "event_id"),
            )


def consume(url, owner, callback, stop=None):
    queue = {
        "quant-serving": QUANT_QUEUE,
        "portfolio": PORTFOLIO_QUEUE,
        "market-data": MARKET_QUEUE,
    }[owner]
    with connection_from_url(url) as connection:

        def handle(body, message):
            handle_delivery(body, message, owner, callback)

        with connection.Consumer(
            queues=[queue],
            callbacks=[handle],
            accept=["json"],
            prefetch_count=1,
            auto_declare=False,
        ):
            while not (stop and stop()):
                try:
                    connection.drain_events(timeout=5)
                except TimeoutError:
                    connection.heartbeat_check()
