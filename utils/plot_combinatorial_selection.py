"""
Plot Combinatorial Stock Selection 
=====================================================
Generates a 2D scatter plot showing K=5 selected medoids (highlighted)
among all VN30 stocks. Uses real price data + MDS projection.

Usage:
    cd <project_root>
    python reports/BC2_De_Cuong_Luan_Van/figures/plot_combinatorial_selection.py

Output:
    reports/BC2_De_Cuong_Luan_Van/figures/combinatorial_selection.png
"""

import sys
from pathlib import Path

# Ensure project root is importable
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch
from sklearn.manifold import MDS

from gen_view.ranking.stock_selection import compute_distance_matrix, select_representatives


# ─── Configuration ───────────────────────────────────────────────────────────
K = 5
OUTPUT_PATH = PROJECT_ROOT / "reports" / "BC2_De_Cuong_Luan_Van" / "figures" / "combinatorial_selection.png"
FIGSIZE = (12, 8)  # landscape for slide 16:9
DPI = 200
FONT_SIZE_TICKER = 9
FONT_SIZE_TITLE = 16
FONT_SIZE_SUBTITLE = 11


def load_vn30_prices() -> pd.DataFrame:
    """Load full-period price data for all VN30 stocks."""
    vn30_list_path = PROJECT_ROOT / "datasets" / "vn30_list.txt"
    with open(vn30_list_path) as f:
        tickers = [line.strip() for line in f if line.strip()]

    frames = {}
    for ticker in tickers:
        csv_path = PROJECT_ROOT / "datasets" / "stocks" / "train" / f"{ticker}_train.csv"
        if csv_path.exists():
            df = pd.read_csv(csv_path, parse_dates=["date"])
            df = df.set_index("date").sort_index()
            frames[ticker] = df["close"]

    prices = pd.DataFrame(frames).dropna()
    return prices


def project_to_2d(distance_matrix: np.ndarray) -> np.ndarray:
    """Project stocks into 2D using Multidimensional Scaling (MDS)."""
    mds = MDS(
        n_components=2,
        dissimilarity="precomputed",
        random_state=42,
        normalized_stress="auto",
        max_iter=500,
    )
    coords = mds.fit_transform(distance_matrix)
    return coords


