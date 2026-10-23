#!/usr/bin/env python3
"""Check the running disposable stack's DB/broker boundaries without logging secrets.

Run using the software test venv after the Compose stack is healthy. This creates
and removes one uniquely named test table in each database. It does not consume
application messages or alter application records.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import secrets

from amqp.exceptions import AccessRefused
from kombu import Connection
import psycopg
import httpx

ROOT = Path(__file__).resolve().parent


def verify_databases(values: dict[str, str]) -> None:
    for service in ("portfolio", "quant", "identity"):

        def connect(kind: str, database: str | None = None):
            return psycopg.connect(
                host="127.0.0.1",
                port=5433,
                dbname=database or service + "_db",
                user=service + "_" + kind,
                password=values[service.upper() + "_" + kind.upper() + "_PASSWORD"],
                autocommit=True,
                connect_timeout=5,
            )

        probe = psycopg.sql.Identifier("local_permission_probe_" + secrets.token_hex(6))
        forbidden_probe = psycopg.sql.Identifier("forbidden_" + secrets.token_hex(6))
        with connect("migrator") as connection:
            assert (
                connection.execute("SELECT current_user").fetchone()[0]
                == service + "_owner"
            )
            connection.execute(
                psycopg.sql.SQL(
                    "CREATE TABLE public.{} (id integer PRIMARY KEY)"
                ).format(probe)
            )
        try:
            with connect("runtime") as connection:
                assert (
                    connection.execute("SELECT current_user").fetchone()[0]
                    == service + "_runtime"
                )
                connection.execute(
                    psycopg.sql.SQL("INSERT INTO public.{} VALUES (1)").format(probe)
                )
                assert (
                    connection.execute(
                        psycopg.sql.SQL("SELECT count(*) FROM public.{}").format(probe)
                    ).fetchone()[0]
                    == 1
                )
                connection.execute(
                    psycopg.sql.SQL("UPDATE public.{} SET id = 2").format(probe)
                )
                connection.execute(
                    psycopg.sql.SQL("DELETE FROM public.{}").format(probe)
                )
                for command in (
                    psycopg.sql.SQL(
                        "ALTER TABLE public.{} ADD COLUMN forbidden integer"
                    ).format(probe),
                    psycopg.sql.SQL("SET ROLE {}").format(
                        psycopg.sql.Identifier(service + "_owner")
                    ),
                    psycopg.sql.SQL("CREATE TABLE public.{} (id integer)").format(
                        forbidden_probe
                    ),
                ):
                    try:
                        connection.execute(command)
                    except psycopg.errors.InsufficientPrivilege:
                        pass
                    else:
                        raise AssertionError(
                            f"{service}: runtime schema/owner action allowed"
                        )
            for other in (
                "portfolio_db",
                "quant_db",
                "identity_db",
                "postgres",
                "template1",
            ):
                if other == service + "_db":
                    continue
                try:
                    with connect("runtime", other):
                        pass
                except psycopg.OperationalError as error:
                    assert "permission denied for database" in str(error), (
                        f"{service}: unexpected DB connection failure"
                    )
                else:
                    raise AssertionError(
                        f"{service}: runtime cross-database access allowed"
                    )
        finally:
            with connect("migrator") as connection:
                connection.execute(
                    psycopg.sql.SQL("DROP TABLE public.{}").format(probe)
                )
                connection.execute(
                    psycopg.sql.SQL("DROP TABLE IF EXISTS public.{}").format(
                        forbidden_probe
                    )
                )
    print(
        "PASS: DB ownership, own DML, denied DDL/owner escalation, denied cross-database connections"
    )


def verify_broker(values: dict[str, str]) -> None:
    with httpx.Client(
        base_url="http://127.0.0.1:15673",
        auth=("local_admin", values["RABBITMQ_ADMIN_PASSWORD"]),
        timeout=10,
    ) as client:
        response = client.get("/api/permissions/portfolio")
        response.raise_for_status()
        permissions = {item["user"]: item for item in response.json()}
        response = client.get("/api/queues/portfolio")
        response.raise_for_status()
        queues = {item["name"]: item for item in response.json()}
        for queue in ["quant.optimize.v1", "portfolio.results.v1"]:
            assert queues[queue]["type"] == queues[queue + ".dead"]["type"] == "quorum"
            assert queues[queue]["arguments"]["x-delivery-limit"] == 3
            assert (
                queues[queue]["arguments"]["x-dead-letter-exchange"] == "portfolio.dead"
            )

    for service, own_exchange, own_queue, forbidden_exchange, forbidden_queue in [
        (
            "portfolio",
            "portfolio.commands",
            "portfolio.results.v1",
            "portfolio.events",
            "quant.optimize.v1",
        ),
        (
            "quant",
            "portfolio.events",
            "quant.optimize.v1",
            "portfolio.commands",
            "portfolio.results.v1",
        ),
    ]:
        for kind in ("publisher", "consumer"):
            username = service + "_" + kind
            permission = permissions[username]
            assert not any(
                re.search(permission["configure"], resource)
                for resource in [own_exchange, own_queue, "forbidden-probe"]
            )
            allowed = "write" if kind == "publisher" else "read"
            denied = "read" if kind == "publisher" else "write"
            assert re.search(
                permission[allowed], own_exchange if kind == "publisher" else own_queue
            )
            assert not any(
                re.search(permission[denied], resource)
                for resource in [
                    own_exchange,
                    own_queue,
                    forbidden_exchange,
                    forbidden_queue,
                ]
            )

            def connection():
                return Connection(
                    hostname="127.0.0.1",
                    port=5673,
                    userid=username,
                    password=values[username.upper() + "_PASSWORD"],
                    virtual_host="portfolio",
                    connect_timeout=5,
                )

            with connection() as broker:
                if kind == "publisher":
                    # Deliberately unroutable; proves permission without delivering
                    # a synthetic command into a business queue.
                    with broker.Producer(
                        serializer="json", auto_declare=False
                    ) as producer:
                        producer.publish(
                            {"boundary_probe": True},
                            exchange=own_exchange,
                            routing_key="unroutable.boundary.probe",
                            declare=[],
                        )
                else:
                    broker.channel().queue_declare(queue=own_queue, passive=True)

            with connection() as broker:
                try:
                    if kind == "publisher":
                        with broker.Producer(
                            serializer="json", auto_declare=False
                        ) as producer:
                            producer.publish(
                                {"boundary_probe": True},
                                exchange=forbidden_exchange,
                                routing_key="unroutable.boundary.probe",
                                declare=[],
                            )
                            # A synchronous method observes asynchronous channel
                            # closure caused by a refused basic.publish.
                            producer.channel.basic_qos(prefetch_count=1)
                    else:
                        broker.channel().queue_declare(
                            queue=forbidden_queue, passive=True
                        )
                except AccessRefused:
                    pass
                else:
                    raise AssertionError(
                        f"{username}: forbidden broker operation allowed"
                    )
            with connection() as broker:
                try:
                    broker.channel().queue_declare(
                        queue="boundary-probe-" + secrets.token_hex(6), auto_delete=True
                    )
                except AccessRefused:
                    pass
                else:
                    raise AssertionError(
                        f"{username}: runtime topology declaration allowed"
                    )
    print(
        "PASS: quorum/dead-letter topology and owner-specific publisher/consumer broker ACLs"
    )


def verify_identity(values: dict[str, str]) -> None:
    accounts = json.loads((ROOT / ".generated" / "accounts.json").read_text())["users"]
    alice = next(account for account in accounts if account["username"] == "alice")
    issuer = "http://localhost:8080/realms/portfolio"
    with httpx.Client(timeout=10) as client:
        response = client.get(issuer + "/.well-known/openid-configuration")
        response.raise_for_status()
        assert response.json()["issuer"] == issuer
        response = client.post(
            issuer + "/protocol/openid-connect/token",
            data={
                "grant_type": "password",
                "client_id": "portfolio-web",
                "client_secret": values["OIDC_CLIENT_SECRET"],
                "username": alice["username"],
                "password": alice["password"],
                "scope": "openid",
            },
        )
        assert (
            response.status_code == 400
            and response.json().get("error") == "unauthorized_client"
        ), "Normal web client's password grant must be disabled"
    print("PASS: public OIDC issuer and normal web client password-grant denial")


if __name__ == "__main__":
    credentials = json.loads((ROOT / ".generated" / "secrets.json").read_text())
    verify_databases(credentials)
    verify_broker(credentials)
    verify_identity(credentials)
