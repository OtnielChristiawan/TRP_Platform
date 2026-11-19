"""Test suite for F-16 Security, Role-Based Access Control (RBAC), and Audit Trail.

Validates:
1. Public health check without credentials returns 200 OK.
2. Missing or invalid API key returns HTTP 401 Unauthorized.
3. Viewer role accessing operator or admin endpoints returns HTTP 403 Forbidden.
4. Operator role accessing admin endpoints returns HTTP 403 Forbidden.
5. Operator role successfully executes operational endpoints (200 OK).
6. Admin role has full access to audit log and credentials reload (200 OK).
7. Sensitive actions generate structured audit trail in audit_log.jsonl.
"""
import json
import os
import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

# Ensure S3 endpoint points to localhost for local testing
os.environ["S3_ENDPOINT"] = "localhost:9000"
os.environ["MINIO_ENDPOINT"] = "localhost:9000"

from app.main import app
from app.core.security import (
    API_KEY_VIEWER,
    API_KEY_OPERATOR,
    API_KEY_ADMIN,
    AUDIT_LOG_FILE,
)


@pytest.fixture
def unauthenticated_client():
    return TestClient(app)


@pytest.fixture
def viewer_client():
    return TestClient(app, headers={"X-API-Key": API_KEY_VIEWER})


@pytest.fixture
def operator_client():
    return TestClient(app, headers={"X-API-Key": API_KEY_OPERATOR})


@pytest.fixture
def admin_client():
    return TestClient(app, headers={"X-API-Key": API_KEY_ADMIN})


def test_public_health_endpoint_allows_unauthenticated(unauthenticated_client):
    """Health probes must succeed without authentication for orchestrator probes."""
    res = unauthenticated_client.get("/api/v1/health")
    assert res.status_code == 200
    assert res.json()["status"].lower() == "healthy"


def test_analytics_endpoint_unauthorized_without_key(unauthenticated_client):
    """Protected analytics endpoints must reject requests with 401 if API key is omitted."""
    res = unauthenticated_client.get("/api/v1/sales/daily")
    assert res.status_code == 401
    assert "Invalid or missing API Key" in res.json()["detail"]


def test_analytics_endpoint_unauthorized_with_invalid_key(unauthenticated_client):
    """Protected analytics endpoints must reject requests with 401 if API key is invalid."""
    res = unauthenticated_client.get(
        "/api/v1/sales/daily",
        headers={"X-API-Key": "invalid-hacker-key-999"},
    )
    assert res.status_code == 401
    assert "Invalid or missing API Key" in res.json()["detail"]


def test_bearer_token_authorization_header(unauthenticated_client):
    """Bearer token syntax in Authorization header must be accepted."""
    res = unauthenticated_client.get(
        "/api/v1/data/freshness",
        headers={"Authorization": f"Bearer {API_KEY_VIEWER}"},
    )
    assert res.status_code == 200
    assert res.json()["status"].lower() == "healthy"


def test_viewer_authorized_for_analytics(viewer_client):
    """Viewer key must be allowed to read analytics marts."""
    res = unauthenticated = viewer_client.get("/api/v1/data/freshness")
    assert res.status_code == 200


def test_viewer_forbidden_from_operator_actions(viewer_client):
    """Viewer key attempting operator action must be rejected with 403 Forbidden."""
    res = viewer_client.post("/api/v1/operations/cache/refresh")
    assert res.status_code == 403
    assert "Forbidden" in res.json()["detail"]
    assert "operator" in res.json()["detail"]


def test_viewer_forbidden_from_admin_actions(viewer_client):
    """Viewer key attempting admin action must be rejected with 403 Forbidden."""
    res = viewer_client.get("/api/v1/admin/security/audit-log")
    assert res.status_code == 403
    assert "Forbidden" in res.json()["detail"]
    assert "admin" in res.json()["detail"]


def test_operator_authorized_for_operations(operator_client):
    """Operator key must be allowed to trigger operational actions."""
    res = operator_client.post("/api/v1/operations/cache/refresh")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["triggered_by"] == "operator"


def test_operator_forbidden_from_admin_actions(operator_client):
    """Operator key attempting admin actions must be rejected with 403 Forbidden."""
    res = operator_client.get("/api/v1/admin/security/audit-log")
    assert res.status_code == 403
    assert "Forbidden" in res.json()["detail"]
    assert "admin" in res.json()["detail"]


def test_admin_authorized_for_all_actions(admin_client):
    """Admin key must have full access to audit log and access matrix."""
    # Test Access Matrix
    res_matrix = admin_client.get("/api/v1/admin/security/access-matrix")
    assert res_matrix.status_code == 200
    matrix_data = res_matrix.json()
    assert "roles" in matrix_data
    assert "access_rules" in matrix_data
    assert len(matrix_data["access_rules"]) >= 4

    # Test Audit Log inspection
    res_log = admin_client.get("/api/v1/admin/security/audit-log?limit=10")
    assert res_log.status_code == 200
    assert isinstance(res_log.json(), list)


def test_audit_log_record_persistence(operator_client, admin_client):
    """Ensure that executing a privileged action creates an entry in audit_log.jsonl."""
    # Execute an operator action
    operator_client.post("/api/v1/operations/pipeline/trigger-gold")

    # Read audit log as admin
    res = admin_client.get("/api/v1/admin/security/audit-log?limit=20")
    assert res.status_code == 200
    log_entries = res.json()
    assert len(log_entries) > 0

    # Verify latest action details
    actions = [e["action"] for e in log_entries]
    assert "TRIGGER_GOLD_PIPELINE" in actions
