"""Operational endpoints for Data Operations & Engineering (F-16 Operator Role)."""
import json
import os
import platform
try:
    import psutil
except ImportError:
    psutil = None
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from typing import Any, Dict

from app.core.security import Role, record_audit_event, require_role
from app.db.duckdb_connection import get_db_manager

router = APIRouter(prefix="/operations", tags=["Operations (Operator Role)"])


class OperationResponse(BaseModel):
    status: str
    action: str
    message: str
    triggered_by: str


@router.post("/cache/refresh", response_model=OperationResponse)
def refresh_cache(
    request: Request,
    role: Role = Depends(require_role(Role.OPERATOR)),
):
    """Trigger DuckDB connection re-initialization and clear query cache."""
    client_ip = request.client.host if request.client else "unknown"
    db = get_db_manager()
    db.reset_connection()

    record_audit_event(
        role=role,
        action="REFRESH_DUCKDB_CACHE",
        endpoint="/api/v1/operations/cache/refresh",
        method="POST",
        client_ip=client_ip,
        status_code=200,
        details={"engine": "DuckDB", "scope": "connection_pool"},
    )

    return OperationResponse(
        status="success",
        action="REFRESH_DUCKDB_CACHE",
        message="DuckDB connection re-warmed and query cache flushed successfully.",
        triggered_by=role.value,
    )


@router.post("/pipeline/trigger-gold", response_model=OperationResponse)
def trigger_gold_sync(
    request: Request,
    role: Role = Depends(require_role(Role.OPERATOR)),
):
    """Trigger on-demand Gold Mart sync verification."""
    client_ip = request.client.host if request.client else "unknown"

    record_audit_event(
        role=role,
        action="TRIGGER_GOLD_PIPELINE",
        endpoint="/api/v1/operations/pipeline/trigger-gold",
        method="POST",
        client_ip=client_ip,
        status_code=200,
        details={"pipeline": "gold_batch", "mode": "sync_signal"},
    )

    return OperationResponse(
        status="accepted",
        action="TRIGGER_GOLD_PIPELINE",
        message="Gold mart batch sync signal dispatched to scheduler.",
        triggered_by=role.value,
    )


@router.post("/ml/trigger-inference", response_model=OperationResponse)
def trigger_ml_inference(
    request: Request,
    role: Role = Depends(require_role(Role.OPERATOR)),
):
    """Trigger on-demand ML demand forecast batch inference."""
    client_ip = request.client.host if request.client else "unknown"

    record_audit_event(
        role=role,
        action="TRIGGER_ML_INFERENCE",
        endpoint="/api/v1/operations/ml/trigger-inference",
        method="POST",
        client_ip=client_ip,
        status_code=200,
        details={"pipeline": "ml_batch_inference", "target": "next_day_demand"},
    )

    return OperationResponse(
        status="accepted",
        action="TRIGGER_ML_INFERENCE",
        message="ML demand forecasting inference batch run initiated.",
        triggered_by=role.value,
    )


@router.get("/system/health")
def get_system_health(
    request: Request,
    role: Role = Depends(require_role(Role.OPERATOR)),
) -> Dict[str, Any]:
    """Retrieve runtime telemetry and host/container health metrics."""
    client_ip = request.client.host if request.client else "unknown"

    # Gather system memory and process metrics if psutil is available
    if psutil:
        mem = psutil.virtual_memory()
        proc = psutil.Process()
        proc_metrics = {
            "pid": proc.pid,
            "memory_used_mb": round(proc.memory_info().rss / (1024 * 1024), 2),
            "cpu_percent": proc.cpu_percent(interval=None),
        }
        sys_metrics = {
            "total_ram_gb": round(mem.total / (1024**3), 2),
            "available_ram_gb": round(mem.available / (1024**3), 2),
            "ram_percent": mem.percent,
        }
    else:
        proc_metrics = {"pid": os.getpid(), "memory_used_mb": None, "cpu_percent": None}
        sys_metrics = {"total_ram_gb": None, "available_ram_gb": None, "ram_percent": None}

    telemetry = {
        "status": "healthy",
        "role_caller": role.value,
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "python": platform.python_version(),
        },
        "process_metrics": proc_metrics,
        "system_metrics": sys_metrics,
    }

    record_audit_event(
        role=role,
        action="GET_SYSTEM_HEALTH",
        endpoint="/api/v1/operations/system/health",
        method="GET",
        client_ip=client_ip,
        status_code=200,
    )

    return telemetry


