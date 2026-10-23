import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from .artifacts import ArtifactCatalog


def sessions_from_env():
    return sessionmaker(
        create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True),
        expire_on_commit=False,
    )


def catalog_from_env():
    return ArtifactCatalog(
        os.environ["BUNDLE_DIRECTORY"],
        allow_demo=os.environ.get("ALLOW_DEMO_INPUTS") == "true",
    )
