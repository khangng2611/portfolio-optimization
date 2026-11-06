"""Record transitive runtime constraints from a verified software environment."""

import importlib.metadata as metadata
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[1]
LOCAL = {
    "portfolio-service-observability",
    "portfolio-service",
    "portfolio-quant-service",
    "portfolio-contracts",
    "portfolio-service-auth",
    "portfolio-core",
    "portfolio-market-service",
    "portfolio-ml-platform",
}
for service, distribution in {
    "portfolio": "portfolio-service",
    "quant-serving": "portfolio-quant-service",
    "market-data": "portfolio-market-service",
    "ml-platform": "portfolio-ml-platform",
}.items():
    seen, todo = set(), [(distribution, set())]
    while todo:
        name, extras = todo.pop()
        name = canonicalize_name(name)
        key = (name, tuple(sorted(extras)))
        if key in seen:
            continue
        seen.add(key)
        for line in metadata.requires(name) or []:
            requirement = Requirement(line)
            if requirement.marker is None or any(
                requirement.marker.evaluate({"extra": extra}) for extra in extras | {""}
            ):
                todo.append((requirement.name, set(requirement.extras)))
    lines = sorted(
        {
            canonicalize_name(name) + "==" + metadata.version(name)
            for name, _ in seen
            if name not in LOCAL
        }
    )
    if service in ("quant-serving", "ml-platform"):
        # Linux serving uses the CPU wheel, avoiding the optional CUDA/NCCL runtime.
        lines = sorted(
            [
                line
                for line in lines
                if not line.startswith(("xgboost==", "xgboost-cpu=="))
            ]
            + [
                "xgboost-cpu==3.2.0; sys_platform == 'linux'",
                "xgboost==3.2.0; sys_platform != 'linux'",
            ]
        )
    (ROOT / "services" / service / "requirements.lock").write_text(
        "# Runtime constraints resolved with Python 3.12. Use pip -c alongside service packages.\n"
        + "\n".join(lines)
        + "\n"
    )
    print(service, len(lines), "runtime constraints")
