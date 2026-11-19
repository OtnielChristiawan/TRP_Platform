"""Daily Master Menu snapshot ingestion: archive original + Spark Bronze Parquet.
Run under the batch container or locally; each change creates a distinct snapshot, never overwrites.
Preserves all source rows, sheets, and columns in Bronze.
"""
import argparse
import csv
import hashlib
import json
import os
import sqlite3
import subprocess
import tempfile
import time
from datetime import date, datetime, time as dtime, timezone, timedelta
from decimal import Decimal
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Asia/Jakarta")
except Exception:
    TZ = timezone(timedelta(hours=7))


def clean(x):
    return "" if x is None else str(x).strip()


def json_cell(value):
    """Lossless conversion of spreadsheet cells to JSON-compatible values."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dtime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (int, float, bool)):
        return value
    if value is None:
        return None
    s = str(value).strip()
    return s if s != "" else None


def hashfile(path):
    """Compute SHA-256 checksum of a file."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def iter_master_rows(path):
    """Yield (sheet_name, line_number, headers, row_dict) for all valid menu items in path.
    Preserves all original columns and their values without alteration or deduplication.
    """
    path = Path(path)
    if path.suffix.lower() == ".xlsx":
        from openpyxl import load_workbook
        wb = load_workbook(path, read_only=True, data_only=True)
        try:
            for ws in wb:
                headers = None
                for line_no, row in enumerate(ws.iter_rows(values_only=True), 1):
                    if headers is None:
                        # Find header row containing Menu Name / Nama Menu
                        if any(clean(v).lower() in ("menu name", "nama menu") for v in row):
                            headers = [clean(v) for v in row]
                        continue
                    if not any(v is not None and clean(v) != "" for v in row):
                        continue
                    padded = list(row[:len(headers)]) + [None] * max(0, len(headers) - len(row))
                    row_dict = {h: json_cell(v) for h, v in zip(headers, padded) if h}
                    # Keep row if it has an identifiable menu name
                    if row_dict.get("Menu Name"):
                        yield ws.title, line_no, headers, row_dict
        finally:
            wb.close()
    elif path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f)
            headers = None
            for line_no, row in enumerate(reader, 1):
                if headers is None:
                    if any(clean(v).lower() in ("menu name", "nama menu") for v in row):
                        headers = [clean(v) for v in row]
                    continue
                if not any(clean(v) != "" for v in row):
                    continue
                padded = list(row[:len(headers)]) + [None] * max(0, len(headers) - len(row))
                row_dict = {h: json_cell(v) for h, v in zip(headers, padded) if h}
                if row_dict.get("Menu Name"):
                    yield "CSV", line_no, headers, row_dict
    else:
        raise ValueError(f"Unsupported file format: {path}")


def rows(path):
    """Backward compatibility helper yielding row dicts with 'Menu Name'."""
    for _sheet, _line, _headers, row_dict in iter_master_rows(path):
        yield row_dict


