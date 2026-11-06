"""A real issuer's test-client claims must include the configured Market boundary."""

import base64
import importlib.util
import json
from pathlib import Path

import httpx
import pytest


ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "claims, error",
    [
        (
            {
                "aud": "portfolio-api",
                "scope": "openid market:read market:write chat:read chat:write",
                "realm_access": {"roles": ["data-operator"]},
            },
            "Market audience",
        ),
        (
            {
                "aud": ["portfolio-api", "market-api", "chat-api"],
                "scope": "openid market:read chat:read chat:write",
                "realm_access": {"roles": ["data-operator"]},
            },
            "Market scopes",
        ),
        (
            {
                "aud": ["market-api", "chat-api"],
                "scope": "openid market:read market:write chat:read chat:write",
                "realm_access": {"roles": ["investor"]},
            },
            "operator role",
        ),
        (
            {
                "aud": ["portfolio-api", "market-api", "chat-api"],
                "scope": "openid market:read market:write chat:read chat:write",
                "realm_access": {"roles": ["data-operator"]},
            },
            None,
        ),
    ],
)
def test_live_identity_check_requires_market_audience_scopes_and_operator_role(
    tmp_path, monkeypatch, capsys, claims, error
):
    spec = importlib.util.spec_from_file_location(
        "local_boundaries", ROOT / "infra/local/verify_boundaries.py"
    )
    boundary = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(boundary)
    boundary.ROOT = tmp_path
    directory = tmp_path / ".generated"
    directory.mkdir()
    (directory / "accounts.json").write_text(
        json.dumps(
            {
                "users": [
                    {
                        "username": "alice",
                        "password": "alice-password",
                        "roles": ["investor"],
                    },
                    {
                        "username": "data-operator",
                        "password": "operator-password",
                        "roles": ["data-operator"],
                    },
                ]
            }
        )
    )
    (directory / "settings.json").write_text('{"test_client":true}')
    payload = (
        base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
    )
    issuer = "http://localhost:8080/realms/portfolio"

    def serve(request):
        if request.url.path.endswith("/.well-known/openid-configuration"):
            return httpx.Response(200, json={"issuer": issuer})
        if b"client_id=portfolio-web" in request.content:
            return httpx.Response(400, json={"error": "unauthorized_client"})
        if b"client_id=portfolio-test" in request.content:
            return httpx.Response(
                200, json={"access_token": "e30." + payload + ".test-signature"}
            )
        if b"client_id=chat-service" in request.content:
            machine = {
                "aud": ["portfolio-api", "market-api"],
                "scope": "chat:delegate market:chat:read",
            }
        elif b"client_id=portfolio-account-reader" in request.content:
            machine = {
                "resource_access": {"realm-management": {"roles": ["view-users"]}}
            }
        elif request.url.path == "/admin/realms/portfolio/users":
            return httpx.Response(200, json=[{"id": "alice-id"}])
        elif request.url.path.endswith("/users/alice-id"):
            return httpx.Response(200, json={"enabled": True})
        elif request.url.path.endswith("/role-mappings/realm/composite"):
            return httpx.Response(200, json=[{"name": "investor"}])
        else:
            raise AssertionError("Unexpected boundary call")
        encoded = (
            base64.urlsafe_b64encode(json.dumps(machine).encode()).decode().rstrip("=")
        )
        return httpx.Response(
            200, json={"access_token": "e30." + encoded + ".test-signature"}
        )

    client = httpx.Client(transport=httpx.MockTransport(serve))
    monkeypatch.setattr(boundary.httpx, "Client", lambda **kwargs: client)
    values = {
        "OIDC_CLIENT_SECRET": "web-secret",
        "TEST_CLIENT_SECRET": "test-secret",
        "CHAT_CLIENT_SECRET": "chat-secret",
        "PORTFOLIO_ACCOUNT_READER_SECRET": "reader-secret",
    }
    if error:
        with pytest.raises(AssertionError, match=error):
            boundary.verify_identity(values)
    else:
        boundary.verify_identity(values)
        assert "PASS:" in capsys.readouterr().out


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
