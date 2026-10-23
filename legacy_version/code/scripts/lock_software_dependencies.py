"""Record transitive runtime constraints from a verified software environment."""

import importlib.metadata as metadata
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[1]
LOCAL = {
    "portfolio-service",
    "portfolio-quant-service",
    "portfolio-contracts",
    "portfolio-service-auth",
    "portfolio-core",
}
for service, distribution in {
    "portfolio": "portfolio-service",
    "quant-serving": "portfolio-quant-service",
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
    (ROOT / "services" / service / "requirements.lock").write_text(
        "# Runtime constraints resolved with Python 3.12. Use pip -c alongside service packages.\n"
        + "\n".join(lines)
        + "\n"
    )
    print(service, len(lines), "runtime constraints")
