"""
XGBoost Return Predictor
========================

Pure ML forecasting module: train, predict, save, load.
Knows nothing about Black-Litterman views.

Use :func:`view_generators.generate_ml_views` to convert predictions
into BL view dicts.
"""

import pickle
import warnings
from pathlib import Path
from typing import Optional, Union

import numpy as np
import pandas as pd

from view_generators import (
    DEFAULT_FEATURE_WINDOW,
    DEFAULT_PREDICTION_HORIZON,
    compute_ema,
    compute_macd,
    compute_momentum,
    compute_rsi,
)

warnings.filterwarnings("ignore")


class XGBoostReturnPredictor:
    """
    XGBoost Return Predictor
    ------------------------
    Pure ML forecasting: train, predict, save, load.
    Knows nothing about Black-Litterman views.

    Use this when you only need return predictions (e.g. training scripts).
    Use ``generate_ml_views()`` from ``view_generators`` to convert
    predictions into BL view dicts.
    """

    def __init__(
        self,
        feature_window: int = DEFAULT_FEATURE_WINDOW,
        prediction_horizon: int = DEFAULT_PREDICTION_HORIZON,
        model_params: Optional[dict] = None,
    ):
        self.feature_window = feature_window
        self.prediction_horizon = prediction_horizon
        self.model_params = model_params or {}
        self.models: dict = {}  # {asset_name: trained_model}
        self.feature_cols: list[str] = []

    def _compute_features(self, prices: pd.Series) -> pd.DataFrame:
        """
        Compute technical indicator features.

        Features:
        - Momentum (5, 10, 20 days)
        - Moving averages ratios
        - RSI
        - Volatility
        - MACD histogram
        """
        features = []

        for i in range(self.feature_window, len(prices)):
            price_slice = prices.iloc[: i + 1]

            feature_dict = {
                "momentum_5": compute_momentum(price_slice, 5),
                "momentum_10": compute_momentum(price_slice, 10),
                "momentum_20": compute_momentum(price_slice, 20),
                "rsi_14": compute_rsi(price_slice, 14),
                "ma_ratio_10_30": (
                    compute_ema(price_slice, 10).iloc[-1]
                    / compute_ema(price_slice, 30).iloc[-1]
                    - 1
                ),
                "volatility_20": price_slice.pct_change().tail(20).std(),
                "macd_hist": compute_macd(price_slice)[2],
                "price_std_20": price_slice.tail(20).std()
                / price_slice.tail(20).mean(),
            }

            features.append(feature_dict)

        df = pd.DataFrame(features, index=prices.index[self.feature_window :])
        return df

    def _compute_labels(self, prices: pd.Series) -> pd.Series:
        """
        Compute forward returns as labels.

        Label = (Price[t+h] - Price[t]) / Price[t]
        where h = prediction_horizon
        """
        returns = []

        for i in range(len(prices) - self.prediction_horizon):
            future_price = prices.iloc[i + self.prediction_horizon]
            current_price = prices.iloc[i]
            ret = (future_price - current_price) / current_price
            returns.append(ret)

        # Pad with NaN for last few days
        returns.extend([np.nan] * self.prediction_horizon)

        return pd.Series(returns, index=prices.index)

    def train(self, prices: pd.DataFrame, verbose: bool = True):
        """
        Train XGBoost models for each asset.

        Parameters
        ----------
        prices : pd.DataFrame
            Historical price data (columns = assets)
        verbose : bool
            Print training progress
        """
        try:
            import xgboost as xgb
        except ImportError as e:
            raise ImportError(
                "XGBoost is required. Install with: pip install xgboost"
            ) from e

        default_params = {
            "n_estimators": 100,
            "max_depth": 6,
            "learning_rate": 0.1,
            "random_state": 42,
        }

        params = {**default_params, **self.model_params}

        for asset in prices.columns:
            if verbose:
                print(f"Training xgboost for {asset}...")

            price_series = prices[asset].dropna()

            if len(price_series) < self.feature_window + self.prediction_horizon + 50:
                if verbose:
                    print(f"  Skipping {asset}: not enough data")
                continue

            features_df = self._compute_features(price_series)
            labels_series = self._compute_labels(price_series)

            common_idx = features_df.index.intersection(labels_series.index)
            X = features_df.loc[common_idx]
            y = labels_series.loc[common_idx]

            valid_mask = (~X.isna().any(axis=1)) & y.notna()
            X = X[valid_mask]
            y = y[valid_mask]

            if len(X) < 50:
                if verbose:
                    print(f"  Skipping {asset}: not enough valid samples")
                continue

            model = xgb.XGBRegressor(**params)
            model.fit(X, y)
            self.models[asset] = model
            self.feature_cols = list(X.columns)

            if verbose:
                train_score = model.score(X, y)
                print(f"  \u2713 {asset} trained. R\u00b2 score: {train_score:.3f}")

        if verbose:
            print(f"\nTraining complete. {len(self.models)} models trained.")

    def predict(self, prices: pd.DataFrame) -> dict[str, tuple[float, float]]:
        """
        Predict future returns for each asset.

        Parameters
        ----------
        prices : pd.DataFrame
            Recent price data (needs at least feature_window days)

        Returns
        -------
        dict
            {asset_name: (predicted_return, confidence)}
        """
        predictions = {}

        for asset, model in self.models.items():
            if asset not in prices.columns:
                continue

            price_series = prices[asset].dropna()

            if len(price_series) < self.feature_window:
                continue

            features_df = self._compute_features(price_series)

            if features_df.empty:
                continue

            latest_features = features_df.iloc[-1:][self.feature_cols]

            pred_return = model.predict(latest_features)[0]

            # Confidence heuristic: higher feature variance -> lower confidence
            feature_values = latest_features.values[0]
            feature_variance = np.var(feature_values)
            confidence = max(0.3, min(0.9, 0.6 - feature_variance * 5))

            predictions[asset] = (pred_return, confidence)

        return predictions

    def save(self, filepath: Union[str, Path]):
        """Save trained models to disk."""
        save_dict = {
            "model_type": "xgboost",
            "feature_window": self.feature_window,
            "prediction_horizon": self.prediction_horizon,
            "model_params": self.model_params,
            "models": self.models,
            "feature_cols": self.feature_cols,
        }
        with open(filepath, "wb") as f:
            pickle.dump(save_dict, f)
        print(f"Models saved to {filepath}")

    def load(self, filepath: Union[str, Path]):
        """Load trained models from disk."""
        with open(filepath, "rb") as f:
            save_dict = pickle.load(f)

        if save_dict.get("model_type") != "xgboost":
            raise ValueError(
                "Only XGBoost model artifacts are supported. "
                "Please retrain with view_ml/xgboost_train.py --method xgboost"
            )

        self.feature_window = save_dict["feature_window"]
        self.prediction_horizon = save_dict["prediction_horizon"]
        self.model_params = save_dict["model_params"]
        self.models = save_dict["models"]
        self.feature_cols = save_dict["feature_cols"]
        print(f"Models loaded from {filepath}")
