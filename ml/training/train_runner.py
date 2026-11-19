"""Training Runner: Chronological Split, Multi-Model Training, Evaluation, and Promotion."""
import hashlib
import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional, Tuple
import pandas as pd
from ml.config import DATASETS_DIR, RANDOM_SEED
from ml.data.extractor import GoldDataExtractor
from ml.evaluation.evaluator import compute_metrics
from ml.tracking.tracker import ExperimentTracker
from ml.training.baseline import NaiveDemandBaseline
from ml.training.rf_model import RandomForestDemandRegressor
from ml.training.ridge_model import RidgeDemandRegressor

logger = logging.getLogger("bakery.ml.training")


def run_training_pipeline(
    extractor: Optional[GoldDataExtractor] = None,
    tracker: Optional[ExperimentTracker] = None,
) -> Dict[str, Any]:
    """Executes end-to-end ML training, evaluation, and model selection."""
    extractor = extractor or GoldDataExtractor()
    tracker = tracker or ExperimentTracker()

    logger.info("Starting ML Training Pipeline...")

    # 1. Extract data
    try:
        df = extractor.get_demand_features()
    except Exception as e:
        logger.error(f"Cannot extract features: {e}")
        return {"status": "failed", "error": str(e)}

    if df.empty or len(df) < 5:
        logger.warning("Insufficient data available in Gold layer.")
        return {
            "status": "insufficient_data",
            "message": "Fewer than 5 records available in gold_ml_demand_features.",
            "record_count": len(df),
        }

    # 2. Version dataset
    dates = sorted(df["sales_date"].unique())
    dataset_version = f"dset_{dates[0].strftime('%Y%m%d')}_{dates[-1].strftime('%Y%m%d')}_{len(df)}"
    dataset_hash = hashlib.sha256(df.to_json(date_format="iso").encode("utf-8")).hexdigest()[:12]

    dataset_meta = {
        "dataset_version": dataset_version,
        "dataset_hash": dataset_hash,
        "total_rows": len(df),
        "unique_menus": int(df["menu_key"].nunique()),
        "min_date": str(dates[0]),
        "max_date": str(dates[-1]),
        "dates_covered": [str(d) for d in dates],
    }

    with open(DATASETS_DIR / f"{dataset_version}.json", "w", encoding="utf-8") as f:
        json.dump(dataset_meta, f, indent=2)

    # 3. Chronological Train / Holdout Test Split
    if len(dates) >= 2:
        train_dates = dates[:-1]
        test_dates = [dates[-1]]
        df_train = df[df["sales_date"].isin(train_dates)].copy()
        df_test = df[df["sales_date"].isin(test_dates)].copy()
        eval_status = "provisional" if len(dates) < 7 else "valid"
    else:
        # Only 1 date available: Train on all, evaluate on self as provisional
        df_train = df.copy()
        df_test = df.copy()
        train_dates = dates
        test_dates = dates
        eval_status = "insufficient_data"

    logger.info(
        f"Split: Train {len(df_train)} rows ({train_dates}), Test {len(df_test)} rows ({test_dates})"
    )

    experiment_id = f"exp_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    # 4. Train Model 1: Baseline
    baseline = NaiveDemandBaseline()
    baseline.fit(df_train, target_col="qty_sold")
    y_test = df_test["qty_sold"].values
    preds_baseline = baseline.predict(df_test)
    metrics_baseline = compute_metrics(y_test, preds_baseline)

    run_baseline = tracker.log_run(
        experiment_id=experiment_id,
        model_name="baseline_naive",
        model_version="v1.0.0",
        hyperparameters={"type": "naive_lag_1"},
        metrics=metrics_baseline,
        train_date_range=[str(d) for d in train_dates],
        test_date_range=[str(d) for d in test_dates],
        dataset_meta=dataset_meta,
        model_artifact=baseline,
        evaluation_status=eval_status,
    )

    # 5. Train Model 2: Ridge Regression
    ridge = RidgeDemandRegressor(alpha=1.0, random_state=RANDOM_SEED)
    ridge.fit(df_train, target_col="qty_sold")
    preds_ridge = ridge.predict(df_test)
    metrics_ridge = compute_metrics(y_test, preds_ridge)

    run_ridge = tracker.log_run(
        experiment_id=experiment_id,
        model_name="ridge_regression",
        model_version="v1.0.0",
        hyperparameters={"alpha": 1.0, "random_state": RANDOM_SEED},
        metrics=metrics_ridge,
        train_date_range=[str(d) for d in train_dates],
        test_date_range=[str(d) for d in test_dates],
        dataset_meta=dataset_meta,
        model_artifact=ridge,
        evaluation_status=eval_status,
    )

    # 6. Train Model 3: Random Forest Regressor
    rf = RandomForestDemandRegressor(
        n_estimators=50, max_depth=4, min_samples_leaf=2, random_state=RANDOM_SEED
    )
    rf.fit(df_train, target_col="qty_sold")
    preds_rf = rf.predict(df_test)
    metrics_rf = compute_metrics(y_test, preds_rf)

    run_rf = tracker.log_run(
        experiment_id=experiment_id,
        model_name="random_forest",
        model_version="v1.0.0",
        hyperparameters={"n_estimators": 50, "max_depth": 4, "min_samples_leaf": 2},
        metrics=metrics_rf,
        train_date_range=[str(d) for d in train_dates],
        test_date_range=[str(d) for d in test_dates],
        dataset_meta=dataset_meta,
        model_artifact=rf,
        evaluation_status=eval_status,
    )

    # 7. Model Promotion Policy
    # Select candidate with lowest MAE
    candidates = [
        ("ridge_regression", run_ridge, metrics_ridge),
        ("random_forest", run_rf, metrics_rf),
    ]
    candidates.sort(key=lambda c: c[2]["mae"])
    best_candidate_name, best_candidate_run, best_candidate_metrics = candidates[0]

    baseline_mae = metrics_baseline["mae"]
    best_mae = best_candidate_metrics["mae"]

    # Promotion Rule:
    # If candidate outperforms baseline MAE on the holdout set, promote it.
    # Otherwise, fallback to baseline.
    if best_mae <= baseline_mae:
        promoted_name = best_candidate_name
        promoted_version = best_candidate_run["model_version"]
        promoted_run_id = best_candidate_run["run_id"]
        promoted_metrics = best_candidate_metrics
        promotion_reason = (
            f"Candidate '{best_candidate_name}' outperformed baseline MAE "
            f"({best_mae:.2f} <= {baseline_mae:.2f})."
        )
    else:
        promoted_name = "baseline_naive"
        promoted_version = run_baseline["model_version"]
        promoted_run_id = run_baseline["run_id"]
        promoted_metrics = metrics_baseline
        promotion_reason = (
            f"Candidates did not beat baseline MAE ({best_mae:.2f} > {baseline_mae:.2f}). "
            "Retained Baseline Naive."
        )

    tracker.register_and_promote_model(
        model_name=promoted_name,
        model_version=promoted_version,
        run_id=promoted_run_id,
        metrics=promoted_metrics,
        reason=promotion_reason,
        status="active" if eval_status == "valid" else "provisional",
    )

    result = {
        "status": "success",
        "experiment_id": experiment_id,
        "dataset_meta": dataset_meta,
        "evaluation_status": eval_status,
        "models_evaluated": {
            "baseline_naive": metrics_baseline,
            "ridge_regression": metrics_ridge,
            "random_forest": metrics_rf,
        },
        "promoted_model": {
            "name": promoted_name,
            "version": promoted_version,
            "run_id": promoted_run_id,
            "metrics": promoted_metrics,
            "reason": promotion_reason,
            "status": "active" if eval_status == "valid" else "provisional",
        },
    }
    logger.info(f"Training completed successfully. Result: {result['promoted_model']}")
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    res = run_training_pipeline()
    print("\n--- Pipeline Execution Summary ---")
    print(json.dumps(res, indent=2))
