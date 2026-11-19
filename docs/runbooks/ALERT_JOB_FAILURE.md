# Operational Runbook: ALERT_A_JOB_FAILURE
## Spark Batch Job Execution Failure

**Alert ID:** `ALERT_A_JOB_FAILURE`  
**Severity:** `CRITICAL`  
**Target SLAs:** TTR (Time to Resolve) < 30 Minutes  
**Component:** Apache Spark Batch (Silver Transformation / Gold Mart Publication / Master Menu Ingestion)  
**Owner:** Data Engineer on-duty (`data-platform@tokorotipagi.local`)  

---

### 1. Alert Summary
This alert fires when a scheduled batch job crashes, exits with a non-zero exit code, or encounters an unhandled exception before committing its snapshot to SQLite / MinIO metadata.

### 2. Immediate Triage Steps
1. **Identify the Failed Job Container**:
   ```bash
   docker ps -a --filter "name=scheduler" --filter "status=exited"
   ```
2. **Inspect Container Execution Logs**:
   ```bash
   # If silver scheduler failed:
   docker logs --tail 100 bakery-v4-silver-scheduler-1

   # If gold scheduler failed:
   docker logs --tail 100 bakery-v4-gold-scheduler-1
   ```
3. **Verify SQLite State Lock Status**:
   Check if a dangling lock file exists in `./state/`:
   ```bash
   ls -la state/*.sqlite
   ```

### 3. Remediation & Recovery Procedure
1. **If MinIO Object Storage Connection Timed Out**:
   Verify MinIO health at port 9000:
   ```bash
   curl -I http://localhost:9000/minio/health/live
   ```
   Restart MinIO if unresponsive:
   ```bash
   docker restart bakery-v4-minio-1
   ```

2. **Run Manual Idempotent Retry**:
   Trigger the job in manual mode (`--once`):
   ```bash
   docker compose run --rm silver-batch --once
   docker compose run --rm gold-batch --once
   ```

3. **Verify State Manifest**:
   Confirm that the new snapshot has been published:
   ```bash
   # Check Gold manifest in MinIO
   cat state/gold_state.sqlite
   ```

### 4. Resolution & Clear Verification
- When the manual rerun or next scheduled interval finishes with `exit code 0`, the Alert Manager automatically transitions the alert status from **`FIRING`** to **`RESOLVED`**.
- An audit event `ALERT_STATUS_RESOLVED` is dispatched to `state/alerts/notifications.jsonl`.
