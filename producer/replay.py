"""Lossless-at-field-level replay from ESB XLSX/CSV to Kafka.

One Kafka event per bill; every source row is nested under items[].source_row.
All columns and their original order are retained as source_headers.
To preserve the exact original file bytes, archive the XLSX/CSV separately.

Use a NEW SQLite state and existing Kafka topic for safe backfill. Do not reset old state.
"""
import argparse
import csv
import hashlib
import json
import sqlite3
import time
from datetime import date, datetime, timedelta, time as dtime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Jakarta")
NEEDED = {"Sales Number", "Bill Number", "Sales Date Out", "Menu", "Qty"}


def text(value):
    return "" if value is None else str(value).strip()


def iso_datetime(value):
    if isinstance(value, datetime):
        result = value
    else:
        result = datetime.fromisoformat(" ".join(text(value).split()))
    return result.replace(tzinfo=TZ) if result.tzinfo is None else result.astimezone(TZ)


def json_cell(value):
    """Convert openpyxl values without dropping any column or empty cell."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dtime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def file_hash(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def iter_rows(path):
    """Yield worksheet, 1-based line number, ordered headers and complete row."""
    if path.suffix.lower() == ".xlsx":
        from openpyxl import load_workbook
        workbook = load_workbook(path, read_only=True, data_only=True)
        try:
            for sheet in workbook:
                headers = None
                for line, values in enumerate(sheet.values, 1):
                    values = tuple(values)
                    if headers is None:
                        possible = [text(v) for v in values]
                        if NEEDED.issubset(set(possible)):
                            if len(set(possible)) != len(possible) or not all(possible):
                                raise ValueError(f"{path}:{sheet.title}:{line} duplicate/empty header")
                            headers = possible
                        continue
                    if not any(v is not None and text(v) != "" for v in values):
                        continue
                    padded = list(values[:len(headers)]) + [None] * max(0, len(headers) - len(values))
                    if any(v is not None and text(v) != "" for v in values[len(headers):]):
                        raise ValueError(f"{path}:{sheet.title}:{line} values exceed header width")
                    yield sheet.title, line, headers, dict(zip(headers, (json_cell(v) for v in padded)))
        finally:
            workbook.close()
    elif path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.reader(stream)
            headers = None
            for line, values in enumerate(reader, 1):
                if headers is None:
                    possible = [text(v) for v in values]
                    if NEEDED.issubset(set(possible)):
                        if len(set(possible)) != len(possible) or not all(possible):
                            raise ValueError(f"{path}:{line} duplicate/empty header")
                        headers = possible
                    continue
                if not any(v != "" for v in values):
                    continue
                if len(values) > len(headers):
                    raise ValueError(f"{path}:{line} values exceed header width")
                padded = values + [""] * (len(headers) - len(values))
                yield "CSV", line, headers, dict(zip(headers, padded))
    else:
        raise ValueError(f"Unsupported source format: {path}")


def extract(path):
    bills = {}
    for sheet, line, headers, raw_row in iter_rows(path):
        sales = text(raw_row.get("Sales Number"))
        bill = text(raw_row.get("Bill Number"))
        menu = text(raw_row.get("Menu"))
        if not sales and not bill:
            # ESB reports can contain footer totals outside transaction rows.
            # Preserve exact footer cells in original source archive, not bill event.
            continue
        if not sales or not bill or not menu:
            raise ValueError(f"{path}:{sheet}:{line} missing sales/bill/menu")
        event_time = iso_datetime(raw_row["Sales Date Out"]).isoformat()
        eid = f"{sales}:{bill}"
        if eid not in bills:
            bills[eid] = {
                "event_id": eid,
                "sales_number": sales,
                "bill_number": bill,
                "event_time": event_time,
                "event_type": "sale.completed",
                "payload_version": 2,
                "branch": text(raw_row.get("Branch")),
                "source_file_type": path.suffix.lower().lstrip("."),
                "source_headers": list(headers),
                "items": [],
            }
        event = bills[eid]
        if event["event_time"] != event_time:
            raise ValueError(f"{path}:{sheet}:{line} conflicting event time within bill")
        if event["source_headers"] != headers:
            raise ValueError(f"{path}:{sheet}:{line} inconsistent column layout within bill")
        event["items"].append({
            "source_sheet": sheet,
            "source_row_number": line,
            "menu": menu,
            "category": text(raw_row.get("Menu Category")),
            "category_detail": text(raw_row.get("Menu Category Detail")),
            "qty": text(raw_row.get("Qty")),
            "price": text(raw_row.get("Price")),
            "order_time": text(raw_row.get("Order Time")),
            "source_row": raw_row,  # ALL 46 columns (or actual source headers)
        })
    return bills


def canonical(event):
    # Preserve item order (no sorting) and full field map in source_row.
    return json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def db(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS config(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS files(sha256 TEXT PRIMARY KEY, filename TEXT NOT NULL, scanned_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS events(
            event_id TEXT PRIMARY KEY, content_hash TEXT NOT NULL, payload TEXT NOT NULL,
            source_filename TEXT NOT NULL, scheduled_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending', sent_at TEXT
        );
        CREATE TABLE IF NOT EXISTS conflicts(event_id TEXT, filename TEXT, reason TEXT, detected_at TEXT);
    """)
    connection.commit()
    return connection


