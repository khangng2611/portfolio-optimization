"""
Plotting utilities for technical indicators and portfolio visualization.
"""

from typing import Optional

import numpy as np
import pandas as pd

from gen_view.view_generators import (
    compute_bollinger_bands,
    compute_ema,
    compute_macd,
    compute_rsi,
)


def plot_indicators(
    prices: pd.Series,
    asset_name: str,
    save_path: Optional[str] = None,
    show: bool = True,
):
    """
    Plot price with technical indicators for visualization.

    Creates a 3-panel chart:
    1. Price + MA lines + Bollinger Bands
    2. RSI
    3. MACD
    """
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(3, 1, figsize=(14, 10), sharex=True)
    fig.suptitle(f"Technical Indicators: {asset_name}", fontsize=14)

    # Panel 1: Price + MAs + Bollinger Bands
    ax1 = axes[0]
    ax1.plot(prices.index, prices.values, label="Price", color="black", linewidth=1)

    ema_10 = compute_ema(prices, 10)
    ema_30 = compute_ema(prices, 30)
    ax1.plot(prices.index, ema_10.values, label="EMA 10", color="blue", linewidth=0.8)
    ax1.plot(prices.index, ema_30.values, label="EMA 30", color="red", linewidth=0.8)

    bb_lower, bb_middle, bb_upper = [], [], []
    for i in range(len(prices)):
        if i < 20:
            bb_lower.append(np.nan)
            bb_middle.append(np.nan)
            bb_upper.append(np.nan)
        else:
            l, m, u = compute_bollinger_bands(prices.iloc[:i + 1], 20, 2.0)
            bb_lower.append(l)
            bb_middle.append(m)
            bb_upper.append(u)

    ax1.fill_between(prices.index, bb_lower, bb_upper, alpha=0.2, color="gray", label="Bollinger Bands")
    ax1.set_ylabel("Price")
    ax1.legend(loc="upper left")
    ax1.grid(True, alpha=0.3)

    # Panel 2: RSI
    ax2 = axes[1]
    rsi_values = []
    for i in range(len(prices)):
        if i < 14:
            rsi_values.append(50)
        else:
            rsi_values.append(compute_rsi(prices.iloc[:i + 1], 14))

    ax2.plot(prices.index, rsi_values, label="RSI (14)", color="purple", linewidth=1)
    ax2.axhline(y=70, color="red", linestyle="--", linewidth=0.8, label="Overbought (70)")
    ax2.axhline(y=30, color="green", linestyle="--", linewidth=0.8, label="Oversold (30)")
    ax2.axhline(y=50, color="gray", linestyle="-", linewidth=0.5)
    ax2.set_ylabel("RSI")
    ax2.set_ylim(0, 100)
    ax2.legend(loc="upper left")
    ax2.grid(True, alpha=0.3)

    # Panel 3: MACD
    ax3 = axes[2]
    macd_line, signal_line, histogram = [], [], []
    for i in range(len(prices)):
        if i < 26:
            macd_line.append(0)
            signal_line.append(0)
            histogram.append(0)
        else:
            m, s, h = compute_macd(prices.iloc[:i + 1])
            macd_line.append(m)
            signal_line.append(s)
            histogram.append(h)

    ax3.plot(prices.index, macd_line, label="MACD", color="blue", linewidth=1)
    ax3.plot(prices.index, signal_line, label="Signal", color="red", linewidth=1)
    colors = ["green" if h >= 0 else "red" for h in histogram]
    ax3.bar(prices.index, histogram, color=colors, alpha=0.5, label="Histogram")
    ax3.axhline(y=0, color="gray", linestyle="-", linewidth=0.5)
    ax3.set_ylabel("MACD")
    ax3.legend(loc="upper left")
    ax3.grid(True, alpha=0.3)

    ax3.set_xlabel("Date")

    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches="tight")
        print(f"Saved indicator chart to: {save_path}")

    if show:
        plt.show()
    else:
        plt.close()
