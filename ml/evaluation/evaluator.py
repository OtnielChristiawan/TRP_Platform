"""Evaluation metrics and model comparison for Demand Forecasting."""
from typing import Dict
import numpy as np


def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, float]:
    """Computes MAE, RMSE, and WAPE evaluation metrics."""
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)

    if len(y_true) == 0:
        return {"mae": 0.0, "rmse": 0.0, "wape": 0.0, "sample_count": 0}

    mae = float(np.mean(np.abs(y_true - y_pred)))
    rmse = float(np.sqrt(np.mean((y_true - y_pred) ** 2)))

    sum_true = float(np.sum(y_true))
    if sum_true > 0:
        wape = float(np.sum(np.abs(y_true - y_pred)) / sum_true)
    else:
        wape = 0.0

    return {
        "mae": round(mae, 4),
        "rmse": round(rmse, 4),
        "wape": round(wape, 4),
        "sample_count": len(y_true),
    }
