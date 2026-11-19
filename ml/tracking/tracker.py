"""Experiment Tracking & Model Registry for Bakery Data Platform V4 (F-11 Compliance)."""
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import joblib
from ml.config import ARTIFACTS_DIR, EXPERIMENTS_DIR, STATE_DIR

logger = logging.getLogger("bakery.ml.tracking")


class ExperimentTracker:
    """Tracks training runs, hyperparameters, metrics, and manages the model registry."""

    def __init__(self, registry_file: Optional[Path] = None):
        self.registry_file = registry_file or (STATE_DIR / "model_registry.json")
        self._ensure_registry()

    def _ensure_registry(self):
        if not self.registry_file.exists():
            default_reg = {
                "active_model": None,
                "active_version": None,
                "active_run_id": None,
                "status": "uninitialized",
                "last_promoted_at": None,
                "models": {},
            }
            with open(self.registry_file, "w", encoding="utf-8") as f:
                json.dump(default_reg, f, indent=2)

    def log_run(
        self,
        experiment_id: str,
        model_name: str,
        model_version: str,
        hyperparameters: Dict[str, Any],
        metrics: Dict[str, float],
        train_date_range: List[str],
        test_date_range: List[str],
        dataset_meta: Dict[str, Any],
        model_artifact: Any,
        evaluation_status: str = "valid",
    ) -> Dict[str, Any]:
        """Logs an experiment run, persists the artifact, and returns run summary."""
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_id = f"{model_name}_{timestamp_str}"
        artifact_filename = f"{run_id}.joblib"
        artifact_path = ARTIFACTS_DIR / artifact_filename

        # Save model artifact safely
        joblib.dump(model_artifact, artifact_path)

        run_metadata = {
            "run_id": run_id,
            "experiment_id": experiment_id,
            "model_name": model_name,
            "model_version": model_version,
            "timestamp": datetime.now().isoformat(),
            "hyperparameters": hyperparameters,
            "metrics": metrics,
            "train_date_range": train_date_range,
            "test_date_range": test_date_range,
            "dataset_meta": dataset_meta,
            "artifact_path": str(artifact_path),
            "evaluation_status": evaluation_status,
        }

        # Save run log
        run_file = EXPERIMENTS_DIR / f"{run_id}.json"
        with open(run_file, "w", encoding="utf-8") as f:
            json.dump(run_metadata, f, indent=2)

        logger.info(f"Logged experiment run '{run_id}' with metrics: {metrics}")
        return run_metadata

    def get_registry(self) -> Dict[str, Any]:
        """Reads active model registry."""
        with open(self.registry_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def register_and_promote_model(
        self,
        model_name: str,
        model_version: str,
        run_id: str,
        metrics: Dict[str, float],
        reason: str,
        status: str = "active",
    ):
        """Promotes a model as active or provisional in the registry."""
        reg = self.get_registry()
        reg["active_model"] = model_name
        reg["active_version"] = model_version
        reg["active_run_id"] = run_id
        reg["status"] = status
        reg["last_promoted_at"] = datetime.now().isoformat()
        reg["promotion_reason"] = reason
        reg["latest_metrics"] = metrics

        reg["models"][model_name] = {
            "version": model_version,
            "run_id": run_id,
            "promoted_at": datetime.now().isoformat(),
            "metrics": metrics,
            "status": status,
        }

        with open(self.registry_file, "w", encoding="utf-8") as f:
            json.dump(reg, f, indent=2)
        logger.info(f"Model '{model_name}' ({model_version}) promoted with status: {status}")

    def load_active_model(self) -> Tuple[Any, Dict[str, Any]]:
        """Loads the currently active model artifact and metadata."""
        reg = self.get_registry()
        run_id = reg.get("active_run_id")
        if not run_id:
            raise FileNotFoundError("No active model found in registry.")

        artifact_path = ARTIFACTS_DIR / f"{run_id}.joblib"
        if not artifact_path.exists():
            raise FileNotFoundError(f"Active model artifact not found at {artifact_path}")

        model = joblib.load(artifact_path)
        return model, reg
