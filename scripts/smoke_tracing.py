"""Verify real local BFF/RabbitMQ/Market traces without printing credentials."""

import argparse
import json
import subprocess
import sys
import time
from html.parser import HTMLParser
from urllib.parse import urlsplit
from uuid import uuid4

import httpx

from smoke_software import GENERATED, MARKET, SmokeFailure, login, request, require

WEB = "http://localhost:3000"
JAEGER = "http://localhost:16686"


def compose(*arguments):
    subprocess.run(
        [
            "docker",
            "compose",
            "--env-file",
            str(GENERATED / ".env"),
            "-f",
            "infra/local/compose.yaml",
            "-f",
            "infra/local/compose.tracing.yaml",
            *arguments,
        ],
        check=True,
        stdout=subprocess.DEVNULL,
    )


class LoginForm(HTMLParser):
    action = None

    def handle_starttag(self, tag, attributes):
        values = dict(attributes)
        if tag == "form" and values.get("id") == "kc-form-login":
            self.action = values.get("action")


def browser_login(client, accounts):
    response = client.get(WEB + "/auth/login")
    require(response.status_code == 302, "BFF login redirect missing")
    location = response.headers["location"]
    require(
        urlsplit(location).hostname == "localhost" and urlsplit(location).port == 8080,
        "Unexpected identity redirect",
    )
    page = client.get(location)
    parser = LoginForm()
    parser.feed(page.text)
    require(parser.action is not None, "Keycloak login form missing")
    action = urlsplit(parser.action)
    require(
        action.hostname == "localhost"
        and action.port == 8080
        and action.path.startswith("/realms/portfolio/login-actions/"),
        "Unexpected login action",
    )
    account = next(item for item in accounts["users"] if item["username"] == "alice")
    # Browsers consider localhost a secure context; HTTPX needs explicit local cookies.
    cookies = "; ".join(
        cookie.name + "=" + cookie.value
        for cookie in client.cookies.jar
        if cookie.domain in {"localhost", "localhost.local"}
        and action.path.startswith(cookie.path)
    )
    response = client.post(
        parser.action,
        data={"username": "alice", "password": account["password"], "credentialId": ""},
        headers={"Cookie": cookies, "Origin": "http://localhost:8080"},
    )
    require(response.status_code in {302, 303}, "Keycloak code login failed")
    callback = response.headers["location"]
    parsed = urlsplit(callback)
    require(
        parsed.hostname == "localhost"
        and parsed.port == 3000
        and parsed.path == "/auth/callback",
        "Unexpected BFF callback",
    )
    require(client.get(callback).status_code in {302, 303}, "BFF callback failed")
    response = client.get(WEB + "/auth/session")
    require(
        response.status_code == 200 and response.json().get("authenticated"),
        "BFF session unavailable",
    )
    return response.json()["csrfToken"]


def read_trace(identity, services, operations, forbidden):
    require(
        isinstance(identity, str) and len(identity) == 32, "Missing submission trace ID"
    )
    deadline = time.monotonic() + 20
    data = None
    while time.monotonic() < deadline:
        response = httpx.get(JAEGER + "/api/v3/traces/" + identity, timeout=5)
        if response.status_code == 200:
            # Stable v3 query API streams OTLP JSON resource batches.
            resources = [
                resource
                for line in response.text.splitlines()
                if line.strip()
                for resource in json.loads(line)
                .get("result", {})
                .get("resourceSpans", [])
            ]
            if resources:
                data = {"resourceSpans": resources}
                actual_services = {
                    attribute["value"]["stringValue"]
                    for resource in resources
                    for attribute in resource.get("resource", {}).get("attributes", [])
                    if attribute["key"] == "service.name"
                }
                spans = [
                    item
                    for resource in resources
                    for scope in resource.get("scopeSpans", [])
                    for item in scope.get("spans", [])
                ]
                names = {item["name"] for item in spans}
                if services <= actual_services and operations <= names:
                    break
        time.sleep(0.5)
    require(data is not None, "Trace not exported to Jaeger")
    require(
        services <= actual_services,
        "Incomplete trace services: " + ", ".join(sorted(services - actual_services)),
    )
    require(
        operations <= names,
        "Incomplete trace operations: " + ", ".join(sorted(operations - names)),
    )
    require(
        all(item["traceId"] == identity for item in spans),
        "Trace identity changed across broker",
    )
    encoded = json.dumps(data)
    require(
        not any(value and value in encoded for value in forbidden),
        "Sensitive value exported in trace",
    )
    blocked = {
        "http.url",
        "url.full",
        "http.request.header.authorization",
        "http.request.header.cookie",
        "db.statement",
        "db.query.text",
        "exception.message",
        "exception.stacktrace",
    }
    for item in spans:
        require(
            not blocked.intersection(tag["key"] for tag in item.get("attributes", [])),
            "Sensitive span attribute exported",
        )
    return {
        "trace_id": identity,
        "trace_url": JAEGER + "/trace/" + identity,
        "services": sorted(actual_services),
        "span_count": len(spans),
    }


