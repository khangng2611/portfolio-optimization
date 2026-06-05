"""Plot real (cumulative) return of individual assets from assets.json.

Usage
-----
    # Default: plot all default-selection assets for the "full" phase
    python -m utils.plot_asset_returns

    # Specific phase
    python -m utils.plot_asset_returns --phase test

    # Specific assets
    python -m utils.plot_asset_returns --assets E1VFVN30,GOLD

    # Save to file instead of showing
    python -m utils.plot_asset_returns --save reports/real_return.png

Can also be imported and used programmatically:

    from utils.plot_asset_returns import plot_asset_returns

    plot_asset_returns(phase="train", assets=["E1VFVN30", "GOLD"])
"""

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from config import BACKTEST_DATA_MODE, PHASE_PERIODS, TRADING_DAYS_PER_YEAR
from utils.data_loader import build_price_table, load_assets_config


def _compute_cumulative_return(prices: pd.DataFrame) -> pd.DataFrame:
    """Compute cumulative return (base = 1.0) from a price table."""
    return prices / prices.iloc[0]


def _compute_drawdown(prices: pd.DataFrame) -> pd.DataFrame:
    """Compute drawdown series from a price table."""
    cummax = prices.cummax()
    return prices / cummax - 1.0


def plot_asset_returns(
    phase: str = "full",
    assets: list[str] | None = None,
    assets_config: str | Path | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    save: str | Path | None = None,
    show: bool = True,
    figsize: tuple[int, int] = (12, 6),
) -> plt.Figure:
    """Plot real (cumulative) return for each asset.

    Parameters
    ----------
    phase : str
        Phase period: "train", "test", or "full".
    assets : list[str], optional
        Subset of assets to plot.  Defaults to ``default_selection`` in
        ``assets.json``.
    assets_config : str or Path, optional
        Path to assets JSON config file.
    start_date, end_date : str, optional
        Override phase period dates (both required if either is given).
    save : str or Path, optional
        File path to save the figure.  Directory is created if needed.
    show : bool
        Whether to display the figure interactively.
    figsize : tuple
        Figure size in inches.

    Returns
    -------
    matplotlib.figure.Figure
    """
    # Resolve date range
    if start_date or end_date:
        if not start_date or not end_date:
            raise ValueError(
                "When overriding dates, both start_date and end_date are required"
            )
    else:
        start_date, end_date = PHASE_PERIODS[phase]

    # Load asset configuration
    resolved_assets = load_assets_config(
        config_path=assets_config,
        selected_assets=assets,
    )

    # Build aligned price table (reuse existing data_loader logic)
    prices = build_price_table(
        start_date=start_date,
        end_date=end_date,
        assets=resolved_assets,
        phase=phase,
        data_mode=BACKTEST_DATA_MODE,
        window=1,  # minimal window — we only need prices
    )

    # Cumulative return
    cum_ret = _compute_cumulative_return(prices)

    # --- Summary stats --------------------------------------------------
    total_ret = prices.iloc[-1] / prices.iloc[0] - 1
    n_days = len(prices)
    ann_ret = (1 + total_ret) ** (TRADING_DAYS_PER_YEAR / n_days) - 1
    ann_vol = prices.pct_change().dropna().std() * (TRADING_DAYS_PER_YEAR ** 0.5)

    # --- Plot -----------------------------------------------------------
    fig, ax = plt.subplots(figsize=figsize)

    for col in cum_ret.columns:
        ax.plot(cum_ret.index, cum_ret[col].values, label=col, linewidth=1.4)

    ax.set_title(
        f"Real Return by Asset  ({phase}: {start_date} → {end_date})",
        fontsize=13,
    )
    ax.set_ylabel("Cumulative Return (base = 1.0)")
    ax.set_xlabel("Date")
    ax.legend(loc="best", fontsize=9)
    ax.grid(True, alpha=0.3)
    ax.axhline(y=1.0, color="grey", linestyle="--", linewidth=0.7)

    # Annotate summary in the plot
    summary_lines = []
    for asset_name in cum_ret.columns:
        summary_lines.append(
            f"{asset_name}: ret={total_ret[asset_name]:+.1%}, "
            f"ann={ann_ret[asset_name]:+.1%}, "
            f"vol={ann_vol[asset_name]:.1%}"
        )
    summary_text = "\n".join(summary_lines)
    ax.text(
        0.01,
        0.01,
        summary_text,
        transform=ax.transAxes,
        fontsize=8,
        verticalalignment="bottom",
        fontfamily="monospace",
        bbox=dict(boxstyle="round,pad=0.4", facecolor="white", alpha=0.8),
    )

    plt.tight_layout()

    # Save
    if save:
        save_path = Path(save)
        if not save_path.is_absolute():
            save_path = Path.cwd() / save_path
        save_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_path, dpi=160, bbox_inches="tight")
        print(f"Saved plot to: {save_path}")

    if show:
        plt.show()
    else:
        plt.close(fig)

    return fig


def main():
    parser = argparse.ArgumentParser(
        description="Plot real (cumulative) return of assets from assets.json",
    )
    parser.add_argument(
        "--phase",
        choices=list(PHASE_PERIODS.keys()),
        default="full",
        help="Data phase: train/test/full (default: full)",
    )
    parser.add_argument(
        "--start-date",
        default=None,
        help="Override start date YYYY-MM-DD",
    )
    parser.add_argument(
        "--end-date",
        default=None,
        help="Override end date YYYY-MM-DD",
    )
    parser.add_argument(
        "--assets-config",
        default=None,
        help="Path to assets JSON config (default: assets.json)",
    )
    parser.add_argument(
        "--assets",
        default=None,
        help="Comma-separated asset list, e.g. E1VFVN30,GOLD,DCDS",
    )
    parser.add_argument(
        "--save",
        default=None,
        help="Save plot to file path, e.g. reports/real_return.png",
    )
    parser.add_argument(
        "--no-show",
        action="store_true",
        help="Do not display the plot interactively",
    )
    args = parser.parse_args()

    selected_assets = None
    if args.assets:
        selected_assets = [
            a.strip() for a in args.assets.split(",") if a.strip()
        ]

    plot_asset_returns(
        phase=args.phase,
        assets=selected_assets,
        assets_config=args.assets_config,
        start_date=args.start_date,
        end_date=args.end_date,
        save=args.save,
        show=not args.no_show,
    )


if __name__ == "__main__":
    main()
