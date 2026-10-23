import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for directory in (
    "packages/service-observability",
    "packages/contracts",
    "packages/service-auth",
    "packages/portfolio-core",
    "services/portfolio",
    "services/quant-serving",
    "services/market-data",
):
    sys.path.insert(0, str(ROOT / directory / "src"))
