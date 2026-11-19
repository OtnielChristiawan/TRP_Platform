"""Administrative and Security Governance Endpoints (F-16 Admin Role)."""
import json
from pathlib import Path
from typing import Any, Dict, List
from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

from app.core.security import AUDIT_LOG_FILE, Role, record_audit_event, require_role
from app.db.duckdb_connection import get_db_manager

router = APIRouter(prefix="/admin", tags=["Admin (Admin Role)"])


class AuditLogEntry(BaseModel):
    timestamp: str
    role: str
    action: str
    endpoint: str
    method: str
    client_ip: str
    status_code: int
    details: Dict[str, Any]


class AccessMatrixResponse(BaseModel):
    roles: List[str]
    access_rules: List[Dict[str, Any]]
    policy_enforcement: str


@router.get("/security/audit-log", response_model=List[AuditLogEntry])
def get_audit_log(
    request: Request,
    limit: int = Query(50, ge=1, le=500, description="Number of recent audit events to fetch"),
    role: Role = Depends(require_role(Role.ADMIN)),
):
    """Retrieve persistent security and operational audit trail logs (Admin only)."""
    client_ip = request.client.host if request.client else "unknown"

    entries = []
    if AUDIT_LOG_FILE.exists():
        try:
            with open(AUDIT_LOG_FILE, "r", encoding="utf-8") as f:
                lines = f.readlines()
                for line in lines[-limit:]:
                    line = line.strip()
                    if line:
                        entries.append(json.loads(line))
        except Exception as e:
            entries.append({
                "timestamp": "",
                "role": "admin",
                "action": "ERROR_READING_AUDIT_LOG",
                "endpoint": "/api/v1/admin/security/audit-log",
                "method": "GET",
                "client_ip": client_ip,
                "status_code": 500,
                "details": {"error": str(e)},
            })

    record_audit_event(
        role=role,
        action="INSPECT_SECURITY_AUDIT_LOG",
        endpoint="/api/v1/admin/security/audit-log",
        method="GET",
        client_ip=client_ip,
        status_code=200,
        details={"retrieved_count": len(entries)},
    )

    return entries[::-1]  # Return newest first


@router.get("/security/access-matrix", response_model=AccessMatrixResponse)
def get_access_matrix(
    request: Request,
    role: Role = Depends(require_role(Role.ADMIN)),
):
    """Retrieve formal Role-Based Access Control (RBAC) permission matrix."""
    rules = [
        {
            "resource": "Sales & Analytics Marts",
            "endpoints": ["/api/v1/sales/*", "/api/v1/menus/*", "/api/v1/categories/*", "/api/v1/payments/*", "/api/v1/dashboard/*"],
            "viewer": "ALLOW (Read)",
            "operator": "ALLOW (Read)",
            "admin": "ALLOW (Read)",
        },
        {
            "resource": "ML Demand Forecasts",
            "endpoints": ["/api/v1/ml/*"],
            "viewer": "ALLOW (Read)",
            "operator": "ALLOW (Read)",
            "admin": "ALLOW (Read)",
        },
        {
            "resource": "Operational Triggers & Health",
            "endpoints": ["/api/v1/operations/*"],
            "viewer": "DENY (HTTP 403)",
            "operator": "ALLOW (Execute)",
            "admin": "ALLOW (Execute)",
        },
        {
            "resource": "Security Audit Trail & Secrets",
            "endpoints": ["/api/v1/admin/*"],
            "viewer": "DENY (HTTP 403)",
            "operator": "DENY (HTTP 403)",
            "admin": "ALLOW (Full Control)",
        },
        {
            "resource": "System Health Probes",
            "endpoints": ["/health", "/api/v1/health"],
            "viewer": "ALLOW (Anonymous / Public)",
            "operator": "ALLOW (Anonymous / Public)",
            "admin": "ALLOW (Anonymous / Public)",
        },
    ]

    return AccessMatrixResponse(
        roles=["viewer", "operator", "admin"],
        access_rules=rules,
        policy_enforcement="Strict Header-based API Key & Bearer Token Authentication",
    )


@router.post("/system/reload-credentials")
def reload_system_credentials(
    request: Request,
    role: Role = Depends(require_role(Role.ADMIN)),
):
    """Reload DuckDB S3 secrets and internal connection credentials without service restart."""
    client_ip = request.client.host if request.client else "unknown"
    db = get_db_manager()
    db.reset_connection()

    record_audit_event(
        role=role,
        action="RELOAD_SYSTEM_CREDENTIALS",
        endpoint="/api/v1/admin/system/reload-credentials",
        method="POST",
        client_ip=client_ip,
        status_code=200,
        details={"component": "DuckDB_S3_Secrets", "action": "CREATE OR REPLACE SECRET"},
    )

    return {
        "status": "success",
        "action": "RELOAD_SYSTEM_CREDENTIALS",
        "message": "S3 secret credentials re-configured and verified in DuckDB runtime.",
        "triggered_by": role.value,
    }
