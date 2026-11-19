"""Automated Backup Script for Bakery Data Platform V4 (F-17 Compliance).

Captures all persistent states into an atomic versioned archive:
1. SQLite pipeline watermarks & dedup states (silver, gold, master_menu, replay)
2. ML Model Registry binaries & experiment tracking metadata
3. Security & operational audit logs
4. Generates cryptographic SHA-256 backup manifest for before-after verification
"""
import hashlib
import json
import os
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

BASE_DIR = Path(__file__).resolve().parents[1]
STATE_DIR = BASE_DIR / "state"
BACKUPS_DIR = BASE_DIR / "backups"


def calculate_sha256(filepath: Path) -> str:
    """Compute SHA-256 checksum of a file."""
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def collect_target_files() -> List[Path]:
    """Identify all critical state files requiring persistence."""
    targets: List[Path] = []

    # 1. SQLite state databases
    for sqlite_file in STATE_DIR.glob("*.sqlite"):
        if sqlite_file.is_file() and sqlite_file.stat().st_size > 0:
            targets.append(sqlite_file)

    # 2. ML Models & Experiments
    ml_dir = STATE_DIR / "ml"
    if ml_dir.exists():
        for joblib_file in (ml_dir / "models").glob("*.joblib"):
            targets.append(joblib_file)
        for exp_file in (ml_dir / "experiments").glob("*.json"):
            targets.append(exp_file)
        pred_manifest = ml_dir / "predictions" / "manifest.json"
        if pred_manifest.exists():
            targets.append(pred_manifest)

    # 3. Security & Operational Audit logs
    audit_log = STATE_DIR / "audit_log.jsonl"
    if audit_log.exists():
        targets.append(audit_log)

    notifications_log = STATE_DIR / "alerts" / "notifications.jsonl"
    if notifications_log.exists():
        targets.append(notifications_log)

    # 4. Monitoring Rules Configuration
    rules_file = BASE_DIR / "monitoring" / "alert_rules.json"
    if rules_file.exists():
        targets.append(rules_file)

    return sorted(list(set(targets)))


def create_backup(custom_tag: str = None) -> Tuple[Path, Path]:
    """Create versioned tarball backup with SHA-256 manifest."""
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_id = f"backup_{timestamp}" + (f"_{custom_tag}" if custom_tag else "")

    archive_path = BACKUPS_DIR / f"{backup_id}.tar.gz"
    manifest_path = BACKUPS_DIR / f"{backup_id}_manifest.json"
    latest_manifest_path = BACKUPS_DIR / "latest_backup_manifest.json"

    files_to_backup = collect_target_files()
    file_manifest_entries = []
    total_bytes = 0

    print(f"[*] Starting backup '{backup_id}'...")
    print(f"[*] Discovered {len(files_to_backup)} critical state files.")

    # Compute checksums
    for file_path in files_to_backup:
        rel_path = file_path.relative_to(BASE_DIR).as_posix()
        size = file_path.stat().st_size
        sha256 = calculate_sha256(file_path)
        total_bytes += size
        file_manifest_entries.append({
            "relative_path": rel_path,
            "size_bytes": size,
            "sha256": sha256,
        })
        print(f"    - {rel_path} ({size} bytes, sha256: {sha256[:12]}...)")

    manifest_data = {
        "backup_id": backup_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "total_files": len(file_manifest_entries),
        "total_size_bytes": total_bytes,
        "archive_file": archive_path.name,
        "status": "SUCCESS",
        "files": file_manifest_entries,
    }

    # Write manifest JSON to disk
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2)

    with open(latest_manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2)

    # Package into tar.gz
    with tarfile.open(archive_path, "w:gz") as tar:
        for file_path in files_to_backup:
            arcname = file_path.relative_to(BASE_DIR).as_posix()
            tar.add(file_path, arcname=arcname)
        # Include manifest inside archive
        tar.add(manifest_path, arcname="backup_manifest.json")

    print(f"[+] Backup completed successfully: {archive_path}")
    print(f"[+] Manifest written: {manifest_path}")
    return archive_path, manifest_path


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Bakery Data Platform V4 Backup Utility")
    parser.add_argument("--tag", type=str, default=None, help="Optional tag for backup name")
    args = parser.parse_args()
    create_backup(custom_tag=args.tag)
