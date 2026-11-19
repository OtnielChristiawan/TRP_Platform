# Security Audit & Access Control (RBAC) Specification
## Bakery Data Platform V4 — Toko Roti Pagi (TRP)
**Document Version:** 1.0.0  
**Compliance Standard:** Functional Requirement F-16 (Security, RBAC, Audit Trail)  
**Security Classification:** Internal Data Platform Engineering  

---

## 1. Executive Summary

Bakery Data Platform V4 implements a multi-layered **Defense-in-Depth** security architecture to safeguard analytical datasets, stream events, machine learning artifacts, and serving interfaces.

Key security controls enforced:
1. **Role-Based Access Control (RBAC)**: Strict segregation of duties across three personas (`Viewer`, `Operator`, `Admin`).
2. **Standardized HTTP Status Codes**: Explicit enforcement of `401 Unauthorized` for missing/invalid tokens and `403 Forbidden` for privilege escalation attempts.
3. **Structured Security & Operational Audit Trail**: Immutable JSONL audit logging for all privileged, operational, and administrative actions.
4. **Secret Management & Repo Cleanliness**: Strict decoupling of secrets from Git via `.env` files and environment injection.
5. **Network Perimeter & Port Isolation**: Isolated Docker container network (`bakery-network`) restricting inter-service communication.

---

## 2. Role-Based Access Control (RBAC) Matrix

### 2.1 Role Definitions
- **`viewer`**: Business Analyst, Store Manager, and Executive personas requiring read-only access to sales analytics marts, KPIs, and ML demand projections.
- **`operator`**: Data Engineers and Operations personnel responsible for pipeline execution, metadata cache warming, and on-demand model inference triggering.
- **`admin`**: Lead Data Architect and Security Administrators possessing full supervisory authority, audit trail inspection rights, and credentials rotation capability.

### 2.2 Access Control Matrix

| Resource Category | API Endpoints | Viewer | Operator | Admin |
|:---|:---|:---:|:---:|:---:|
| **Public Probes** | `GET /api/v1/health` | **ALLOW** | **ALLOW** | **ALLOW** |
| **Sales Analytics Marts** | `GET /api/v1/sales/*`<br>`GET /api/v1/menus/*`<br>`GET /api/v1/categories/*`<br>`GET /api/v1/payments/*`<br>`GET /api/v1/dashboard/*` | **ALLOW** | **ALLOW** | **ALLOW** |
| **Data Freshness & Filters** | `GET /api/v1/data/freshness`<br>`GET /api/v1/filters` | **ALLOW** | **ALLOW** | **ALLOW** |
| **ML Demand Forecasts** | `GET /api/v1/ml/*` | **ALLOW** | **ALLOW** | **ALLOW** |
| **DuckDB Cache Refresh** | `POST /api/v1/operations/cache/refresh` | ❌ **DENY (403)** | **ALLOW** | **ALLOW** |
| **Pipeline Sync Trigger** | `POST /api/v1/operations/pipeline/trigger-gold` | ❌ **DENY (403)** | **ALLOW** | **ALLOW** |
| **ML Inference Trigger** | `POST /api/v1/operations/ml/trigger-inference` | ❌ **DENY (403)** | **ALLOW** | **ALLOW** |
| **Runtime Telemetry** | `GET /api/v1/operations/system/health` | ❌ **DENY (403)** | **ALLOW** | **ALLOW** |
| **Security Audit Trail** | `GET /api/v1/admin/security/audit-log` | ❌ **DENY (403)** | ❌ **DENY (403)** | **ALLOW** |
| **Access Matrix Schema** | `GET /api/v1/admin/security/access-matrix` | ❌ **DENY (403)** | ❌ **DENY (403)** | **ALLOW** |
| **Credentials Reload** | `POST /api/v1/admin/system/reload-credentials` | ❌ **DENY (403)** | ❌ **DENY (403)** | **ALLOW** |

---

## 3. Authentication Mechanisms

The API supports dual header-based authentication schemes:

1. **API Key Header**:
   ```http
   X-API-Key: trp-viewer-key-2026
   ```