def get_anchor(connection, source_date, replay_date):
    old = connection.execute("SELECT value FROM config WHERE key='source_anchor'").fetchone()
    if old:
        replay = connection.execute("SELECT value FROM config WHERE key='replay_anchor'").fetchone()
        if not replay:
            raise RuntimeError("SQLite config missing replay_anchor")
        return date.fromisoformat(old[0]), date.fromisoformat(replay[0])
    source = date.fromisoformat(source_date)
    replay = date.fromisoformat(replay_date)
    with connection:
        connection.execute("INSERT INTO config VALUES('source_anchor',?)", (source.isoformat(),))
        connection.execute("INSERT INTO config VALUES('replay_anchor',?)", (replay.isoformat(),))
    return source, replay


def scheduled_at(when, source, replay):
    timestamp = iso_datetime(when)
    target_date = replay + timedelta(days=(timestamp.date() - source).days)
    return datetime.combine(target_date, timestamp.timetz().replace(tzinfo=None), TZ).isoformat()


def schedule(when, source, replay):
    return datetime.fromisoformat(scheduled_at(when, source, replay))


def scan(connection, folder, prefix, source, replay):
    scanned = new = conflicts = 0
    for path in sorted(folder.glob("*")):
        if not path.is_file() or path.suffix.lower() not in (".csv", ".xlsx"):
            continue
        if not path.name.startswith(prefix) or path.name.startswith("~$"):
            continue
        digest = file_hash(path)
        if connection.execute("SELECT 1 FROM files WHERE sha256=?", (digest,)).fetchone():
            continue
        events = extract(path)
        new_file = conflict_file = 0
        with connection:
            for event in events.values():
                eid = event["event_id"]
                payload = canonical(event)
                h = hashlib.sha256(payload.encode("utf-8")).hexdigest()
                previous = connection.execute("SELECT content_hash FROM events WHERE event_id=?", (eid,)).fetchone()
                if previous:
                    if previous[0] != h:
                        connection.execute("INSERT INTO conflicts VALUES(?,?,?,?)", (
                            eid, path.name, "Bill payload differs across source files", datetime.now(TZ).isoformat()
                        ))
                        conflicts += 1
                        conflict_file += 1
                    continue
                connection.execute("""INSERT INTO events(event_id,content_hash,payload,source_filename,scheduled_at,status)
                                      VALUES(?,?,?,?,?,'pending')""", (
                    eid, h, payload, path.name, scheduled_at(event["event_time"], source, replay)
                ))
                new += 1
                new_file += 1
            connection.execute("INSERT INTO files VALUES(?,?,?)", (digest, path.name, datetime.now(TZ).isoformat()))
        scanned += 1
        print(f"SCANNED {path.name}: bills={len(events)} new={new_file} conflicts={conflict_file}", flush=True)
    return scanned, new, conflicts


def send_due(connection, producer, topic, limit=200):
    now = datetime.now(TZ).isoformat()
    events = connection.execute("""SELECT event_id,payload,scheduled_at,source_filename FROM events
        WHERE status='pending' AND scheduled_at<=? ORDER BY scheduled_at,event_id LIMIT ?""", (now, limit)).fetchall()
    for eid, payload, schedule, filename in events:
        data = json.loads(payload)
        data["replay_scheduled_at"] = schedule
        data["producer_sent_at"] = datetime.now(TZ).isoformat()
        data["source_filename"] = filename
        errors = []
        def ack(error, _message):
            if error:
                errors.append(str(error))
        producer.produce(topic, key=eid.encode(), value=json.dumps(data, ensure_ascii=False).encode(), on_delivery=ack)
        if producer.flush(30) or errors:
            raise RuntimeError(f"Kafka delivery failed for {eid}: {errors}")
        with connection:
            connection.execute("UPDATE events SET status='sent',sent_at=? WHERE event_id=?", (datetime.now(TZ).isoformat(), eid))
        print(f"SENT {eid} scheduled={schedule} rows={len(data['items'])}", flush=True)
    return len(events)


def main():
    parser = argparse.ArgumentParser(description="ESB full-column bill replay")
    parser.add_argument("--folder", default="data/transactions/incoming")
    parser.add_argument("--prefix", default="Sales Recapitulation Detail Report_")
    parser.add_argument("--state", default="state/replay_full_corrected.sqlite")
    parser.add_argument("--source-anchor-date", default="2026-10-18")
    parser.add_argument("--replay-date", default=None)
    parser.add_argument("--interval", type=int, default=15)
    parser.add_argument("--bootstrap", default="localhost:19092")
    parser.add_argument("--topic", default="bakery.transactions.v1")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    connection = db(Path(args.state))
    replay_day = args.replay_date or datetime.now(TZ).date().isoformat()
    source, replay = get_anchor(connection, args.source_anchor_date, replay_day)
    print(f"SOURCE ANCHOR={source} REPLAY ANCHOR={replay} (full-column persistent)", flush=True)
    producer = None
    if not args.dry_run:
        from confluent_kafka import Producer
        producer = Producer({"bootstrap.servers": args.bootstrap, "acks": "all", "enable.idempotence": True})
    try:
        while True:
            scan(connection, Path(args.folder), args.prefix, source, replay)
            if producer:
                send_due(connection, producer, args.topic)
            pending = connection.execute("SELECT COUNT(*) FROM events WHERE status='pending'").fetchone()[0]
            sent = connection.execute("SELECT COUNT(*) FROM events WHERE status='sent'").fetchone()[0]
            print(f"REPLAY pending={pending} sent={sent}", flush=True)
            if args.once:
                break
            time.sleep(max(1, args.interval))
    finally:
        connection.close()


if __name__ == "__main__":
    main()
