"""
XGBoost Core Model
========================

Pure ML forecasting module: train, predict, save, load.

Use :func:`view_generators.generate_ml_views` to convert predictions into BL view dicts.
"""

import pickle
import warnings
from pathlib import Path
from typing import Optional, Union

import numpy as np
import pandas as pd

from gen_view.xgboost.config import (
    CONFIDENCE_BASE,
    CONFIDENCE_MAX,
    CONFIDENCE_MIN,
    CONFIDENCE_VAR_SCALE,
    DEFAULT_FEATURE_WINDOW,
    DEFAULT_PREDICTION_HORIZON,
    DEFAULT_XGB_PARAMS,
    EARLY_STOPPING_ROUNDS,
    ENSEMBLE_BASE_SEED,
    ENSEMBLE_CONF_MAX,
    ENSEMBLE_CONF_MIN,
    ENSEMBLE_CONF_SCALE,
    ENSEMBLE_SIZE,
    MACD_FAST,
    MACD_SIGNAL,
    MACD_SLOW,
    MA_LONG_PERIOD,
    MA_SHORT_PERIOD,
    MIN_DATA_SAMPLES,
    MIN_TRAIN_SAMPLES,
    MIN_VALID_SAMPLES,
    MOMENTUM_PERIODS,
    PRICE_STD_WINDOW,
    RSI_PERIOD,
    VALIDATION_SPLIT_RATIO,
    VOLATILITY_WINDOW,
)
from gen_view.view_generators import (
    compute_ema,
    compute_macd,
    compute_momentum,
    compute_rsi,
)

warnings.filterwarnings("ignore")


