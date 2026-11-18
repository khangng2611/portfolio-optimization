"""Disposable local operator CLI: credentials stay in memory and tokens out of arguments."""

import os
from smoke_knowledge import tokens
from knowledge_service.cli import main

if __name__ == "__main__":
    os.environ["KNOWLEDGE_OPERATOR_TOKEN"] = tokens()[0]
    main()
