"""Executive dashboard summary and KPIs."""
from typing import Optional
from fastapi import APIRouter, Depends, Query
from app.schemas.responses import SummaryKPI
from app.services.gold_query_service import GoldQueryService, get_gold_service

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/summary", response_model=SummaryKPI)
def get_dashboard_summary(
    start_date: Optional[str] = Query(None, description="Start date in YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="End date in YYYY-MM-DD"),
    branch: Optional[str] = Query(None, description="Branch filter"),
    service: GoldQueryService = Depends(get_gold_service),
):
    return service.get_dashboard_summary(start_date=start_date, end_date=end_date, branch=branch)
