import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

import backtest as bt
from config import PHASE_PERIODS
from utils.data_loader import build_price_table, load_assets_config, resolve_period


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Generate inspection plots: EW NAV vs each asset NAV for "
            "rule_based and xgboost view-generation modes."
        )
    )
    parser.add_argument(
        "--phase",
        choices=list(PHASE_PERIODS.keys()),
        default="test",
        help="Backtest phase (train/test/full)",
    )
    parser.add_argument("--start-date", default=None, help="Override start date YYYY-MM-DD")
    parser.add_argument("--end-date", default=None, help="Override end date YYYY-MM-DD")
    parser.add_argument(
        "--assets-config",
        default=None,
        help="Path to assets config JSON (default: assets.json)",
    )
    parser.add_argument(
        "--assets",
        default=None,
        help="Comma-separated assets, e.g. E1VFVN30,GOLD,DCDS,MBBOND",
    )
    parser.add_argument(
        "--output-dir",
        default="reports",
        help="Directory to save generated plots",
    )
    parser.add_argument(
        "--no-show",
        action="store_true",
        help="Do not open interactive plot windows",
    )
    return parser.parse_args()


def build_bl_decomposition(result: dict) -> tuple[pd.Series, pd.DataFrame, pd.DataFrame]:
    """
    Build BL return decomposition by asset using realized weights.

    Returns
    -------
    tuple
        bl_daily_ret, contrib_df, weights_df
    """
    assets = result["assets"]
    returns = result["returns"]
    # bl_weights_hist has one row per realized return step from returns.iloc[WINDOW:]
    ret_slice = returns.iloc[bt.WINDOW:]

    weights_df = pd.DataFrame(
        result["bl_weights_hist"],
        index=ret_slice.index,
        columns=assets,
    )
    contrib_df = weights_df * ret_slice[assets]
    bl_daily_ret = contrib_df.sum(axis=1)
    return bl_daily_ret, contrib_df, weights_df


def plot_bl_inspection(
    ew_nav: pd.Series,
    bl_nav: pd.Series,
    contrib_df: pd.DataFrame,
    weights_df: pd.DataFrame,
    method_name: str,
    phase: str,
    output_path: Path,
    show_plot: bool,
):
    fig, axes = plt.subplots(3, 1, figsize=(14, 12), sharex=True)

    # 1) NAV comparison
    axes[0].plot(ew_nav.index, ew_nav.values, label="EW NAV", linewidth=2.2)
    axes[0].plot(bl_nav.index, bl_nav.values, label=f"BL NAV ({method_name})", linewidth=2.2)
    axes[0].set_ylabel("NAV")
    axes[0].set_title(f"BL Inspection ({method_name}, phase={phase})")
    axes[0].grid(True, alpha=0.3)
    axes[0].legend(loc="best")

    # 2) Cumulative contribution by asset: cumsum(w_t * r_t)
    cum_contrib = contrib_df.cumsum()
    for col in cum_contrib.columns:
        axes[1].plot(cum_contrib.index, cum_contrib[col], label=col, linewidth=1.8)
    axes[1].axhline(0.0, color="black", linewidth=1.0, alpha=0.7)
    axes[1].set_ylabel("Cumulative contribution")
    axes[1].grid(True, alpha=0.3)
    axes[1].legend(loc="best", ncol=2)

    # 3) BL weights over time (stacked area)
    axes[2].stackplot(
        weights_df.index,
        *[weights_df[c].values for c in weights_df.columns],
        labels=list(weights_df.columns),
        alpha=0.85,
    )
    axes[2].set_ylabel("Weight")
    axes[2].set_xlabel("Date")
    axes[2].set_ylim(0, 1.0)
    axes[2].grid(True, alpha=0.3)
    axes[2].legend(loc="upper left", ncol=2)

    plt.tight_layout()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=170, bbox_inches="tight")
    print(f"Saved plot: {output_path}")

    if show_plot:
        plt.show()
    else:
        plt.close(fig)


def main():
    args = parse_args()
    start_date, end_date = resolve_period(args, PHASE_PERIODS, args.phase)

    selected_assets = None
    if args.assets:
        selected_assets = [item.strip() for item in args.assets.split(",") if item.strip()]

    assets = load_assets_config(
        config_path=args.assets_config,
        selected_assets=selected_assets,
    )

    prices = build_price_table(
        start_date=start_date,
        end_date=end_date,
        assets=assets,
        phase=args.phase,
        data_mode=bt.BACKTEST_DATA_MODE,
        window=bt.WINDOW,
    )

    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = Path.cwd() / output_dir

    # 1) rule_based
    print("Running backtest for rule_based...")
    result_rule = bt.backtest(
        prices,
        view_mode="rule_based",
        ml_model=None,
    )
    ew_rule = result_rule["ew_nav"]
    bl_rule = result_rule["bl_nav"]
    _, contrib_rule, weights_rule = build_bl_decomposition(result_rule)
    plot_bl_inspection(
        ew_nav=ew_rule,
        bl_nav=bl_rule,
        contrib_df=contrib_rule,
        weights_df=weights_rule,
        method_name="rule_based",
        phase=args.phase,
        output_path=output_dir / "inspect_bl_decomp_rule_based.png",
        show_plot=not args.no_show,
    )

    # Save detailed tables for drill-down
    contrib_rule.to_csv(output_dir / "inspect_bl_contrib_rule_based.csv")
    weights_rule.to_csv(output_dir / "inspect_bl_weights_rule_based.csv")

    # 2) xgboost
    print("Running backtest for xgboost...")
    xgb_model = bt.load_ml_model("xgboost")
    result_xgb = bt.backtest(
        prices,
        view_mode="ml",
        ml_model=xgb_model,
    )
    ew_xgb = result_xgb["ew_nav"]
    bl_xgb = result_xgb["bl_nav"]
    _, contrib_xgb, weights_xgb = build_bl_decomposition(result_xgb)
    plot_bl_inspection(
        ew_nav=ew_xgb,
        bl_nav=bl_xgb,
        contrib_df=contrib_xgb,
        weights_df=weights_xgb,
        method_name="xgboost",
        phase=args.phase,
        output_path=output_dir / "inspect_bl_decomp_xgboost.png",
        show_plot=not args.no_show,
    )

    contrib_xgb.to_csv(output_dir / "inspect_bl_contrib_xgboost.csv")
    weights_xgb.to_csv(output_dir / "inspect_bl_weights_xgboost.csv")


if __name__ == "__main__":
    main()
