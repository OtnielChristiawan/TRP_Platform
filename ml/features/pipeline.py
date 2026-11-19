"""Feature Engineering Pipeline for Demand Forecasting."""
import hashlib
import json
import logging
from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.preprocessing import OneHotEncoder, StandardScaler

logger = logging.getLogger("bakery.ml.features")


class DemandFeaturePipeline(BaseEstimator, TransformerMixin):
    """Encodes calendar, lag, and categorical features without target leakage."""

    def __init__(self, feature_schema_version: str = "v1.0.0"):
        self.feature_schema_version = feature_schema_version
        self.cat_encoder = OneHotEncoder(handle_unknown="ignore", sparse_output=False)
        self.num_scaler = StandardScaler()
        self.num_features = [
            "day_of_week",
            "day_of_month",
            "month",
            "is_weekend",
            "lag_1_qty",
            "lag_7_qty",
            "rolling_avg_7d_qty",
        ]
        self.cat_features = ["menu_category", "branch"]
        self.is_fitted = False
        self.feature_names_: List[str] = []

    def fit(self, X: pd.DataFrame, y=None):
        """Fits encoders and scalers on training data."""
        df = X.copy()
        # Ensure numeric features have non-null fallbacks
        for col in ["lag_1_qty", "lag_7_qty", "rolling_avg_7d_qty"]:
            if col in df.columns:
                df[col] = df[col].fillna(0.0)

        if "is_weekend" in df.columns:
            df["is_weekend"] = df["is_weekend"].astype(int)

        X_num = df[self.num_features].values
        self.num_scaler.fit(X_num)

        X_cat = df[self.cat_features].astype(str).values
        self.cat_encoder.fit(X_cat)

        cat_feature_names = self.cat_encoder.get_feature_names_out(self.cat_features).tolist()
        self.feature_names_ = self.num_features + cat_feature_names
        self.is_fitted = True
        return self

    def transform(self, X: pd.DataFrame) -> np.ndarray:
        """Transforms input DataFrame into feature array."""
        if not self.is_fitted:
            raise ValueError("FeaturePipeline must be fitted before transforming.")
        df = X.copy()

        for col in ["lag_1_qty", "lag_7_qty", "rolling_avg_7d_qty"]:
            if col in df.columns:
                df[col] = df[col].fillna(0.0)
            else:
                df[col] = 0.0

        if "is_weekend" in df.columns:
            df["is_weekend"] = df["is_weekend"].astype(int)
        else:
            df["is_weekend"] = 0

        for col in self.num_features:
            if col not in df.columns:
                df[col] = 0.0

        for col in self.cat_features:
            if col not in df.columns:
                df[col] = "UNKNOWN"

        X_num = df[self.num_features].values
        X_num_scaled = self.num_scaler.transform(X_num)

        X_cat = df[self.cat_features].astype(str).values
        X_cat_encoded = self.cat_encoder.transform(X_cat)

        return np.hstack([X_num_scaled, X_cat_encoded])

    def get_feature_hash(self) -> str:
        """Returns deterministic hash of feature names schema."""
        raw = json.dumps(self.feature_names_, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
