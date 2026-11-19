# Operational Runbook: ALERT_B_STREAM_LAG
## Stream Freshness High Lag / Ingestion Delay

**Alert ID:** `ALERT_B_STREAM_LAG`  
**Severity:** `WARNING`  
**Target SLAs:** TTR < 15 Minutes  
**Component:** Redpanda Kafka Broker + Spark Structured Streaming + Python Replay Producer  
**Owner:** Streaming Platform Engineer (`streaming-ops@tokorotipagi.local`)  

---

### 1. Alert Summary
This alert fires when:
1. Time since the latest ingested transaction exceeds 1800 seconds (30 minutes) during business hours, OR
2. Consumer lag in topic `bakery.transactions.v1` exceeds 100 uncommitted messages.

### 2. Immediate Triage Steps
1. **Check Redpanda Broker Status**:
   Inspect console UI at `http://localhost:8080` or execute:
   ```bash
   docker exec -it bakery-v4-redpanda-1 rpk cluster health
   ```
2. **Inspect Spark Streaming Consumer**:
   ```bash
   docker logs --tail 50 bakery-v4-spark-bronze-1
   ```
3. **Verify Producer Process**:
   Check if Python replay script is alive:
   ```bash
   docker ps --filter "name=producer"
   ```

### 3. Remediation & Recovery Procedure
1. **Restarting Spark Streaming Consumer**:
   If Spark Structured Streaming hung on a network partition:
   ```bash
   docker restart bakery-v4-spark-bronze-1
   ```
   Spark will automatically resume from the checkpoint stored in `s3://bakery-bronze/checkpoints/transactions_stream`.

2. **Triggering Ingestion Catch-up**:
   Run replay producer to stream missing transaction batches:
   ```bash
   python producer/replay.py --source-anchor-date 2026-10-18 --speed 5.0
   ```

### 4. Resolution & Clear Verification
- Once new events flow into Bronze and data freshness drops below 300 seconds, the Alert Manager automatically transitions the alert to **`RESOLVED`**.
