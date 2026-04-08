"""
LLM/ML View Generators for Black-Litterman Model
=================================================

This module provides 3 advanced approaches to generate dynamic views:
1. Traditional ML (Random Forest, XGBoost) - supervised learning
2. Deep Learning (LSTM) - sequential modeling
3. LLM-based (GPT-4, Claude) - combines quantitative + qualitative data

Author: Nguyen Khang
"""

import hashlib
import json
import os
import pickle
import warnings
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Union

import numpy as np
import pandas as pd
from bs4 import BeautifulSoup

warnings.filterwarnings("ignore")

# ====================== CONSTANTS ======================
TRADING_DAYS_PER_YEAR = 252
DEFAULT_FEATURE_WINDOW = 20
DEFAULT_PREDICTION_HORIZON = 5  # days ahead
CACHE_DIR = Path(__file__).parent / ".cache"
CACHE_DIR.mkdir(exist_ok=True)

# ====================== OPTION 1: TRADITIONAL ML ======================


class TraditionalMLViewGenerator:
    """
    Option 1: Traditional ML View Generator
    ----------------------------------------
    Uses Random Forest or XGBoost to predict future returns.

    Training Process:
    1. Extract features from historical price data (MA, RSI, momentum, etc.)
    2. Label data with future returns (e.g., 5-day forward return)
    3. Train supervised model: features -> future return
    4. Use model to predict returns for current assets

    Advantages:
    - Fast training and inference
    - Interpretable feature importance
    - No need for large datasets
    - Works well with tabular financial data

    Disadvantages:
    - Cannot capture complex sequential patterns
    - Requires manual feature engineering
    - May overfit to historical patterns
    """

    def __init__(
        self,
        model_type: str = "random_forest",
        feature_window: int = DEFAULT_FEATURE_WINDOW,
        prediction_horizon: int = DEFAULT_PREDICTION_HORIZON,
        model_params: Optional[dict] = None,
    ):
        """
        Parameters
        ----------
        model_type : str
            "random_forest" or "xgboost"
        feature_window : int
            Window size for feature calculation (e.g., 20 days)
        prediction_horizon : int
            How many days ahead to predict (e.g., 5 days)
        model_params : dict, optional
            Custom parameters for the model
        """
        self.model_type = model_type
        self.feature_window = feature_window
        self.prediction_horizon = prediction_horizon
        self.model_params = model_params or {}
        self.models = {}  # {asset_name: trained_model}
        self.feature_cols = []

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
        from view_generators import (
            compute_momentum,
            compute_rsi,
            compute_ema,
            compute_macd,
        )

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
        Train ML models for each asset.

        Parameters
        ----------
        prices : pd.DataFrame
            Historical price data (columns = assets)
        verbose : bool
            Print training progress
        """
        if self.model_type == "random_forest":
            from sklearn.ensemble import RandomForestRegressor

            default_params = {
                "n_estimators": 100,
                "max_depth": 10,
                "min_samples_split": 20,
                "min_samples_leaf": 10,
                "random_state": 42,
            }
        elif self.model_type == "xgboost":
            try:
                import xgboost as xgb

                default_params = {
                    "n_estimators": 100,
                    "max_depth": 6,
                    "learning_rate": 0.1,
                    "random_state": 42,
                }
            except ImportError:
                if verbose:
                    print("XGBoost not installed. Falling back to Random Forest.")
                from sklearn.ensemble import RandomForestRegressor

                self.model_type = "random_forest"
                default_params = {
                    "n_estimators": 100,
                    "max_depth": 10,
                    "random_state": 42,
                }
        else:
            raise ValueError(f"Unknown model_type: {self.model_type}")

        # Merge default params with custom params
        params = {**default_params, **self.model_params}

        for asset in prices.columns:
            if verbose:
                print(f"Training {self.model_type} for {asset}...")

            price_series = prices[asset].dropna()

            if len(price_series) < self.feature_window + self.prediction_horizon + 50:
                if verbose:
                    print(f"  Skipping {asset}: not enough data")
                continue

            # Compute features and labels
            features_df = self._compute_features(price_series)
            labels_series = self._compute_labels(price_series)

            # Align features and labels
            common_idx = features_df.index.intersection(labels_series.index)
            X = features_df.loc[common_idx]
            y = labels_series.loc[common_idx]

            # Remove rows with NaN in either X or y
            valid_mask = (~X.isna().any(axis=1)) & y.notna()
            X = X[valid_mask]
            y = y[valid_mask]

            if len(X) < 50:
                if verbose:
                    print(f"  Skipping {asset}: not enough valid samples")
                continue

            # Train model
            if self.model_type == "random_forest":
                model = RandomForestRegressor(**params)
            else:
                model = xgb.XGBRegressor(**params)

            model.fit(X, y)
            self.models[asset] = model
            self.feature_cols = list(X.columns)

            if verbose:
                train_score = model.score(X, y)
                print(f"  ✓ {asset} trained. R² score: {train_score:.3f}")

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

            # Compute features for latest data point
            features_df = self._compute_features(price_series)

            if features_df.empty:
                continue

            latest_features = features_df.iloc[-1:][self.feature_cols]

            # Predict
            pred_return = model.predict(latest_features)[0]

            # Estimate confidence (simple heuristic based on feature importance variance)
            # Higher variance in features = lower confidence
            feature_values = latest_features.values[0]
            feature_variance = np.var(feature_values)
            confidence = max(0.3, min(0.9, 0.6 - feature_variance * 5))

            predictions[asset] = (pred_return, confidence)

        return predictions

    def generate_views(
        self,
        prices: pd.DataFrame,
        min_return_threshold: float = 0.005,  # 0.5% over prediction_horizon
    ) -> list[dict]:
        """
        Generate Black-Litterman views from ML predictions.

        Parameters
        ----------
        prices : pd.DataFrame
            Recent price data
        min_return_threshold : float
            Minimum predicted return to generate a view

        Returns
        -------
        list[dict]
            List of view dictionaries
        """
        predictions = self.predict(prices)
        views = []

        for asset, (pred_return, confidence) in predictions.items():
            if abs(pred_return) < min_return_threshold:
                continue

            # Annualize the prediction
            # pred_return is for prediction_horizon days
            view_return_annual = pred_return * (
                TRADING_DAYS_PER_YEAR / self.prediction_horizon
            )
            view_return_annual = max(-0.50, min(0.50, view_return_annual))  # Cap

            views.append(
                {
                    "name": f"{asset}_ml_{self.model_type}",
                    "legs": {asset: 1.0},
                    "view_return_annual": view_return_annual,
                    "confidence": confidence,
                    "source": "traditional_ml",
                    "model_type": self.model_type,
                    "predicted_return_horizon": pred_return,
                }
            )

        return views

    def save(self, filepath: Union[str, Path]):
        """Save trained models to disk."""
        save_dict = {
            "model_type": self.model_type,
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

        self.model_type = save_dict["model_type"]
        self.feature_window = save_dict["feature_window"]
        self.prediction_horizon = save_dict["prediction_horizon"]
        self.model_params = save_dict["model_params"]
        self.models = save_dict["models"]
        self.feature_cols = save_dict["feature_cols"]
        print(f"Models loaded from {filepath}")


# ====================== OPTION 2: DEEP LEARNING (LSTM) ======================


class LSTMViewGenerator:
    """
    Option 2: Deep Learning (LSTM) View Generator
    ----------------------------------------------
    Uses LSTM neural network to model sequential price patterns.

    Training Process:
    1. Create sliding windows of price sequences
    2. Normalize prices to returns or log-returns
    3. Train LSTM to predict next N-day returns
    4. Use model to generate forecasts

    Advantages:
    - Captures complex temporal dependencies
    - No manual feature engineering needed
    - Can learn non-linear patterns
    - State-of-the-art for time series

    Disadvantages:
    - Requires more data (1000+ samples)
    - Slower training and inference
    - Black-box (harder to interpret)
    - Risk of overfitting
    """

    def __init__(
        self,
        sequence_length: int = 60,  # 60 days lookback
        prediction_horizon: int = DEFAULT_PREDICTION_HORIZON,
        hidden_size: int = 64,
        num_layers: int = 2,
        dropout: float = 0.2,
        learning_rate: float = 0.001,
        epochs: int = 50,
        batch_size: int = 32,
        device: str = "cpu",
    ):
        """
        Parameters
        ----------
        sequence_length : int
            Length of input sequence (e.g., 60 days)
        prediction_horizon : int
            How many days ahead to predict
        hidden_size : int
            LSTM hidden layer size
        num_layers : int
            Number of LSTM layers
        dropout : float
            Dropout rate for regularization
        learning_rate : float
            Learning rate for Adam optimizer
        epochs : int
            Number of training epochs
        batch_size : int
            Batch size for training
        device : str
            "cpu" or "cuda"
        """
        self.sequence_length = sequence_length
        self.prediction_horizon = prediction_horizon
        self.hidden_size = hidden_size
        self.num_layers = num_layers
        self.dropout = dropout
        self.learning_rate = learning_rate
        self.epochs = epochs
        self.batch_size = batch_size
        self.device = device

        self.models = {}  # {asset_name: trained_model}
        self.scalers = {}  # {asset_name: scaler}

        # Check if PyTorch is available
        try:
            import torch

            self.torch = torch
            self.torch_available = True
        except ImportError:
            self.torch_available = False
            print("WARNING: PyTorch not installed. LSTM generator will not work.")
            print("Install with: pip install torch")

    def _create_sequences(self, prices: pd.Series) -> tuple[np.ndarray, np.ndarray]:
        """
        Create (X, y) sequences for LSTM training.

        X: [num_samples, sequence_length, 1]
        y: [num_samples]
        """
        # Convert to returns
        returns = prices.pct_change().fillna(0).values

        X, y = [], []

        for i in range(self.sequence_length, len(returns) - self.prediction_horizon):
            X.append(returns[i - self.sequence_length : i])
            # Target: cumulative return over prediction_horizon
            future_returns = returns[i : i + self.prediction_horizon]
            cumulative_return = np.prod(1 + future_returns) - 1
            y.append(cumulative_return)

        return np.array(X), np.array(y)

    def _build_model(self):
        """Build LSTM model using PyTorch."""
        import torch.nn as nn

        class LSTMModel(nn.Module):
            def __init__(self, input_size, hidden_size, num_layers, dropout):
                super(LSTMModel, self).__init__()
                self.lstm = nn.LSTM(
                    input_size=input_size,
                    hidden_size=hidden_size,
                    num_layers=num_layers,
                    dropout=dropout,
                    batch_first=True,
                )
                self.fc = nn.Linear(hidden_size, 1)

            def forward(self, x):
                # x: [batch, seq_len, input_size]
                out, (hn, cn) = self.lstm(x)
                # Take last time step
                out = out[:, -1, :]
                out = self.fc(out)
                return out.squeeze()

        model = LSTMModel(
            input_size=1,
            hidden_size=self.hidden_size,
            num_layers=self.num_layers,
            dropout=self.dropout,
        )

        return model

    def train(self, prices: pd.DataFrame, verbose: bool = True):
        """
        Train LSTM models for each asset.

        Parameters
        ----------
        prices : pd.DataFrame
            Historical price data
        verbose : bool
            Print training progress
        """
        if not self.torch_available:
            print("ERROR: PyTorch not available. Cannot train LSTM.")
            return

        import torch.nn as nn
        import torch.optim as optim
        from torch.utils.data import TensorDataset, DataLoader

        for asset in prices.columns:
            if verbose:
                print(f"Training LSTM for {asset}...")

            price_series = prices[asset].dropna()

            if len(price_series) < self.sequence_length + self.prediction_horizon + 100:
                if verbose:
                    print(f"  Skipping {asset}: not enough data (need 100+ samples)")
                continue

            # Create sequences
            X, y = self._create_sequences(price_series)

            if len(X) < 50:
                if verbose:
                    print(f"  Skipping {asset}: not enough sequences")
                continue

            # Convert to PyTorch tensors
            X_tensor = self.torch.FloatTensor(X).unsqueeze(-1)  # Add feature dimension
            y_tensor = self.torch.FloatTensor(y)

            # Split train/val
            split_idx = int(len(X_tensor) * 0.8)
            X_train, X_val = X_tensor[:split_idx], X_tensor[split_idx:]
            y_train, y_val = y_tensor[:split_idx], y_tensor[split_idx:]

            # Create data loaders
            train_dataset = TensorDataset(X_train, y_train)
            train_loader = DataLoader(
                train_dataset, batch_size=self.batch_size, shuffle=True
            )

            # Build model
            model = self._build_model()
            model.to(self.device)

            criterion = nn.MSELoss()
            optimizer = optim.Adam(model.parameters(), lr=self.learning_rate)

            # Training loop
            best_val_loss = float("inf")
            patience = 10
            patience_counter = 0

            for epoch in range(self.epochs):
                model.train()
                train_loss = 0.0

                for batch_X, batch_y in train_loader:
                    batch_X = batch_X.to(self.device)
                    batch_y = batch_y.to(self.device)

                    optimizer.zero_grad()
                    outputs = model(batch_X)
                    loss = criterion(outputs, batch_y)
                    loss.backward()
                    optimizer.step()

                    train_loss += loss.item()

                train_loss /= len(train_loader)

                # Validation
                model.eval()
                with self.torch.no_grad():
                    val_pred = model(X_val.to(self.device))
                    val_loss = criterion(val_pred, y_val.to(self.device)).item()

                if verbose and (epoch + 1) % 10 == 0:
                    print(
                        f"  Epoch {epoch + 1}/{self.epochs}: Train Loss={train_loss:.6f}, Val Loss={val_loss:.6f}"
                    )

                # Early stopping
                if val_loss < best_val_loss:
                    best_val_loss = val_loss
                    patience_counter = 0
                    best_model_state = model.state_dict()
                else:
                    patience_counter += 1
                    if patience_counter >= patience:
                        if verbose:
                            print(f"  Early stopping at epoch {epoch + 1}")
                        break

            # Restore best model
            model.load_state_dict(best_model_state)
            self.models[asset] = model

            if verbose:
                print(f"  ✓ {asset} trained. Best Val Loss: {best_val_loss:.6f}")

        if verbose:
            print(f"\nTraining complete. {len(self.models)} LSTM models trained.")

    def predict(self, prices: pd.DataFrame) -> dict[str, tuple[float, float]]:
        """
        Predict future returns using trained LSTM models.

        Parameters
        ----------
        prices : pd.DataFrame
            Recent price data

        Returns
        -------
        dict
            {asset_name: (predicted_return, confidence)}
        """
        if not self.torch_available:
            return {}

        predictions = {}

        for asset, model in self.models.items():
            if asset not in prices.columns:
                continue

            price_series = prices[asset].dropna()

            if len(price_series) < self.sequence_length:
                continue

            # Get last sequence
            returns = price_series.pct_change().fillna(0).values
            last_sequence = returns[-self.sequence_length :]

            # Convert to tensor
            X = self.torch.FloatTensor(last_sequence).unsqueeze(0).unsqueeze(-1)
            X = X.to(self.device)

            # Predict
            model.eval()
            with self.torch.no_grad():
                pred_return = model(X).item()

            # Confidence heuristic: based on recent volatility
            recent_vol = np.std(returns[-20:])
            confidence = max(0.3, min(0.9, 0.7 - recent_vol * 10))

            predictions[asset] = (pred_return, confidence)

        return predictions

    def generate_views(
        self,
        prices: pd.DataFrame,
        min_return_threshold: float = 0.005,
    ) -> list[dict]:
        """
        Generate Black-Litterman views from LSTM predictions.

        Parameters
        ----------
        prices : pd.DataFrame
            Recent price data
        min_return_threshold : float
            Minimum predicted return to generate a view

        Returns
        -------
        list[dict]
            List of view dictionaries
        """
        predictions = self.predict(prices)
        views = []

        for asset, (pred_return, confidence) in predictions.items():
            if abs(pred_return) < min_return_threshold:
                continue

            # Annualize
            view_return_annual = pred_return * (
                TRADING_DAYS_PER_YEAR / self.prediction_horizon
            )
            view_return_annual = max(-0.50, min(0.50, view_return_annual))

            views.append(
                {
                    "name": f"{asset}_lstm",
                    "legs": {asset: 1.0},
                    "view_return_annual": view_return_annual,
                    "confidence": confidence,
                    "source": "deep_learning",
                    "model_type": "lstm",
                    "predicted_return_horizon": pred_return,
                }
            )

        return views

    def save(self, filepath: Union[str, Path]):
        """Save trained models to disk."""
        if not self.torch_available:
            return

        save_dict = {
            "sequence_length": self.sequence_length,
            "prediction_horizon": self.prediction_horizon,
            "hidden_size": self.hidden_size,
            "num_layers": self.num_layers,
            "models": {k: v.state_dict() for k, v in self.models.items()},
        }
        self.torch.save(save_dict, filepath)
        print(f"LSTM models saved to {filepath}")

    def load(self, filepath: Union[str, Path]):
        """Load trained models from disk."""
        if not self.torch_available:
            return

        save_dict = self.torch.load(filepath)
        self.sequence_length = save_dict["sequence_length"]
        self.prediction_horizon = save_dict["prediction_horizon"]
        self.hidden_size = save_dict["hidden_size"]
        self.num_layers = save_dict["num_layers"]

        for asset, state_dict in save_dict["models"].items():
            model = self._build_model()
            model.load_state_dict(state_dict)
            model.eval()
            self.models[asset] = model

        print(f"LSTM models loaded from {filepath}")


# ====================== OPTION 3: LLM-BASED ======================


class LLMViewGenerator:
    """
    Option 3: LLM-based View Generator (GPT-4, Claude)
    ---------------------------------------------------
    Uses Large Language Models to analyze both quantitative and qualitative data.

    Input Sources:
    1. Price data & technical indicators (quantitative)
    2. News headlines and articles (qualitative)
    3. Market sentiment from social media (optional)

    Process:
    1. Crawl news from CafeF, VnExpress, etc.
    2. Extract relevant articles for each asset
    3. Construct prompt with price data + news
    4. Query LLM API (GPT-4 or Claude)
    5. Parse LLM response to extract views

    Advantages:
    - Combines quantitative + qualitative analysis
    - Can interpret news, events, sentiment
    - No training needed (zero-shot or few-shot)
    - Human-like reasoning

    Disadvantages:
    - High API costs ($0.03-0.10 per view)
    - Latency (2-5 seconds per call)
    - Non-deterministic outputs
    - Requires internet connection
    """

    def __init__(
        self,
        llm_provider: str = "openai",  # "openai" or "anthropic"
        model_name: str = "gpt-4",  # or "claude-3-sonnet-20240229"
        api_key: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 500,
        enable_caching: bool = True,
        cache_ttl_hours: int = 24,
        enable_news: bool = True,
        news_lookback_days: int = 7,
    ):
        """
        Parameters
        ----------
        llm_provider : str
            "openai" or "anthropic"
        model_name : str
            Model name (e.g., "gpt-4", "gpt-3.5-turbo", "claude-3-sonnet")
        api_key : str, optional
            API key (if None, will look for environment variable)
        temperature : float
            Sampling temperature (0-1, lower = more deterministic)
        max_tokens : int
            Maximum tokens for response
        enable_caching : bool
            Cache LLM responses to reduce costs
        cache_ttl_hours : int
            Cache time-to-live in hours
        enable_news : bool
            Whether to include news in prompts
        news_lookback_days : int
            How many days of news to retrieve
        """
        self.llm_provider = llm_provider.lower()
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.enable_caching = enable_caching
        self.cache_ttl_hours = cache_ttl_hours
        self.enable_news = enable_news
        self.news_lookback_days = news_lookback_days

        # Get API key
        if api_key is None:
            if self.llm_provider == "openai":
                api_key = os.getenv("OPENAI_API_KEY")
            elif self.llm_provider == "anthropic":
                api_key = os.getenv("ANTHROPIC_API_KEY")

        self.api_key = api_key

        # Initialize client
        self.client = None
        if self.api_key:
            self._initialize_client()

        # Cost tracking
        self.total_cost = 0.0
        self.total_calls = 0

    def _initialize_client(self):
        """Initialize LLM API client."""
        try:
            if self.llm_provider == "openai":
                import openai

                self.client = openai.OpenAI(api_key=self.api_key)
            elif self.llm_provider == "anthropic":
                import anthropic

                self.client = anthropic.Anthropic(api_key=self.api_key)
            else:
                print(f"WARNING: Unknown LLM provider: {self.llm_provider}")
        except ImportError as e:
            print(f"ERROR: {e}")
            print(f"Install with: pip install {self.llm_provider}")

    def _get_cache_key(self, asset: str, prices: pd.Series, news: list[dict]) -> str:
        """Generate cache key based on inputs."""
        # Hash based on asset, recent prices, and news titles
        content = f"{asset}_{prices.tail(5).to_json()}"
        if news:
            content += "_" + "_".join([n["title"] for n in news[:3]])
        return hashlib.md5(content.encode()).hexdigest()

    def _get_cached_response(self, cache_key: str) -> Optional[dict]:
        """Retrieve cached LLM response if valid."""
        cache_file = CACHE_DIR / f"llm_{cache_key}.json"

        if not cache_file.exists():
            return None

        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                cached = json.load(f)

            # Check TTL
            cache_time = datetime.fromisoformat(cached["timestamp"])
            if datetime.now() - cache_time > timedelta(hours=self.cache_ttl_hours):
                return None

            return cached["response"]
        except Exception:
            return None

    def _save_cached_response(self, cache_key: str, response: dict):
        """Save LLM response to cache."""
        cache_file = CACHE_DIR / f"llm_{cache_key}.json"

        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "timestamp": datetime.now().isoformat(),
                    "response": response,
                },
                f,
                ensure_ascii=False,
                indent=2,
            )

    def _crawl_news(self, asset: str, days: int = 7) -> list[dict]:
        """
        Crawl news for a specific asset.

        Returns
        -------
        list[dict]
            [{"title": str, "date": str, "url": str, "snippet": str}, ...]
        """
        # Mapping asset to search keywords (Vietnamese)
        asset_keywords = {
            "E1VFVN30": ["VN30", "HOSE", "chứng khoán", "VNIndex"],
            "GOLD": ["vàng SJC", "giá vàng", "vàng trong nước"],
            "DCDS": ["DCDS", "Dragon Capital", "quỹ đầu tư"],
            "MBBOND": ["MBBOND", "MB", "trái phiếu", "quỹ trái phiếu"],
        }

        keywords = asset_keywords.get(asset, [asset])
        news = []

        # Placeholder for actual news crawling
        # In practice, you would use BeautifulSoup to scrape CafeF, VnExpress, etc.
        # For demonstration, return empty list

        # TODO: Implement actual news crawling
        # Example sources:
        # - https://cafef.vn/
        # - https://vnexpress.net/kinh-doanh
        # - https://baodautu.vn/

        # Simulated news for demo
        if asset == "GOLD":
            news.append(
                {
                    "title": "Giá vàng SJC tăng mạnh do USD yếu",
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "url": "https://cafef.vn/...",
                    "snippet": "Giá vàng SJC trong nước tăng 200 nghìn đồng...",
                }
            )

        return news

    def _construct_prompt(
        self,
        asset: str,
        prices: pd.Series,
        news: list[dict],
    ) -> str:
        """
        Construct prompt for LLM.

        Prompt structure:
        1. Task description (tiếng Việt)
        2. Asset information
        3. Recent price data & technical indicators
        4. News headlines (if available)
        5. Output format specification
        """
        from view_generators import compute_momentum, compute_rsi, compute_macd

        # Calculate indicators
        momentum_5 = compute_momentum(prices, 5)
        momentum_20 = compute_momentum(prices, 20)
        rsi = compute_rsi(prices, 14)
        macd, signal, hist = compute_macd(prices)

        # Recent prices (last 10 days)
        recent_prices = prices.tail(10)
        price_table = "\n".join(
            [
                f"  {date.strftime('%Y-%m-%d')}: {price:,.0f}"
                for date, price in recent_prices.items()
            ]
        )

        # News section
        news_section = ""
        if news:
            news_section = "\n\n## Tin tức gần đây:\n"
            for n in news[:5]:
                news_section += f"- [{n['date']}] {n['title']}\n"
                if n.get("snippet"):
                    news_section += f"  {n['snippet'][:100]}...\n"

        prompt = f"""Bạn là chuyên gia phân tích tài chính Việt Nam. Nhiệm vụ của bạn là đánh giá triển vọng của tài sản "{asset}" và đưa ra dự báo lợi nhuận.

