import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path
import cvxpy as cp

# ====================== CONFIG ======================
START_DATE = "2023-01-01"
END_DATE = "2026-01-01"
WINDOW = 120
REBALANCE_FREQ = 5
INITIAL_NAV = 100000.0
TRADING_DAYS_PER_YEAR = 252
RISK_FREE_RATE_ANNUAL = 0.06

BL_TAU = 0.05
BL_DELTA = 2.5
BL_VIEW_CONFIDENCE = 0.5

BASE_DIR = Path("datasets")
ASSETS = {
    "E1VFVN30": {
        "path": BASE_DIR / "stocks" / "E1VFVN30.csv",
        "date_col": "date",
        "price_col": "close",
    },
    "GOLD": {
        "path": BASE_DIR / "gold" / "pnj_sjc_price.csv",
        "date_col": "date",
        "price_col": "sjc_sell",
    },
    "DCDS": {
        "path": BASE_DIR / "funds" / "DCDS.csv",
        "date_col": "date",
        "price_col": "price",
    },
    "SSISCA": {
        "path": BASE_DIR / "funds" / "SSISCA.csv",
        "date_col": "date",
        "price_col": "price",
    },
    "MBBOND": {
        "path": BASE_DIR / "funds" / "MBBOND.csv",
        "date_col": "date",
        "price_col": "price",
    },
}


def load_asset_series(asset_name, cfg):
    df = pd.read_csv(cfg["path"])
    df[cfg["date_col"]] = pd.to_datetime(df[cfg["date_col"]])
    s = (
        df[[cfg["date_col"], cfg["price_col"]]]
        .dropna(subset=[cfg["price_col"]])
        .drop_duplicates(subset=[cfg["date_col"]], keep="last")
        .sort_values(cfg["date_col"])
        .set_index(cfg["date_col"])[cfg["price_col"]]
        .astype(float)
    )
    s.name = asset_name
    return s


def build_price_table(start_date=START_DATE, end_date=END_DATE):
    calendar = pd.date_range(start=start_date, end=end_date, freq="B")
    data = {}

    for asset, cfg in ASSETS.items():
        series = load_asset_series(asset, cfg)
        series = series.reindex(calendar).ffill()
        data[asset] = series

    prices = pd.DataFrame(data, index=calendar)

    # Bỏ các ngày đầu còn thiếu dữ liệu do tài sản chưa có lịch sử trước đó
    prices = prices.dropna(how="any")
    if len(prices) <= WINDOW:
        raise ValueError(
            f"Không đủ dữ liệu sau khi đồng bộ: {len(prices)} dòng, cần > WINDOW={WINDOW}"
        )

    return prices


def optimize_weight(mu, Sigma, risk_aversion=0.5):
    mu = np.asarray(mu, dtype=float)
    Sigma = np.asarray(Sigma, dtype=float)
    n = len(mu)

    Sigma = np.nan_to_num(Sigma, nan=0.0, posinf=0.0, neginf=0.0)
    Sigma = 0.5 * (Sigma + Sigma.T)
    eigvals, eigvecs = np.linalg.eigh(Sigma)
    eigvals = np.clip(eigvals, 1e-8, None)
    Sigma = eigvecs @ np.diag(eigvals) @ eigvecs.T

    w = cp.Variable(n)
    objective = cp.Maximize(mu @ w - risk_aversion * cp.quad_form(w, Sigma))
    constraints = [cp.sum(w) == 1, w >= 0]
    problem = cp.Problem(objective, constraints)

    installed = set(cp.installed_solvers())
    for solver_name in ["ECOS", "OSQP", "SCS"]:
        if solver_name in installed:
            try:
                problem.solve(solver=getattr(cp, solver_name))
                if problem.status in [cp.OPTIMAL, cp.OPTIMAL_INACCURATE] and w.value is not None:
                    weight = np.maximum(w.value, 0)
                    total = np.sum(weight)
                    if total > 0:
                        return weight / total
            except Exception:
                continue

    return np.full(n, 1.0 / n)


