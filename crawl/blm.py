# ================================================
# BLM + MPT CORE AGENT - Phiên bản sạch
# ================================================

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime

# ====================== 1. DATA LOADER ======================
def load_all_assets(data_dir):
    data_dir = Path(data_dir)
    all_assets = {}

    for file in data_dir.glob("*.csv"):
        df = pd.read_csv(file)
        symbol = df['symbol'].iloc[0] if 'symbol' in df.columns else file.stem
        
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')
        df['return'] = df['close'].pct_change().fillna(0)
        
        all_assets[symbol] = df[['date', 'close', 'return']]
    
    print(f"Đã load {len(all_assets)} assets")
    return all_assets

# ====================== 2. BLACK-LITTERMAN CORE ======================
class BLMDeterministicAgent:
    def __init__(self, assets_dict):
        self.assets = assets_dict
        self.symbols = list(assets_dict.keys())
        self.returns_df = self._build_returns_matrix()
    
    def _build_returns_matrix(self):
        df = pd.DataFrame()
        for sym, data in self.assets.items():
            df[sym] = data.set_index('date')['return']
        return df.dropna()  # Chỉ giữ ngày có đầy đủ dữ liệu
    
    def run_blm(self, views=None, tau=0.025, delta=2.5):
        """
        views: list of dicts, ví dụ:
        [{"P": [1, -1, 0...], "Q": 0.03, "omega": 0.0001}, ...]
        """
        returns = self.returns_df
        Sigma = returns.cov().values          # Covariance matrix
        mu_hist = returns.mean().values       # Historical mean
        
        # Equilibrium returns Π
        market_weights = np.ones(len(self.symbols)) / len(self.symbols)  # Giả sử equal weight ban đầu
        Pi = delta * Sigma @ market_weights
        
        # Nếu không có views → dùng historical mean
        if not views:
            mu_bl = Pi
        else:
            # Xây dựng ma trận P, Q, Omega từ views
            P = np.array([v['P'] for v in views])
            Q = np.array([v['Q'] for v in views])
            Omega = np.diag([v['omega'] for v in views])
            
            # Công thức Black-Litterman
            tau_Sigma_inv = np.linalg.inv(tau * Sigma)
            P_Omega_inv_P = P.T @ np.linalg.inv(Omega) @ P
            inv_term = np.linalg.inv(tau_Sigma_inv + P_Omega_inv_P)
            
            mu_bl = inv_term @ (tau_Sigma_inv @ Pi + P.T @ np.linalg.inv(Omega) @ Q)
        
        # Tối ưu MPT với mu_bl
        from scipy.optimize import minimize
        def objective(w):
            ret = w @ mu_bl
            risk = w.T @ Sigma @ w
            return -(ret - 0.5 * risk)
        
        constraints = ({'type': 'eq', 'fun': lambda w: np.sum(w) - 1})
        bounds = [(0, 1) for _ in self.symbols]
        
        res = minimize(objective, x0=np.ones(len(self.symbols))/len(self.symbols),
                       bounds=bounds, constraints=constraints)
        
        weights = res.x
        portfolio_return = weights @ mu_bl
        portfolio_risk = np.sqrt(weights.T @ Sigma @ weights)
        
        return {
            'weights': dict(zip(self.symbols, weights.round(4))),
            'expected_return': portfolio_return,
            'risk': portfolio_risk,
            'sharpe': (portfolio_return - 0.05) / portfolio_risk if portfolio_risk > 0 else 0  # rf=5%
        }

# ====================== CHẠY THỬ ======================
if __name__ == "__main__":
    assets = load_all_assets("datasets/stocks")          # Thư mục bạn lưu CSV
    agent = BLMDeterministicAgent(assets)
    
    # Test với views đơn giản
    test_views = [
        {"P": [1, -1] + [0]*(len(assets)-2), "Q": 0.03, "omega": 0.0001}  # Ví dụ: VCB vượt BID 3%
    ]
    
    result = agent.run_blm(views=test_views)
    
    print("\n=== KẾT QUẢ BLACK-LITTERMAN ===")
    print("Weights:", result['weights'])
    print(f"Expected Return: {result['expected_return']:.4f}")
    print(f"Risk (Std): {result['risk']:.4f}")
    print(f"Sharpe Ratio: {result['sharpe']:.4f}")