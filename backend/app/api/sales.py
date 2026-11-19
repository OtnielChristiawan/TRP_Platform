"""Sales trend and hourly analytical endpoints."""
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from app.schemas.responses import DailySalesItem, HourlySalesItem
from app.services.gold_query_service import GoldQueryService, get_gold_service

router = APIRouter(prefix="/sales", tags=["Sales Analytics"])


@router.get("/daily", response_model=List[DailySalesItem])
def get_daily_sales(
    start_date: Optional[str] = Query(None, description="Start date in YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="End date in YYYY-MM-DD"),
    branch: Optional[str] = Query(None, description="Branch filter"),
    service: GoldQueryService = Depends(get_gold_service),
):
    return service.get_daily_sales(start_date=start_date, end_date=end_date, branch=branch)


@router.get("/hourly", response_model=List[HourlySalesItem])
def get_hourly_sales(
    start_date: Optional[str] = Query(None, description="Start date in YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="End date in YYYY-MM-DD"),
    branch: Optional[str] = Query(None, description="Branch filter"),
    service: GoldQueryService = Depends(get_gold_service),
):
    return service.get_hourly_sales(start_date=start_date, end_date=end_date, branch=branch)
