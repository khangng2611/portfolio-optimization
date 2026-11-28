"""Check repeat output hashes, reconcile one pending/fill/settlement example and plot NAV."""

import json
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

from freeze import HERE, ROOT, sha, write_json


def verify(first, repeat):
    runs = [HERE / "runs" / name for name in (first, repeat)]
    manifests = [json.loads((r / "manifest.json").read_text()) for r in runs]
    assert all(m["status"] == "complete" for m in manifests)
    assert manifests[0]["source_sha256"] == manifests[1]["source_sha256"]
    names = sorted(p.name for p in runs[0].glob("*.csv")) + ["default-check.json"]
    for name in names:
        digests = [sha(r / name) for r in runs]
        assert digests[0] == digests[1] and all(
            m["artifact_sha256"][name] == digests[0] for m in manifests
        )
    ledger = ROOT / "services/portfolio/src/portfolio_service/paper_ledger.py"
    assert sha(ledger) == manifests[0]["source_sha256"]["paper_ledger.py"]
    d = pd.read_csv(runs[0] / "daily.csv")
    events = pd.read_csv(runs[0] / "events.csv")
    b = d.query("arm=='B'").set_index("date")
    e = events.query("arm=='B'")
    examples = {}
    for label, subset in (
        ("pending_buy", b[(b.reserved > 0) & (b.open_orders > 0)].index),
        (
            "sale_with_fee",
            e[(e.kind == "fill") & (e.side == "sell") & (e.fee > 0)].date,
        ),
        ("cash_settlement", e[e.kind == "settle"].date),
    ):
        date = min(subset)
        row = b.loc[date]
        assert (
            abs(row.nav - row.cash - row.reserved - row.receivable - row.invested)
            < 0.001
        )
        examples[label] = dict(
            date=date,
            **{
                k: float(row[k])
                for k in ("nav", "cash", "reserved", "receivable", "invested")
            },
        )
    nav = d.pivot(index="date", columns="arm", values="nav") / 1e6
    nav.index = pd.to_datetime(nav.index)
    assert (nav.B == nav.C).all()
    fig, axes = plt.subplots(2, 1, figsize=(10.2, 6.5), layout="constrained")
    for ax, panel, title, y in [
        (axes[0], nav, "Toàn kỳ · vốn ban đầu 10 triệu đồng", "Triệu VND"),
        (
            axes[1],
            nav.loc["2023-09-29":].div(nav.loc["2023-09-29"]) * 100,
            "Đánh giá hồi cứu · quy về 100 tại ngày 29/09/2023",
            "Chỉ số NAV",
        ),
    ]:
        ax.plot(
            panel.index,
            panel.A,
            label="A · Giữ sau mua đầu",
            color="#636C7B",
            linewidth=1.5,
        )
        ax.plot(
            panel.index,
            panel.B,
            label="B · Mỗi 5 phiên",
            color="#155B95",
            linewidth=2.2,
        )
        ax.plot(
            panel.index,
            panel.C,
            label="C · Ngưỡng 2% (trùng B)",
            color="#DA7400",
            linestyle=(0, (3, 5)),
            linewidth=1.3,
        )
        ax.set_title(title, loc="left", fontsize=12)
        ax.set_ylabel(y)
        ax.grid(axis="y", alpha=0.22)
        ax.spines[["right", "top"]].set_visible(False)
        ax.xaxis.set_major_locator(mdates.YearLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    axes[0].axvline(pd.Timestamp("2023-09-29"), ls=":", color="black", lw=1)
    axes[0].legend(frameon=False, loc="upper left", ncols=3, fontsize=9)
    fig.savefig(HERE / "nav.png", dpi=155)
    plt.close(fig)
    write_json(
        HERE / "verification.json",
        dict(
            primary=first,
            repeat=repeat,
            matched_deterministic_artifacts=names,
            ledger_sha256=sha(ledger),
            exact_daily_nav_B_equals_C=True,
            examples=examples,
            nav_plot_sha256=sha(HERE / "nav.png"),
        ),
    )


if __name__ == "__main__":
    verify(*sys.argv[1:])
