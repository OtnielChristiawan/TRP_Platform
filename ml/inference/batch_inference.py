"""Batch Inference Engine: Generates Product, 7-Day, Hourly, and Production Recommendations."""
import hashlib
import json
import logging
import math
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
import duckdb
import numpy as np
import pandas as pd
from ml.config import (
    GOLD_BUCKET,
    MINIO_ROOT_PASSWORD,
    MINIO_ROOT_USER,
    OPERATIONAL_HOURS_END,
    OPERATIONAL_HOURS_START,
    PREDICTIONS_DIR,
    S3_ENDPOINT,
    SAFETY_STOCK_Z,
    STATE_DIR,
)
from ml.data.extractor import GoldDataExtractor
from ml.tracking.tracker import ExperimentTracker

logger = logging.getLogger("bakery.ml.inference")


class BatchInferenceEngine:
    """Executes scheduled batch inference and produces versioned prediction datasets."""

    def __init__(
        self,
        extractor: Optional[GoldDataExtractor] = None,
        tracker: Optional[ExperimentTracker] = None,
    ):
        self.extractor = extractor or GoldDataExtractor()
        self.tracker = tracker or ExperimentTracker()
        self.policy_version = "policy_v1.0.0"

    def run_inference(self) -> Dict[str, Any]:
        """Runs batch inference for Next-Day Product, 7-Day Total, Hourly, and Recommendations."""
        now = datetime.now()
        forecast_run_id = f"fcst_{now.strftime('%Y%m%d_%H%M%S')}"
        created_at_iso = now.isoformat()

        logger.info(f"Starting Batch Inference run '{forecast_run_id}'...")

        # 1. Load active model and registry
        try:
            model, reg = self.tracker.load_active_model()
            active_model_name = reg.get("active_model", "baseline_naive")
            active_model_version = reg.get("active_version", "v1.0.0")
            model_status = reg.get("status", "provisional")
        except Exception as e:
            logger.error(f"Failed to load active model: {e}")
            return {"status": "failed", "error": f"Active model loading failed: {e}"}

        # 2. Extract recent data
        try:
            df_features = self.extractor.get_demand_features()
            df_hourly = self.extractor.get_hourly_sales()
            df_daily = self.extractor.get_daily_sales()
        except Exception as e:
            logger.error(f"Data extraction failed during inference: {e}")
            return {"status": "failed", "error": f"Extraction error: {e}"}

        if df_features.empty:
            logger.warning("No feature data found in Gold layer.")
            return {"status": "insufficient_data", "message": "No data in gold_ml_demand_features"}

        latest_sales_date = pd.to_datetime(df_features["sales_date"].max()).date()
        target_forecast_date = latest_sales_date + timedelta(days=1)
        branch = df_features["branch"].iloc[0] if "branch" in df_features.columns else "Toko Roti Pagi"

        logger.info(
            f"Latest historical date: {latest_sales_date}. Forecasting target: {target_forecast_date}"
        )

        # ----------------------------------------------------------------------
        # Output A: Next-Day Product Demand Forecast (ml_forecast_product_daily)
        # ----------------------------------------------------------------------
        # Build inference features for target date
        # Group by menu_key to get latest observed metrics
        latest_menus = df_features[df_features["sales_date"] == latest_sales_date].copy()

        # If some menu was not sold on latest date, retrieve its most recent row
        all_unique_menus = (
            df_features.groupby("menu_key")
            .agg(
                menu_name=("menu_name", "last"),
                menu_category=("menu_category", "last"),
                branch=("branch", "last"),
                hist_mean=("qty_sold", "mean"),
                hist_std=("qty_sold", "std"),
            )
            .reset_index()
        )

        inference_rows = []
        dow = target_forecast_date.weekday() + 1  # 1=Mon in python weekday, spark dayofweek is 1=Sun, 2=Mon
        # Standardize Spark dayofweek: Sun=1, Mon=2, Tue=3, Wed=4, Thu=5, Fri=6, Sat=7
        spark_dow = (target_forecast_date.weekday() + 1) % 7 + 1
        is_weekend = spark_dow in [1, 7]

        for _, menu in all_unique_menus.iterrows():
            m_key = menu["menu_key"]
            m_name = menu["menu_name"]
            m_cat = menu["menu_category"]
            m_branch = menu["branch"]

            # Lookup lag_1 from latest date
            m_latest = latest_menus[latest_menus["menu_key"] == m_key]
            if not m_latest.empty:
                lag_1 = float(m_latest["qty_sold"].iloc[0])
            else:
                lag_1 = 0.0

            inference_rows.append(
                {
                    "forecast_date": target_forecast_date,
                    "branch": m_branch,
                    "menu_key": m_key,
                    "menu_name": m_name,
                    "menu_category": m_cat,
                    "day_of_week": spark_dow,
                    "day_of_month": target_forecast_date.day,
                    "month": target_forecast_date.month,
                    "is_weekend": is_weekend,
                    "lag_1_qty": lag_1,
                    "lag_7_qty": 0.0,
                    "rolling_avg_7d_qty": float(menu["hist_mean"]),
                    "hist_mean": float(menu["hist_mean"]),
                    "hist_std": float(menu["hist_std"]) if pd.notna(menu["hist_std"]) else 1.0,
                }
            )

        df_infer = pd.DataFrame(inference_rows)

        # Predict using model
        try:
            preds = model.predict(df_infer)
            # Clip nonnegative explicitly
            preds = np.clip(preds, a_min=0.0, a_max=None)
        except Exception as e:
            logger.warning(f"Model prediction failed ({e}). Falling back to historical mean.")
            preds = df_infer["hist_mean"].values

        df_infer["predicted_qty"] = [round(float(p), 1) for p in preds]
        df_infer["forecast_run_id"] = forecast_run_id
        df_infer["model_version"] = active_model_version
        df_infer["model_name"] = active_model_name
        df_infer["status"] = model_status
        df_infer["prediction_created_at"] = created_at_iso

        df_product_forecast = df_infer[
            [
                "forecast_run_id",
                "forecast_date",
                "branch",
                "menu_key",
                "menu_name",
                "menu_category",
                "predicted_qty",
                "model_version",
                "model_name",
                "status",
                "prediction_created_at",
            ]
        ].copy()

        # ----------------------------------------------------------------------
        # Output B: Seven-Day Demand Forecast (ml_forecast_next_7_days)
        # ----------------------------------------------------------------------
        seven_day_rows = []
        # Multi-step recursive / calendar extrapolation
        # Compute historical base total per day
        base_daily_qty = float(df_daily["total_qty_sold"].mean()) if not df_daily.empty else 500.0

        for h in range(1, 8):
            fcst_d = latest_sales_date + timedelta(days=h)
            h_dow = (fcst_d.weekday() + 1) % 7 + 1
            # Weekend multiplier if applicable
            multiplier = 1.15 if h_dow in [1, 7] else 0.95
            est_qty = round(base_daily_qty * multiplier, 1)

            seven_day_rows.append(
                {
                    "forecast_run_id": forecast_run_id,
                    "forecast_date": fcst_d,
                    "branch": branch,
                    "predicted_total_qty": est_qty,
                    "horizon_step": h,
                    "model_version": active_model_version,
                    "model_name": active_model_name,
                    "forecast_status": model_status,
                    "prediction_created_at": created_at_iso,
                }
            )

        df_7day_forecast = pd.DataFrame(seven_day_rows)

        # ----------------------------------------------------------------------
        # Output C: Hourly Demand Forecast (ml_forecast_hourly)
        # ----------------------------------------------------------------------
        # Calculate historical distribution across operational hours [9..19]
        hourly_rows = []
        if not df_hourly.empty:
            hour_agg = df_hourly.groupby("sales_hour")["total_qty_sold"].sum()
            total_hourly_qty = float(hour_agg.sum())
            hour_weights = (hour_agg / total_hourly_qty).to_dict() if total_hourly_qty > 0 else {}
        else:
            hour_weights = {}

        next_day_total = float(df_product_forecast["predicted_qty"].sum())

        for hour in range(OPERATIONAL_HOURS_START, OPERATIONAL_HOURS_END + 1):
            weight = hour_weights.get(hour, 1.0 / 11)
            hour_qty = round(next_day_total * weight, 1)

            hourly_rows.append(
                {
                    "forecast_run_id": forecast_run_id,
                    "forecast_date": target_forecast_date,
                    "forecast_hour": hour,
                    "branch": branch,
                    "predicted_qty": hour_qty,
                    "model_version": active_model_version,
                    "status": model_status,
                    "prediction_created_at": created_at_iso,
                }
            )

        df_hourly_forecast = pd.DataFrame(hourly_rows)

        # ----------------------------------------------------------------------
        # Output D: Production Preparation Recommendation (ml_production_recommendations)
        # ----------------------------------------------------------------------
        rec_rows = []
        disclaimer_text = (
            "Rekomendasi bersifat decision support awal berbasis forecast penjualan. "
            "Belum memperhitungkan sisa stok toko aktual, kapasitas oven, bahan baku, dan waktu kadaluarsa."
        )

        for _, row in df_infer.iterrows():
            fcst_qty = float(row["predicted_qty"])
            std_dev = float(row["hist_std"])

            # Rule-based safety buffer: Z * sigma
            # Constrain buffer between 1 and 5 units for small bakery operations
            raw_buffer = SAFETY_STOCK_Z * std_dev
            safety_buffer = max(1.0, min(raw_buffer, 6.0))

            if fcst_qty <= 0.0:
                suggested_prepare = 0
                reason = "Demand nol diprediksi; tidak disarankan batch baking."
                rec_status = "provisional" if model_status == "provisional" else "active"
            elif row["menu_category"] == "PASTRY":
                suggested_prepare = int(math.ceil(fcst_qty + safety_buffer))
                reason = (
                    f"Kategori Pastry berputar cepat; ditambah safety buffer {safety_buffer:.0f} pcs "
                    f"untuk antisipasi jam sibuk makan siang."
                )
                rec_status = "provisional" if model_status == "provisional" else "active"
            elif row["menu_category"] == "BEVERAGE":
                suggested_prepare = int(math.ceil(fcst_qty))
                reason = "Kategori Minuman disiapkan on-demand (make-to-order); buffer minimum."
                rec_status = "provisional" if model_status == "provisional" else "active"
            else:
                suggested_prepare = int(math.ceil(fcst_qty + 1.0))
                reason = "Kategori Dessert/Pelengkap; buffer 1 unit standar."
                rec_status = "provisional" if model_status == "provisional" else "active"

            rec_rows.append(
                {
                    "forecast_run_id": forecast_run_id,
                    "menu_key": row["menu_key"],
                    "menu_name": row["menu_name"],
                    "menu_category": row["menu_category"],
                    "branch": row["branch"],
                    "forecast_date": target_forecast_date,
                    "forecast_qty": fcst_qty,
                    "suggested_prepare_qty": suggested_prepare,
                    "recommendation_reason": reason,
                    "model_version": active_model_version,
                    "policy_version": self.policy_version,
                    "recommendation_status": rec_status,
                    "disclaimer": disclaimer_text,
                    "prediction_created_at": created_at_iso,
                }
            )

        df_recommendations = pd.DataFrame(rec_rows)

        # ----------------------------------------------------------------------
        # 3. Persist Datasets (Local State and MinIO)
        # ----------------------------------------------------------------------
        run_output_dir = PREDICTIONS_DIR / forecast_run_id
        latest_output_dir = PREDICTIONS_DIR / "latest"
        run_output_dir.mkdir(parents=True, exist_ok=True)
        latest_output_dir.mkdir(parents=True, exist_ok=True)

        datasets = {
            "ml_forecast_product_daily": df_product_forecast,
            "ml_forecast_next_7_days": df_7day_forecast,
            "ml_forecast_hourly": df_hourly_forecast,
            "ml_production_recommendations": df_recommendations,
        }

        # Save Parquet files locally using DuckDB
        con_local = duckdb.connect()
        for name, df in datasets.items():
            con_local.register("tmp_local", df)
            p1 = str(run_output_dir / f"{name}.parquet").replace("\\", "/")
            p2 = str(latest_output_dir / f"{name}.parquet").replace("\\", "/")
            con_local.execute(f"COPY tmp_local TO '{p1}' (FORMAT PARQUET);")
            con_local.execute(f"COPY tmp_local TO '{p2}' (FORMAT PARQUET);")
            con_local.unregister("tmp_local")
        con_local.close()

        # Save manifest
        manifest = {
            "forecast_run_id": forecast_run_id,
            "created_at": created_at_iso,
            "model_name": active_model_name,
            "model_version": active_model_version,
            "model_status": model_status,
            "target_date": str(target_forecast_date),
            "datasets": {k: len(v) for k, v in datasets.items()},
        }
        with open(PREDICTIONS_DIR / "manifest.json", "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        # Publish to MinIO if accessible
        self._publish_to_minio(run_output_dir, datasets)

        logger.info(
            f"Batch Inference '{forecast_run_id}' completed. "
            f"Generated {len(df_product_forecast)} menu predictions."
        )

        return {
            "status": "success",
            "forecast_run_id": forecast_run_id,
            "target_date": str(target_forecast_date),
            "model_version": active_model_version,
            "model_status": model_status,
            "counts": {k: len(v) for k, v in datasets.items()},
        }

    def _publish_to_minio(self, local_dir: Path, datasets: Dict[str, pd.DataFrame]):
        """Uploads inference parquet files to MinIO bakery-gold bucket."""
        try:
            conn = duckdb.connect()
            endpoint = S3_ENDPOINT.replace("http://", "").replace("https://", "")
            conn.execute(
                f"""
                INSTALL httpfs; LOAD httpfs;
                CREATE OR REPLACE SECRET minio_secret (
                    TYPE S3,
                    KEY_ID '{MINIO_ROOT_USER}',
                    SECRET '{MINIO_ROOT_PASSWORD}',
                    ENDPOINT '{endpoint}',
                    USE_SSL false,
                    URL_STYLE 'path'
                );
                """
            )
            for name, df in datasets.items():
                s3_path = f"s3://{GOLD_BUCKET}/ml/predictions/latest/{name}.parquet"
                conn.register("tmp_table", df)
                conn.execute(
                    f"COPY tmp_table TO '{s3_path}' (FORMAT PARQUET, OVERWRITE_OR_IGNORE true);"
                )
                conn.unregister("tmp_table")
            logger.info("Successfully published ML predictions to MinIO Gold.")
        except Exception as e:
            logger.warning(
                f"Could not publish predictions directly to MinIO ({e}). Local copy retained."
            )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    engine = BatchInferenceEngine()
    res = engine.run_inference()
    print("\n--- Inference Execution Summary ---")
    print(json.dumps(res, indent=2))
