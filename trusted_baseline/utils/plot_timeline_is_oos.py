"""
Plot IS/OOS Timeline with Rebalance / Retrain / Reselect markers — Slide 15
============================================================================
Generates a horizontal timeline bar showing:
- IS (2020-01 → 2023-10) in blue
- OOS (2023-10 → 2026-03) in orange
- Markers for rebalance (every 5 sessions), retrain (every 20), reselect (every 60)

Usage:
    cd <project_root>
    python utils/plot_timeline_is_oos.py

Output:
    reports/BC2_De_Cuong_Luan_Van/figures/timeline_is_oos.png
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.dates as mdates
import pandas as pd
import numpy as np
from datetime import datetime

from config import PHASE_PERIODS, REBALANCE_FREQ, RANKING_RETRAIN_FREQUENCY, RANKING_RESELECT_FREQUENCY

# ─── Configuration ───────────────────────────────────────────────────────────
OUTPUT_PATH = PROJECT_ROOT / "reports" / "BC2_De_Cuong_Luan_Van" / "figures" / "timeline_is_oos.png"
FIGSIZE = (14, 5)
DPI = 200

# Dates
IS_START = datetime(2020, 1, 2)
IS_END = datetime(2023, 10, 31)
OOS_START = datetime(2023, 10, 31)
OOS_END = datetime(2026, 3, 31)

# Colors
IS_COLOR = "#4A90D9"
OOS_COLOR = "#F5A623"
REBALANCE_COLOR = "#8BC34A"
RETRAIN_COLOR = "#9C27B0"
RESELECT_COLOR = "#E91E63"


def generate_trading_dates(start, end, freq_days=1):
    """Generate approximate trading dates (weekdays only)."""
    dates = pd.bdate_range(start=start, end=end)
    return dates


def main():
    fig, ax = plt.subplots(figsize=FIGSIZE, facecolor="white")

    # ── Draw IS and OOS bars ──
    bar_y = 0.5
    bar_height = 0.3

    # IS bar
    is_width = mdates.date2num(IS_END) - mdates.date2num(IS_START)
    ax.barh(
        bar_y, is_width, left=mdates.date2num(IS_START),
        height=bar_height, color=IS_COLOR, alpha=0.7, edgecolor="white", linewidth=0.5,
        label=f"In-Sample (01/2020 → 10/2023, ~950 phiên)"
    )

    # OOS bar
    oos_width = mdates.date2num(OOS_END) - mdates.date2num(OOS_START)
    ax.barh(
        bar_y, oos_width, left=mdates.date2num(OOS_START),
        height=bar_height, color=OOS_COLOR, alpha=0.7, edgecolor="white", linewidth=0.5,
        label=f"Out-of-Sample (10/2023 → 03/2026, ~600 phiên)"
    )

    # IS/OOS text labels
    is_mid = mdates.date2num(IS_START) + is_width / 2
    oos_mid = mdates.date2num(OOS_START) + oos_width / 2
    ax.text(is_mid, bar_y, "IN-SAMPLE\n~950 phiên", ha="center", va="center",
            fontsize=12, fontweight="bold", color="white")
    ax.text(oos_mid, bar_y, "OUT-OF-SAMPLE\n~600 phiên", ha="center", va="center",
            fontsize=12, fontweight="bold", color="white")

    # ── Generate trading dates for marker placement ──
    trading_dates = generate_trading_dates(IS_START, OOS_END)

    # Marker positions (below the bar)
    marker_y_rebalance = 0.15
    marker_y_retrain = 0.0
    marker_y_reselect = -0.15

    # Rebalance markers (every 5 sessions) — show only a subset to avoid clutter
    rebalance_dates = trading_dates[::REBALANCE_FREQ]
    # Only show every 10th rebalance marker to avoid visual overload
    rebalance_show = rebalance_dates[::10]
    ax.scatter(
        [mdates.date2num(d) for d in rebalance_show],
        [marker_y_rebalance] * len(rebalance_show),
        marker="|", s=30, color=REBALANCE_COLOR, alpha=0.6, linewidths=0.8,
        zorder=3,
    )

    # Retrain markers (every 20 sessions)
    retrain_dates = trading_dates[::RANKING_RETRAIN_FREQUENCY]
    ax.scatter(
        [mdates.date2num(d) for d in retrain_dates],
        [marker_y_retrain] * len(retrain_dates),
        marker="^", s=25, color=RETRAIN_COLOR, alpha=0.7, linewidths=0.5,
        zorder=3,
    )

    # Reselect markers (every 60 sessions)
    reselect_dates = trading_dates[::RANKING_RESELECT_FREQUENCY]
    ax.scatter(
        [mdates.date2num(d) for d in reselect_dates],
        [marker_y_reselect] * len(reselect_dates),
        marker="D", s=40, color=RESELECT_COLOR, alpha=0.9, linewidths=0.5,
        zorder=3,
    )

    # ── Annotation lines for frequency labels ──
    ax.axhline(y=marker_y_rebalance, color=REBALANCE_COLOR, alpha=0.2, linewidth=0.5, linestyle="--")
    ax.axhline(y=marker_y_retrain, color=RETRAIN_COLOR, alpha=0.2, linewidth=0.5, linestyle="--")
    ax.axhline(y=marker_y_reselect, color=RESELECT_COLOR, alpha=0.2, linewidth=0.5, linestyle="--")

    # Right-side labels for each marker row
    label_x = mdates.date2num(OOS_END) + 15
    ax.text(label_x, marker_y_rebalance, f"Rebalance\n(mỗi {REBALANCE_FREQ} phiên ≈ 1 tuần)",
            va="center", fontsize=9, color=REBALANCE_COLOR, fontweight="bold")
    ax.text(label_x, marker_y_retrain, f"Retrain XGBoost\n(mỗi {RANKING_RETRAIN_FREQUENCY} phiên ≈ 1 tháng)",
            va="center", fontsize=9, color=RETRAIN_COLOR, fontweight="bold")
    ax.text(label_x, marker_y_reselect, f"Reselect K=5\n(mỗi {RANKING_RESELECT_FREQUENCY} phiên ≈ 3 tháng)",
            va="center", fontsize=9, color=RESELECT_COLOR, fontweight="bold")

    # ── Split line ──
    split_x = mdates.date2num(IS_END)
    ax.axvline(x=split_x, color="#333333", linewidth=2, linestyle="-", alpha=0.8, zorder=4)
    ax.text(split_x, bar_y + bar_height / 2 + 0.05, "Split\n10/2023",
            ha="center", va="bottom", fontsize=9, fontweight="bold", color="#333333")

    # ── Title ──
    ax.set_title(
        "Walk-forward Backtest Timeline: IS / OOS + Rebalance / Retrain / Reselect",
        fontsize=14, fontweight="bold", pad=15,
    )

    # ── Axis formatting ──
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.xaxis.set_minor_locator(mdates.MonthLocator(bymonth=[1, 4, 7, 10]))

    ax.set_xlim(mdates.date2num(datetime(2019, 11, 1)), mdates.date2num(datetime(2026, 6, 1)))
    ax.set_ylim(-0.4, 0.85)
    ax.set_yticks([])
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.grid(axis="x", alpha=0.3, linestyle="--")

    # ── Info box ──
    info_text = (
        "Portfolio = K=5 stocks (dynamic) + GOLD + MBBOND\n"
        "Universe = VN30 (30 stocks)\n"
        f"Rebalance freq = {REBALANCE_FREQ} sessions\n"
        f"Retrain freq  = {RANKING_RETRAIN_FREQUENCY} sessions\n"
        f"Reselect freq = {RANKING_RESELECT_FREQUENCY} sessions"
    )
    props = dict(boxstyle="round,pad=0.4", facecolor="#F5F5F5", edgecolor="#CCCCCC", alpha=0.9)
    ax.text(0.01, 0.98, info_text, transform=ax.transAxes,
            fontsize=9, verticalalignment="top", bbox=props, family="monospace")

    plt.tight_layout()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT_PATH, dpi=DPI, bbox_inches="tight", facecolor="white")
    print(f"✅ Saved: {OUTPUT_PATH}")
    print(f"   Resolution: {FIGSIZE[0]*DPI} × {FIGSIZE[1]*DPI} px")
    plt.close(fig)


if __name__ == "__main__":
    main()
