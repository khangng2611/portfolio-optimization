import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from .providers import CsvProvider


def sessions_from_env():
    return sessionmaker(
        create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True),
        expire_on_commit=False,
    )


def provider_from_env():
    return CsvProvider(os.environ["DATASET_DIRECTORY"])