def black_litterman_posterior_mu(
    Sigma,
    q_view,
    market_weights,
    tau=BL_TAU,
    delta=BL_DELTA,
    view_confidence=BL_VIEW_CONFIDENCE,
):
    Sigma = np.asarray(Sigma, dtype=float)
    q_view = np.asarray(q_view, dtype=float)
    market_weights = np.asarray(market_weights, dtype=float)
    n = len(market_weights)

    Sigma = np.nan_to_num(Sigma, nan=0.0, posinf=0.0, neginf=0.0)
    Sigma = 0.5 * (Sigma + Sigma.T)
    eigvals, eigvecs = np.linalg.eigh(Sigma)
    eigvals = np.clip(eigvals, 1e-8, None)
    Sigma = eigvecs @ np.diag(eigvals) @ eigvecs.T

    pi = delta * Sigma @ market_weights
    p = np.eye(n)

    omega_diag = np.diag(p @ (tau * Sigma) @ p.T)
    omega_diag = np.clip(omega_diag, 1e-10, None)
    confidence = np.clip(view_confidence, 1e-6, 1.0)
    omega = np.diag(omega_diag / confidence)

    inv_tau_sigma = np.linalg.inv(tau * Sigma)
    inv_omega = np.linalg.inv(omega)

    middle = inv_tau_sigma + p.T @ inv_omega @ p
    rhs = inv_tau_sigma @ pi + p.T @ inv_omega @ q_view
    mu_bl = np.linalg.solve(middle, rhs)
    return mu_bl


def backtest(prices, window=WINDOW, rebalance_freq=REBALANCE_FREQ, initial_nav=INITIAL_NAV):
    returns = prices.pct_change().dropna()
    assets = list(prices.columns)
    m = len(assets)

    ew_weight = np.full(m, 1.0 / m)
    mvo_weight = np.full(m, 1.0 / m)
    bl_weight = np.full(m, 1.0 / m)

    ew_nav = [initial_nav]
    mvo_nav = [initial_nav]
    bl_nav = [initial_nav]
    ew_weights_hist = []
    mvo_weights_hist = []
    bl_weights_hist = []
    rebalance_dates = []

    for t in range(window, len(returns)):
        hist = returns.iloc[t - window : t]
        r_t = returns.iloc[t].values

        # EW update (buy & hold theo weight cố định)
        ew_nav.append(ew_nav[-1] * (1 + np.dot(ew_weight, r_t)))
        ew_weights_hist.append(ew_weight.copy())

        # MVO rebalance
        if (t - window) % rebalance_freq == 0:
            mu = hist.mean().values
            Sigma = hist.cov().values
            mvo_weight = optimize_weight(mu, Sigma)

            market_weights = np.full(m, 1.0 / m)
            mu_bl = black_litterman_posterior_mu(Sigma, mu, market_weights)
            bl_weight = optimize_weight(mu_bl, Sigma)
            rebalance_dates.append(returns.index[t])

        mvo_nav.append(mvo_nav[-1] * (1 + np.dot(mvo_weight, r_t)))
        bl_nav.append(bl_nav[-1] * (1 + np.dot(bl_weight, r_t)))
        mvo_weights_hist.append(mvo_weight.copy())
        bl_weights_hist.append(bl_weight.copy())

    nav_index = returns.index[window - 1 :]
    ew_series = pd.Series(ew_nav, index=nav_index)
    mvo_series = pd.Series(mvo_nav, index=nav_index)
    bl_series = pd.Series(bl_nav, index=nav_index)

    return {
        "returns": returns,
        "ew_nav": ew_series,
        "mvo_nav": mvo_series,
        "bl_nav": bl_series,
        "ew_weights_hist": np.array(ew_weights_hist),
        "mvo_weights_hist": np.array(mvo_weights_hist),
        "bl_weights_hist": np.array(bl_weights_hist),
        "rebalance_dates": rebalance_dates,
        "assets": assets,
    }


def sharpe_ratio(nav_series):
    ret = nav_series.pct_change().dropna()
    if len(ret) == 0 or ret.std() == 0:
        return np.nan
    rf_daily = (1 + RISK_FREE_RATE_ANNUAL) ** (1 / TRADING_DAYS_PER_YEAR) - 1
    excess_ret = ret - rf_daily
    excess_vol = excess_ret.std()
    if excess_vol == 0:
        return np.nan
    return np.sqrt(TRADING_DAYS_PER_YEAR) * excess_ret.mean() / excess_vol


def max_drawdown(nav_series):
    peak = nav_series.cummax()
    drawdown = nav_series / peak - 1
    return drawdown.min()


