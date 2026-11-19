"""End-to-End Test Suite for F-15 Alerting System.

Validates the full lifecycle for the three mandatory lecturer rules:
1. Alert A: Job Execution Failure (exit_code != 0 -> FIRING -> exit_code == 0 -> RESOLVED)
2. Alert B: Stream Freshness High Lag (lag > 1800s -> FIRING -> lag < 300s -> RESOLVED)
3. Alert C: Service/Resource Unhealthy (container down -> FIRING -> container up -> RESOLVED)
4. Notification log delivery persistence in state/alerts/notifications.jsonl
5. Operational API endpoints (/alerts/active, /alerts/history, /alerts/trigger-test, /alerts/resolve)
"""
import json
import os
import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))
ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

os.environ["S3_ENDPOINT"] = "localhost:9000"
os.environ["MINIO_ENDPOINT"] = "localhost:9000"

from app.main import app
from app.core.security import API_KEY_OPERATOR, API_KEY_VIEWER
from monitoring.alert_manager import (
    AlertManager,
    AlertStatus,
    AlertSeverity,
    get_alert_manager,
    RULES_FILE,
    NOTIFICATIONS_LOG,
)


@pytest.fixture
def alert_mgr():
    return get_alert_manager()


@pytest.fixture
def operator_client():
    return TestClient(app, headers={"X-API-Key": API_KEY_OPERATOR})


@pytest.fixture
def viewer_client():
    return TestClient(app, headers={"X-API-Key": API_KEY_VIEWER})


