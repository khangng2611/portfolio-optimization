"""Shared utilities for scenario-comparison scripts.

Both ``_compare_backtests`` (rule_based / ml / ranking) and
``_compare_ranking`` (ranking vs ranking_absolute) share the same
runner, table formatting, CSV export, and plotting infrastructure.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

import backtest as bt
from config import VN30_LIST_PATH, WINDOW
from backtest._metrics import metric_summary


# ---------------------------------------------------------------------------
# Scenario runner
# ---------------------------------------------------------------------------

def run_one_mode(
    prices: pd.DataFrame,
    scenario_name: str,
    view_mode: str,
    ml_model=None,
    ranking_universe_prices: pd.DataFrame = None,
    ranking_market_prices: pd.Series = None,
) -> tuple[dict, list[dict]]:
    """Run a single backtest scenario and return (result_dict, metric_rows)."""
    result = bt.backtest(
        prices,
        view_mode=view_mode,
        ml_model=ml_model,
        ranking_universe_prices=ranking_universe_prices,
        ranking_market_prices=ranking_market_prices,
    )

    views_history = result.get("views_history", [])
    total_views = sum(len(v.get("view_names", [])) for v in views_history)
    rebalance_count = len(views_history)

    rows = [
        {
            "scenario": scenario_name,
            "strategy": strategy_name,
            **metric_summary(nav_series),
            "rebalance_count": rebalance_count,
            "total_generated_views": total_views,
        }
        for strategy_name, nav_series in [
            ("EW", result["ew_nav"]),
            ("MVO", result["mvo_nav"]),
            ("BL", result["bl_nav"]),
        ]
    ]
    return result, rows


# ---------------------------------------------------------------------------
# VN30 universe loading + alignment
# ---------------------------------------------------------------------------

def load_and_align_ranking_data(prices, phase):
    """Load VN30 universe prices and align indices with the portfolio prices.

    Returns ``(prices_aligned, ranking_universe, ranking_market)`` or raises.
    """
    ranking_universe_prices = bt.load_vn30_universe_prices(
        prices.index.min().strftime("%Y-%m-%d"),
        prices.index.max().strftime("%Y-%m-%d"),
        phase,
        WINDOW,
    )
    ranking_market_prices = bt.load_market_proxy_prices(
        prices.index.min().strftime("%Y-%m-%d"),
        prices.index.max().strftime("%Y-%m-%d"),
        phase,
        WINDOW,
    )

    common_idx = (
        prices.index
        .intersection(ranking_universe_prices.index)
        .intersection(ranking_market_prices.index)
    )
    if len(common_idx) < WINDOW + 60:
        raise ValueError(
            f"Insufficient data overlap (common rows = {len(common_idx)})"
        )

    return (
        prices.loc[common_idx],
        ranking_universe_prices.loc[common_idx],
        ranking_market_prices.loc[common_idx],
    )


# ---------------------------------------------------------------------------
# Result table printing
# ---------------------------------------------------------------------------

_RESULT_FORMATTERS = {
    "final_nav": lambda x: f"{x:.3f}",
    "ann_return": lambda x: f"{x:.2%}",
    "ann_volatility": lambda x: f"{x:.2%}",
    "sharpe": lambda x: f"{x:.3f}",
    "sortino": lambda x: f"{x:.3f}",
    "max_drawdown": lambda x: f"{x:.2%}",
    "calmar": lambda x: f"{x:.3f}",
}


def print_result_table(df: pd.DataFrame) -> None:
    """Print the full EW/MVO/BL result table."""
    print("\n" + "=" * 80)
    print("RESULT TABLE")
    print("=" * 80)
    print(df.to_string(index=False, formatters=_RESULT_FORMATTERS))


def print_bl_ranked(df: pd.DataFrame) -> pd.DataFrame:
    """Print BL scenarios ranked by Sharpe. Returns the BL-only DataFrame."""
    bl_only = (
        df[df["strategy"] == "BL"]
        .sort_values("sharpe", ascending=False)
        .reset_index(drop=True)
    )
    print("\n" + "=" * 80)
    print("BL SCENARIOS RANKED (by Sharpe)")
    print("=" * 80)
    for i, row in bl_only.iterrows():
        print(
            f"{i + 1}. {row['scenario']:<12} | "
            f"NAV={row['final_nav']:.3f} | "
            f"AnnRet={row['ann_return']:.2%} | "
            f"Vol={row['ann_volatility']:.2%} | "
            f"Sharpe={row['sharpe']:.3f} | "
            f"Sortino={row['sortino']:.3f} | "
            f"MDD={row['max_drawdown']:.2%} | "
            f"Calmar={row['calmar']:.3f}"
        )
    return bl_only


def print_head_to_head(
    df: pd.DataFrame,
    scenario_a: str,
    scenario_b: str,
    label_a: str = "",
    label_b: str = "",
    extra_keys: list | None = None,
) -> None:
    """Print a side-by-side metric comparison for two BL scenarios."""
    bl_only = df[df["strategy"] == "BL"]
    row_a = bl_only[bl_only["scenario"] == scenario_a]
    row_b = bl_only[bl_only["scenario"] == scenario_b]
    if row_a.empty or row_b.empty:
        return
    row_a, row_b = row_a.iloc[0], row_b.iloc[0]

    label_a = label_a or scenario_a
    label_b = label_b or scenario_b

    metric_keys = [
        ("final_nav", "{:.3f}"),
        ("ann_return", "{:.2%}"),
        ("ann_volatility", "{:.2%}"),
        ("sharpe", "{:.3f}"),
        ("sortino", "{:.3f}"),
        ("max_drawdown", "{:.2%}"),
        ("calmar", "{:.3f}"),
    ]
    if extra_keys:
        metric_keys.extend(extra_keys)

    print(f"\n{'=' * 80}")
    print(f"HEAD-TO-HEAD: BL ({label_a}) vs BL ({label_b})")
    print(f"{'=' * 80}")
    w = max(len(label_a), len(label_b), 14)
    print(f"  {'Metric':<22} {label_a:>{w}} {label_b:>{w}} {'Delta':>{w}}")
    print(f"  {'-'*22} {'-'*w} {'-'*w} {'-'*w}")
    for key, fmt in metric_keys:
        a_val = row_a[key]
        b_val = row_b[key]
        delta = b_val - a_val
        print(
            f"  {key:<22} {fmt.format(a_val):>{w}} "
            f"{fmt.format(b_val):>{w}} {fmt.format(delta):>{w}}"
        )

    winner = label_a if row_a["sharpe"] >= row_b["sharpe"] else label_b
    print(f"\n  >>> Winner (by Sharpe): {winner}")


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------

def save_csv(df: pd.DataFrame, output_path: str) -> None:
    """Save result DataFrame to CSV."""
    out = Path(output_path)
    if not out.is_absolute():
        out = Path.cwd() / out
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    print(f"\nSaved CSV to: {out}")


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------

def plot_scenarios(
    results_by_scenario: dict,
    scenario_labels: list[tuple[str, str]],
    output_path: str,
    suptitle: str = "Backtest NAV Comparison",
    figsize_per_panel: float = 7.0,
    show_plot: bool = True,
) -> None:
    """Generic multi-panel NAV comparison plot.

    Parameters
    ----------
    results_by_scenario : dict
        ``{scenario_key: backtest_result_dict}``.
    scenario_labels : list of (key, bl_label)
        Ordered list of scenarios to plot.
    output_path : str
        Where to save the PNG.
    suptitle : str
        Figure super-title.
    figsize_per_panel : float
        Width per panel (height is fixed at 6).
    show_plot : bool
        Whether to call ``plt.show()``.
    """
    scenario_labels = [s for s in scenario_labels if s[0] in results_by_scenario]
    n = len(scenario_labels)
    if n == 0:
        print("No scenarios to plot.")
        return

    fig, axes = plt.subplots(1, n, figsize=(figsize_per_panel * n, 6), sharey=True)
    if n == 1:
        axes = [axes]

    colors = {"EW": "#7f8c8d", "MVO": "#3498db", "BL": "#e74c3c"}

    for ax, (scenario_key, bl_label) in zip(axes, scenario_labels):
        result = results_by_scenario[scenario_key]
        ax.plot(result["ew_nav"].index, result["ew_nav"].values,
                label="EW", color=colors["EW"], alpha=0.7)
        ax.plot(result["mvo_nav"].index, result["mvo_nav"].values,
                label="MVO", color=colors["MVO"], alpha=0.7)
        ax.plot(result["bl_nav"].index, result["bl_nav"].values,
                label=bl_label, color=colors["BL"], linewidth=2)
        ax.set_title(scenario_key, fontsize=12, fontweight="bold")
        ax.grid(True, alpha=0.3)
        ax.set_xlabel("Date")

    axes[0].set_ylabel("NAV (initial = 1.0)")
    handles, labels = axes[-1].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=3, fontsize=10)
    fig.suptitle(suptitle, fontsize=13)
    plt.tight_layout(rect=[0, 0, 1, 0.92])

    out_path = Path(output_path)
    if not out_path.is_absolute():
        out_path = Path.cwd() / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_path, dpi=160, bbox_inches="tight")
    print(f"Saved comparison plot to: {out_path}")

    if show_plot:
        plt.show()
    else:
        plt.close(fig)
