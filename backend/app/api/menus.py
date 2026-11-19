"""Product and menu performance endpoints."""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from app.schemas.responses import TopMenuItem
from app.services.gold_query_service import GoldQueryService, get_gold_service

router = APIRouter(prefix="/menus", tags=["Product Analytics"])


@router.get("/top", response_model=List[TopMenuItem])
def get_top_menus(
    start_date: Optional[str] = Query(None, description="Start date in YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="End date in YYYY-MM-DD"),
    branch: Optional[str] = Query(None, description="Branch filter"),
    limit: int = Query(10, ge=1, le=100, description="Max items to return (1-100)"),
    sort_by: str = Query("quantity", description="Sort by: 'quantity' or 'sales'"),
    category: Optional[str] = Query(None, description="Filter by menu category"),
    service: GoldQueryService = Depends(get_gold_service),
):
    if sort_by.lower() not in ("quantity", "sales"):
        raise HTTPException(status_code=400, detail="Invalid sort_by parameter. Must be 'quantity' or 'sales'.")
    return service.get_top_menus(
        start_date=start_date,
        end_date=end_date,
        branch=branch,
        limit=limit,
        sort_by=sort_by,
        category=category,
    )