def plot_selection(
    coords: np.ndarray,
    stock_names: list[str],
    selected: list[str],
    distance_matrix: np.ndarray,
    output_path: Path,
):
    """Create the scatter plot with medoid highlighting and cluster lines."""
    fig, ax = plt.subplots(figsize=FIGSIZE, facecolor="white")

    selected_set = set(selected)
    selected_indices = [i for i, name in enumerate(stock_names) if name in selected_set]
    non_selected_indices = [i for i, name in enumerate(stock_names) if name not in selected_set]

    # ── Draw connection lines (non-selected → nearest medoid) ──
    for i in non_selected_indices:
        # Find nearest medoid
        nearest_medoid_idx = min(
            selected_indices, key=lambda m: distance_matrix[i, m]
        )
        ax.plot(
            [coords[i, 0], coords[nearest_medoid_idx, 0]],
            [coords[i, 1], coords[nearest_medoid_idx, 1]],
            color="#CCCCCC",
            linewidth=0.8,
            linestyle="--",
            alpha=0.6,
            zorder=1,
        )

    # ── Plot non-selected stocks ──
    ax.scatter(
        coords[non_selected_indices, 0],
        coords[non_selected_indices, 1],
        s=120,
        c="#6C8EBF",
        edgecolors="#2D4F7C",
        linewidths=1.2,
        alpha=0.85,
        zorder=3,
        label=f"VN30 stocks (N={len(stock_names)})",
    )

    # ── Plot selected medoids (larger, different color) ──
    ax.scatter(
        coords[selected_indices, 0],
        coords[selected_indices, 1],
        s=350,
        c="#FF6B35",
        edgecolors="#B33F00",
        linewidths=2.0,
        alpha=1.0,
        zorder=5,
        marker="*",
        label=f"Selected representatives (K={K})",
    )

    # ── Label all stocks ──
    for i, name in enumerate(stock_names):
        is_selected = name in selected_set
        fontweight = "bold" if is_selected else "normal"
        fontsize = FONT_SIZE_TICKER + 1 if is_selected else FONT_SIZE_TICKER
        color = "#B33F00" if is_selected else "#333333"
        offset_y = 12 if is_selected else 8

        ax.annotate(
            name,
            (coords[i, 0], coords[i, 1]),
            textcoords="offset points",
            xytext=(0, offset_y),
            ha="center",
            fontsize=fontsize,
            fontweight=fontweight,
            color=color,
            zorder=6,
        )

    # ── Draw "cluster" ellipses (convex hull-ish) around each medoid group ──
    from matplotlib.patches import Ellipse

    for mi in selected_indices:
        # Get all points assigned to this medoid
        cluster_pts = [i for i in range(len(stock_names))
                       if min(selected_indices, key=lambda m: distance_matrix[i, m]) == mi]
        if len(cluster_pts) < 2:
            continue
        cluster_coords = coords[cluster_pts]
        cx, cy = cluster_coords.mean(axis=0)
        # Use std for ellipse size
        rx = max(cluster_coords[:, 0].std() * 2.2, 0.02)
        ry = max(cluster_coords[:, 1].std() * 2.2, 0.02)
        ellipse = Ellipse(
            (cx, cy), width=rx * 2, height=ry * 2,
            fill=False, edgecolor="#FF6B35", linewidth=1.5,
            linestyle=":", alpha=0.5, zorder=2,
        )
        ax.add_patch(ellipse)

    # ── Titles and legend ──
    ax.set_title(
        "Combinatorial Stock Selection: VN30 → K=5 Representatives",
        fontsize=FONT_SIZE_TITLE,
        fontweight="bold",
        pad=20,
    )
    ax.text(
        0.5, 1.02,
        f"Global optimum via exhaustive C({len(stock_names)},{K}) = "
        f"{int(__import__('math').comb(len(stock_names), K)):,} combinations  |  "
        f"Distance = 1 − ρ (correlation-based)  |  "
        f"2D projection via MDS",
        transform=ax.transAxes,
        ha="center",
        fontsize=FONT_SIZE_SUBTITLE,
        color="#555555",
        style="italic",
    )

    ax.legend(
        loc="lower right",
        fontsize=11,
        framealpha=0.9,
        edgecolor="#CCCCCC",
    )

    ax.set_xlabel("MDS Dimension 1 (correlation distance)", fontsize=11)
    ax.set_ylabel("MDS Dimension 2 (correlation distance)", fontsize=11)
    ax.grid(True, alpha=0.3, linestyle="--")
    ax.set_axisbelow(True)

    # Add text box with key stats
    textstr = (
        f"N = {len(stock_names)} stocks\n"
        f"K = {K} representatives\n"
        f"Search space: C({len(stock_names)},{K}) = {int(__import__('math').comb(len(stock_names), K)):,}\n"
        f"Method: Exhaustive + Pruning\n"
        f"Guarantee: Global Optimum"
    )
    props = dict(boxstyle="round,pad=0.5", facecolor="#FFF3E0", edgecolor="#FF6B35", alpha=0.9)
    ax.text(
        0.02, 0.98, textstr, transform=ax.transAxes,
        fontsize=10, verticalalignment="top",
        bbox=props, family="monospace",
    )

    plt.tight_layout()
    fig.savefig(output_path, dpi=DPI, bbox_inches="tight", facecolor="white")
    print(f"✅ Saved: {output_path}")
    print(f"   Resolution: {FIGSIZE[0]*DPI} × {FIGSIZE[1]*DPI} px")
    plt.close(fig)


def main():
    print("Loading VN30 price data...")
    prices = load_vn30_prices()
    print(f"   {prices.shape[1]} stocks × {prices.shape[0]} days")

    print("Computing correlation-based distance matrix...")
    dist_matrix, stock_names = compute_distance_matrix(prices)
    print(f"   Distance matrix: {dist_matrix.shape}")

    print(f"Running combinatorial selection (K={K})...")
    selected = select_representatives(prices, k=K)
    print(f"   Selected: {selected}")

    print("Projecting to 2D via MDS...")
    coords = project_to_2d(dist_matrix)

    print("Plotting...")
    plot_selection(coords, stock_names, selected, dist_matrix, OUTPUT_PATH)


if __name__ == "__main__":
    main()