class XGBoostCoreModel:
    """
    XGBoost Core Model
    ------------------------
    Pure ML forecasting: train, predict, save, load.

    Use this when you only need return predictions (e.g. training scripts).
    Use ``generate_ml_views()`` from ``view_generators`` to convert predictions into BL view dicts.
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
                "momentum_5": compute_momentum(price_slice, MOMENTUM_PERIODS[0]),
                "momentum_10": compute_momentum(price_slice, MOMENTUM_PERIODS[1]),
                "momentum_20": compute_momentum(price_slice, MOMENTUM_PERIODS[2]),
                "rsi_14": compute_rsi(price_slice, RSI_PERIOD),
                "ma_ratio_10_30": (
                    compute_ema(price_slice, MA_SHORT_PERIOD).iloc[-1]
                    / compute_ema(price_slice, MA_LONG_PERIOD).iloc[-1]
                    - 1
                ),
                "volatility_20": price_slice.pct_change().tail(VOLATILITY_WINDOW).std(),
                "macd_hist": compute_macd(price_slice, MACD_FAST, MACD_SLOW, MACD_SIGNAL)[2],
                "price_std_20": price_slice.tail(PRICE_STD_WINDOW).std()
                / price_slice.tail(PRICE_STD_WINDOW).mean(),
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

        params = {**DEFAULT_XGB_PARAMS, **self.model_params}

        for asset in prices.columns:
            if verbose:
                print(f"Training xgboost for {asset}...")

            price_series = prices[asset].dropna()

            if len(price_series) < self.feature_window + self.prediction_horizon + MIN_DATA_SAMPLES:
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

            if len(X) < MIN_VALID_SAMPLES:
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
            confidence = max(
                CONFIDENCE_MIN,
                min(CONFIDENCE_MAX, CONFIDENCE_BASE - feature_variance * CONFIDENCE_VAR_SCALE),
            )

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
                "Please retrain with gen_view/xgboost/model_train.py --method xgboost"
            )

        self.feature_window = save_dict["feature_window"]
        self.prediction_horizon = save_dict["prediction_horizon"]
        self.model_params = save_dict["model_params"]
        self.models = save_dict["models"]
        self.feature_cols = save_dict["feature_cols"]
        print(f"Models loaded from {filepath}")


class XGBoostEnsembleModel:
    """
    XGBoost Ensemble Model with Walk-Forward Training
    --------------------------------------------------
    Trains N XGBoost models per asset with different random seeds.
    Confidence is derived from ensemble agreement (prediction std).
    Supports StandardScaler for feature normalization.

    Use for walk-forward backtesting where the model is retrained
    periodically on expanding windows of data.
    """

    def __init__(
        self,
        feature_window: int = DEFAULT_FEATURE_WINDOW,
        prediction_horizon: int = DEFAULT_PREDICTION_HORIZON,
        model_params: Optional[dict] = None,
        n_ensemble: int = ENSEMBLE_SIZE,
        base_seed: int = ENSEMBLE_BASE_SEED,
    ):
        self.feature_window = feature_window
        self.prediction_horizon = prediction_horizon
        self.model_params = model_params or {}
        self.n_ensemble = n_ensemble
        self.base_seed = base_seed
        self.ensemble_models: dict[str, list] = {}  # {asset: [model1, ..., modelN]}
        self.scalers: dict = {}  # {asset: StandardScaler}
        self.feature_cols: list[str] = []
        self._trained = False

    @property
    def is_trained(self) -> bool:
        return self._trained and len(self.ensemble_models) > 0

    def _compute_features(self, prices: pd.Series) -> pd.DataFrame:
        """Compute technical indicator features (same as XGBoostCoreModel)."""
        features = []

        for i in range(self.feature_window, len(prices)):
            price_slice = prices.iloc[: i + 1]

            feature_dict = {
                "momentum_5": compute_momentum(price_slice, MOMENTUM_PERIODS[0]),
                "momentum_10": compute_momentum(price_slice, MOMENTUM_PERIODS[1]),
                "momentum_20": compute_momentum(price_slice, MOMENTUM_PERIODS[2]),
                "rsi_14": compute_rsi(price_slice, RSI_PERIOD),
                "ma_ratio_10_30": (
                    compute_ema(price_slice, MA_SHORT_PERIOD).iloc[-1]
                    / compute_ema(price_slice, MA_LONG_PERIOD).iloc[-1]
                    - 1
                ),
                "volatility_20": price_slice.pct_change().tail(VOLATILITY_WINDOW).std(),
                "macd_hist": compute_macd(price_slice, MACD_FAST, MACD_SLOW, MACD_SIGNAL)[2],
                "price_std_20": price_slice.tail(PRICE_STD_WINDOW).std()
                / price_slice.tail(PRICE_STD_WINDOW).mean(),
            }

            features.append(feature_dict)

        df = pd.DataFrame(features, index=prices.index[self.feature_window:])
        return df

    def _compute_labels(self, prices: pd.Series) -> pd.Series:
        """Compute forward returns as labels."""
        returns = []

        for i in range(len(prices) - self.prediction_horizon):
            future_price = prices.iloc[i + self.prediction_horizon]
            current_price = prices.iloc[i]
            ret = (future_price - current_price) / current_price
            returns.append(ret)

        returns.extend([np.nan] * self.prediction_horizon)
        return pd.Series(returns, index=prices.index)

    def train(self, prices: pd.DataFrame, verbose: bool = True):
        """
        Train ensemble XGBoost models for each asset with StandardScaler
        and early stopping.

        Parameters
        ----------
        prices : pd.DataFrame
            Historical price data (columns = assets). Should only contain
            data up to the current time point (no future data).
        verbose : bool
            Print training progress
        """
        try:
            import xgboost as xgb
        except ImportError as e:
            raise ImportError(
                "XGBoost is required. Install with: pip install xgboost"
            ) from e

        from sklearn.preprocessing import StandardScaler

        base_params = {**DEFAULT_XGB_PARAMS, **self.model_params}
        # Remove random_state from base — we'll set per ensemble member
        base_params.pop("random_state", None)

        self.ensemble_models = {}
        self.scalers = {}

        for asset in prices.columns:
            price_series = prices[asset].dropna()

            if len(price_series) < self.feature_window + self.prediction_horizon + MIN_TRAIN_SAMPLES:
                if verbose:
                    print(f"  Skipping {asset}: not enough data ({len(price_series)} days)")
                continue

            features_df = self._compute_features(price_series)
            labels_series = self._compute_labels(price_series)

            common_idx = features_df.index.intersection(labels_series.index)
            X = features_df.loc[common_idx]
            y = labels_series.loc[common_idx]

            valid_mask = (~X.isna().any(axis=1)) & y.notna()
            X = X[valid_mask]
            y = y[valid_mask]

            if len(X) < MIN_TRAIN_SAMPLES:
                if verbose:
                    print(f"  Skipping {asset}: not enough valid samples ({len(X)})")
                continue

            # Temporal train/validation split
            split_idx = int(len(X) * (1 - VALIDATION_SPLIT_RATIO))
            X_train, X_val = X.iloc[:split_idx], X.iloc[split_idx:]
            y_train, y_val = y.iloc[:split_idx], y.iloc[split_idx:]

            # Fit StandardScaler on training data only
            scaler = StandardScaler()
            X_train_scaled = pd.DataFrame(
                scaler.fit_transform(X_train),
                columns=X_train.columns,
                index=X_train.index,
            )
            X_val_scaled = pd.DataFrame(
                scaler.transform(X_val),
                columns=X_val.columns,
                index=X_val.index,
            )
            self.scalers[asset] = scaler

            # Train N ensemble members with different seeds and data perturbation
            asset_models = []
            for i in range(self.n_ensemble):
                seed = self.base_seed + i
                params = {
                    **base_params,
                    "random_state": seed,
                    # Diversity: each model sees different feature/data subsets
                    "subsample": 0.8,
                    "colsample_bytree": 0.7 + 0.05 * i,  # vary: 0.7, 0.75, 0.8, 0.85, 0.9
                }
                model = xgb.XGBRegressor(**params, early_stopping_rounds=EARLY_STOPPING_ROUNDS)
                model.fit(
                    X_train_scaled,
                    y_train,
                    eval_set=[(X_val_scaled, y_val)],
                    verbose=False,
                )
                asset_models.append(model)

            self.ensemble_models[asset] = asset_models
            self.feature_cols = list(X.columns)

            if verbose:
                # Report ensemble mean R² on validation
                val_preds = [m.predict(X_val_scaled) for m in asset_models]
                mean_pred = np.mean(val_preds, axis=0)
                ss_res = np.sum((y_val.values - mean_pred) ** 2)
                ss_tot = np.sum((y_val.values - y_val.mean()) ** 2)
                r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
                print(f"  {asset}: ensemble R2 (val) = {r2:.3f} ({len(X_train)} train, {len(X_val)} val)")

        self._trained = len(self.ensemble_models) > 0

        if verbose:
            print(f"  Ensemble training complete: {len(self.ensemble_models)} assets, {self.n_ensemble} models each.")

    def _compute_ensemble_confidence(self, predictions_array: np.ndarray) -> float:
        """
        Compute confidence from ensemble prediction disagreement.

        High agreement (low std) -> high confidence.
        High disagreement (high std) -> low confidence.
        """
        pred_std = np.std(predictions_array)
        confidence = ENSEMBLE_CONF_MAX - (pred_std / ENSEMBLE_CONF_SCALE)
        return float(np.clip(confidence, ENSEMBLE_CONF_MIN, ENSEMBLE_CONF_MAX))

    def predict(self, prices: pd.DataFrame) -> dict[str, tuple[float, float]]:
        """
        Predict future returns using ensemble and compute confidence
        from prediction disagreement.

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

        for asset, models in self.ensemble_models.items():
            if asset not in prices.columns:
                continue

            price_series = prices[asset].dropna()

            if len(price_series) < self.feature_window:
                continue

            features_df = self._compute_features(price_series)

            if features_df.empty:
                continue

            latest_features = features_df.iloc[-1:][self.feature_cols]

            # Apply stored scaler
            if asset in self.scalers:
                latest_scaled = pd.DataFrame(
                    self.scalers[asset].transform(latest_features),
                    columns=latest_features.columns,
                    index=latest_features.index,
                )
            else:
                latest_scaled = latest_features

            # Get predictions from all ensemble members
            ensemble_preds = np.array([m.predict(latest_scaled)[0] for m in models])

            mean_pred = float(np.mean(ensemble_preds))
            confidence = self._compute_ensemble_confidence(ensemble_preds)

            predictions[asset] = (mean_pred, confidence)

        return predictions

    def save(self, filepath: Union[str, Path]):
        """Save ensemble models and scalers to disk."""
        save_dict = {
            "model_type": "xgboost_ensemble",
            "feature_window": self.feature_window,
            "prediction_horizon": self.prediction_horizon,
            "model_params": self.model_params,
            "n_ensemble": self.n_ensemble,
            "base_seed": self.base_seed,
            "ensemble_models": self.ensemble_models,
            "scalers": self.scalers,
            "feature_cols": self.feature_cols,
        }
        with open(filepath, "wb") as f:
            pickle.dump(save_dict, f)
        print(f"Ensemble models saved to {filepath}")

    def load(self, filepath: Union[str, Path]):
        """Load ensemble models from disk."""
        with open(filepath, "rb") as f:
            save_dict = pickle.load(f)

        if save_dict.get("model_type") != "xgboost_ensemble":
            raise ValueError(
                "Expected xgboost_ensemble artifact. "
                "Use XGBoostCoreModel for single-model artifacts."
            )

        self.feature_window = save_dict["feature_window"]
        self.prediction_horizon = save_dict["prediction_horizon"]
        self.model_params = save_dict["model_params"]
        self.n_ensemble = save_dict["n_ensemble"]
        self.base_seed = save_dict["base_seed"]
        self.ensemble_models = save_dict["ensemble_models"]
        self.scalers = save_dict["scalers"]
        self.feature_cols = save_dict["feature_cols"]
        self._trained = len(self.ensemble_models) > 0
        print(f"Ensemble models loaded from {filepath}")
