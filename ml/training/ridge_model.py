"""Model 2: Ridge Regression for Bakery Demand Forecasting."""
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from ml.features.pipeline import DemandFeaturePipeline


class RidgeDemandRegressor:
    """Supervised regression using L2 regularized linear model and feature pipeline."""

    def __init__(self, alpha: float = 1.0, random_state: int = 42):
        self.alpha = alpha
        self.random_state = random_state
        self.pipeline = DemandFeaturePipeline()
        self.model = Ridge(alpha=alpha, random_state=random_state)
        self.is_fitted = False

    def fit(self, df: pd.DataFrame, target_col: str = "qty_sold"):
        """Fits feature pipeline and Ridge regressor on training data."""
        y = df[target_col].values.astype(float)
        X = self.pipeline.fit_transform(df)
        self.model.fit(X, y)
        self.is_fitted = True
        return self

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        """Transforms input features and outputs nonnegative clipped predictions."""
        if not self.is_fitted:
            raise ValueError("RidgeDemandRegressor must be fitted before calling predict.")
        X = self.pipeline.transform(df)
        preds = self.model.predict(X)
        return np.clip(preds, a_min=0.0, a_max=None)
