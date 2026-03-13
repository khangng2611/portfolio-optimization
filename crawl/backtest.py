# ================================================
# BACKTEST MPT
# Sử dụng dữ liệu từ các file CSV bạn đã crawl
# ================================================

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
import cvxpy as cp
from datetime import datetime

# ====================== CÀI ĐẶT ======================
DATA_DIR = Path("datasets/stocks")          # Thư mục chứa tất cả file CSV
WINDOW = 20                                 # wd = 20 ngày
REBALANCE_FREQ = 5                          # Rebalance mỗi 5 ngày

# ====================== 1. DATA LOADER ======================
print("Đang đọc dữ liệu từ các file CSV...")

DATA = {'cls': {}, 'vol': {}}
symbols = []

for file in DATA_DIR.glob("*.csv"):
    df = pd.read_csv(file)
    symbol = df['symbol'].iloc[0] if 'symbol' in df.columns else file.stem.replace('_ohlcv', '')
    
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date')
    
    DATA['cls'][symbol] = df['close'].values
    DATA['vol'][symbol] = df['volume'].values if 'volume' in df.columns else np.zeros(len(df))
    
    symbols.append(symbol)

print(f"Đã load {len(symbols)} mã: {symbols[:10]}...")

STK = symbols

# Chuẩn hóa độ dài dữ liệu giữa các mã để tránh lỗi index out of bounds
lengths = [len(DATA['cls'][symbol]) for symbol in STK]
n = min(lengths)
if n <= WINDOW:
    raise ValueError(f"Không đủ dữ liệu để backtest: n={n}, WINDOW={WINDOW}")

for symbol in STK:
    DATA['cls'][symbol] = DATA['cls'][symbol][-n:]
    DATA['vol'][symbol] = DATA['vol'][symbol][-n:]

def look_back(DATA, STK, i, wd=WINDOW):
    r, mu, Sigma, m = {}, [], None, len(STK)
    for j in range(m):
        r[STK[j]] = []
        for k in range(i + 1 - wd, i + 1):
            r[STK[j]].append(DATA['cls'][STK[j]][k] / DATA['cls'][STK[j]][k - 1] - 1)
    for j in range(m):
        mu.append(np.nanmean(r[STK[j]]))
    for j in range(m):
        row = []
        for k in range(m):
            row.append(np.corrcoef(r[STK[j]], r[STK[k]])[0, 1])
        Sigma = np.vstack([Sigma, row]) if Sigma is not None else np.array([row])
    return mu, Sigma

def optimize_weight(mu, Sigma):
    mu = np.asarray(mu, dtype=float)
    Sigma = np.asarray(Sigma, dtype=float)
    n = len(mu)

    Sigma = np.nan_to_num(Sigma, nan=0.0, posinf=0.0, neginf=0.0)
    Sigma = 0.5 * (Sigma + Sigma.T)
    eigvals, eigvecs = np.linalg.eigh(Sigma)
    eigvals = np.clip(eigvals, 1e-8, None)
    Sigma = eigvecs @ np.diag(eigvals) @ eigvecs.T

    w = cp.Variable(n)
    risk = cp.quad_form(w, Sigma)
    ret = mu @ w
    problem = cp.Problem(cp.Maximize(ret - 0.5 * risk), [cp.sum(w) == 1, w >= 0])

    installed = set(cp.installed_solvers())
    for solver_name in ["ECOS", "OSQP", "SCS"]:
        if solver_name in installed:
            try:
                problem.solve(solver=getattr(cp, solver_name))
                if problem.status in [cp.OPTIMAL, cp.OPTIMAL_INACCURATE] and w.value is not None:
                    weight = np.maximum(w.value, 0)
                    total = np.sum(weight)
                    return weight / total if total > 0 else np.full(n, 1.0 / n)
            except Exception:
                continue

    return np.full(n, 1.0 / n)
# def optimize_weight(mu, Sigma):
#     n = len(mu)
#     w = cp.Variable(n)
#     risk = cp.quad_form(w, Sigma)
#     ret = mu @ w
#     problem = cp.Problem(cp.Maximize(ret - 0.5*risk), [cp.sum(w) == 1, w >= 0])
#     problem.solve()
#     return w.value

def update_weight(DATA, STK, w, i, freq=REBALANCE_FREQ, wd=WINDOW):
    if i % freq == 0:
        mu, Sigma = look_back(DATA, STK, i, wd)
        return optimize_weight(mu, Sigma)
    else:
        return w

def get_pnl(P):
    return np.sum(P, axis=1)

def get_sharpe(pnl):
    def core(sub):
        ret = sub[1:] / sub[:-1] - 1
        vola = np.std(ret)
        return np.mean(ret) / vola * np.sqrt(252) if vola > 0 else np.nan
    shp = [core(pnl[:i]) for i in range(5, len(pnl))]
    return np.array(shp)

def compare_pnl(PNL):
    print("\n" + "="*60)
    print("KẾT QUẢ BACKTEST")
    print("="*60)
    for label in PNL:
        nav = PNL[label][-1]
        shp = get_sharpe(PNL[label])[-1]
        print(f"{label:8} → NAV cuối kỳ: {nav:8.2f} | Sharpe: {shp:.2f}")
    
    # Vẽ biểu đồ
    plt.figure(figsize=(12, 6))
    for label in PNL:
        plt.plot(PNL[label], label=label)
    plt.title("Backtest: Equal Weight vs Mean-Variance Optimization")
    plt.ylabel("NAV (giả sử vốn ban đầu = 100)")
    plt.legend()
    plt.grid(True)
    plt.show()

# ====================== 3. CHẠY BACKTEST ======================
P = {'ew': None, 'mvo': None}
w = np.full(len(STK), 1.0 / len(STK))

print("Đang chạy backtest Equal Weight (EW)...")
for i in range(WINDOW, n):
    row = []
    for j in range(len(STK)):
        if i == WINDOW:
            row = 100 * w
        else:
            row.append(P['ew'][i - WINDOW - 1, j] * DATA['cls'][STK[j]][i] / DATA['cls'][STK[j]][i - 1])
    P['ew'] = np.vstack([P['ew'], row]) if P['ew'] is not None else np.array([row])

print("Đang chạy backtest Mean-Variance Optimization (MVO)...")
w = np.full(len(STK), 1.0 / len(STK))
for i in range(WINDOW, n):
    row = []
    w = update_weight(DATA, STK, w, i, REBALANCE_FREQ, WINDOW)
    if i == WINDOW:
        row = 100 * w
    else:
        nav = sum(P['mvo'][i - WINDOW - 1, j] * DATA['cls'][STK[j]][i] / DATA['cls'][STK[j]][i - 1] 
                  for j in range(len(STK)))
        row = [nav * w[j] for j in range(len(STK))]
    P['mvo'] = np.vstack([P['mvo'], row]) if P['mvo'] is not None else np.array([row])

PNL = {'ew': get_pnl(P['ew']), 'mvo': get_pnl(P['mvo'])}

# ====================== 4. HIỂN THỊ KẾT QUẢ ======================
compare_pnl(PNL)