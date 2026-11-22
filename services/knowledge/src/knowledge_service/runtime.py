import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def sessions_from_env():
    return sessionmaker(
        create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True),
        expire_on_commit=False,
    )
