"""Shared transport topology; only JSON wire contracts cross the boundary."""

import logging

from kombu import Connection, Exchange, Queue

COMMANDS = Exchange("portfolio.commands", type="direct", durable=True)
EVENTS = Exchange("portfolio.events", type="direct", durable=True)
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


def publish(connection, owner, payload):
    exchange, route = (
        (COMMANDS, "quant.optimize.v1")
        if owner == "portfolio"
        else (EVENTS, "portfolio.results.v1")
    )
    with connection.Producer(serializer="json", auto_declare=False) as producer:
        producer.publish(
            payload,
            exchange=exchange,
            routing_key=route,
            delivery_mode=2,
            retry=False,
            mandatory=True,
            timeout=5,
        )


def consume(url, owner, callback, stop=None):
    queue = QUANT_QUEUE if owner == "quant-serving" else PORTFOLIO_QUEUE
    with Connection(url, heartbeat=30, connect_timeout=5) as connection:

        def handle(body, message):
            try:
                callback(body)
            except ValueError:
                logging.exception("Rejecting invalid event")
                message.reject(requeue=False)
            except Exception:
                logging.exception(
                    "Transient consumer error; quorum delivery limit bounds retries"
                )
                message.reject(requeue=True)
            else:
                message.ack()

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
