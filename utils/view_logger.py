"""View history logging utilities.

Save generated Black-Litterman view history from backtest runs
into timestamped JSON log files under the ``logs/`` directory.
Optionally save the NAV comparison plot under ``logs/plots/``.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import matplotlib

from config import RISK_FREE_RATE_ANNUAL, TRADING_DAYS_PER_YEAR
matplotlib.use("Agg")  # non-interactive backend for headless saving
import matplotlib.pyplot as plt

ROOT_DIR = Path(__file__).resolve().parents[1]
LOGS_DIR = ROOT_DIR / "logs"
PLOTS_DIR = LOGS_DIR / "plots"


def _ensure_logs_dir() -> None:
    """Create the logs and plots directories if they do not exist."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)


def _compute_nav_metrics(nav_series) -> dict:
    """Return final NAV, annualised Sharpe, and MDD for a NAV series."""
    import numpy as np

    ret = nav_series.pct_change().dropna()
    trading_days = TRADING_DAYS_PER_YEAR
    rf_daily = (1 + RISK_FREE_RATE_ANNUAL) ** (1 / trading_days) - 1

    final_nav = float(nav_series.iloc[-1])

    if len(ret) > 0 and ret.std() > 0:
        excess = ret - rf_daily
        sharpe = float(np.sqrt(trading_days) * excess.mean() / excess.std())
    else:
        sharpe = float("nan")

    peak = nav_series.cummax()
    mdd = float((nav_series / peak - 1).min())

    return {"final_nav": final_nav, "sharpe": sharpe, "mdd": mdd}


def _generate_and_save_nav_plot(
    *,
    ew_nav,
    mvo_nav,
    bl_nav,
    view_mode: str,
    phase: str,
    timestamp: str,
    plots_dir: Path | None = None,
) -> Path | None:
    """Generate the EW/MVO/BL NAV comparison figure and save it to disk.

    The figure has two rows:
    * Top row  – NAV curves for EW, MVO, BL.
    * Bottom row – bar charts for Final NAV, Sharpe ratio, and Max Drawdown.

    Parameters
    ----------
    ew_nav, mvo_nav, bl_nav : pd.Series
        NAV time series for each strategy.
    view_mode : str
        View generation mode (used in the filename and title).
    phase : str
        Backtest phase (train / test / full).
    timestamp : str
        Timestamp string already computed for the JSON log (e.g. ``YYYYMMDD_HHMMSS``).
    plots_dir : Path, optional
        Override the default plots directory.

    Returns
    -------
    Path | None
        Path to the saved PNG file, or ``None`` if saving failed.
    """
    out_dir = Path(plots_dir) if plots_dir else PLOTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    filename = f"nav_{view_mode}_{phase}_{timestamp}.png"
    filepath = out_dir / filename

    try:
        import numpy as np

        metrics = {
            "EW": _compute_nav_metrics(ew_nav),
            "MVO": _compute_nav_metrics(mvo_nav),
            f"BL\n({view_mode})": _compute_nav_metrics(bl_nav),
        }
        labels = list(metrics.keys())
        colors = ["#4C72B0", "#DD8452", "#55A868"]

        fig = plt.figure(figsize=(14, 9))
        gs = fig.add_gridspec(2, 3, height_ratios=[2, 1], hspace=0.45, wspace=0.35)

        # ── Top row: full-width NAV line chart ──────────────────────────────
        ax_nav = fig.add_subplot(gs[0, :])
        ax_nav.plot(ew_nav.index, ew_nav.values, label="EW", linewidth=1.5, color=colors[0])
        ax_nav.plot(mvo_nav.index, mvo_nav.values, label="MVO", linewidth=1.5, color=colors[1])
        ax_nav.plot(bl_nav.index, bl_nav.values, label=f"BL ({view_mode})", linewidth=1.5, color=colors[2])
        ax_nav.set_title(f"Backtest ({phase}): EW vs MVO vs BL ({view_mode})", fontsize=13)
        ax_nav.set_ylabel("NAV (initial = 1.0)")
        ax_nav.grid(True, alpha=0.3)
        ax_nav.legend(loc="best")

        # ── Bottom row: bar charts for Final NAV, Sharpe, MDD ───────────────
        metric_keys = [
            ("final_nav", "Final NAV", "{:.2f}"),
            ("sharpe",    "Sharpe Ratio", "{:.3f}"),
            ("mdd",       "Max Drawdown", "{:.2%}"),
        ]
        x = np.arange(len(labels))
        bar_width = 0.5

        for col_idx, (key, title, fmt) in enumerate(metric_keys):
            ax = fig.add_subplot(gs[1, col_idx])
            values = [metrics[lbl][key] for lbl in labels]
            bar_colors = [
                colors[i] if not (key == "mdd" and v == min(values)) else "#C44E52"
                for i, v in enumerate(values)
            ]
            bars = ax.bar(x, values, width=bar_width, color=bar_colors, edgecolor="white")
            ax.set_title(title, fontsize=10)
            ax.set_xticks(x)
            ax.set_xticklabels([lbl.replace("\n", "\n") for lbl in labels], fontsize=9)
            ax.grid(True, axis="y", alpha=0.3)
            # Annotate bar values
            for bar, v in zip(bars, values):
                label_txt = fmt.format(v)
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    bar.get_height() * (1.01 if v >= 0 else 0.99),
                    label_txt,
                    ha="center",
                    va="bottom" if v >= 0 else "top",
                    fontsize=8,
                    fontweight="bold",
                )

        fig.savefig(filepath, dpi=150, bbox_inches="tight")
        plt.close(fig)
    except Exception as exc:
        print(f"[view_logger] WARNING: Could not save plot: {exc}")
        return None

    return filepath


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

    Notes
    -----
    * The EW strategy is omitted because it always produces equal weights.
    * Assets with a weight of exactly 0 are excluded from the output.
    """
    if not weights_history:
        return None

    formatted: list[dict] = []
    for entry in weights_history:
        date = entry.get("date")
        out: dict[str, Any] = {
            "date": date.isoformat() if hasattr(date, "isoformat") else str(date),
        }
        for strategy in ("MVO", "BL"):
            if strategy not in entry:
                continue
            raw = entry[strategy]
            values = raw.tolist() if hasattr(raw, "tolist") else list(raw)
            paired = [
                (asset, float(values[i]))
                for i, asset in enumerate(assets)
                if i < len(values) and float(values[i]) >= 0.000001
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
    ew_nav=None,
    mvo_nav=None,
    bl_nav=None,
) -> tuple[Path, Path | None]:
    """Save the full view history from a backtest run to a JSON log file
    and (optionally) save the NAV comparison plot.

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
    ew_nav, mvo_nav, bl_nav : pd.Series, optional
        NAV time series for each strategy. If all three are provided, a
        NAV comparison plot is generated and saved to ``logs/plots/``.

    Returns
    -------
    tuple[Path, Path | None]
        (json_log_path, plot_path). ``plot_path`` is ``None`` when NAV
        series are not provided or saving fails.
    """
    _ensure_logs_dir()
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

    # Save NAV plot if all three series are provided
    plot_path = None
    if ew_nav is not None and mvo_nav is not None and bl_nav is not None:
        plot_path = _generate_and_save_nav_plot(
            ew_nav=ew_nav,
            mvo_nav=mvo_nav,
            bl_nav=bl_nav,
            view_mode=view_mode,
            phase=phase,
            timestamp=timestamp,
        )

    return filepath, plot_path
