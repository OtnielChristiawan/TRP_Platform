"""Pydantic schemas for Machine Learning Demand Forecasting endpoints."""
from datetime import date, datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class MLSummaryKPI(BaseModel):
    predicted_total_items_tomorrow: float = Field(..., description="Total items predicted to be sold tomorrow")
    menus_forecasted_count: int = Field(..., description="Number of unique menus forecasted")
    active_model_name: str = Field(..., description="Currently active model name")
    active_model_version: str = Field(..., description="Active model semantic version")
    model_status: str = Field(..., description="Model status (valid, provisional, insufficient_data)")
    forecast_target_date: Optional[date] = Field(None, description="Target forecast date")
    last_forecast_created_at: Optional[str] = Field(None, description="Timestamp of latest forecast generation")
    top_demanded_menu: Optional[str] = Field(None, description="Menu with highest predicted demand")


class MLProductForecastItem(BaseModel):
    forecast_run_id: str
    forecast_date: date
    branch: str
    menu_key: str
    menu_name: str
    menu_category: str
    predicted_qty: float
    model_version: str
    model_name: str
    status: str
    prediction_created_at: str


class MLSevenDayItem(BaseModel):
    forecast_run_id: str
    forecast_date: date
    branch: str
    predicted_total_qty: float
    horizon_step: int
    model_version: str
    model_name: str
    forecast_status: str
    prediction_created_at: str


class MLHourlyForecastItem(BaseModel):
    forecast_run_id: str
    forecast_date: date
    forecast_hour: int
    branch: str
    predicted_qty: float
    model_version: str
    status: str
    prediction_created_at: str


class MLProductionRecommendationItem(BaseModel):
    forecast_run_id: str
    menu_key: str
    menu_name: str
    menu_category: str
    branch: str
    forecast_date: date
    forecast_qty: float
    suggested_prepare_qty: int
    recommendation_reason: str
    model_version: str
    policy_version: str
    recommendation_status: str
    disclaimer: str
    prediction_created_at: str


class MLModelMetricsResponse(BaseModel):
    active_model: str
    active_version: str
    active_run_id: str
    status: str
    last_promoted_at: Optional[str]
    promotion_reason: Optional[str]
    latest_metrics: Dict[str, float]
    all_models_evaluated: Optional[Dict[str, Any]] = None


class MLModelStatusResponse(BaseModel):
    status: str = Field(..., description="System ML health status")
    has_active_model: bool
    model_name: Optional[str]
    model_version: Optional[str]
    evaluation_status: Optional[str]
    data_readiness_status: str
    message: str
