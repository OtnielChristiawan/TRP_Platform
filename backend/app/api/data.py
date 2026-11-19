"""Data freshness and pipeline metadata endpoints."""
from fastapi import APIRouter, Depends
from app.schemas.responses import FreshnessResponse
from app.services.gold_query_service import GoldQueryService, get_gold_service

router = APIRouter(prefix="/data", tags=["Data Freshness"])


@router.get("/freshness", response_model=FreshnessResponse)
def get_data_freshness(service: GoldQueryService = Depends(get_gold_service)):
    return service.get_freshness()
