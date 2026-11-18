"""Local DB and broker isolation probes."""

import importlib.util
from pathlib import Path

import httpx
import pytest


ROOT = Path(__file__).resolve().parents[2]


def test_broker_check_reads_vhost_permissions_and_rejects_runtime_topology_grants(
    monkeypatch,
):
    spec = importlib.util.spec_from_file_location(
        "local_broker_boundaries", ROOT / "infra/local/verify_boundaries.py"
    )
    boundary = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(boundary)
    permission = {
        "user": "portfolio_publisher",
        "vhost": "portfolio",
        "configure": ".*",
        "write": "^portfolio\\.commands$",
        "read": "^$",
    }
    queues = [
        {
            "name": name + suffix,
            "vhost": "portfolio",
            "type": "quorum",
            "durable": True,
            "auto_delete": False,
            "arguments": {
                "x-queue-type": "quorum",
                "x-delivery-limit": 3,
                "x-dead-letter-exchange": "portfolio.dead",
            }
            if not suffix
            else {"x-queue-type": "quorum"},
        }
        for name in ["quant.optimize.v1", "portfolio.results.v1", "market.ingest.v1"]
        for suffix in ["", ".dead"]
    ]

    def serve(request):
        if (
            request.method == "GET"
            and request.url.path == "/api/vhosts/portfolio/permissions"
        ):
            return httpx.Response(200, json=[permission])
        if request.method == "GET" and request.url.path == "/api/queues/portfolio":
            return httpx.Response(200, json=queues)
        return httpx.Response(404, json={"error": "Object Not Found"})

    client = httpx.Client(
        base_url="http://127.0.0.1:15673", transport=httpx.MockTransport(serve)
    )
    monkeypatch.setattr(boundary.httpx, "Client", lambda **kwargs: client)
    # The management response must reach the actual ACL guard. A stale endpoint
    # yields HTTP 404 before the guard, and a skipped permission fetch cannot pass.
    with pytest.raises(AssertionError):
        boundary.verify_broker({"RABBITMQ_ADMIN_PASSWORD": "test-admin-secret"})


def test_broker_publish_denial_uses_real_pyamqp_qos_signature_without_consuming_messages(
    monkeypatch, capsys
):
    from amqp import Channel, spec as amqp_spec
    from amqp.exceptions import AccessRefused

    spec = importlib.util.spec_from_file_location(
        "local_broker_qos_boundaries", ROOT / "infra/local/verify_boundaries.py"
    )
    boundary = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(boundary)
    ownership = {
        "portfolio": ("portfolio.commands", "portfolio.results.v1"),
        "quant": ("portfolio.events", "quant.optimize.v1"),
        "market": ("market.commands", "market.ingest.v1"),
    }
    permissions = [
        {
            "user": service + "_" + kind,
            "vhost": "portfolio",
            "configure": "^$",
            "write": "^" + exchange.replace(".", "\\.") + "$"
            if kind == "publisher"
            else "^$",
            "read": "^" + queue.replace(".", "\\.") + "$"
            if kind == "consumer"
            else "^$",
        }
        for service, (exchange, queue) in ownership.items()
        for kind in ["publisher", "consumer"]
    ]
    queues = [
        {
            "name": name + suffix,
            "vhost": "portfolio",
            "type": "quorum",
            "durable": True,
            "auto_delete": False,
            "arguments": {
                "x-queue-type": "quorum",
                "x-delivery-limit": 3,
                "x-dead-letter-exchange": "portfolio.dead",
            }
            if not suffix
            else {"x-queue-type": "quorum"},
        }
        for name in ["quant.optimize.v1", "portfolio.results.v1", "market.ingest.v1"]
        for suffix in ["", ".dead"]
    ]

    def serve(request):
        if request.url.path == "/api/vhosts/portfolio/permissions":
            return httpx.Response(200, json=permissions)
        if request.url.path == "/api/queues/portfolio":
            return httpx.Response(200, json=queues)
        return httpx.Response(404)

    client = httpx.Client(
        base_url="http://127.0.0.1:15673", transport=httpx.MockTransport(serve)
    )
    monkeypatch.setattr(boundary.httpx, "Client", lambda **kwargs: client)

    class TransportChannel:
        # Use the installed py-amqp method, including its real argument contract;
        # only the external wire send is replaced by the broker refusal response.
        basic_qos = Channel.basic_qos

        def __init__(self, username):
            self.username = username
            self.forbidden_publish = False

        def send_method(self, signature, argsig, arguments, wait):
            assert signature == amqp_spec.Basic.Qos
            assert arguments == (0, 1, False)
            assert wait == amqp_spec.Basic.QosOk
            if self.forbidden_publish:
                raise AccessRefused("Publish denied")

        def queue_declare(self, queue, passive=False, auto_delete=False):
            service, kind = self.username.rsplit("_", 1)
            if not passive or kind != "consumer" or queue != ownership[service][1]:
                raise AccessRefused("Queue operation denied")
            return queue, 0, 0

    class TransportProducer:
        def __init__(self, channel):
            self.channel = channel

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def publish(self, body, exchange, routing_key, declare):
            assert routing_key == "unroutable.boundary.probe"
            assert declare == []
            service, _ = self.channel.username.rsplit("_", 1)
            if exchange != ownership[service][0]:
                self.channel.forbidden_publish = True

    class TransportConnection:
        def __init__(self, *, userid, **kwargs):
            self._channel = TransportChannel(userid)

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def Producer(self, **kwargs):
            return TransportProducer(self._channel)

        def channel(self):
            return self._channel

    monkeypatch.setattr(boundary, "Connection", TransportConnection)
    credentials = {"RABBITMQ_ADMIN_PASSWORD": "test-admin-secret"}
    credentials.update(
        {
            permission["user"].upper() + "_PASSWORD": "test-secret"
            for permission in permissions
        }
    )
    boundary.verify_broker(credentials)
    assert "PASS: quorum/dead-letter topology" in capsys.readouterr().out