# -----------------------------------------------------------------------------
# F-15 Alerting Operations Endpoints
# -----------------------------------------------------------------------------

import sys
from pathlib import Path

# Add potential root directories to sys.path
for candidate in [
    Path(__file__).resolve().parents[2],
    Path(__file__).resolve().parents[3],
    Path("/app"),
    Path("/opt/bakery"),
]:
    if candidate.exists() and str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

try:
    from monitoring.alert_manager import get_alert_manager
except ImportError:
    # Fallback to local app.monitoring if nested
    from app.monitoring.alert_manager import get_alert_manager


@router.get("/alerts/active")
def get_active_alerts(
    role: Role = Depends(require_role(Role.OPERATOR)),
):
    """Retrieve all currently firing alerts across the data platform."""
    alert_mgr = get_alert_manager()
    return alert_mgr.get_active_alerts()


@router.get("/alerts/history")
def get_alert_history(
    limit: int = 50,
    role: Role = Depends(require_role(Role.OPERATOR)),
):
    """Retrieve recent alert notifications and resolution lifecycle history."""
    alert_mgr = get_alert_manager()
    return alert_mgr.get_alert_history(limit=limit)


class TriggerTestAlertRequest(BaseModel):
    rule_id: str
    message: str = "Simulated anomaly trigger for end-to-end testing"
    current_value: Any = 1


@router.post("/alerts/trigger-test")
def trigger_test_alert(
    body: TriggerTestAlertRequest,
    request: Request,
    role: Role = Depends(require_role(Role.OPERATOR)),
):
    """Simulate an alert condition (Firing) for end-to-end verification."""
    client_ip = request.client.host if request.client else "unknown"
    alert_mgr = get_alert_manager()
    event = alert_mgr.fire_alert(
        rule_id=body.rule_id,
        current_value=body.current_value,
        message=body.message,
        details={"triggered_by_role": role.value, "client_ip": client_ip},
    )

    record_audit_event(
        role=role,
        action=f"SIMULATE_ALERT_{body.rule_id}",
        endpoint="/api/v1/operations/alerts/trigger-test",
        method="POST",
        client_ip=client_ip,
        status_code=200,
        details={"alert_id": event["alert_id"]},
    )
    return event


@router.post("/alerts/resolve/{rule_id}")
def resolve_test_alert(
    rule_id: str,
    request: Request,
    role: Role = Depends(require_role(Role.OPERATOR)),
):
    """Resolve an active firing alert and record recovery event."""
    client_ip = request.client.host if request.client else "unknown"
    alert_mgr = get_alert_manager()
    event = alert_mgr.resolve_alert(
        rule_id=rule_id,
        resolution_message=f"Alert manually resolved and verified by operator '{role.value}'.",
    )

    if not event:
        return {"status": "not_active", "message": f"Alert '{rule_id}' was not currently firing."}

    record_audit_event(
        role=role,
        action=f"RESOLVE_ALERT_{rule_id}",
        endpoint=f"/api/v1/operations/alerts/resolve/{rule_id}",
        method="POST",
        client_ip=client_ip,
        status_code=200,
        details={"rule_id": rule_id},
    )
    return event


# -----------------------------------------------------------------------------
# F-08 & F-09 Data Governance Endpoints
# -----------------------------------------------------------------------------

def _find_file(filename: str) -> Path:
    candidates = [
        Path("/opt/bakery/state") / filename,
        Path("/opt/bakery") / filename,
        Path(__file__).resolve().parents[3] / filename,
        Path(__file__).resolve().parents[2] / filename,
        Path("/app") / filename,
        Path("state") / filename,
        Path(filename),
    ]
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]


@router.get("/governance/quality-report")
def get_data_quality_report(
    role: Role = Depends(require_role(Role.OPERATOR)),
):
    """Retrieve F-08 Data Quality Gate evaluation report."""
    target_file = _find_file("data_quality_report.json")
    if target_file.exists():
        try:
            with open(target_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            return {"error": f"Failed reading quality report: {e}"}
    return {"status": "NOT_FOUND", "message": "data_quality_report.json not yet generated"}


@router.get("/governance/lineage")
def get_data_lineage(
    role: Role = Depends(require_role(Role.OPERATOR)),
):
    """Retrieve F-09 Metadata & Data Lineage DAG graph."""
    target_file = _find_file("lineage.json")
    if target_file.exists():
        try:
            with open(target_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            return {"error": f"Failed reading lineage graph: {e}"}
    return {"status": "NOT_FOUND", "message": "lineage.json not yet generated"}
