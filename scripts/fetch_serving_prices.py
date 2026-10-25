"""Fetch a bounded real stock input pack without changing research datasets.

Use the existing optional vnstock 4 environment, not the serving environment.
Output includes exact raw-file hashes, requested provider and documented units.
"""

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import re
from datetime import datetime, timezone


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols", nargs="+", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if (
        not 2 <= len(args.symbols) <= 20
        or len(set(args.symbols)) != len(args.symbols)
        or any(not re.fullmatch("[A-Z0-9]{1,12}", s) for s in args.symbols)
    ):
        raise ValueError("Two to twenty distinct stock symbols required")
    version = importlib.metadata.version("vnstock")
    if not version.startswith("4."):
        raise ValueError("This fetch adapter targets the vnstock 4 Market contract")
    from vnstock.ui import Market

    root = Path(args.output)
    root.mkdir(parents=True, exist_ok=False)
    files = []
    for symbol in args.symbols:
        frame = (
            Market()
            .equity(symbol)
            .ohlcv(
                start=args.start,
                end=args.end,
                resolution="1D",
                count=5000,
                source="kbs",
            )
        )
        if frame.empty or not {"time", "close"} <= set(frame.columns):
            raise ValueError("Provider did not return required daily prices")
        path = root / f"{symbol}.csv"
        frame.to_csv(path, index=False)
        files.append(
            {
                "asset_id": symbol,
                "file": path.name,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "row_count": len(frame),
                "first_date": str(frame["time"].min())[:10],
                "last_date": str(frame["time"].max())[:10],
            }
        )
        print(
            f"{symbol}: {len(frame)} daily bars, latest {files[-1]['last_date']}",
            flush=True,
        )
    manifest = {
        "schema_version": 1,
        "data_origin": "real",
        "requested_provider": "kbs",
        "library": "vnstock",
        "library_version": version,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "source_unit": "thousand_VND/share",
        "price_basis": "provider_adjusted",
        "documentation": "https://vnstocks.com/docs/vnstock/thi-truong-market",
        "files": files,
    }
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
