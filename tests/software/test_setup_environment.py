"""Environment readiness honors platform-specific dependency constraints."""

import importlib.util
from pathlib import Path


def test_platform_marked_locks_only_check_current_runtime(tmp_path, monkeypatch):
    path = Path(__file__).resolve().parents[2] / "scripts/setup_software.py"
    spec = importlib.util.spec_from_file_location("software_setup", path)
    setup = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(setup)
    lock = tmp_path / "requirements.lock"
    lock.write_text(
        "numpy==2.2.6\nxgboost-cpu==3.2.0; sys_platform == 'linux'\nxgboost==3.2.0; sys_platform != 'linux'\n"
    )
    monkeypatch.setattr(setup, "LOCK", lock)
    monkeypatch.setattr(setup, "VENV", tmp_path)
    monkeypatch.setattr(setup, "PYTHON", Path(__import__("sys").executable))
    captured = []

    def run(command, **kwargs):
        captured.append(command)
        return ""

    monkeypatch.setattr(setup, "run", run)
    assert setup.python_environment_ready()
    import json

    expected = json.loads(captured[0][-2])
    from packaging.markers import Marker

    # Execute the actual filtering expression generated for the target runtime.
    expression = captured[0][2].split("expected=", 2)[2].split("; assert", 1)[0]
    filtered = eval(expression, {"expected": expected, "Marker": Marker})
    assert all(";" not in v for v in filtered.values())
    assert ("xgboost-cpu" in filtered) != ("xgboost" in filtered)
