"""Unit and Integration tests for FastAPI endpoints against Gold Layer."""
import os
import sys
from pathlib import Path
from fastapi.testclient import TestClient
import pytest

# Ensure backend directory is in sys.path
BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

# Ensure S3 endpoint points to localhost for local testing
os.environ["S3_ENDPOINT"] = "localhost:9000"
os.environ["MINIO_ENDPOINT"] = "localhost:9000"

from app.main import app

client = TestClient(app, headers={"X-API-Key": "trp-viewer-key-2026"})


def test_health_endpoint():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "version" in data
    assert "timestamp" in data


def test_data_freshness_endpoint():
    response = client.get("/api/v1/data/freshness")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "last_refresh_at" in data
    assert data["latest_transaction_date"] is not None


def test_filters_endpoint():
    response = client.get("/api/v1/filters")
    assert response.status_code == 200
    data = response.json()
    assert "branches" in data
    assert "min_date" in data
    assert "max_date" in data
    assert "categories" in data
    assert "payment_methods" in data
    assert len(data["branches"]) > 0


def test_dashboard_summary_endpoint():
    # Test without params
    response = client.get("/api/v1/dashboard/summary")
    assert response.status_code == 200
    data = response.json()
    assert data["total_bills"] > 0
    assert data["total_net_sales"] > 0.0
    assert data["average_order_value"] > 0.0
    assert data["total_qty_sold"] > 0.0

    # Test with date range filters (verifies DuckDB DATE vs VARCHAR casting)
    p_resp = client.get("/api/v1/dashboard/summary?start_date=2026-10-18&end_date=2026-10-19")
    assert p_resp.status_code == 200
    p_data = p_resp.json()
    assert p_data["total_bills"] > 0
    assert p_data["total_net_sales"] > 0.0


def test_sales_daily_endpoint():
    response = client.get("/api/v1/sales/daily")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
    first = data[0]
    assert "sales_date" in first
    assert "net_sales" in first
    assert "total_bills" in first


def test_sales_hourly_endpoint():
    response = client.get("/api/v1/sales/hourly")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
    for item in data:
        assert 0 <= item["sales_hour"] <= 23
        assert item["net_sales"] >= 0.0


def test_menus_top_endpoint():
    # Test valid sort
    response = client.get("/api/v1/menus/top?limit=5&sort_by=quantity")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) <= 5
    if len(data) > 0:
        assert data[0]["rank"] == 1
        assert "menu_name" in data[0]

    # Test invalid sort
    invalid_resp = client.get("/api/v1/menus/top?sort_by=hacked_column")
    assert invalid_resp.status_code == 400


def test_category_performance_endpoint():
    response = client.get("/api/v1/categories/performance")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
    # Verify contribution percentages sum approximately to 100%
    total_pct = sum(item["sales_contribution_pct"] for item in data)
    assert 99.0 <= total_pct <= 101.0


def test_payments_summary_endpoint():
    response = client.get("/api/v1/payments/summary")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
    total_pct = sum(item["payment_contribution_pct"] for item in data)
    assert 99.0 <= total_pct <= 101.0


# ------------------------------------------------------------------------------
# ML Demand Forecasting Endpoints Tests (F-12 & F-13 Compliance)
# ------------------------------------------------------------------------------
def test_ml_summary_endpoint():
    response = client.get("/api/v1/ml/summary")
    assert response.status_code == 200
    data = response.json()
    assert "predicted_total_items_tomorrow" in data
    assert "menus_forecasted_count" in data
    assert "active_model_name" in data
    assert "active_model_version" in data
    assert "model_status" in data
    assert data["menus_forecasted_count"] > 0
    assert data["predicted_total_items_tomorrow"] >= 0.0


def test_ml_product_forecasts_endpoint():
    response = client.get("/api/v1/ml/forecast/products?limit=10")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
    first = data[0]
    assert "menu_name" in first
    assert "predicted_qty" in first
    assert first["predicted_qty"] >= 0.0
    assert "status" in first


def test_ml_weekly_forecast_endpoint():
    response = client.get("/api/v1/ml/forecast/weekly")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 7  # 7-day projection H+1 to H+7
    for item in data:
        assert 1 <= item["horizon_step"] <= 7
        assert item["predicted_total_qty"] >= 0.0


def test_ml_hourly_forecast_endpoint():
    response = client.get("/api/v1/ml/forecast/hourly")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 11  # Operational hours 9 to 19
    for item in data:
        assert 9 <= item["forecast_hour"] <= 19
        assert item["predicted_qty"] >= 0.0


def test_ml_recommendations_endpoint():
    response = client.get("/api/v1/ml/recommendations?limit=10")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
    first = data[0]
    assert "suggested_prepare_qty" in first
    assert "recommendation_reason" in first
    assert "disclaimer" in first
    assert first["suggested_prepare_qty"] >= 0


def test_ml_model_metrics_endpoint():
    response = client.get("/api/v1/ml/model/metrics")
    assert response.status_code == 200
    data = response.json()
    assert "active_model" in data
    assert "latest_metrics" in data
    assert "mae" in data["latest_metrics"]
    assert "rmse" in data["latest_metrics"]
    assert "wape" in data["latest_metrics"]


def test_ml_model_status_endpoint():
    response = client.get("/api/v1/ml/model/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["has_active_model"] is True
    assert "model_name" in data
    assert "data_readiness_status" in data
