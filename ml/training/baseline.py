"""Model 1: Naive Demand Forecast Baseline."""
import numpy as np
import pandas as pd


class NaiveDemandBaseline:
    """Baseline forecasting model using lag-1 (last observed value) with fallback to menu mean."""

    def __init__(self):
        self.menu_means_ = {}
        self.global_mean_ = 0.0
        self.is_fitted = False

    def fit(self, df: pd.DataFrame, target_col: str = "qty_sold"):
        """Computes historical means per menu to serve as fallback when lag_1 is unavailable."""
        self.global_mean_ = float(df[target_col].mean()) if len(df) > 0 else 0.0
        grouped = df.groupby("menu_key")[target_col].mean().to_dict()
        self.menu_means_ = {k: float(v) for k, v in grouped.items()}
        self.is_fitted = True
        return self

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        """Generates predictions strictly based on lag_1_qty or fallback mean."""
        preds = []
        for _, row in df.iterrows():
            lag_1 = row.get("lag_1_qty")
            menu_key = row.get("menu_key")
            if pd.notna(lag_1) and lag_1 > 0:
                val = float(lag_1)
            elif menu_key in self.menu_means_:
                val = self.menu_means_[menu_key]
            else:
                val = self.global_mean_
            preds.append(max(0.0, float(val)))
        return np.array(preds)