def db(path):
    """Initialize or connect to the Master Menu SQLite state database."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(path))
    c.execute("PRAGMA journal_mode=WAL")
    c.executescript("""
        CREATE TABLE IF NOT EXISTS snapshots (
            sha256 TEXT PRIMARY KEY,
            filename TEXT NOT NULL,
            snapshot_id TEXT NOT NULL,
            status TEXT NOT NULL,
            row_count INTEGER DEFAULT 0,
            output_path TEXT,
            execution_time_sec REAL DEFAULT 0.0,
            created_at TEXT NOT NULL,
            completed_at TEXT,
            error_message TEXT
        );
    """)
    c.commit()
    return c


def ingest(c, path, bronze_bucket="bakery-bronze", spark_submit=None, packages=None, dry_run=False):
    """Ingest a single Master Menu file into MinIO Bronze Parquet with state tracking."""
    path = Path(path)
    digest = hashfile(path)

    # 1. Idempotency check: skip if already successfully processed
    row = c.execute(
        "SELECT status, snapshot_id, output_path, row_count FROM snapshots WHERE sha256=?",
        (digest,)
    ).fetchone()

    if row and row[0] == "success":
        print(f"ALREADY PROCESSED {path.name}: sha256={digest[:12]} snapshot={row[1]} rows={row[3]}", flush=True)
        return False

    start_time = time.time()
    sid = datetime.now(TZ).strftime("%Y%m%dT%H%M%S") + "_" + digest[:12]
    now_iso = datetime.now(TZ).isoformat()
    snapshot_date = datetime.now(TZ).strftime("%Y-%m-%d")

    # 2. Extract and validate all rows and columns
    records = list(iter_master_rows(path))
    if not records:
        err = f"No valid Master Menu items found in {path.name}"
        with c:
            c.execute("""
                INSERT OR REPLACE INTO snapshots (sha256, filename, snapshot_id, status, created_at, completed_at, error_message)
                VALUES (?, ?, ?, 'failed', ?, ?, ?)
            """, (digest, path.name, sid, now_iso, datetime.now(TZ).isoformat(), err))
        raise ValueError(err)

    if dry_run:
        print(f"DRY RUN SUCCESS {path.name}: sha256={digest[:12]}, rows={len(records)}", flush=True)
        return True

    # 3. Mark state as in_progress
    with c:
        c.execute("""
            INSERT OR REPLACE INTO snapshots (sha256, filename, snapshot_id, status, created_at, error_message)
            VALUES (?, ?, ?, 'in_progress', ?, NULL)
        """, (digest, path.name, sid, now_iso))

    try:
        # 4. Upload immutable original archive to MinIO
        from minio import Minio
        s3_ep = os.environ.get("S3_ENDPOINT", "http://minio:9000")
        minio_endpoint = os.environ.get(
            "MINIO_HOST",
            s3_ep.replace("http://", "").replace("https://", "").rstrip("/")
        )
        minio_user = os.environ.get("MINIO_ROOT_USER", "bakeryadmin")
        minio_password = os.environ.get("MINIO_ROOT_PASSWORD", "bakerydemo123")
        is_secure = s3_ep.startswith("https://")

        client = Minio(minio_endpoint, access_key=minio_user, secret_key=minio_password, secure=is_secure)
        if not client.bucket_exists(bronze_bucket):
            client.make_bucket(bronze_bucket)

        archive_object_name = f"originals/master_menu/{sid}/{path.name}"
        client.fput_object(bronze_bucket, archive_object_name, str(path))

        # 5. Prepare JSONL containing technical metadata and complete raw source payload
        spark_submit = spark_submit or os.getenv("SPARK_SUBMIT", "/opt/spark/bin/spark-submit")
        packages = packages or "org.apache.hadoop:hadoop-aws:3.3.4"

        with tempfile.TemporaryDirectory(prefix="master_menu_") as td:
            input_path = Path(td) / "menu.jsonl"
            with input_path.open("w", encoding="utf-8") as out:
                for sheet, line_no, _headers, item in records:
                    doc = {
                        "snapshot_id": sid,
                        "snapshot_date": snapshot_date,
                        "batch_run_id": sid,
                        "batch_ingested_at": now_iso,
                        "source_filename": path.name,
                        "source_file_hash": digest,
                        "source_sheet": sheet,
                        "source_row_number": line_no,
                        "raw_payload": json.dumps(item, ensure_ascii=False),
                        "menu_name": item.get("Menu Name"),
                        "menu_code": item.get("Menu Code"),
                        "category": item.get("Category") or item.get("Menu Category"),
                        "category_detail": item.get("Category Detail") or item.get("Menu Category Detail"),
                        "price": item.get("Price"),
                        "status": item.get("Status"),
                        "source_row": item,
                    }
                    out.write(json.dumps(doc, ensure_ascii=False) + "\n")

            # 6. Execute Spark Batch ingestion
            spark_script = os.getenv("SPARK_MENU_SCRIPT", "/opt/bakery/spark/master_menu_bronze.py")
            cmd = [
                spark_submit,
                "--master", "local[2]",
                "--driver-memory", "2g",
                "--conf", "spark.sql.shuffle.partitions=2",
                "--packages", packages,
                spark_script,
                str(input_path),
                sid,
            ]
            subprocess.run(cmd, check=True)

        # 7. Verification and status update
        duration = round(time.time() - start_time, 2)
        completed_iso = datetime.now(TZ).isoformat()
        base_out = os.getenv("MENU_BRONZE_PATH", "s3a://bakery-bronze/master_menu/").rstrip("/")
        out_path = f"{base_out}/snapshot_id={sid}/"

        with c:
            c.execute("""
                UPDATE snapshots
                SET status = 'success',
                    row_count = ?,
                    output_path = ?,
                    execution_time_sec = ?,
                    completed_at = ?,
                    error_message = NULL
                WHERE sha256 = ?
            """, (len(records), out_path, duration, completed_iso, digest))

        print(
            f"BATCH SUCCESS {path.name}: rows={len(records)}, snapshot={sid}, duration={duration}s, out={out_path}",
            flush=True
        )
        return True

    except Exception as exc:
        err_msg = str(exc)
        with c:
            c.execute("""
                UPDATE snapshots
                SET status = 'failed',
                    completed_at = ?,
                    error_message = ?
                WHERE sha256 = ?
            """, (datetime.now(TZ).isoformat(), err_msg, digest))
        print(f"BATCH FAILED {path.name}: {err_msg}", flush=True)
        raise


def scan_and_process(c, folder, bronze_bucket, spark_submit, packages, dry_run=False):
    """Scan folder for any new Master Menu files and ingest unprocessed ones."""
    folder = Path(folder)
    if not folder.exists():
        print(f"Incoming folder does not exist: {folder}", flush=True)
        return 0

    processed_count = 0
    for file in sorted(folder.glob("*")):
        if not file.is_file():
            continue
        # Ignore temporary / office lock files and hidden files
        if file.name.startswith(("~$", ".")):
            continue
        # Support both .xlsx and .csv
        if file.suffix.lower() not in (".xlsx", ".csv"):
            continue
        # Match ESB Master Menu export prefixes
        if not file.name.startswith(("Master Menu", "Master Menu Template Data")):
            continue
        # Ensure file is not 0 bytes (e.g. still copying)
        if file.stat().st_size == 0:
            continue

        try:
            did_ingest = ingest(c, file, bronze_bucket, spark_submit, packages, dry_run=dry_run)
            if did_ingest:
                processed_count += 1
        except Exception as exc:
            print(f"BATCH SKIP ON ERROR {file.name}: {exc}", flush=True)

    return processed_count


def main():
    parser = argparse.ArgumentParser(description="ESB Master Menu Batch Ingestion")
    parser.add_argument("--folder", default="/opt/bakery/data/master_menu/incoming")
    parser.add_argument("--state", default="/opt/bakery/state/master_menu.sqlite")
    parser.add_argument("--bucket", default="bakery-bronze")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument("--interval", type=int, default=60, help="Check interval in seconds")
    parser.add_argument("--at", default="06:00", help="Daily job scheduled time in WIB (HH:MM)")
    parser.add_argument("--dry-run", action="store_true", help="Inspect and validate without writing")
    args = parser.parse_args()

    c = db(Path(args.state))
    spark_submit = os.getenv("SPARK_SUBMIT", "/opt/spark/bin/spark-submit")
    packages = "org.apache.hadoop:hadoop-aws:3.3.4"

    print(
        f"MASTER MENU BATCH INITIALIZED (State: {args.state}, Target Time: {args.at} WIB, Interval: {args.interval}s)",
        flush=True
    )

    try:
        # CATCH-UP ON STARTUP: Immediately process any pending or missed files
        print("Executing startup catch-up scan...", flush=True)
        scan_and_process(c, args.folder, args.bucket, spark_submit, packages, dry_run=args.dry_run)

        if args.once:
            print("Batch run completed (--once).", flush=True)
            return

        # Daemon scheduler loop: checks daily at target time (06:00 WIB) and polls for newly dropped files
        last_scheduled_date = None
        now = datetime.now(TZ)
        if now.strftime("%H:%M") >= args.at:
            last_scheduled_date = now.date()

        while True:
            time.sleep(max(5, args.interval))
            now = datetime.now(TZ)
            current_hm = now.strftime("%H:%M")

            # Check if scheduled time arrived for today
            if current_hm >= args.at and last_scheduled_date != now.date():
                print(f"Triggering scheduled daily batch at {now.isoformat()} (Target: {args.at} WIB)", flush=True)
                scan_and_process(c, args.folder, args.bucket, spark_submit, packages, dry_run=args.dry_run)
                last_scheduled_date = now.date()
            else:
                # Also poll incoming folder periodically for newly arrived files
                scan_and_process(c, args.folder, args.bucket, spark_submit, packages, dry_run=args.dry_run)

    finally:
        c.close()


if __name__ == "__main__":
    main()
