"""Lightweight Silver Layer Incremental Scheduler & Orchestrator.
- Manages SQLite state at state/silver_state.sqlite
- Prevents concurrent executions with SQLite locking
- Checks MinIO for new Bronze data without booting heavy Spark context if idle
- Invokes Spark batch incremental transformation when new data is detected
- Supports --once (manual backfill / test) and --interval 900 (15-min daemon loop)
- Timezone: Asia/Jakarta (WIB)
"""
import argparse
import os
import sqlite3
import subprocess
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Asia/Jakarta")
except Exception:
    TZ = timezone(timedelta(hours=7))


def get_db(state_path):
    path = Path(state_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(path), timeout=60.0)
    try:
        c.execute("PRAGMA busy_timeout = 60000")
        c.execute("PRAGMA journal_mode = MEMORY")
    except Exception:
        pass
    c.executescript("""
        CREATE TABLE IF NOT EXISTS silver_watermark (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS silver_batches (
            batch_id TEXT PRIMARY KEY,
            batch_type TEXT NOT NULL,
            status TEXT NOT NULL,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            duration_sec REAL DEFAULT 0.0,
            bronze_records INTEGER DEFAULT 0,
            silver_bills INTEGER DEFAULT 0,
            silver_items INTEGER DEFAULT 0,
            zero_price_items INTEGER DEFAULT 0,
            v1_count INTEGER DEFAULT 0,
            v2_count INTEGER DEFAULT 0,
            error_message TEXT
        );
        CREATE TABLE IF NOT EXISTS silver_lock (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            locked_at TEXT NOT NULL,
            process_id INTEGER
        );
    """)
    c.commit()
    return c


def acquire_lock(c):
    now_iso = datetime.now(TZ).isoformat()
    try:
        with c:
            c.execute("INSERT INTO silver_lock (id, locked_at, process_id) VALUES (1, ?, ?)", (now_iso, os.getpid()))
        return True
    except sqlite3.IntegrityError:
        # Check if lock is stale (older than 2 minutes)
        row = c.execute("SELECT locked_at, process_id FROM silver_lock WHERE id = 1").fetchone()
        if row:
            try:
                locked_time = datetime.fromisoformat(row[0])
                if (datetime.now(TZ) - locked_time).total_seconds() > 120:
                    print(f"Clearing stale Silver lock from {row[0]}...", flush=True)
                    with c:
                        c.execute("DELETE FROM silver_lock WHERE id = 1")
                        c.execute("INSERT INTO silver_lock (id, locked_at, process_id) VALUES (1, ?, ?)", (now_iso, os.getpid()))
                    return True
            except Exception:
                pass
        return False


def release_lock(c):
    try:
        with c:
            c.execute("DELETE FROM silver_lock WHERE id = 1")
    except Exception:
        pass


def get_minio_client():
    from minio import Minio
    s3_ep = os.getenv("S3_ENDPOINT", "http://minio:9000")
    endpoint = os.getenv("MINIO_HOST", s3_ep.replace("http://", "").replace("https://", "").rstrip("/"))
    user = os.getenv("MINIO_ROOT_USER", "bakeryadmin")
    password = os.getenv("MINIO_ROOT_PASSWORD", "bakerydemo123")
    is_secure = s3_ep.startswith("https://")
    return Minio(endpoint, access_key=user, secret_key=password, secure=is_secure)


def ensure_silver_bucket_exists():
    try:
        client = get_minio_client()
        silver_bucket = "bakery-silver"
        if not client.bucket_exists(silver_bucket):
            client.make_bucket(silver_bucket)
            print(f"Created MinIO bucket '{silver_bucket}'.", flush=True)
    except Exception as e:
        print(f"Warning checking MinIO bucket: {e}", flush=True)


def check_for_new_bronze_data(c):
    """Fast lightweight check using MinIO client to detect if new Parquet files exist in Bronze."""
    try:
        client = get_minio_client()
        last_processed_str = None
        row = c.execute("SELECT value FROM silver_watermark WHERE key = 'last_processed_bronze_ts'").fetchone()
        if row:
            last_processed_str = row[0]

        # Scan transactions in bronze
        objects = client.list_objects("bakery-bronze", prefix="transactions/", recursive=True)
        latest_mod = None
        for obj in objects:
            if obj.object_name.endswith(".parquet"):
                if latest_mod is None or obj.last_modified > latest_mod:
                    latest_mod = obj.last_modified

        # Also check master menu in bronze
        menu_objects = client.list_objects("bakery-bronze", prefix="master_menu/", recursive=True)
        latest_menu_mod = None
        for obj in menu_objects:
            if obj.object_name.endswith(".parquet"):
                if latest_menu_mod is None or obj.last_modified > latest_menu_mod:
                    latest_menu_mod = obj.last_modified

        overall_latest = latest_mod
        if latest_menu_mod and (overall_latest is None or latest_menu_mod > overall_latest):
            overall_latest = latest_menu_mod

        if overall_latest is None:
            return False, None

        if last_processed_str:
            last_dt = datetime.fromisoformat(last_processed_str)
            if overall_latest <= last_dt:
                return False, overall_latest.isoformat()

        return True, overall_latest.isoformat()

    except Exception as e:
        print(f"MinIO check error, defaulting to run Spark: {e}", flush=True)
        return True, datetime.now(TZ).isoformat()


