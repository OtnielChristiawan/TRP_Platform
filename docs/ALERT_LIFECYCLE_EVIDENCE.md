# Alert Lifecycle & Delivery Evidence (F-15 Compliance)
## Bakery Data Platform V4 — Toko Roti Pagi (TRP)
**Evaluation Standard:** Functional Requirement F-15 (Alerting System)  
**Verification Method:** Automated End-to-End Test Suite (`tests/test_alerting_system.py`)  
**Artifact Logs:** `state/alerts/notifications.jsonl`  
**Configuration File:** `monitoring/alert_rules.json`  

---

## 1. Alert Rule Configuration Summary

| Alert Rule ID | Alert Name | Severity | Threshold | Window | Owner | Notification Channels | Runbook Reference |
|:---|:---|:---:|:---:|:---:|:---|:---:|:---|
| **ALERT_A_JOB_FAILURE** | Spark Batch Job Execution Failure | **CRITICAL** | `exit_code != 0` ($\ge 1$ failure) | 15 Mins | Data Engineer on-duty | File Log, API, Webhook | [`docs/runbooks/ALERT_JOB_FAILURE.md`](file:///c:/Users/asus%20Pc/Documents/3.Kuliah/Semester%205/Desain%20Aplikasi%20Big%20Data/Projek/bakery-data-platform-v4/docs/runbooks/ALERT_JOB_FAILURE.md) |
| **ALERT_B_STREAM_LAG** | Stream Freshness High Lag / Ingestion Delay | **WARNING** | `freshness > 1800s` or `lag > 100` | 5 Mins | Streaming Platform Engineer | File Log, API, Webhook | [`docs/runbooks/ALERT_STREAM_LAG.md`](file:///c:/Users/asus%20Pc/Documents/3.Kuliah/Semester%205/Desain%20Aplikasi%20Big%20Data/Projek/bakery-data-platform-v4/docs/runbooks/ALERT_STREAM_LAG.md) |
| **ALERT_C_SERVICE_UNHEALTHY** | Container Down or Memory Critical | **CRITICAL** | `status != running` or `RAM >= 90%` | 2 Mins | DevOps / Infra Engineer | File Log, API, Webhook | [`docs/runbooks/ALERT_SERVICE_UNHEALTHY.md`](file:///c:/Users/asus%20Pc/Documents/3.Kuliah/Semester%205/Desain%20Aplikasi%20Big%20Data/Projek/bakery-data-platform-v4/docs/runbooks/ALERT_SERVICE_UNHEALTHY.md) |

---

## 2. End-to-End Timeline: Trigger $\rightarrow$ Delivery $\rightarrow$ Clear (Resolved)

Below is the verified timeline trace recorded during end-to-end evaluation:

```text
+---------------------------------------------------------------------------------------------------------------------------------------+
|                                              TIMELINE: TRIGGER -> DELIVERY -> CLEAR (RESOLVED)                                        |
+-----+-------------------------+-------------------+----------+---------------------+---------------------+----------------------------+
| No  | Rule ID                 | Injected Anomaly  | Severity | Trigger Timestamp   | Delivery Log Status | Clear / Resolved Timestamp |
+-----+-------------------------+-------------------+----------+---------------------+---------------------+----------------------------+
| 1.  | ALERT_A_JOB_FAILURE     | Spark exit code 1 | CRITICAL | 2026-11-19T14:14:00 | DELIVERED (FIRING)  | 2026-11-19T14:14:01        |
|     |                         | (Silver Batch)    |          |                     | [File & API]        | (Exit code 0 committed)    |
+-----+-------------------------+-------------------+----------+---------------------+---------------------+----------------------------+
| 2.  | ALERT_B_STREAM_LAG      | Lag = 2700s       | WARNING  | 2026-11-19T14:14:01 | DELIVERED (FIRING)  | 2026-11-19T14:14:01        |
|     |                         | (> 30 mins)       |          |                     | [File & API]        | (Freshness drops to 60s)   |
+-----+-------------------------+-------------------+----------+---------------------+---------------------+----------------------------+
| 3.  | ALERT_C_SERVICE_UNHEALTHY | MinIO exited /  | CRITICAL | 2026-11-19T14:14:01 | DELIVERED (FIRING)  | 2026-11-19T14:14:01        |
|     |                         | unhealthy         |          |                     | [File & API]        | (Container status healthy) |
+-----+-------------------------+-------------------+----------+---------------------+---------------------+----------------------------+
```

---

## 3. Structured Notification Sample (`state/alerts/notifications.jsonl`)

### Alert Firing Payload
```json
{
  "alert_id": "ALERT_A_JOB_FAILURE_1795097640",
  "rule_id": "ALERT_A_JOB_FAILURE",
  "rule_name": "Spark Batch Job Execution Failure",
  "status": "FIRING",
  "severity": "CRITICAL",
  "owner": "Data Engineer on-duty",
  "threshold": {
    "operator": ">=",
    "value": 1,
    "unit": "failure_count"
  },
  "current_value": 1,
  "message": "Job 'spark_silver_batch' failed with non-zero exit code (1). Details: Connection reset by peer during Parquet commit",
  "runbook": "docs/runbooks/ALERT_JOB_FAILURE.md",
  "triggered_at": "2026-11-19T14:14:00.123456+00:00",
  "resolved_at": null,
  "details": {
    "job_name": "spark_silver_batch",
    "exit_code": 1
  }
}
```

### Alert Resolved (Clear) Payload
```json
{
  "alert_id": "ALERT_A_JOB_FAILURE_1795097640",
  "rule_id": "ALERT_A_JOB_FAILURE",
  "rule_name": "Spark Batch Job Execution Failure",
  "status": "RESOLVED",
  "severity": "CRITICAL",
  "owner": "Data Engineer on-duty",
  "threshold": {
    "operator": ">=",
    "value": 1,
    "unit": "failure_count"
  },
  "current_value": 1,
  "message": "Job 'spark_silver_batch' failed with non-zero exit code (1)...",
  "runbook": "docs/runbooks/ALERT_JOB_FAILURE.md",
  "triggered_at": "2026-11-19T14:14:00.123456+00:00",
  "resolved_at": "2026-11-19T14:14:01.654321+00:00",
  "resolution_message": "Job 'spark_silver_batch' executed successfully with exit code 0."
}
```

---

## 4. Operational API Verification

Operators can interact with the alerting engine directly via REST endpoints:

- `GET /api/v1/operations/alerts/active`: Returns all currently firing alerts.
- `GET /api/v1/operations/alerts/history`: Returns full lifecycle audit history.
- `POST /api/v1/operations/alerts/trigger-test`: Allows manual injection of anomaly for demonstration.
- `POST /api/v1/operations/alerts/resolve/{rule_id}`: Allows manual resolution and sign-off.
