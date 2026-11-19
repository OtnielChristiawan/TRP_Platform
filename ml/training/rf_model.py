"""Model 3: Random Forest Regressor for Bakery Demand Forecasting."""
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from ml.features.pipeline import DemandFeaturePipeline


class RandomForestDemandRegressor:
    """Supervised regression using Random Forest with depth constraints to prevent overfitting."""

    def __init__(
        self,
        n_estimators: int = 50,
        max_depth: int = 4,
        min_samples_leaf: int = 2,
        random_state: int = 42,
    ):
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.min_samples_leaf = min_samples_leaf
        self.random_state = random_state
        self.pipeline = DemandFeaturePipeline()
        self.model = RandomForestRegressor(
            n_estimators=n_estimators,
            max_depth=max_depth,
            min_samples_leaf=min_samples_leaf,
            random_state=random_state,
        )
        self.is_fitted = False

    def fit(self, df: pd.DataFrame, target_col: str = "qty_sold"):
        """Fits feature pipeline and Random Forest regressor on training data."""
        y = df[target_col].values.astype(float)
        X = self.pipeline.fit_transform(df)
        self.model.fit(X, y)
        self.is_fitted = True
        return self

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        """Transforms input features and outputs nonnegative clipped predictions."""
        if not self.is_fitted:
            raise ValueError("RandomForestDemandRegressor must be fitted before calling predict.")
        X = self.pipeline.transform(df)
        preds = self.model.predict(X)
        return np.clip(preds, a_min=0.0, a_max=None)
