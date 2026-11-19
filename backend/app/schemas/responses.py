"""Pydantic schemas for standardized API responses."""
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = "healthy"
    app_name: str
    version: str
    environment: str
    timestamp: datetime


class FreshnessResponse(BaseModel):
    batch_id: Optional[str] = None
    published_at: Optional[str] = None
    latest_transaction_date: Optional[str] = None
    last_refresh_at: str
    status: str = "HEALTHY"
    marts_status: Dict[str, Any] = Field(default_factory=dict)


class FilterOptionsResponse(BaseModel):
    branches: List[str]
    min_date: Optional[str]
    max_date: Optional[str]
    categories: List[str]
    payment_methods: List[str]


class SummaryKPI(BaseModel):
    total_net_sales: float
    total_gross_sales: float
    total_discount: float
    total_bills: int
    total_qty_sold: float
    total_item_rows: int
    average_order_value: float
    zero_price_item_count: int
    last_updated_at: Optional[str] = None
    # Growth comparison (if valid previous period exists)
    previous_period_net_sales: Optional[float] = None
    sales_growth_pct: Optional[float] = None
    bills_growth_pct: Optional[float] = None


class DailySalesItem(BaseModel):
    sales_date: str
    branch: str
    total_bills: int
    total_item_rows: int
    total_qty_sold: float
    gross_sales: float
    total_discount: float
    net_sales: float
    average_order_value: float
    zero_price_item_count: int


class HourlySalesItem(BaseModel):
    sales_hour: int
    total_bills: int
    total_item_rows: int
    total_qty_sold: float
    gross_sales: float
    net_sales: float
    average_order_value: float


class TopMenuItem(BaseModel):
    rank: int
    menu_key: str
    menu_name: str
    menu_category: Optional[str]
    menu_category_detail: Optional[str]
    qty_sold: float
    total_bills: int
    gross_sales: float
    net_sales: float
    zero_price_qty: float
    is_master_matched: bool
    master_match_status: str


class CategoryPerformanceItem(BaseModel):
    menu_category: str
    qty_sold: float
    total_bills: int
    total_item_rows: int
    gross_sales: float
    net_sales: float
    sales_contribution_pct: float


class PaymentSummaryItem(BaseModel):
    payment_method: str
    total_bills: int
    net_sales: float
    payment_contribution_pct: float


class ErrorResponse(BaseModel):
    detail: str
    error_code: Optional[str] = None
