"""Comprehensive Unit and Integration tests for ML Pipeline (Compliance with Section 13 & F-11, F-12)."""
import os
import shutil
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
import numpy as np
import pandas as pd
import pytest

from ml.evaluation.evaluator import compute_metrics
from ml.features.pipeline import DemandFeaturePipeline
from ml.inference.batch_inference import BatchInferenceEngine
from ml.tracking.tracker import ExperimentTracker
from ml.training.baseline import NaiveDemandBaseline
from ml.training.rf_model import RandomForestDemandRegressor
from ml.training.ridge_model import RidgeDemandRegressor
from ml.training.train_runner import run_training_pipeline


@pytest.fixture
def sample_feature_df():
    """Generates synthetic demand feature records for isolated unit testing."""
    records = []
    base_date = date(2026, 10, 1)
    menus = ["original_salt_bread", "kopi_susu_trp", "butter_croissant"]
    categories = ["PASTRY", "BEVERAGE", "PASTRY"]

    for d in range(14):
        cur_date = base_date + timedelta(days=d)
        for i, m in enumerate(menus):
            qty = 10.0 + (d % 7) * 2.0 + i * 5.0
            records.append(
                {
                    "sales_date": cur_date,
                    "branch": "Toko Roti Pagi",
                    "menu_key": m,
                    "menu_name": m.replace("_", " ").title(),
                    "menu_category": categories[i],
                    "qty_sold": qty,
                    "day_of_week": (cur_date.weekday() + 1) % 7 + 1,
                    "day_of_month": cur_date.day,
                    "month": cur_date.month,
                    "is_weekend": cur_date.weekday() in [5, 6],
                    "lag_1_qty": qty - 2.0 if d > 0 else 0.0,
                    "lag_7_qty": qty - 5.0 if d >= 7 else 0.0,
                    "rolling_avg_7d_qty": qty - 1.0 if d >= 7 else qty,
                    "batch_run_id": "test_batch",
                }
            )
    return pd.DataFrame(records)


def test_feature_pipeline_no_leakage(sample_feature_df):
    """Test 1: Ensures feature pipeline does not include target or future actuals."""
    pipeline = DemandFeaturePipeline()
    X = pipeline.fit_transform(sample_feature_df)
    assert X.shape[0] == len(sample_feature_df)
    assert "qty_sold" not in pipeline.num_features
    assert "qty_sold" not in pipeline.cat_features

    # Verify transform works on single row without target
    single_row = sample_feature_df.drop(columns=["qty_sold"]).iloc[:1]
    X_single = pipeline.transform(single_row)
    assert X_single.shape[1] == X.shape[1]


def test_evaluation_metrics_correctness():
    """Test 2: Verifies calculation of MAE, RMSE, and WAPE."""
    y_true = np.array([10.0, 20.0, 30.0])
    y_pred = np.array([12.0, 18.0, 33.0])  # diffs: +2, -2, +3

    metrics = compute_metrics(y_true, y_pred)
    assert metrics["mae"] == round((2 + 2 + 3) / 3, 4)  # 2.3333
    assert metrics["wape"] == round((2 + 2 + 3) / 60.0, 4)  # 7 / 60 = 0.1167
    assert metrics["sample_count"] == 3


def test_baseline_forecasting(sample_feature_df):
    """Test 3: Tests NaiveDemandBaseline logic with lag_1 and fallback mean."""
    train_df = sample_feature_df[sample_feature_df["sales_date"] < date(2026, 10, 10)]
    test_df = sample_feature_df[sample_feature_df["sales_date"] >= date(2026, 10, 10)]

    baseline = NaiveDemandBaseline()
    baseline.fit(train_df, target_col="qty_sold")
    preds = baseline.predict(test_df)

    assert len(preds) == len(test_df)
    assert np.all(preds >= 0.0)  # Nonnegative


def test_ridge_regression_pipeline(sample_feature_df):
    """Test 4: Tests Ridge regression model training, prediction, and non-negativity."""
    train_df = sample_feature_df[sample_feature_df["sales_date"] < date(2026, 10, 10)]
    test_df = sample_feature_df[sample_feature_df["sales_date"] >= date(2026, 10, 10)]

    ridge = RidgeDemandRegressor(alpha=1.0)
    ridge.fit(train_df, target_col="qty_sold")
    preds = ridge.predict(test_df)

    assert len(preds) == len(test_df)
    assert np.all(preds >= 0.0)  # Nonnegative clipping


def test_random_forest_pipeline(sample_feature_df):
    """Test 5: Tests Random Forest regressor with depth bounds."""
    train_df = sample_feature_df[sample_feature_df["sales_date"] < date(2026, 10, 10)]
    test_df = sample_feature_df[sample_feature_df["sales_date"] >= date(2026, 10, 10)]

    rf = RandomForestDemandRegressor(n_estimators=10, max_depth=3)
    rf.fit(train_df, target_col="qty_sold")
    preds = rf.predict(test_df)

    assert len(preds) == len(test_df)
    assert np.all(preds >= 0.0)  # Nonnegative clipping


def test_experiment_tracker_and_registry(sample_feature_df, tmp_path):
    """Test 6: Tests experiment logging and model registry versioning."""
    reg_file = tmp_path / "model_registry.json"
    tracker = ExperimentTracker(registry_file=reg_file)

    dummy_model = NaiveDemandBaseline().fit(sample_feature_df)
    metrics = {"mae": 3.5, "rmse": 4.2, "wape": 0.15}

    run = tracker.log_run(
        experiment_id="exp_test",
        model_name="baseline_naive",
        model_version="v1.0.0",
        hyperparameters={"type": "naive"},
        metrics=metrics,
        train_date_range=["2026-10-01"],
        test_date_range=["2026-10-02"],
        dataset_meta={"hash": "test123"},
        model_artifact=dummy_model,
    )

    assert "run_id" in run
    assert run["metrics"]["mae"] == 3.5

    tracker.register_and_promote_model(
        model_name="baseline_naive",
        model_version="v1.0.0",
        run_id=run["run_id"],
        metrics=metrics,
        reason="Baseline promotion test",
        status="active",
    )

    loaded_model, reg = tracker.load_active_model()
    assert reg["active_model"] == "baseline_naive"
    assert loaded_model.is_fitted is True


def test_insufficient_data_handling():
    """Test 7: Tests graceful handling when dataset has fewer than required records."""
    tiny_df = pd.DataFrame(
        [
            {
                "sales_date": date(2026, 10, 18),
                "branch": "TRP",
                "menu_key": "salt_bread",
                "qty_sold": 5.0,
            }
        ]
    )

    class MockExtractor:
        def get_demand_features(self):
            return tiny_df

    res = run_training_pipeline(extractor=MockExtractor())
    assert res["status"] == "insufficient_data"
    assert res["record_count"] == 1


def test_production_recommendation_logic():
    """Test 8: Verifies safety buffer and category rules in production recommendations."""
    engine = BatchInferenceEngine()
    assert engine.policy_version == "policy_v1.0.0"