def poll(fetch, url):
    deadline = time.monotonic() + 65
    while time.monotonic() < deadline:
        status, state = fetch(url)
        require(status == 200, "Job polling failed")
        if state["status"] != "QUEUED":
            require(state["status"] == "SUCCEEDED", "Asynchronous traced job failed")
            return state
        time.sleep(0.5)
    raise SmokeFailure("Traced job timed out")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--restart-dispatcher", action="store_true")
    parser.add_argument(
        "--collector-outage",
        action="store_true",
        help="Stop only Jaeger, verify business workflow, restart collector before fresh trace demo",
    )
    args = parser.parse_args()
    accounts = json.loads((GENERATED / "accounts.json").read_text())
    settings = dict(
        line.split("=", 1)
        for line in (GENERATED / ".env").read_text().splitlines()
        if line and not line.startswith("#")
    )
    forbidden = [account["password"] for account in accounts["users"]]
    receipt = {
        "schema_version": 1,
        "dispatcher_restart": args.restart_dispatcher,
        "collector_outage": args.collector_outage,
    }
    if args.collector_outage:
        try:
            compose("stop", "jaeger")
            subprocess.run([sys.executable, "scripts/smoke_software.py"], check=True)
        finally:
            compose("start", "jaeger")
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            try:
                if httpx.get(JAEGER + "/api/v3/services", timeout=2).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.5)
    with httpx.Client(timeout=10, follow_redirects=False) as client:
        csrf = browser_login(client, accounts)
        forbidden.append(csrf)
        headers = {"Origin": WEB, "X-CSRF-Token": csrf}
        private_name = "Tracing demo " + str(uuid4())
        forbidden.append(private_name)
        response = client.post(
            WEB + "/api/v1/portfolios",
            headers=headers,
            json={
                "name": private_name,
                "capital_vnd": "1000000",
                "universe_id": "DEMO",
                "max_position_weight": 0.5,
            },
        )
        require(response.status_code == 201, "BFF portfolio creation failed")
        portfolio = response.json()
        path = WEB + "/api/v1/portfolios/" + portfolio["id"] + "/recommendations"
        stopped = False
        try:
            if args.restart_dispatcher:
                compose("stop", "portfolio-dispatch")
                stopped = True
            key = {**headers, "Idempotency-Key": str(uuid4())}
            response = client.post(path, headers=key, json={"strategy": "MVO"})
            require(response.status_code == 202, "BFF MVO enqueue failed")
            accepted = response.json()
            require(
                response.headers.get("x-trace-id") == accepted.get("job_trace_id"),
                "BFF origin trace not propagated to job",
            )
            replay = client.post(path, headers=key, json={"strategy": "MVO"})
            require(
                replay.status_code == 202 and replay.json() == accepted,
                "Traced idempotent replay changed origin",
            )
            if stopped:
                state = client.get(WEB + accepted["status_url"]).json()
                require(
                    state["status"] == "QUEUED",
                    "Stopped dispatcher did not retain queued job",
                )
                compose("start", "portfolio-dispatch")
                stopped = False

            def fetch(url):
                result = client.get(url)
                return result.status_code, result.json()

            state = poll(fetch, WEB + accepted["status_url"])
            require(
                state.get("job_trace_id") == accepted["job_trace_id"],
                "Persisted job trace changed",
            )
            response = client.get(
                WEB + "/api/v1/recommendations/" + state["recommendation_id"]
            )
            require(response.status_code == 200, "Traced recommendation missing")
            require(
                response.json().get("job_trace_id") == accepted["job_trace_id"],
                "Recommendation origin missing",
            )
            receipt["portfolio"] = read_trace(
                accepted["job_trace_id"],
                {
                    "web-bff",
                    "portfolio-api",
                    "portfolio-dispatch",
                    "quant-consume",
                    "quant-dispatch",
                    "portfolio-consume",
                },
                {"rabbitmq.publish", "rabbitmq.consume", "portfolio_core.allocate"},
                forbidden,
            )
        finally:
            if stopped:
                compose("start", "portfolio-dispatch")
            client.post(WEB + "/auth/logout", headers=headers)
    operator = login("data-operator", accounts, settings)
    forbidden.append(operator)
    status, accepted = request(
        "POST",
        MARKET + "/api/v1/market/ingestions",
        token=operator,
        body={"dataset_id": "DEMO_STOCK"},
        headers={"Idempotency-Key": str(uuid4())},
    )
    require(status == 202, "Market traced enqueue failed")
    state = poll(
        lambda url: request("GET", url, token=operator), MARKET + accepted["status_url"]
    )
    require(
        state.get("job_trace_id") == accepted.get("job_trace_id"),
        "Market origin missing",
    )
    receipt["market"] = read_trace(
        accepted["job_trace_id"],
        {"market-api", "market-dispatch", "market-consume"},
        {"rabbitmq.publish", "rabbitmq.consume"},
        forbidden,
    )
    (GENERATED / "tracing-receipt.json").write_text(
        json.dumps(receipt, indent=2) + "\n"
    )
    print(
        "PASS: BFF code/PKCE + async MVO + Market, durable trace propagation, idempotency and export privacy"
    )
    for item in (receipt["portfolio"], receipt["market"]):
        print(item["trace_url"] + " (" + str(item["span_count"]) + " spans)")


if __name__ == "__main__":
    try:
        main()
    except (
        SmokeFailure,
        OSError,
        KeyError,
        StopIteration,
        httpx.HTTPError,
        subprocess.CalledProcessError,
    ) as error:
        raise SystemExit(
            "FAIL: "
            + (
                str(error)
                if isinstance(error, SmokeFailure)
                else type(error).__name__ + "; check local stack"
            )
        ) from None
