"""ML analytical query service powered by DuckDB reading Parquet predictions."""
import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from app.core.config import settings
from app.db.duckdb_connection import get_db_manager
from app.schemas.ml_responses import (
    MLHourlyForecastItem,
    MLModelMetricsResponse,
    MLModelStatusResponse,
    MLProductForecastItem,
    MLProductionRecommendationItem,
    MLSevenDayItem,
    MLSummaryKPI,
)

logger = logging.getLogger("bakery.ml.service")


class MLQueryService:
    def __init__(self):
        self.db = get_db_manager()
        self.bucket = settings.GOLD_BUCKET
        self.local_state_dir = Path("/opt/bakery/state/ml")
        if not self.local_state_dir.exists():
            self.local_state_dir = Path(__file__).resolve().parent.parent.parent.parent / "state" / "ml"

    def _resolve_parquet(self, dataset_name: str) -> str:
        """Resolves local fallback or S3 path for Parquet predictions."""
        local_path = self.local_state_dir / "predictions" / "latest" / f"{dataset_name}.parquet"
        if local_path.exists():
            return str(local_path).replace("\\", "/")
        return f"s3://{self.bucket}/ml/predictions/latest/{dataset_name}.parquet"

    def get_summary(self, branch: Optional[str] = None) -> MLSummaryKPI:
        """Returns executive KPI summary for tomorrow's forecast."""
        product_pq = self._resolve_parquet("ml_forecast_product_daily")
        query = f"""
        SELECT 
            COALESCE(SUM(predicted_qty), 0.0) as total_qty,
            COUNT(DISTINCT menu_key) as menu_count,
            MIN(forecast_date) as target_date,
            MIN(model_name) as model_name,
            MIN(model_version) as model_version,
            MIN(status) as status,
            MIN(prediction_created_at) as created_at
        FROM read_parquet('{product_pq}')
        WHERE (? IS NULL OR branch = ?)
        """
        top_query = f"""
        SELECT menu_name, predicted_qty
        FROM read_parquet('{product_pq}')
        WHERE (? IS NULL OR branch = ?)
        ORDER BY predicted_qty DESC
        LIMIT 1
        """
        try:
            rows = self.db.query(query, [branch, branch])
            top_rows = self.db.query(top_query, [branch, branch])
            top_menu = top_rows[0]["menu_name"] if top_rows else None

            if rows and rows[0]["menu_count"] > 0:
                r = rows[0]
                return MLSummaryKPI(
                    predicted_total_items_tomorrow=round(float(r["total_qty"]), 1),
                    menus_forecasted_count=int(r["menu_count"]),
                    active_model_name=str(r["model_name"] or "baseline_naive"),
                    active_model_version=str(r["model_version"] or "v1.0.0"),
                    model_status=str(r["status"] or "provisional"),
                    forecast_target_date=r["target_date"],
                    last_forecast_created_at=str(r["created_at"]) if r["created_at"] else None,
                    top_demanded_menu=top_menu,
                )
        except Exception as e:
            logger.warning(f"Error fetching ML summary: {e}")

        return MLSummaryKPI(
            predicted_total_items_tomorrow=0.0,
            menus_forecasted_count=0,
            active_model_name="uninitialized",
            active_model_version="v0.0.0",
            model_status="insufficient_data",
            forecast_target_date=None,
            last_forecast_created_at=None,
            top_demanded_menu=None,
        )

    def get_product_forecasts(
        self,
        branch: Optional[str] = None,
        forecast_date: Optional[str] = None,
        menu_key: Optional[str] = None,
        limit: int = 100,
    ) -> List[MLProductForecastItem]:
        """Returns per-product demand forecasts."""
        product_pq = self._resolve_parquet("ml_forecast_product_daily")
        query = f"""
        SELECT 
            forecast_run_id,
            forecast_date,
            branch,
            menu_key,
            menu_name,
            menu_category,
            predicted_qty,
            model_version,
            model_name,
            status,
            prediction_created_at
        FROM read_parquet('{product_pq}')
        WHERE (? IS NULL OR branch = ?)
          AND (? IS NULL OR forecast_date = TRY_CAST(? AS DATE))
          AND (? IS NULL OR menu_key = ?)
        ORDER BY predicted_qty DESC, menu_name ASC
        LIMIT ?
        """
        try:
            rows = self.db.query(
                query,
                [branch, branch, forecast_date, forecast_date, menu_key, menu_key, limit],
            )
            return [
                MLProductForecastItem(
                    forecast_run_id=str(r["forecast_run_id"]),
                    forecast_date=r["forecast_date"],
                    branch=str(r["branch"]),
                    menu_key=str(r["menu_key"]),
                    menu_name=str(r["menu_name"]),
                    menu_category=str(r["menu_category"]),
                    predicted_qty=float(r["predicted_qty"]),
                    model_version=str(r["model_version"]),
                    model_name=str(r["model_name"]),
                    status=str(r["status"]),
                    prediction_created_at=str(r["prediction_created_at"]),
                )
                for r in rows
            ]
        except Exception as e:
            logger.warning(f"Error fetching product forecasts: {e}")
            return []

    def get_weekly_forecast(self, branch: Optional[str] = None) -> List[MLSevenDayItem]:
        """Returns 7-day multi-step demand projections."""
        weekly_pq = self._resolve_parquet("ml_forecast_next_7_days")
        query = f"""
        SELECT 
            forecast_run_id,
            forecast_date,
            branch,
            predicted_total_qty,
            horizon_step,
            model_version,
            model_name,
            forecast_status,
            prediction_created_at
        FROM read_parquet('{weekly_pq}')
        WHERE (? IS NULL OR branch = ?)
        ORDER BY forecast_date ASC
        """
        try:
            rows = self.db.query(query, [branch, branch])
            return [
                MLSevenDayItem(
                    forecast_run_id=str(r["forecast_run_id"]),
                    forecast_date=r["forecast_date"],
                    branch=str(r["branch"]),
                    predicted_total_qty=float(r["predicted_total_qty"]),
                    horizon_step=int(r["horizon_step"]),
                    model_version=str(r["model_version"]),
                    model_name=str(r["model_name"]),
                    forecast_status=str(r["forecast_status"]),
                    prediction_created_at=str(r["prediction_created_at"]),
                )
                for r in rows
            ]
        except Exception as e:
            logger.warning(f"Error fetching weekly forecast: {e}")
            return []

    def get_hourly_forecast(
        self,
        branch: Optional[str] = None,
        forecast_date: Optional[str] = None,
    ) -> List[MLHourlyForecastItem]:
        """Returns hourly predictions for the target operational day."""
        hourly_pq = self._resolve_parquet("ml_forecast_hourly")
        query = f"""
        SELECT 
            forecast_run_id,
            forecast_date,
            forecast_hour,
            branch,
            predicted_qty,
            model_version,
            status,
            prediction_created_at
        FROM read_parquet('{hourly_pq}')
        WHERE (? IS NULL OR branch = ?)
          AND (? IS NULL OR forecast_date = TRY_CAST(? AS DATE))
        ORDER BY forecast_hour ASC
        """
        try:
            rows = self.db.query(query, [branch, branch, forecast_date, forecast_date])
            return [
                MLHourlyForecastItem(
                    forecast_run_id=str(r["forecast_run_id"]),
                    forecast_date=r["forecast_date"],
                    forecast_hour=int(r["forecast_hour"]),
                    branch=str(r["branch"]),
                    predicted_qty=float(r["predicted_qty"]),
                    model_version=str(r["model_version"]),
                    status=str(r["status"]),
                    prediction_created_at=str(r["prediction_created_at"]),
                )
                for r in rows
            ]
        except Exception as e:
            logger.warning(f"Error fetching hourly forecast: {e}")
            return []

    def get_recommendations(
        self,
        branch: Optional[str] = None,
        menu_key: Optional[str] = None,
        limit: int = 100,
    ) -> List[MLProductionRecommendationItem]:
        """Returns production preparation recommendations."""
        rec_pq = self._resolve_parquet("ml_production_recommendations")
        query = f"""
        SELECT 
            forecast_run_id,
            menu_key,
            menu_name,
            menu_category,
            branch,
            forecast_date,
            forecast_qty,
            suggested_prepare_qty,
            recommendation_reason,
            model_version,
            policy_version,
            recommendation_status,
            disclaimer,
            prediction_created_at
        FROM read_parquet('{rec_pq}')
        WHERE (? IS NULL OR branch = ?)
          AND (? IS NULL OR menu_key = ?)
        ORDER BY suggested_prepare_qty DESC, menu_name ASC
        LIMIT ?
        """
        try:
            rows = self.db.query(query, [branch, branch, menu_key, menu_key, limit])
            return [
                MLProductionRecommendationItem(
                    forecast_run_id=str(r["forecast_run_id"]),
                    menu_key=str(r["menu_key"]),
                    menu_name=str(r["menu_name"]),
                    menu_category=str(r["menu_category"]),
                    branch=str(r["branch"]),
                    forecast_date=r["forecast_date"],
                    forecast_qty=float(r["forecast_qty"]),
                    suggested_prepare_qty=int(r["suggested_prepare_qty"]),
                    recommendation_reason=str(r["recommendation_reason"]),
                    model_version=str(r["model_version"]),
                    policy_version=str(r["policy_version"]),
                    recommendation_status=str(r["recommendation_status"]),
                    disclaimer=str(r["disclaimer"]),
                    prediction_created_at=str(r["prediction_created_at"]),
                )
                for r in rows
            ]
        except Exception as e:
            logger.warning(f"Error fetching recommendations: {e}")
            return []

    def get_model_metrics(self) -> MLModelMetricsResponse:
        """Returns active model evaluation metrics and comparison registry."""
        reg_file = self.local_state_dir / "model_registry.json"
        if reg_file.exists():
            with open(reg_file, "r", encoding="utf-8") as f:
                reg = json.load(f)
            return MLModelMetricsResponse(
                active_model=reg.get("active_model", "baseline_naive"),
                active_version=reg.get("active_version", "v1.0.0"),
                active_run_id=reg.get("active_run_id", "none"),
                status=reg.get("status", "provisional"),
                last_promoted_at=reg.get("last_promoted_at"),
                promotion_reason=reg.get("promotion_reason"),
                latest_metrics=reg.get("latest_metrics", {"mae": 0.0, "rmse": 0.0, "wape": 0.0}),
                all_models_evaluated=reg.get("models"),
            )

        return MLModelMetricsResponse(
            active_model="none",
            active_version="v0.0.0",
            active_run_id="none",
            status="uninitialized",
            last_promoted_at=None,
            promotion_reason="No model registry found",
            latest_metrics={"mae": 0.0, "rmse": 0.0, "wape": 0.0},
        )

    def get_model_status(self) -> MLModelStatusResponse:
        """Returns overall health, governance, and readiness status."""
        reg = self.get_model_metrics()
        has_active = reg.active_model != "none"
        return MLModelStatusResponse(
            status="healthy" if has_active else "uninitialized",
            has_active_model=has_active,
            model_name=reg.active_model,
            model_version=reg.active_version,
            evaluation_status=reg.status,
            data_readiness_status="provisional_2_days",
            message=(
                "Model operates in PROVISIONAL mode based on 2 committed Gold calendar days. "
                "Evaluated on identical holdout test set with strict nonnegative bounds."
            ),
        )
