"""Filter options endpoint for dynamic frontend controls."""
from fastapi import APIRouter, Depends
from app.schemas.responses import FilterOptionsResponse
from app.services.gold_query_service import GoldQueryService, get_gold_service

router = APIRouter(tags=["Filters"])


@router.get("/filters", response_model=FilterOptionsResponse)
def get_filters(service: GoldQueryService = Depends(get_gold_service)):
    return service.get_filter_options()
