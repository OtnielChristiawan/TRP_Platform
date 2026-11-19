"""Automated Restore & Integrity Verification Script for Bakery Data Platform V4 (F-17 Compliance).

Restores persistent state from a backup archive and performs cryptographic
before-and-after SHA-256 checksum validation to prove zero data corruption.
"""
import hashlib
import json
import os
import tarfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

BASE_DIR = Path(__file__).resolve().parents[1]
BACKUPS_DIR = BASE_DIR / "backups"


def calculate_sha256(filepath: Path) -> str:
    """Compute SHA-256 checksum of a file."""
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def find_latest_backup() -> Tuple[Path, Path]:
    """Identify the most recent backup archive and manifest."""
    latest_manifest = BACKUPS_DIR / "latest_backup_manifest.json"
    if not latest_manifest.exists():
        raise FileNotFoundError(f"No backup manifest found at {latest_manifest}")

    with open(latest_manifest, "r", encoding="utf-8") as f:
        data = json.load(f)

    archive_name = data.get("archive_file")
    archive_path = BACKUPS_DIR / archive_name
    if not archive_path.exists():
        raise FileNotFoundError(f"Backup archive '{archive_path}' referenced in manifest does not exist.")

    return archive_path, latest_manifest


def restore_backup(
    archive_path: Optional[Path] = None,
    manifest_path: Optional[Path] = None,
) -> bool:
    """Extract archive and verify 100% checksum consistency against manifest."""
    if not archive_path or not manifest_path:
        archive_path, manifest_path = find_latest_backup()

    print(f"[*] Restoring from archive: {archive_path.name}")
    print(f"[*] Validating against manifest: {manifest_path.name}")

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    expected_files = {entry["relative_path"]: entry["sha256"] for entry in manifest["files"]}

    # Extract files
    with tarfile.open(archive_path, "r:gz") as tar:
        for member in tar.getmembers():
            if member.name == "backup_manifest.json":
                continue
            tar.extract(member, path=BASE_DIR)

    print(f"[*] Extracted {len(expected_files)} files. Running cryptographic verification...")

    all_matched = True
    verification_results = []

    for rel_path_str, expected_sha in expected_files.items():
        restored_path = BASE_DIR / rel_path_str
        if not restored_path.exists():
            print(f"    [FAIL] Missing restored file: {rel_path_str}")
            all_matched = False
            continue

        actual_sha = calculate_sha256(restored_path)
        is_match = (actual_sha == expected_sha)
        verification_results.append({
            "file": rel_path_str,
            "expected_sha": expected_sha[:12],
            "actual_sha": actual_sha[:12],
            "match": is_match,
        })

        status_tag = "[PASS]" if is_match else "[MISMATCH]"
        print(f"    {status_tag} {rel_path_str} (Expected: {expected_sha[:8]}... | Actual: {actual_sha[:8]}...)")

        if not is_match:
            all_matched = False

    if all_matched:
        print(f"\n[+] RESTORE SUCCESSFUL: All {len(expected_files)} state files match SHA-256 checksums 100%!")
    else:
        print(f"\n[-] RESTORE INTEGRITY COMPROMISED: Some files failed checksum verification.")

    return all_matched


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Bakery Data Platform V4 Restore Utility")
    parser.add_argument("--archive", type=str, default=None, help="Path to specific .tar.gz archive")
    parser.add_argument("--manifest", type=str, default=None, help="Path to specific manifest JSON")
    args = parser.parse_args()

    arch = Path(args.archive) if args.archive else None
    man = Path(args.manifest) if args.manifest else None
    success = restore_backup(archive_path=arch, manifest_path=man)
    exit(0 if success else 1)
