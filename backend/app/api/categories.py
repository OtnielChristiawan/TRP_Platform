"""Category performance and sales contribution endpoints."""
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from app.schemas.responses import CategoryPerformanceItem
from app.services.gold_query_service import GoldQueryService, get_gold_service

router = APIRouter(prefix="/categories", tags=["Category Analytics"])


@router.get("/performance", response_model=List[CategoryPerformanceItem])
def get_category_performance(
    start_date: Optional[str] = Query(None, description="Start date in YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="End date in YYYY-MM-DD"),
    branch: Optional[str] = Query(None, description="Branch filter"),
    service: GoldQueryService = Depends(get_gold_service),
):
    return service.get_category_performance(start_date=start_date, end_date=end_date, branch=branch)