def get_next_period_weights(returns, as_of_date=pd.Timestamp(END_DATE), window=WINDOW):
    eligible = returns.loc[returns.index <= as_of_date]
    if len(eligible) < window:
        raise ValueError(
            f"Không đủ dữ liệu để tính weight sau {as_of_date.date()}: có {len(eligible)} dòng"
        )

    hist = eligible.iloc[-window:]
    mu = hist.mean().values
    Sigma = hist.cov().values
    market_weights = np.full(len(mu), 1.0 / len(mu))
    mu_bl = black_litterman_posterior_mu(Sigma, mu, market_weights)

    w_mvo = optimize_weight(mu, Sigma)
    w_bl = optimize_weight(mu_bl, Sigma)
    return w_mvo, w_bl, hist.index[-1]


def summarize_asset_returns(prices):
    returns = prices.pct_change().dropna()
    total_return = prices.iloc[-1] / prices.iloc[0] - 1
    annualized_return = (1 + total_return) ** (TRADING_DAYS_PER_YEAR / len(returns)) - 1
    annualized_vol = returns.std() * np.sqrt(TRADING_DAYS_PER_YEAR)

    summary = pd.DataFrame(
        {
            "Total Return": total_return,
            "Annualized Return": annualized_return,
            "Annualized Vol": annualized_vol,
        }
    )
    return summary


def main():
    print("Đang load và đồng bộ dữ liệu 4 tài sản...")
    prices = build_price_table(START_DATE, END_DATE)
    asset_summary = summarize_asset_returns(prices)

    print(
        f"Khoảng dữ liệu dùng backtest: {prices.index.min().date()} -> {prices.index.max().date()} "
        f"({len(prices)} phiên)"
    )

    print("\n" + "=" * 70)
    print("BẢNG RETURN TỪNG ASSET")
    print("=" * 70)
    print(asset_summary.to_string(float_format=lambda x: f"{x:,.2%}"))

    result = backtest(prices)
    ew_nav = result["ew_nav"]
    mvo_nav = result["mvo_nav"]
    bl_nav = result["bl_nav"]

    print("\n" + "=" * 70)
    print(f"KẾT QUẢ BACKTEST ({START_DATE} đến {END_DATE}, theo dữ liệu khả dụng)")
    print("=" * 70)
    print(
        f"EW   | NAV cuối: {ew_nav.iloc[-1]:8.2f} | Sharpe: {sharpe_ratio(ew_nav):6.2f} | MDD: {max_drawdown(ew_nav):7.2%}"
    )
    print(
        f"MVO  | NAV cuối: {mvo_nav.iloc[-1]:8.2f} | Sharpe: {sharpe_ratio(mvo_nav):6.2f} | MDD: {max_drawdown(mvo_nav):7.2%}"
    )
    print(
        f"BL   | NAV cuối: {bl_nav.iloc[-1]:8.2f} | Sharpe: {sharpe_ratio(bl_nav):6.2f} | MDD: {max_drawdown(bl_nav):7.2%}"
    )

    # Trọng số tối ưu cho giai đoạn tiếp theo sau END_DATE
    w_mvo_next, w_bl_next, last_hist_date = get_next_period_weights(
        result["returns"], as_of_date=pd.Timestamp(END_DATE), window=WINDOW
    )

    print("\n" + "=" * 70)
    print(f"TRỌNG SỐ GỢI Ý CHO GIAI ĐOẠN TIẾP THEO SAU {END_DATE}")
    print(f"(Ước lượng từ cửa sổ {WINDOW} phiên gần nhất đến {last_hist_date.date()})")
    print("=" * 70)
    print("MVO:")
    for asset, weight in zip(result["assets"], w_mvo_next):
        print(f"  {asset:8}: {weight:7.2%}")
    print("BL:")
    for asset, weight in zip(result["assets"], w_bl_next):
        print(f"  {asset:8}: {weight:7.2%}")

    plt.figure(figsize=(12, 6))
    plt.plot(ew_nav.index, ew_nav.values, label="EW")
    plt.plot(mvo_nav.index, mvo_nav.values, label="MVO")
    plt.plot(bl_nav.index, bl_nav.values, label="BL")
    plt.title("Backtest 4 Assets: EW vs MVO vs BL")
    plt.ylabel("NAV (initial = 100)")
    plt.grid(True)
    plt.legend()
    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    main()
