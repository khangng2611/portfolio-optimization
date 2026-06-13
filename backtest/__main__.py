"""Allow ``python -m backtest`` as a shortcut for the CLI entry point."""

from backtest._main import main

if __name__ == "__main__":
    main()