def run_silver_batch(c, dry_run=False):
    """Execute the Silver incremental batch pipeline."""
    if not acquire_lock(c):
        print("Another Silver batch is currently in progress. Skipping.", flush=True)
        return False

    start_time = time.time()
    batch_id = datetime.now(TZ).strftime("%Y%m%dT%H%M%S") + "_silver"
    now_iso = datetime.now(TZ).isoformat()

    try:
        ensure_silver_bucket_exists()
        has_new, latest_bronze_ts = check_for_new_bronze_data(c)

        if not has_new and not dry_run:
            print(f"[SILVER CHECK] No new data in Bronze since {latest_bronze_ts}. Silver is up to date.", flush=True)
            return False

        print(f"Triggering Silver Batch: {batch_id} (Latest Bronze TS: {latest_bronze_ts})", flush=True)

        if dry_run:
            print(f"DRY RUN: Silver batch {batch_id} would be submitted.", flush=True)
            return True

        with c:
            c.execute("""
                INSERT INTO silver_batches (batch_id, batch_type, status, started_at)
                VALUES (?, 'incremental', 'in_progress', ?)
            """, (batch_id, now_iso))

        spark_submit = os.getenv("SPARK_SUBMIT", "/opt/spark/bin/spark-submit")
        packages = "org.apache.hadoop:hadoop-aws:3.3.4"
        transform_script = os.getenv("SILVER_TRANSFORM_SCRIPT", "/opt/bakery/spark/silver_transform.py")

        cmd = [
            spark_submit,
            "--master", "local[2]",
            "--driver-memory", "2g",
            "--conf", "spark.sql.shuffle.partitions=2",
            "--packages", packages,
            transform_script,
            batch_id,
        ]

        print(f"Running Spark command: {' '.join(cmd)}", flush=True)
        subprocess.run(cmd, check=True)

        duration = round(time.time() - start_time, 2)
        completed_iso = datetime.now(TZ).isoformat()

        with c:
            c.execute("""
                UPDATE silver_batches
                SET status = 'success',
                    completed_at = ?,
                    duration_sec = ?
                WHERE batch_id = ?
            """, (completed_iso, duration, batch_id))

            if latest_bronze_ts:
                c.execute("""
                    INSERT OR REPLACE INTO silver_watermark (key, value, updated_at)
                    VALUES ('last_processed_bronze_ts', ?, ?)
                """, (latest_bronze_ts, completed_iso))

        print(f"SILVER BATCH SUCCESS: {batch_id} in {duration}s", flush=True)
        return True

    except Exception as exc:
        err_msg = str(exc)
        duration = round(time.time() - start_time, 2)
        print(f"SILVER BATCH FAILED: {err_msg}", flush=True)
        with c:
            c.execute("""
                UPDATE silver_batches
                SET status = 'failed',
                    completed_at = ?,
                    duration_sec = ?,
                    error_message = ?
                WHERE batch_id = ?
            """, (datetime.now(TZ).isoformat(), duration, err_msg, batch_id))
        raise

    finally:
        release_lock(c)


def main():
    parser = argparse.ArgumentParser(description="Bakery Data Platform V4: Silver Layer Incremental Batch")
    parser.add_argument("--state", default="/opt/bakery/state/silver_state.sqlite")
    parser.add_argument("--interval", type=int, default=900, help="Batch check interval in seconds (default 900 = 15m)")
    parser.add_argument("--once", action="store_true", help="Run a single incremental batch and exit")
    parser.add_argument("--dry-run", action="store_true", help="Preview check without invoking Spark")
    args = parser.parse_args()

    c = get_db(args.state)
    print(f"SILVER LAYER SCHEDULER STARTED (Interval: {args.interval}s, State: {args.state})", flush=True)

    try:
        # CATCH-UP ON STARTUP: Immediately check and process any backlog
        print("Executing startup catch-up scan for Silver...", flush=True)
        run_silver_batch(c, dry_run=args.dry_run)

        if args.once:
            print("Silver batch execution finished (--once).", flush=True)
            return

        # Daemon scheduler loop: runs every 15 minutes
        while True:
            time.sleep(max(10, args.interval))
            now = datetime.now(TZ)
            print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')} WIB] Checking for new Bronze data...", flush=True)
            try:
                run_silver_batch(c, dry_run=args.dry_run)
            except Exception as e:
                print(f"Error during scheduled Silver batch: {e}", flush=True)

    finally:
        release_lock(c)
        c.close()


if __name__ == "__main__":
    main()
