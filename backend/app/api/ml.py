"""FastAPI Router for Machine Learning Demand Forecasting endpoints (F-12 & F-13 Compliance)."""
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from app.schemas.ml_responses import (
    MLHourlyForecastItem,
    MLModelMetricsResponse,
    MLModelStatusResponse,
    MLProductForecastItem,
    MLProductionRecommendationItem,
    MLSevenDayItem,
    MLSummaryKPI,
)
from app.services.ml_query_service import MLQueryService

logger = logging.getLogger("bakery.api.ml")
router = APIRouter(prefix="/ml", tags=["Machine Learning Demand Forecasting"])


def get_ml_service() -> MLQueryService:
    return MLQueryService()


@router.get("/summary", response_model=MLSummaryKPI)
def get_ml_summary(
    branch: Optional[str] = Query(None, description="Optional branch filter"),
    service: MLQueryService = Depends(get_ml_service),
):
    """Returns executive KPI summary for tomorrow's forecast."""
    return service.get_summary(branch=branch)


@router.get("/forecast/products", response_model=List[MLProductForecastItem])
def get_product_forecasts(
    branch: Optional[str] = Query(None, description="Optional branch filter"),
    forecast_date: Optional[str] = Query(None, description="Target forecast date (YYYY-MM-DD)"),
    menu_key: Optional[str] = Query(None, description="Specific menu key"),
    limit: int = Query(100, ge=1, le=500, description="Max records to return"),
    service: MLQueryService = Depends(get_ml_service),
):
    """Returns next-day product demand forecast per menu."""
    return service.get_product_forecasts(
        branch=branch,
        forecast_date=forecast_date,
        menu_key=menu_key,
        limit=limit,
    )


@router.get("/forecast/weekly", response_model=List[MLSevenDayItem])
def get_weekly_forecast(
    branch: Optional[str] = Query(None, description="Optional branch filter"),
    service: MLQueryService = Depends(get_ml_service),
):
    """Returns 7-day multi-step demand projections."""
    return service.get_weekly_forecast(branch=branch)


@router.get("/forecast/hourly", response_model=List[MLHourlyForecastItem])
def get_hourly_forecast(
    branch: Optional[str] = Query(None, description="Optional branch filter"),
    forecast_date: Optional[str] = Query(None, description="Forecast date (YYYY-MM-DD)"),
    service: MLQueryService = Depends(get_ml_service),
):
    """Returns next-day hourly demand predictions across operational hours."""
    return service.get_hourly_forecast(branch=branch, forecast_date=forecast_date)


@router.get("/recommendations", response_model=List[MLProductionRecommendationItem])
def get_production_recommendations(
    branch: Optional[str] = Query(None, description="Optional branch filter"),
    menu_key: Optional[str] = Query(None, description="Specific menu key"),
    limit: int = Query(100, ge=1, le=500, description="Max records to return"),
    service: MLQueryService = Depends(get_ml_service),
):
    """Returns kitchen production preparation suggestions with rule-based safety buffer."""
    return service.get_recommendations(
        branch=branch,
        menu_key=menu_key,
        limit=limit,
    )


@router.get("/model/metrics", response_model=MLModelMetricsResponse)
def get_model_metrics(service: MLQueryService = Depends(get_ml_service)):
    """Returns active model evaluation metrics (MAE, RMSE, WAPE) and comparison registry."""
    return service.get_model_metrics()


@router.get("/model/status", response_model=MLModelStatusResponse)
def get_model_status(service: MLQueryService = Depends(get_ml_service)):
    """Returns overall ML model readiness, governance, and health status."""
    return service.get_model_status()
