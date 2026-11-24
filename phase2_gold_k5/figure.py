"""Render the retrospective evidence on its historical date axis."""
import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


def figure(out):
    data = pd.read_csv(out / "daily.csv",parse_dates=["date"])
    quote = pd.read_csv(out / "gold_quotes.csv",parse_dates=["date"]).set_index("date")
    data = data.loc[(data.bps == 10) & data.gate & (data.date >= "2023-09-29")]
    paths = data.pivot(index="date",columns="arm",values="nav")
    paths = paths / paths.iloc[0]
    quote = quote.loc[paths.index]
    fig, axes = plt.subplots(2,1,figsize=(10,6.2),sharex=True,layout="constrained")
    axes[0].plot(quote.index, (quote.archive_ask+quote.archive_bid)/2000,
                 color="#8a6213", label="SJC HCM, trung điểm giá mua và bán")
    axes[0].set_ylabel("Triệu đồng / lượng")
    axes[1].plot(paths.index,paths.B2, label="Phase 1 · B2",color="#425578")
    axes[1].plot(paths.index,paths.B2_direct,label="B2 + view GOLD–K5 trực tiếp",color="#008078")
    axes[1].set_ylabel("NAV sau chi phí\n(29/09/2023 = 1)")
    for ax in axes:
        ax.axvspan(pd.Timestamp("2024-12-02"), pd.Timestamp("2026-02-24"),color="#d6a659",alpha=.15)
        ax.grid(axis="y", alpha=.21)
        ax.spines[["top","right"]].set_visible(False)
        ax.legend(loc="upper left", frameon=False)
    axes[0].set_title("Hai đoạn báo giá SJC đứng im liên tiếp (vùng tô màu)",loc="left")
    axes[1].set_title("Hai danh mục có cùng quy tắc giảm giao dịch",loc="left")
    fig.suptitle("GOLD–K5  |  Kiểm định hồi cứu trên 641 phiên",fontsize=15,fontweight="semibold")
    fig.savefig(out / "gold_k5_evidence.png",dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("run",type=Path)
    figure(parser.parse_args().run)