def test_alert_rules_schema_and_compliance():
    """Verify that alert_rules.json conforms to F-15 specification requirements."""
    assert RULES_FILE.exists()
    with open(RULES_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert "rules" in data
    rules_by_id = {r["id"]: r for r in data["rules"]}

    # Verify all 3 mandatory lecturer rules exist
    assert "ALERT_A_JOB_FAILURE" in rules_by_id
    assert "ALERT_B_STREAM_LAG" in rules_by_id
    assert "ALERT_C_SERVICE_UNHEALTHY" in rules_by_id

    # Verify all required fields per F-15
    for r_id, rule in rules_by_id.items():
        assert "name" in rule
        assert "threshold" in rule
        assert "window_seconds" in rule
        assert "severity" in rule
        assert "owner" in rule
        assert "channels" in rule
        assert "runbook" in rule

        # Verify runbook exists on disk
        runbook_path = ROOT_DIR / rule["runbook"]
        assert runbook_path.exists(), f"Runbook missing: {rule['runbook']}"


def test_alert_a_job_failure_trigger_and_resolve(alert_mgr):
    """Simulate Alert A lifecycle: failed batch job -> FIRING -> successful job -> RESOLVED."""
    # 1. Simulate failed Spark job
    firing_event = alert_mgr.evaluate_job_status(
        job_name="spark_silver_batch",
        exit_code=1,
        error_details="Connection reset by peer during Parquet commit",
    )
    assert firing_event is not None
    assert firing_event["status"] == AlertStatus.FIRING.value
    assert firing_event["severity"] == AlertSeverity.CRITICAL.value
    assert "ALERT_A_JOB_FAILURE" in alert_mgr.active_alerts

    # 2. Simulate next job run succeeds (remediation)
    resolved_event = alert_mgr.evaluate_job_status(
        job_name="spark_silver_batch",
        exit_code=0,
    )
    assert resolved_event is not None
    assert resolved_event["status"] == AlertStatus.RESOLVED.value
    assert resolved_event["resolved_at"] is not None
    assert "ALERT_A_JOB_FAILURE" not in alert_mgr.active_alerts


def test_alert_b_stream_lag_trigger_and_resolve(alert_mgr):
    """Simulate Alert B lifecycle: stream lag > 1800s -> FIRING -> stream catches up -> RESOLVED."""
    # 1. Simulate 45 minutes lag
    firing_event = alert_mgr.evaluate_stream_freshness(freshness_seconds=2700.0, message_lag=150)
    assert firing_event is not None
    assert firing_event["status"] == AlertStatus.FIRING.value
    assert firing_event["severity"] == AlertSeverity.WARNING.value
    assert "ALERT_B_STREAM_LAG" in alert_mgr.active_alerts

    # 2. Simulate producer sends new data and freshness recovers to 60s
    resolved_event = alert_mgr.evaluate_stream_freshness(freshness_seconds=60.0, message_lag=0)
    assert resolved_event is not None
    assert resolved_event["status"] == AlertStatus.RESOLVED.value
    assert "ALERT_B_STREAM_LAG" not in alert_mgr.active_alerts


def test_alert_c_service_unhealthy_trigger_and_resolve(alert_mgr):
    """Simulate Alert C lifecycle: container down -> FIRING -> restarted -> RESOLVED."""
    # 1. Simulate MinIO container down
    bad_services = {"minio": "exited", "backend-api": "running", "redpanda": "running"}
    firing_event = alert_mgr.evaluate_service_health(container_statuses=bad_services, memory_percent=65.0)
    assert firing_event is not None
    assert firing_event["status"] == AlertStatus.FIRING.value
    assert firing_event["severity"] == AlertSeverity.CRITICAL.value
    assert "ALERT_C_SERVICE_UNHEALTHY" in alert_mgr.active_alerts

    # 2. Simulate service restored
    good_services = {"minio": "healthy", "backend-api": "running", "redpanda": "healthy"}
    resolved_event = alert_mgr.evaluate_service_health(container_statuses=good_services, memory_percent=60.0)
    assert resolved_event is not None
    assert resolved_event["status"] == AlertStatus.RESOLVED.value
    assert "ALERT_C_SERVICE_UNHEALTHY" not in alert_mgr.active_alerts


def test_notification_log_persistence():
    """Verify that every alert event was appended to state/alerts/notifications.jsonl."""
    assert NOTIFICATIONS_LOG.exists()
    with open(NOTIFICATIONS_LOG, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]

    assert len(lines) >= 6  # At least 3 firing + 3 resolved events

    # Parse last line
    latest_event = json.loads(lines[-1])
    assert "status" in latest_event
    assert "rule_id" in latest_event
    assert "message" in latest_event
    assert "triggered_at" in latest_event


def test_api_alerts_endpoints_operational(operator_client, viewer_client):
    """Test operational API endpoints for active alerts, history, trigger-test, and resolve."""
    # 1. Viewer is forbidden from triggering or resolving alerts
    res_forbidden = viewer_client.post("/api/v1/operations/alerts/trigger-test", json={"rule_id": "ALERT_A_JOB_FAILURE"})
    assert res_forbidden.status_code == 403

    # 2. Operator triggers test alert
    res_trigger = operator_client.post(
        "/api/v1/operations/alerts/trigger-test",
        json={"rule_id": "ALERT_B_STREAM_LAG", "message": "Manual test for lecturer demonstration", "current_value": 2500},
    )
    assert res_trigger.status_code == 200
    assert res_trigger.json()["status"] == AlertStatus.FIRING.value

    # 3. Check active alerts
    res_active = operator_client.get("/api/v1/operations/alerts/active")
    assert res_active.status_code == 200
    active_rules = [a["rule_id"] for a in res_active.json()]
    assert "ALERT_B_STREAM_LAG" in active_rules

    # 4. Resolve the test alert via API
    res_resolve = operator_client.post("/api/v1/operations/alerts/resolve/ALERT_B_STREAM_LAG")
    assert res_resolve.status_code == 200
    assert res_resolve.json()["status"] == AlertStatus.RESOLVED.value

    # 5. Check history
    res_hist = operator_client.get("/api/v1/operations/alerts/history?limit=10")
    assert res_hist.status_code == 200
    assert len(res_hist.json()) > 0
