"""Lightweight Gold Layer Incremental Scheduler & Orchestrator.
- Manages SQLite state at state/gold_state.sqlite
- Prevents concurrent executions with SQLite locking (gold_lock)
- Checks MinIO for new Silver data without booting heavy Spark context if idle
- Invokes Spark batch incremental transformation when new data is detected
- Supports --once (manual run / backfill) and --interval 1800 (30-min daemon loop)
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
        CREATE TABLE IF NOT EXISTS gold_watermark (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS gold_batches (
            batch_id TEXT PRIMARY KEY,
            batch_type TEXT NOT NULL,
            status TEXT NOT NULL,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            duration_sec REAL DEFAULT 0.0,
            gold_sales_daily_rows INTEGER DEFAULT 0,
            gold_sales_hourly_rows INTEGER DEFAULT 0,
            gold_menu_perf_rows INTEGER DEFAULT 0,
            gold_cat_perf_rows INTEGER DEFAULT 0,
            gold_payment_rows INTEGER DEFAULT 0,
            gold_ml_features_rows INTEGER DEFAULT 0,
            error_message TEXT
        );
        CREATE TABLE IF NOT EXISTS gold_lock (
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
            c.execute("INSERT INTO gold_lock (id, locked_at, process_id) VALUES (1, ?, ?)", (now_iso, os.getpid()))
        return True
    except sqlite3.IntegrityError:
        # Check if lock is stale (older than 3 minutes)
        row = c.execute("SELECT locked_at, process_id FROM gold_lock WHERE id = 1").fetchone()
        if row:
            try:
                locked_time = datetime.fromisoformat(row[0])
                if (datetime.now(TZ) - locked_time).total_seconds() > 180:
                    print(f"Clearing stale Gold lock from {row[0]}...", flush=True)
                    with c:
                        c.execute("DELETE FROM gold_lock WHERE id = 1")
                        c.execute("INSERT INTO gold_lock (id, locked_at, process_id) VALUES (1, ?, ?)", (now_iso, os.getpid()))
                    return True
            except Exception:
                pass
        return False


def release_lock(c):
    try:
        with c:
            c.execute("DELETE FROM gold_lock WHERE id = 1")
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


def ensure_gold_bucket_exists():
    try:
        client = get_minio_client()
        gold_bucket = "bakery-gold"
        if not client.bucket_exists(gold_bucket):
            client.make_bucket(gold_bucket)
            print(f"Created MinIO bucket '{gold_bucket}'.", flush=True)
    except Exception as e:
        print(f"Warning checking MinIO bucket: {e}", flush=True)


def check_for_new_silver_data(c):
    """Fast lightweight check using MinIO client to detect if new Parquet files exist in Silver."""
    try:
        client = get_minio_client()
        last_processed_str = None
        row = c.execute("SELECT value FROM gold_watermark WHERE key = 'last_processed_silver_ts'").fetchone()
        if row:
            last_processed_str = row[0]

        # Scan sales_bills and sales_items in silver
        latest_mod = None
        for prefix in ["sales_bills/", "sales_items/", "master_menu/"]:
            objects = client.list_objects("bakery-silver", prefix=prefix, recursive=True)
            for obj in objects:
                if obj.object_name.endswith(".parquet"):
                    if latest_mod is None or obj.last_modified > latest_mod:
                        latest_mod = obj.last_modified

        if latest_mod is None:
            return False, None

        if last_processed_str:
            last_dt = datetime.fromisoformat(last_processed_str)
            if latest_mod <= last_dt:
                return False, latest_mod.isoformat()

        return True, latest_mod.isoformat()

    except Exception as e:
        print(f"MinIO check error, defaulting to run Spark: {e}", flush=True)
        return True, datetime.now(TZ).isoformat()


def run_gold_batch(c, dry_run=False, force=False):
    """Execute the Gold batch pipeline."""
    if not acquire_lock(c):
        print("Another Gold batch is currently in progress. Skipping.", flush=True)
        return False

    start_time = time.time()
    batch_id = datetime.now(TZ).strftime("%Y%m%dT%H%M%S") + "_gold"
    now_iso = datetime.now(TZ).isoformat()

    try:
        ensure_gold_bucket_exists()
        has_new, latest_silver_ts = check_for_new_silver_data(c)

        if not has_new and not force and not dry_run:
            print(f"[GOLD CHECK] No new data in Silver since {latest_silver_ts}. Gold is up to date.", flush=True)
            return False

        print(f"Triggering Gold Batch: {batch_id} (Latest Silver TS: {latest_silver_ts}, Force: {force})", flush=True)

        if dry_run:
            print(f"DRY RUN: Gold batch {batch_id} would be submitted.", flush=True)
            return True

        with c:
            c.execute("""
                INSERT INTO gold_batches (batch_id, batch_type, status, started_at)
                VALUES (?, 'batch', 'in_progress', ?)
            """, (batch_id, now_iso))

        spark_submit = os.getenv("SPARK_SUBMIT", "/opt/spark/bin/spark-submit")
        packages = "org.apache.hadoop:hadoop-aws:3.3.4"
        transform_script = os.getenv("GOLD_TRANSFORM_SCRIPT", "/opt/bakery/spark/gold_transform.py")

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
                UPDATE gold_batches
                SET status = 'success',
                    completed_at = ?,
                    duration_sec = ?
                WHERE batch_id = ?
            """, (completed_iso, duration, batch_id))

            if latest_silver_ts:
                c.execute("""
                    INSERT OR REPLACE INTO gold_watermark (key, value, updated_at)
                    VALUES ('last_processed_silver_ts', ?, ?)
                """, (latest_silver_ts, completed_iso))

        print(f"GOLD BATCH SUCCESS: {batch_id} in {duration}s", flush=True)
        return True

    except Exception as exc:
        err_msg = str(exc)
        duration = round(time.time() - start_time, 2)
        print(f"GOLD BATCH FAILED: {err_msg}", flush=True)
        with c:
            c.execute("""
                UPDATE gold_batches
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
    parser = argparse.ArgumentParser(description="Bakery Data Platform V4: Gold Layer Batch Orchestrator")
    parser.add_argument("--state", default="/opt/bakery/state/gold_state.sqlite")
    parser.add_argument("--interval", type=int, default=1200, help="Batch check interval in seconds (default 1200 = 20m)")
    parser.add_argument("--once", action="store_true", help="Run a single batch and exit")
    parser.add_argument("--force", action="store_true", help="Force rebuild even if no new Silver data")
    parser.add_argument("--dry-run", action="store_true", help="Preview check without invoking Spark")
    args = parser.parse_args()

    c = get_db(args.state)
    print(f"GOLD LAYER SCHEDULER STARTED (Interval: {args.interval}s, State: {args.state})", flush=True)

    try:
        # CATCH-UP ON STARTUP: Immediately check and process any backlog
        print("Executing startup scan for Gold (force=True)...", flush=True)
        run_gold_batch(c, dry_run=args.dry_run, force=args.force or True)

        if args.once:
            print("Gold batch execution finished (--once).", flush=True)
            return

        # Daemon scheduler loop: runs every 30 minutes
        while True:
            time.sleep(max(10, args.interval))
            now = datetime.now(TZ)
            print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')} WIB] Checking for new Silver data...", flush=True)
            try:
                run_gold_batch(c, dry_run=args.dry_run, force=False)
            except Exception as e:
                print(f"Error during scheduled Gold batch: {e}", flush=True)

    finally:
        release_lock(c)
        c.close()


if __name__ == "__main__":
    main()
