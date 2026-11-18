import base64
import json
import os

from cryptography.hazmat.primitives.serialization import load_pem_private_key
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from .api import ROLE_SCOPES, create_app, password_hash
from .models import Account


CLIENT_SECRET_ENV = {
    "portfolio-service": "QUANT_CLIENT_SECRET",
    "quant-publisher": "MARKET_READER_CLIENT_SECRET",
    "ml-worker": "ML_MARKET_READER_CLIENT_SECRET",
    "quant-ml-reader": "ML_READER_CLIENT_SECRET",
    "chat-service": "CHAT_CLIENT_SECRET",
}


def sessions_from_env():
    return sessionmaker(
        create_engine(
            os.environ["DATABASE_URL"], pool_pre_ping=True, hide_parameters=True
        ),
        expire_on_commit=False,
    )


def app_factory():
    return create_app(
        sessions_from_env(),
        os.environ["OIDC_ISSUER"],
        load_pem_private_key(
            base64.b64decode(os.environ["AUTH_SIGNING_KEY_B64"], validate=True),
            password=None,
        ),
        os.environ["AUTH_WEB_SECRET"],
        os.environ["PORTFOLIO_ACCOUNT_READER_SECRET"],
        {client: os.environ[name] for client, name in CLIENT_SECRET_ENV.items()},
    )


def seed():
    with sessions_from_env().begin() as db:
        for account in json.loads(
            base64.b64decode(os.environ["AUTH_SEED_ACCOUNTS_B64"], validate=True)
        ):
            username, role = account["username"], account["roles"][0]
            if role not in ROLE_SCOPES:
                raise RuntimeError("Unsupported seed role")
            if (
                db.scalar(select(Account.id).where(Account.username == username))
                is None
            ):
                db.add(
                    Account(
                        username=username,
                        name=username,
                        role=role,
                        password_hash=password_hash(account["password"]),
                    )
                )


if __name__ == "__main__":
    seed()
