"""Dedicated single-process scheduler/provider worker; never run in API handlers."""

import logging
import os
from pathlib import Path
import time

from .runtime import sessions_from_env
from .refresh import tick, run_once
from .refresh_provider import KbsProvider


def main():
    logging.basicConfig(level=logging.INFO)
    sessions = sessions_from_env()
    root = Path(os.environ["DATASET_DIRECTORY"]).resolve()
    directory = Path(os.environ["REFRESH_ARTIFACT_DIRECTORY"]).resolve()
    if directory.parent != root or directory.name != "refresh":
        raise SystemExit("REFRESH_ARTIFACT_DIRECTORY must be DATASET_DIRECTORY/refresh")
    source = KbsProvider()
    while True:
        try:
            tick(sessions)
            run_once(sessions, source, directory)
        except Exception:
            logging.error("Refresh worker unavailable; durable jobs retained")
        time.sleep(5)


if __name__ == "__main__":
    main()