## Thông tin tài sản: {asset}

### Giá gần đây (10 ngày):
{price_table}

### Chỉ báo kỹ thuật:
- Momentum 5 ngày: {momentum_5:.2%}
- Momentum 20 ngày: {momentum_20:.2%}
- RSI (14): {rsi:.1f}
- MACD Histogram: {hist:.4f}

{news_section}

## Yêu cầu:
Dựa trên dữ liệu trên, hãy đánh giá và dự báo:

1. **Xu hướng**: Tài sản này có xu hướng tăng, giảm, hay đi ngang trong 5-10 ngày tới?
2. **Lợi nhuận dự kiến**: Ước tính % lợi nhuận kỳ vọng hàng năm (có thể âm nếu dự báo giảm)
3. **Độ tin cậy**: Mức độ chắc chắn của dự báo (0.0 - 1.0)
4. **Lý do**: Giải thích ngắn gọn (1-2 câu)

## Định dạng trả lời (JSON):
```json
{{
  "trend": "bullish/bearish/neutral",
  "expected_annual_return": 0.05,
  "confidence": 0.7,
  "reasoning": "Lý do phân tích..."
}}
```

Chỉ trả lời JSON, không thêm text khác."""

        return prompt

    def _query_llm(self, prompt: str) -> Optional[dict]:
        """
        Query LLM API and parse response.

        Returns
        -------
        dict or None
            {"trend": str, "expected_annual_return": float, "confidence": float, "reasoning": str}
        """
        if self.client is None:
            print("ERROR: LLM client not initialized. Please provide API key.")
            return None

        try:
            if self.llm_provider == "openai":
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                )
                content = response.choices[0].message.content

                # Estimate cost (rough approximation)
                # GPT-4: ~$0.03/1K input tokens, ~$0.06/1K output tokens
                input_tokens = len(prompt) // 4
                output_tokens = len(content) // 4
                cost = (input_tokens * 0.03 + output_tokens * 0.06) / 1000

            elif self.llm_provider == "anthropic":
                response = self.client.messages.create(
                    model=self.model_name,
                    max_tokens=self.max_tokens,
                    temperature=self.temperature,
                    messages=[{"role": "user", "content": prompt}],
                )
                content = response.content[0].text

                # Estimate cost for Claude
                # Claude Sonnet: ~$0.003/1K input, ~$0.015/1K output
                input_tokens = len(prompt) // 4
                output_tokens = len(content) // 4
                cost = (input_tokens * 0.003 + output_tokens * 0.015) / 1000

            else:
                return None

            self.total_cost += cost
            self.total_calls += 1

            # Parse JSON from response
            # LLM might wrap JSON in ```json ... ``` or include extra text
            content = content.strip()

            # Extract JSON block
            if "```json" in content:
                start = content.index("```json") + 7
                end = content.index("```", start)
                content = content[start:end].strip()
            elif "```" in content:
                start = content.index("```") + 3
                end = content.index("```", start)
                content = content[start:end].strip()

            result = json.loads(content)
            return result

        except Exception as e:
            print(f"ERROR querying LLM: {e}")
            return None

    def generate_views(
        self,
        prices: pd.DataFrame,
        verbose: bool = False,
    ) -> list[dict]:
        """
        Generate views using LLM for each asset.

        Parameters
        ----------
        prices : pd.DataFrame
            Recent price data
        verbose : bool
            Print debug info

        Returns
        -------
        list[dict]
            List of view dictionaries
        """
        views = []

        for asset in prices.columns:
            if verbose:
                print(f"Generating LLM view for {asset}...")

            price_series = prices[asset].dropna()

            if len(price_series) < 30:
                continue

            # Get news if enabled
            news = []
            if self.enable_news:
                news = self._crawl_news(asset, self.news_lookback_days)

            # Check cache
            llm_response = None
            if self.enable_caching:
                cache_key = self._get_cache_key(asset, price_series, news)
                llm_response = self._get_cached_response(cache_key)
                if llm_response and verbose:
                    print(f"  Using cached response for {asset}")

            # Query LLM if not cached
            if llm_response is None:
                prompt = self._construct_prompt(asset, price_series, news)
                llm_response = self._query_llm(prompt)

                if llm_response and self.enable_caching:
                    self._save_cached_response(cache_key, llm_response)

            if llm_response is None:
                continue

            # Convert to view format
            view_return_annual = llm_response.get("expected_annual_return", 0.0)
            confidence = llm_response.get("confidence", 0.5)

            # Validate and cap
            view_return_annual = max(-0.50, min(0.50, view_return_annual))
            confidence = max(0.1, min(0.95, confidence))

            views.append(
                {
                    "name": f"{asset}_llm",
                    "legs": {asset: 1.0},
                    "view_return_annual": view_return_annual,
                    "confidence": confidence,
                    "source": "llm",
                    "llm_provider": self.llm_provider,
                    "model_name": self.model_name,
                    "trend": llm_response.get("trend", "neutral"),
                    "reasoning": llm_response.get("reasoning", ""),
                }
            )

            if verbose:
                print(
                    f"  ✓ View: {view_return_annual:.2%} (confidence: {confidence:.2f})"
                )
                print(f"  Reasoning: {llm_response.get('reasoning', '')}")

        if verbose:
            print(f"\nTotal LLM calls: {self.total_calls}")
            print(f"Total estimated cost: ${self.total_cost:.4f}")

        return views

    def get_cost_summary(self) -> dict:
        """Get cost tracking summary."""
        return {
            "total_calls": self.total_calls,
            "total_cost_usd": self.total_cost,
            "avg_cost_per_call": self.total_cost / max(self.total_calls, 1),
        }


# ====================== UTILITY FUNCTIONS ======================


def crawl_cafef_news(keywords: list[str], days: int = 7) -> list[dict]:
    """
    Crawl news from CafeF.vn

    Parameters
    ----------
    keywords : list[str]
        Search keywords
    days : int
        Lookback days

    Returns
    -------
    list[dict]
        News articles
    """
    import requests

    news = []
    base_url = "https://cafef.vn"

    try:
        # This is a simplified example - actual implementation needs proper scraping
        # You may need to use Selenium for dynamic content

        for keyword in keywords:
            search_url = f"{base_url}/timeline/2.chn"  # Example URL

            response = requests.get(search_url, timeout=10)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, "html.parser")

            # Find article elements (adjust selectors based on actual HTML structure)
            articles = soup.find_all("div", class_="article-item", limit=10)

            for article in articles:
                try:
                    title_elem = article.find("h3")
                    title = title_elem.get_text(strip=True) if title_elem else ""

                    link_elem = article.find("a")
                    url = base_url + link_elem["href"] if link_elem else ""

                    date_elem = article.find("span", class_="date")
                    date = date_elem.get_text(strip=True) if date_elem else ""

                    snippet_elem = article.find("p")
                    snippet = snippet_elem.get_text(strip=True) if snippet_elem else ""

                    if title and keyword.lower() in title.lower():
                        news.append(
                            {
                                "title": title,
                                "url": url,
                                "date": date,
                                "snippet": snippet,
                                "source": "cafef",
                            }
                        )
                except Exception:
                    continue

    except Exception as e:
        print(f"Error crawling CafeF: {e}")

    return news


def combine_multi_source_views(
    traditional_ml_views: list[dict],
    lstm_views: list[dict],
    llm_views: list[dict],
    weights: tuple[float, float, float] = (0.3, 0.3, 0.4),
) -> list[dict]:
    """
    Combine views from multiple ML/LLM sources.

    Parameters
    ----------
    traditional_ml_views : list[dict]
        Views from Random Forest / XGBoost
    lstm_views : list[dict]
        Views from LSTM
    llm_views : list[dict]
        Views from GPT-4 / Claude
    weights : tuple[float, float, float]
        Weights for (traditional_ml, lstm, llm)

    Returns
    -------
    list[dict]
        Combined views with adjusted confidence
    """
    combined = []

    w_ml, w_lstm, w_llm = weights

    for view in traditional_ml_views:
        view = view.copy()
        view["confidence"] *= w_ml
        combined.append(view)

    for view in lstm_views:
        view = view.copy()
        view["confidence"] *= w_lstm
        combined.append(view)

    for view in llm_views:
        view = view.copy()
        view["confidence"] *= w_llm
        combined.append(view)

    return combined


# ====================== EXAMPLE USAGE ======================


if __name__ == "__main__":
    print("=" * 70)
    print("LLM/ML View Generators Demo")
    print("=" * 70)

    # Create sample data
    np.random.seed(42)
    dates = pd.date_range("2023-01-01", periods=200, freq="B")
    sample_prices = pd.DataFrame(
        {
            "E1VFVN30": 100 * (1 + np.random.randn(200).cumsum() * 0.01),
            "GOLD": 50 * (1 + np.random.randn(200).cumsum() * 0.008),
        },
        index=dates,
    )

    print("\nSample Price Data:")
    print(sample_prices.tail())

    # ====================== OPTION 1: Traditional ML ======================
    print("\n" + "=" * 70)
    print("OPTION 1: Traditional ML (Random Forest)")
    print("=" * 70)

    ml_generator = TraditionalMLViewGenerator(
        model_type="random_forest",
        feature_window=20,
        prediction_horizon=5,
    )

    # Split train/test
    train_prices = sample_prices.iloc[:150]
    test_prices = sample_prices.iloc[150:]

    print("\nTraining Random Forest models...")
    ml_generator.train(train_prices, verbose=True)

    print("\nGenerating ML views on test data...")
    ml_views = ml_generator.generate_views(test_prices)

    for v in ml_views:
        print(
            f"  {v['name']}: {v['view_return_annual']:.2%} (confidence: {v['confidence']:.2f})"
        )

    # Save model
    model_path = CACHE_DIR / "random_forest_models.pkl"
    ml_generator.save(model_path)
    print(f"\nModel saved to: {model_path}")

    # ====================== OPTION 2: LSTM ======================
    print("\n" + "=" * 70)
    print("OPTION 2: Deep Learning (LSTM)")
    print("=" * 70)

    lstm_generator = LSTMViewGenerator(
        sequence_length=60,
        prediction_horizon=5,
        hidden_size=32,
        num_layers=1,
        epochs=20,
        batch_size=16,
    )

    if lstm_generator.torch_available:
        print("\nTraining LSTM models...")
        lstm_generator.train(train_prices, verbose=True)

        print("\nGenerating LSTM views on test data...")
        lstm_views = lstm_generator.generate_views(test_prices)

        for v in lstm_views:
            print(
                f"  {v['name']}: {v['view_return_annual']:.2%} (confidence: {v['confidence']:.2f})"
            )

        # Save model
        lstm_path = CACHE_DIR / "lstm_models.pt"
        lstm_generator.save(lstm_path)
        print(f"\nModel saved to: {lstm_path}")
    else:
        print("\nPyTorch not available. Skipping LSTM demo.")
        print("Install with: pip install torch")
        lstm_views = []

    # ====================== OPTION 3: LLM ======================
    print("\n" + "=" * 70)
    print("OPTION 3: LLM-based (GPT-4 / Claude)")
    print("=" * 70)

    # Check for API key
    openai_key = os.getenv("OPENAI_API_KEY")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")

    if openai_key or anthropic_key:
        provider = "openai" if openai_key else "anthropic"
        model = "gpt-4" if provider == "openai" else "claude-3-sonnet-20240229"

        llm_generator = LLMViewGenerator(
            llm_provider=provider,
            model_name=model,
            enable_caching=True,
            enable_news=False,  # Disable for demo (no actual news crawler)
        )

        print(f"\nUsing {provider} ({model})...")
        print("Generating LLM views on test data...")

        llm_views = llm_generator.generate_views(test_prices, verbose=True)

        for v in llm_views:
            print(
                f"  {v['name']}: {v['view_return_annual']:.2%} (confidence: {v['confidence']:.2f})"
            )
            print(f"    Reasoning: {v.get('reasoning', 'N/A')}")

        print("\nCost Summary:")
        cost_summary = llm_generator.get_cost_summary()
        print(f"  Total calls: {cost_summary['total_calls']}")
        print(f"  Total cost: ${cost_summary['total_cost_usd']:.4f}")
        print(f"  Avg cost per call: ${cost_summary['avg_cost_per_call']:.4f}")
    else:
        print("\nNo API key found. Skipping LLM demo.")
        print("Set OPENAI_API_KEY or ANTHROPIC_API_KEY environment variable.")
        llm_views = []

    # ====================== COMBINE VIEWS ======================
    print("\n" + "=" * 70)
    print("COMBINING VIEWS FROM ALL 3 OPTIONS")
    print("=" * 70)

    combined_views = combine_multi_source_views(
        traditional_ml_views=ml_views,
        lstm_views=lstm_views,
        llm_views=llm_views,
        weights=(0.3, 0.3, 0.4),
    )

    print(f"\nTotal combined views: {len(combined_views)}")
    for v in combined_views:
        print(
            f"  [{v['source']}] {v['name']}: {v['view_return_annual']:.2%} (conf: {v['confidence']:.2f})"
        )

    print("\n" + "=" * 70)
    print("Demo complete! You can now experiment with these generators.")
    print("=" * 70)
    print("\nNext steps:")
    print("1. Integrate with backtest.py by setting VIEW_MODE = 'ml'")
    print("2. Train models on your actual data (train period: 2020-2023)")
    print("3. Test on test period (2023-present)")
    print("4. Compare performance with rule_based views")
    print("5. Write thesis chapter on results!")