2. **Standard HTTP Bearer Token**:
   ```http
   Authorization: Bearer trp-admin-key-2026
   ```

### Default Demo Credentials
*(Configurable via environment variables in `.env`)*:
- `API_KEY_VIEWER`: `trp-viewer-key-2026`
- `API_KEY_OPERATOR`: `trp-operator-key-2026`
- `API_KEY_ADMIN`: `trp-admin-key-2026`

---

## 4. Structured Audit Trail (`state/audit_log.jsonl`)

Every privileged operation (`operator` and `admin` routes) generates an immutable, structured audit record.

### Event Schema
```json
{
  "timestamp": "2026-11-19T20:53:00.123456+00:00",
  "role": "operator",
  "action": "TRIGGER_GOLD_PIPELINE",
  "endpoint": "/api/v1/operations/pipeline/trigger-gold",
  "method": "POST",
  "client_ip": "172.22.0.1",
  "status_code": 200,
  "details": {
    "pipeline": "gold_batch",
    "mode": "sync_signal"
  }
}
```

---

## 5. Secret Management & Repository Cleanliness

| Security Principle | Implementation Detail | Status |
|:---|:---|:---:|
| **Zero Hardcoded Secrets in Git** | `.gitignore` blocks `.env`, `*.pem`, `*.key`, and secret dumps. | **PASS** |
| **Environment Decoupling** | Credentials loaded via `pydantic-settings` from environment variables. | **PASS** |
| **MinIO S3 Secret Storage** | DuckDB uses in-memory or session-scoped `CREATE SECRET (TYPE S3 ...)` without exposing plain text in logs. | **PASS** |
| **Non-Root Execution** | Batch workers and services configured with isolated user scopes. | **PASS** |

---

## 6. Threat Modeling & Checklist (STRIDE Analysis)

| Threat Category | Potential Attack Vector | Platform Countermeasure | Status |
|:---|:---|:---|:---:|
| **Spoofing (S)** | Attacker pretends to be Store Manager | API Key / Bearer token validation; client IP and timestamp recorded in audit log. | **MITIGATED** |
| **Tampering (T)** | Unauthorized edit of Gold Mart Parquet | Parquet files are stored in object store; serving layer is read-only via DuckDB. | **MITIGATED** |
| **Repudiation (R)** | Operator triggers unauthorized batch re-sync | All trigger actions are permanently recorded in append-only `audit_log.jsonl`. | **MITIGATED** |
| **Information Disclosure (I)** | Unhandled stack traces leak database internals | Global FastAPI exception handler catches unhandled errors and returns standardized 500 JSON without stack traces. | **MITIGATED** |
| **Denial of Service (D)** | Query flood exhausts server memory | DuckDB query timeouts, connection pooling, and paging (`limit` parameters). | **MITIGATED** |
| **Elevation of Privilege (E)** | Viewer attempts to access admin audit logs | Role hierarchy check strictly enforces `ROLE_HIERARCHY[role] >= min_role`; unauthorized callers receive HTTP 403. | **MITIGATED** |

---

## 7. Automated Test Verification (F-16 & F-18)

Automated tests are located in `tests/test_security_rbac.py` and run via pytest:
```bash
pytest tests/test_security_rbac.py -v
```

All test cases verify:
- `test_public_health_endpoint_allows_unauthenticated`: HTTP 200 OK
- `test_analytics_endpoint_unauthorized_without_key`: HTTP 401 Unauthorized
- `test_analytics_endpoint_unauthorized_with_invalid_key`: HTTP 401 Unauthorized
- `test_bearer_token_authorization_header`: HTTP 200 OK
- `test_viewer_authorized_for_analytics`: HTTP 200 OK
- `test_viewer_forbidden_from_operator_actions`: HTTP 403 Forbidden
- `test_viewer_forbidden_from_admin_actions`: HTTP 403 Forbidden
- `test_operator_authorized_for_operations`: HTTP 200 OK
- `test_operator_forbidden_from_admin_actions`: HTTP 403 Forbidden
- `test_admin_authorized_for_all_actions`: HTTP 200 OK
- `test_audit_log_record_persistence`: Verified JSONL output in `audit_log.jsonl`
