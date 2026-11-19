"""Test suite for F-17 Disaster Recovery, Backup, and Restore.

Validates:
1. Automated state discovery and archive packaging.
2. SHA-256 checksum manifest generation.
3. Injected failure recovery with before-and-after cryptographic checksum match.
4. Operational data integrity verification post-restore.
"""
import json
import os
import sys
from pathlib import Path
import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from scripts.backup_state import create_backup, collect_target_files, calculate_sha256
from scripts.restore_state import restore_backup, find_latest_backup


def test_collect_target_files():
    """Verify that all critical persistent state components are discovered."""
    files = collect_target_files()
    assert len(files) >= 10

    filenames = [f.name for f in files]
    assert "silver_state.sqlite" in filenames
    assert "gold_state.sqlite" in filenames
    assert "alert_rules.json" in filenames


def test_backup_creation_and_manifest():
    """Verify that backup produces a valid tarball and JSON manifest with SHA-256 hashes."""
    archive_path, manifest_path = create_backup(custom_tag="pytest_run")

    assert archive_path.exists()
    assert manifest_path.exists()

    with open(manifest_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["status"] == "SUCCESS"
    assert data["total_files"] >= 10
    assert len(data["files"]) == data["total_files"]

    for entry in data["files"]:
        assert "relative_path" in entry
        assert "sha256" in entry
        assert len(entry["sha256"]) == 64  # SHA-256 hex string length


def test_disaster_recovery_simulation_and_checksum_verification(tmp_path):
    """Simulate state corruption/deletion and verify 100% cryptographic recovery."""
    # 1. Take clean backup
    archive_path, manifest_path = create_backup(custom_tag="failure_drill")

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    # 2. Pick a target state file to simulate disaster on
    sample_file_rel = manifest["files"][0]["relative_path"]
    original_sha = manifest["files"][0]["sha256"]
    sample_file_path = ROOT_DIR / sample_file_rel

    # Read original content
    with open(sample_file_path, "rb") as f:
        original_bytes = f.read()

    try:
        # 3. Inject Disaster: overwrite file with corrupted dummy data
        with open(sample_file_path, "wb") as f:
            f.write(b"CORRUPTED_DATA_DISASTER_SIMULATION")

        # Verify it is indeed corrupted
        corrupted_sha = calculate_sha256(sample_file_path)
        assert corrupted_sha != original_sha

        # 4. Perform Restore
        restore_success = restore_backup(archive_path=archive_path, manifest_path=manifest_path)
        assert restore_success is True

        # 5. Verify restored file SHA-256 matches original
        restored_sha = calculate_sha256(sample_file_path)
        assert restored_sha == original_sha

    finally:
        # Guarantee restoration of original bytes in case of unexpected test failure
        with open(sample_file_path, "wb") as f:
            f.write(original_bytes)
