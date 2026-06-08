"""View history logging utilities.

Save generated Black-Litterman view history from backtest runs
into timestamped JSON log files under the ``logs/`` directory.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
LOGS_DIR = ROOT_DIR / "logs"


def _ensure_logs_dir() -> None:
    """Create the logs directory if it does not exist."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)


def _serialize(obj: Any) -> Any:
    """Convert non-JSON-serializable objects for json.dump."""
    if isinstance(obj, (datetime,)):
        return obj.isoformat()
    if hasattr(obj, "tolist"):
        # numpy ndarray (must be checked before .item() because 1-element
        # arrays also expose .item()).
        try:
            return obj.tolist()
        except Exception:
            pass
    if hasattr(obj, "item"):
        # numpy scalar types (np.int64, np.float64, etc.)
        return obj.item()
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="replace")
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def _format_weights_history(
    weights_history: list[dict] | None,
    assets: list[str],
) -> list[dict] | None:
    """Format per-rebalance weights into asset-keyed dicts for readable JSON.

    Each input entry is expected to look like::

        {"date": <Timestamp>, "EW": ndarray, "MVO": ndarray, "BL": ndarray}

    The output replaces each ndarray with ``{asset_name: weight}``, sorted by
    weight descending so the dominant positions appear first.
    """
    if not weights_history:
        return None

    formatted: list[dict] = []
    for entry in weights_history:
        date = entry.get("date")
        out: dict[str, Any] = {
            "date": date.isoformat() if hasattr(date, "isoformat") else str(date),
        }
        for strategy in ("EW", "MVO", "BL"):
            if strategy not in entry:
                continue
            raw = entry[strategy]
            values = raw.tolist() if hasattr(raw, "tolist") else list(raw)
            paired = [
                (asset, float(values[i]))
                for i, asset in enumerate(assets)
                if i < len(values)
            ]
            paired.sort(key=lambda kv: kv[1], reverse=True)
            out[strategy] = {asset: round(w, 6) for asset, w in paired}
        formatted.append(out)

    return formatted


def log_view_history(
    views_history: list[dict],
    *,
    view_mode: str,
    phase: str,
    assets: list[str],
    backtest_metrics: dict | None = None,
    ml_training_mode: str | None = None,
    log_dir: Path | str | None = None,
    weights_history: list[dict] | None = None,
) -> Path:
    """Save the full view history from a backtest run to a JSON log file.

    Parameters
    ----------
    views_history : list[dict]
        The ``views_history`` list returned by ``backtest()``.
        Each entry is a dict with keys: date, view_names, q_values, confidences.
    view_mode : str
        The view generation mode used (rule_based, relative, ml, combined).
    phase : str
        The backtest phase (train, test, full).
    assets : list[str]
        List of asset names in the backtest.
    backtest_metrics : dict, optional
        Summary metrics: e.g. ``{"EW": {...}, "MVO": {...}, "BL": {...}}``.
    ml_training_mode : str, optional
        ML training mode (pretrained, walk_forward), if applicable.
    log_dir : Path or str, optional
        Override the default logs directory.
    weights_history : list[dict], optional
        Per-rebalance portfolio weights. Each entry should contain ``date``
        and one or more strategy keys (``EW``/``MVO``/``BL``) mapping to a
        weight vector aligned with ``assets``. Stored in the JSON output as
        per-asset weight ratios for each strategy at every rebalance cycle.

    Returns
    -------
    Path
        Path to the written log file.
    """
    out_dir = Path(log_dir) if log_dir else LOGS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"views_{view_mode}_{phase}_{timestamp}.json"
    filepath = out_dir / filename

    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "phase": phase,
        "view_mode": view_mode,
        "ml_training_mode": ml_training_mode,
        "assets": assets,
        "metrics": backtest_metrics,
        "views_history": views_history,
        "weights_history": _format_weights_history(weights_history, assets),
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(log_entry, f, indent=2, default=_serialize, ensure_ascii=False)

    return filepath
