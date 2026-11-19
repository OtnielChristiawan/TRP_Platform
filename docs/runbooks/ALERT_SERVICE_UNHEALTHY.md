# Operational Runbook: ALERT_C_SERVICE_UNHEALTHY
## Infrastructure Container or Host Resource Critical

**Alert ID:** `ALERT_C_SERVICE_UNHEALTHY`  
**Severity:** `CRITICAL`  
**Target SLAs:** TTR < 10 Minutes  
**Component:** Docker Daemon, Host RAM/Disk, Core Service Containers  
**Owner:** DevOps / Infrastructure Engineer (`infra@tokorotipagi.local`)  

---

### 1. Alert Summary
This alert fires when:
1. Any required container (`minio`, `redpanda`, `backend-api`, `frontend`, `spark-bronze`) reports `unhealthy` or `exited`, OR
2. Host RAM consumption exceeds 90% for longer than 2 minutes.

### 2. Immediate Triage Steps
1. **List Container Statuses**:
   ```bash
   docker ps -a --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
   ```
2. **Inspect Host Memory & Disk Usage**:
   ```powershell
   Get-Process | Sort-Object WorkingSet64 -Descending | Select-Object -First 10
   ```

### 3. Remediation & Recovery Procedure
1. **Restarting Dead Services**:
   ```bash
   docker compose up -d --no-recreate
   ```
2. **If Memory is Saturated**:
   Prune unused Docker artifacts and dangling layers:
   ```bash
   docker system prune -f
   ```

### 4. Resolution & Clear Verification
- When all services report status `running`/`healthy` and system memory drops below 85%, the Alert Manager automatically transitions the alert to **`RESOLVED`**.
