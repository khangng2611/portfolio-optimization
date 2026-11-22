import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for directory in (
    "packages/service-observability",
    "packages/contracts",
    "packages/service-auth",
    "packages/portfolio-core",
    "services/auth",
    "services/portfolio",
    "services/quant-serving",
    "services/market-data",
    "services/ml-platform",
    "services/chat",
    "services/knowledge",
):
    sys.path.insert(0, str(ROOT / directory / "src"))
