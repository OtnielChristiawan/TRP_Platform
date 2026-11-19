"""Security, Authentication, and Role-Based Access Control (RBAC) Module.

Defines roles (viewer, operator, admin), API key authentication, permission guards,
and audit trail logging as mandated by F-16 criteria.
"""
import json
import logging
import os
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader

logger = logging.getLogger("bakery.security")


class Role(str, Enum):
    VIEWER = "viewer"
    OPERATOR = "operator"
    ADMIN = "admin"


# Role hierarchy: higher integer has higher privileges
ROLE_HIERARCHY = {
    Role.VIEWER: 1,
    Role.OPERATOR: 2,
    Role.ADMIN: 3,
}

# API Keys loaded from environment variables with secure defaults for local lab demo
API_KEY_VIEWER = os.getenv("API_KEY_VIEWER", "trp-viewer-key-2026")
API_KEY_OPERATOR = os.getenv("API_KEY_OPERATOR", "trp-operator-key-2026")
API_KEY_ADMIN = os.getenv("API_KEY_ADMIN", "trp-admin-key-2026")

KEY_TO_ROLE = {
    API_KEY_VIEWER: Role.VIEWER,
    API_KEY_OPERATOR: Role.OPERATOR,
    API_KEY_ADMIN: Role.ADMIN,
}

# Header extractors
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# Audit log storage path
STATE_DIR = Path(os.getenv("STATE_DIR", Path(__file__).resolve().parents[3] / "state"))
AUDIT_LOG_FILE = STATE_DIR / "audit_log.jsonl"


def get_current_role(
    request: Request,
    api_key_hdr: Optional[str] = Security(api_key_header),
) -> Role:
    """Validate API Key from X-API-Key header or Authorization Bearer header.

    Raises:
        HTTPException(401): If API key is missing, malformed, or invalid.
    """
    token = api_key_hdr

    # Fallback to Authorization: Bearer <key> if X-API-Key not supplied
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()

    if not token or token not in KEY_TO_ROLE:
        logger.warning(f"Unauthorized API access attempt from {request.client.host if request.client else 'unknown'} on {request.url.path}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API Key. Please provide a valid 'X-API-Key' or 'Authorization: Bearer' header.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    return KEY_TO_ROLE[token]


def require_role(min_role: Role):
    """Dependency factory checking that the authenticated caller has at least min_role."""

    def role_checker(role: Role = Depends(get_current_role)) -> Role:
        if ROLE_HIERARCHY[role] < ROLE_HIERARCHY[min_role]:
            logger.warning(f"Forbidden access: role '{role.value}' attempted action requiring '{min_role.value}'")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Forbidden: Action requires at least '{min_role.value}' role, but your role is '{role.value}'.",
            )
        return role

    return role_checker


def record_audit_event(
    role: Role,
    action: str,
    endpoint: str,
    method: str,
    client_ip: str,
    status_code: int = 200,
    details: Optional[dict] = None,
):
    """Append a structured audit log entry to audit_log.jsonl."""
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "role": role.value,
        "action": action,
        "endpoint": endpoint,
        "method": method,
        "client_ip": client_ip,
        "status_code": status_code,
        "details": details or {},
    }

    try:
        AUDIT_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(AUDIT_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")
    except Exception as e:
        logger.error(f"Failed to write audit event: {e}")
