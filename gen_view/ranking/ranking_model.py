"""
XGBoost Ranking Model for Relative Performance Prediction
==========================================================

Uses LambdaMART (pairwise ranking) to predict relative stock performance.
An ensemble of N models with different random seeds provides:
- Mean ranking scores for view generation
- Score standard deviation for confidence estimation

Training setup:
- Each time step forms one "query group" with K items (stocks)
- Labels are forward returns (the ranker learns to order stocks by future return)
- Walk-forward compatible: train on expanding window, predict at each rebalance
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

# Ensure project root is on sys.path so the top-level `config` module imports
# correctly even when this file is executed directly.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import RANKING_FEATURE_WINDOW, RANKING_PREDICTION_HORIZON
from gen_view.ranking.config import (
    DEFAULT_RANKER_PARAMS,
    RANKING_EARLY_STOPPING_ROUNDS,
    RANKING_ENSEMBLE_BASE_SEED,
    RANKING_ENSEMBLE_SIZE,
    RANKING_MIN_TRAIN_SAMPLES,
    RANKING_VALIDATION_SPLIT_RATIO,
)
from gen_view.ranking.feature_engineering import compute_ranking_features

warnings.filterwarnings("ignore")


class XGBoostRankingModel:
    """
    XGBoost Pairwise Ranking Model with Ensemble.

    Trains N XGBRanker models with different seeds on the same data.
    Predicts ranking scores for K stocks; higher score = expected outperformer.

    Attributes
    ----------
    prediction_horizon : int
        Forward-looking days for labels.
    feature_window : int
        Lookback for feature computation.
    n_ensemble : int
        Number of ensemble members.
    is_trained : bool
        Whether the model has been trained.
    """

    def __init__(
        self,
        prediction_horizon: int = RANKING_PREDICTION_HORIZON,
        feature_window: int = RANKING_FEATURE_WINDOW,
        n_ensemble: int = RANKING_ENSEMBLE_SIZE,
        base_seed: int = RANKING_ENSEMBLE_BASE_SEED,
        model_params: Optional[dict] = None,
    ):
        self.prediction_horizon = prediction_horizon
        self.feature_window = feature_window
        self.n_ensemble = n_ensemble
        self.base_seed = base_seed
        self.model_params = model_params or {}
        self.models: list = []  # List of trained XGBRanker models
        self.scaler: Optional[StandardScaler] = None
        self.feature_cols: list[str] = []
        self.stock_universe: list[str] = []
        self._trained = False

    @property
    def is_trained(self) -> bool:
        return self._trained and len(self.models) > 0

    # ---------------------------------------------------------------- helpers

    def _compute_forward_returns(self, prices: pd.DataFrame) -> pd.DataFrame:
        """
        Compute forward returns for each stock at each date.

        label[t, s] = (price[t + horizon, s] - price[t, s]) / price[t, s]

        The last `prediction_horizon` rows have NaN labels (no future data).
        Returns a DataFrame with the same index and columns as `prices`.
        """
        h = self.prediction_horizon
        future_prices = prices.shift(-h)
        labels = (future_prices - prices) / prices
        return labels

    def _build_training_matrix(
        self,
        features: pd.DataFrame,
        labels: pd.DataFrame,
        stocks: list[str],
    ) -> tuple[pd.DataFrame, pd.Series, np.ndarray, pd.DatetimeIndex]:
        """
        Build the (X, y, group sizes, dates) training matrix.

        Each "query group" is one date containing exactly K=len(stocks) items.
        Dates with any NaN feature/label among the K stocks are dropped wholesale
        so that all surviving groups have an identical group size of K.
        """
        K = len(stocks)
        if K == 0:
            empty_X = pd.DataFrame()
            empty_y = pd.Series(dtype=float)
            return empty_X, empty_y, np.array([], dtype=int), pd.DatetimeIndex([])

        # Long-format labels with the same MultiIndex as features.
        labels_long = (
            labels[stocks]
            .stack(future_stack=True)
            .rename("y")
        )
        labels_long.index.set_names(["date", "stock"], inplace=True)

        # Restrict features to the K selected stocks and same index ordering.
        feat_long = features.loc[
            features.index.get_level_values("stock").isin(stocks)
        ].copy()

        joined = feat_long.join(labels_long, how="inner")
        if joined.empty:
            empty_X = pd.DataFrame()
            empty_y = pd.Series(dtype=float)
            return empty_X, empty_y, np.array([], dtype=int), pd.DatetimeIndex([])

        # Drop rows with any NaN in features or label.
        feat_cols = [c for c in joined.columns if c != "y"]
        valid_mask = (~joined[feat_cols].isna().any(axis=1)) & joined["y"].notna()
        joined = joined.loc[valid_mask]
        if joined.empty:
            empty_X = pd.DataFrame()
            empty_y = pd.Series(dtype=float)
            return empty_X, empty_y, np.array([], dtype=int), pd.DatetimeIndex([])

        # Keep only dates that have a complete row for every one of the K stocks.
        counts = joined.groupby(level="date").size()
        complete_dates = counts.index[counts == K]
        if len(complete_dates) == 0:
            empty_X = pd.DataFrame()
            empty_y = pd.Series(dtype=float)
            return empty_X, empty_y, np.array([], dtype=int), pd.DatetimeIndex([])

        joined = joined.loc[
            joined.index.get_level_values("date").isin(complete_dates)
        ]

        # Sort by (date, stock) so each group is contiguous and stocks appear in
        # a stable order within each group.
        stock_order = {s: i for i, s in enumerate(stocks)}
        joined = joined.assign(
            _date_key=joined.index.get_level_values("date"),
            _stock_order=joined.index.get_level_values("stock").map(stock_order),
        )
        joined = joined.sort_values(
            by=["_date_key", "_stock_order"], kind="mergesort"
        )
        joined = joined.drop(columns=["_date_key", "_stock_order"])

        # Convert forward-return labels into per-group integer relevance grades
        # (0..K-1) so they are compatible with XGBoost's ranking eval metrics
        # (NDCG requires non-negative integer labels). Higher rank = better
        # forward return, which matches the ranking semantics we want to learn.
        date_index = joined.index.get_level_values("date")
        ranks = (
            joined["y"]
            .groupby(date_index)
            .rank(method="first", ascending=True)
            .astype(int)
            - 1
        )
        joined["y"] = ranks

        X = joined[feat_cols]
        y = joined["y"]
        unique_dates = pd.DatetimeIndex(
            joined.index.get_level_values("date").unique()
        )
        group_sizes = np.full(len(unique_dates), K, dtype=int)
        return X, y, group_sizes, unique_dates

    # ------------------------------------------------------------------ train

    def train(
        self,
        prices: pd.DataFrame,
        market_prices: pd.Series,
        verbose: bool = True,
    ) -> None:
        """
        Train ensemble ranking models.

        Parameters
        ----------
        prices : pd.DataFrame
            Historical prices for the K selected stocks (columns = tickers).
        market_prices : pd.Series
            Market proxy prices (e.g. E1VFVN30) aligned to the same index.
        verbose : bool
            Print training progress.
        """
        try:
            import xgboost as xgb
        except ImportError as e:
            raise ImportError(
                "xgboost is required. Install with: pip install xgboost"
            ) from e

        # Reset state so retraining is idempotent.
        self.models = []
        self.scaler = None
        self.feature_cols = []
        self.stock_universe = list(prices.columns)
        self._trained = False

        if prices.shape[1] < 2:
            if verbose:
                print("  Ranking train skipped: need at least 2 stocks.")
            return

        if len(prices.index) <= self.feature_window + self.prediction_horizon:
            if verbose:
                print(
                    f"  Ranking train skipped: only {len(prices.index)} days "
                    f"(need > {self.feature_window + self.prediction_horizon})."
                )
            return

        try:
            features = compute_ranking_features(
                prices, market_prices, self.feature_window
            )
        except Exception as exc:
            warnings.warn(f"Ranking feature computation failed: {exc}")
            return

        if features is None or features.empty:
            if verbose:
                print("  Ranking train skipped: no features computed.")
            return

        labels = self._compute_forward_returns(prices)

        X, y, group_sizes, unique_dates = self._build_training_matrix(
            features, labels, self.stock_universe
        )

        if len(unique_dates) < 2 or len(X) < RANKING_MIN_TRAIN_SAMPLES:
            if verbose:
                print(
                    f"  Ranking train skipped: only {len(X)} valid samples / "
                    f"{len(unique_dates)} groups "
                    f"(min {RANKING_MIN_TRAIN_SAMPLES} samples)."
                )
            return

        # Temporal train/validation split on the unique-date axis so groups stay
        # contiguous and never straddle the split boundary.
        n_groups = len(unique_dates)
        split_groups = int(n_groups * (1 - RANKING_VALIDATION_SPLIT_RATIO))
        split_groups = max(1, min(split_groups, n_groups - 1))

        K = prices.shape[1]
        train_dates = unique_dates[:split_groups]
        val_dates = unique_dates[split_groups:]

        date_level = X.index.get_level_values("date")
        train_mask = date_level.isin(train_dates)
        val_mask = date_level.isin(val_dates)

        X_train = X.loc[train_mask]
        y_train = y.loc[train_mask]
        X_val = X.loc[val_mask]
        y_val = y.loc[val_mask]

        if X_train.empty or X_val.empty:
            if verbose:
                print("  Ranking train skipped: empty train or val split.")
            return

        train_groups = np.full(len(train_dates), K, dtype=int)
        val_groups = np.full(len(val_dates), K, dtype=int)

        # Standardize features using training data only.
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

        base_params = {**DEFAULT_RANKER_PARAMS, **self.model_params}
        # We control the seed per ensemble member.
        base_params.pop("random_state", None)
        base_params.pop("seed", None)

        trained_models: list = []
        try:
            for i in range(self.n_ensemble):
                seed = self.base_seed + i
                params = {
                    **base_params,
                    "random_state": seed,
                    # Diversity: each member sees different feature/data subsets.
                    "subsample": 0.8,
                    "colsample_bytree": 0.7 + 0.05 * i,
                }
                ranker = xgb.XGBRanker(
                    **params,
                    early_stopping_rounds=RANKING_EARLY_STOPPING_ROUNDS,
                )
                ranker.fit(
                    X_train_scaled,
                    y_train,
                    group=train_groups,
                    eval_set=[(X_val_scaled, y_val)],
                    eval_group=[val_groups],
                    verbose=False,
                )
                trained_models.append(ranker)
        except Exception as exc:
            warnings.warn(f"Ranking ensemble training failed: {exc}")
            self.models = []
            self.scaler = None
            self._trained = False
            return

        self.models = trained_models
        self.scaler = scaler
        self.feature_cols = list(X_train.columns)
        self._trained = len(self.models) > 0

        if verbose and self._trained:
            print(
                f"  Ranking ensemble trained: {len(self.models)} models, "
                f"{len(train_dates)} train groups, {len(val_dates)} val groups, "
                f"K={K} stocks/group."
            )

    # ---------------------------------------------------------------- predict

    def predict(
        self,
        prices: pd.DataFrame,
        market_prices: pd.Series,
    ) -> tuple[dict[str, float], dict[str, float]]:
        """
        Predict ranking scores for the latest available date.

        Parameters
        ----------
        prices : pd.DataFrame
            Recent price history (needs at least feature_window days).
        market_prices : pd.Series
            Market proxy recent prices.

        Returns
        -------
        tuple[dict[str, float], dict[str, float]]
            ``(rank_scores, ensemble_std)``:
            - ``rank_scores``: ``{stock: mean_score}`` (higher = better).
            - ``ensemble_std``: ``{stock: std_across_ensemble}``.

            Both dicts are empty when prediction is not possible (model not
            trained, insufficient history, missing stocks, etc.).
        """
        if not self.is_trained or self.scaler is None:
            return {}, {}

        if prices is None or prices.empty or len(prices.index) < self.feature_window:
            return {}, {}

        # Restrict to the stock universe seen during training.
        usable_stocks = [s for s in self.stock_universe if s in prices.columns]
        if len(usable_stocks) < 2:
            return {}, {}
        prices_sub = prices[usable_stocks]

        try:
            features = compute_ranking_features(
                prices_sub, market_prices, self.feature_window
            )
        except Exception as exc:
            warnings.warn(f"Ranking prediction feature computation failed: {exc}")
            return {}, {}

        if features is None or features.empty:
            return {}, {}

        # Take the most recent date that has features for every usable stock.
        date_level = features.index.get_level_values("date")
        latest_date = date_level.max()
        latest = features.loc[date_level == latest_date]

        # Reindex per-stock so order matches `usable_stocks` and missing rows
        # become NaN that we can detect.
        latest_by_stock = latest.reset_index().set_index("stock")
        try:
            latest_by_stock = latest_by_stock.loc[usable_stocks]
        except KeyError:
            return {}, {}

        feature_block = latest_by_stock[self.feature_cols]
        if feature_block.isna().any(axis=None):
            # Drop any stocks with NaN features; need at least 2 stocks left to
            # produce a meaningful ranking.
            valid_mask = ~feature_block.isna().any(axis=1)
            if valid_mask.sum() < 2:
                return {}, {}
            feature_block = feature_block.loc[valid_mask]
            usable_stocks = list(feature_block.index)

        X_latest_scaled = pd.DataFrame(
            self.scaler.transform(feature_block),
            columns=feature_block.columns,
            index=feature_block.index,
        )

        # Predict with each ensemble member; each call ranks a single group of
        # size len(usable_stocks).
        try:
            preds = np.vstack([m.predict(X_latest_scaled) for m in self.models])
        except Exception as exc:
            warnings.warn(f"Ranking ensemble prediction failed: {exc}")
            return {}, {}

        mean_scores = preds.mean(axis=0)
        std_scores = preds.std(axis=0)

        rank_scores = {
            stock: float(score) for stock, score in zip(usable_stocks, mean_scores)
        }
        ensemble_std = {
            stock: float(std) for stock, std in zip(usable_stocks, std_scores)
        }
        return rank_scores, ensemble_std
