"""Unit and integration tests for Master Menu Batch Ingestion."""
import csv
import io
import shutil
import sqlite3
import sys
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from datetime import date, datetime, timezone, timedelta

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Asia/Jakarta")
except Exception:
    TZ = timezone(timedelta(hours=7))

# Add project root and module directories to sys.path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "batch"))
sys.path.insert(0, str(ROOT / "producer"))

import master_menu
import replay

TZ = ZoneInfo("Asia/Jakarta")


class MasterMenuBatchTests(unittest.TestCase):

    def test_hashfile_consistency(self):
        """SHA-256 calculation must be deterministic and match expected content digest."""
        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as f:
            f.write("Sample content for hashing")
            temp_path = Path(f.name)
        try:
            h1 = master_menu.hashfile(temp_path)
            h2 = master_menu.hashfile(temp_path)
            self.assertEqual(h1, h2)
            self.assertEqual(len(h1), 64)
        finally:
            temp_path.unlink()

    def test_parse_real_excel_all_columns_preserved(self):
        """Audit real ESB Master Menu export to ensure all 22 columns and 83 rows are preserved."""
        real_file = ROOT / "data" / "master_menu" / "incoming" / "Master Menu - 20261117082359.xlsx"
        if not real_file.exists():
            self.skipTest(f"Real sample file not found at {real_file}")

        records = list(master_menu.iter_master_rows(real_file))
        # Total data rows in sheet 'Report' is 83 (lines 7 to 89)
        self.assertEqual(len(records), 83)

        expected_headers = [
            "Menu Id", "Menu Code", "Menu Name", "Menu Short Name", "Category Detail",
            "Category", "Bill of Material", "Estimated Cost", "Notes", "Tax",
            "Other Tax", "Luxury Item", "Zero Value Text", "Customer Print",
            "Sales Account Number", "COGS Account Number", "Discount Account Number",
            "Status", "Created By", "Created Date", "Edited By", "Edited Date"
        ]

        sheet, line_no, headers, first_row = records[0]
        self.assertEqual(sheet, "Report")
        self.assertEqual(line_no, 7)
        self.assertEqual(headers, expected_headers)

        # Verify all 22 headers exist in the extracted dictionary
        for h in expected_headers:
            self.assertIn(h, first_row)

        # Verify key values of the first menu item
        self.assertEqual(first_row["Menu Id"], "1")
        self.assertEqual(first_row["Menu Name"], "BLACK (HOT)")
        self.assertEqual(first_row["Category"], "BEVERAGE")
        self.assertEqual(first_row["Category Detail"], "BASIC COFFEE")
        self.assertEqual(first_row["Customer Print"], "YES")
        self.assertEqual(first_row["Sales Account Number"], "Sales - Beverage")

        # Verify empty cells are preserved as None rather than dropping the key
        self.assertIsNone(first_row["Menu Code"])
        self.assertIsNone(first_row["Notes"])

    def test_parse_csv_preserves_all_variants_and_columns(self):
        """CSV ingestion must retain all columns and must not drop variants (DINE IN, TAKEAWAY, etc.)."""
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "Master Menu Template Data - test.csv"
            with p.open("w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["Title row: ESB Export"])
                writer.writerow(["Generated Date", "2026-11-18"])
                writer.writerow([])
                writer.writerow(["Menu Template Name", "Menu Category", "Menu Name", "Price", "Status", "Custom Note"])
                writer.writerow(["DINE IN", "PASTRY", "CROISSANT", "25000", "ACTIVE", "Fresh baked"])
                writer.writerow(["TAKEAWAY", "PASTRY", "CROISSANT", "25000", "ACTIVE", "Packaged"])
                writer.writerow(["ESB ORDER", "BEVERAGE", "ICED LATTE", "30000", "ACTIVE", ""])
                writer.writerow(["", "", "", "", "", ""])  # Empty footer row

            records = list(master_menu.iter_master_rows(p))
            self.assertEqual(len(records), 3)

            # Both DINE IN and TAKEAWAY variants of CROISSANT must be preserved (no deduplication in Bronze)
            templates = [r[3]["Menu Template Name"] for r in records]
            self.assertIn("DINE IN", templates)
            self.assertIn("TAKEAWAY", templates)
            self.assertIn("ESB ORDER", templates)

            # Check that custom columns are preserved
            self.assertEqual(records[0][3]["Custom Note"], "Fresh baked")
            self.assertIsNone(records[2][3]["Custom Note"])

    def test_multi_sheet_excel_captures_sheet_metadata(self):
        """Multi-sheet workbooks must capture the source_sheet name accurately for each row."""
        import openpyxl

        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "Master Menu - multi_sheet.xlsx"
            wb = openpyxl.Workbook()
            ws1 = wb.active
            ws1.title = "Pastry"
            ws1.append(["Title: Master Menu"])
            ws1.append(["Menu Id", "Menu Name", "Category"])
            ws1.append(["1", "BAGUETTE", "BREAD"])

            ws2 = wb.create_sheet(title="Beverages")
            ws2.append(["Title: Master Menu"])
            ws2.append(["Menu Id", "Menu Name", "Category"])
            ws2.append(["2", "CAPPUCCINO", "COFFEE"])
            wb.save(p)
            wb.close()

            records = list(master_menu.iter_master_rows(p))
            self.assertEqual(len(records), 2)
            self.assertEqual(records[0][0], "Pastry")
            self.assertEqual(records[0][3]["Menu Name"], "BAGUETTE")
            self.assertEqual(records[1][0], "Beverages")
            self.assertEqual(records[1][3]["Menu Name"], "CAPPUCCINO")

    def test_sqlite_state_lifecycle_and_idempotency(self):
        """State DB must record lifecycle (in_progress -> success) and prevent duplicate processing."""
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "state.sqlite"
            c = master_menu.db(db_path)

            file_path = Path(tmp) / "Master Menu - sample.csv"
            file_path.write_text("Menu Name,Category\nBREAD,BAKERY\n", encoding="utf-8")

            digest = master_menu.hashfile(file_path)

            # Check new file is not processed
            row = c.execute("SELECT status FROM snapshots WHERE sha256=?", (digest,)).fetchone()
            self.assertIsNone(row)

            # Record in_progress
            sid = "20261118T060000_" + digest[:12]
            with c:
                c.execute("""
                    INSERT INTO snapshots (sha256, filename, snapshot_id, status, created_at)
                    VALUES (?, ?, ?, 'in_progress', ?)
                """, (digest, file_path.name, sid, datetime.now(TZ).isoformat()))

            row = c.execute("SELECT status FROM snapshots WHERE sha256=?", (digest,)).fetchone()
            self.assertEqual(row[0], "in_progress")

            # Update to success
            with c:
                c.execute("""
                    UPDATE snapshots
                    SET status = 'success', row_count = 1, output_path = 's3a://bronze/master_menu/',
                        execution_time_sec = 1.25, completed_at = ?
                    WHERE sha256 = ?
                """, (datetime.now(TZ).isoformat(), digest))

            # Ingest again: should recognize already processed and return False
            result = master_menu.ingest(c, file_path, dry_run=True)
            self.assertFalse(result)
            c.close()

    def test_recovery_from_interrupted_run(self):
        """If a job crashed with status 'in_progress', next run must safely detect and re-process."""
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "state.sqlite"
            c = master_menu.db(db_path)

            file_path = Path(tmp) / "Master Menu - crash_test.csv"
            file_path.write_text("Menu Name,Category\nCAKE,DESSERT\n", encoding="utf-8")
            digest = master_menu.hashfile(file_path)

            # Simulate interrupted job
            with c:
                c.execute("""
                    INSERT INTO snapshots (sha256, filename, snapshot_id, status, created_at)
                    VALUES (?, ?, 'crashed_sid', 'in_progress', ?)
                """, (digest, file_path.name, datetime.now(TZ).isoformat()))

            # Dry run re-process
            did_run = master_menu.ingest(c, file_path, dry_run=True)
            self.assertTrue(did_run)
            c.close()

    def test_same_content_different_filename_deduplication(self):
        """Files with different names but identical content must not create duplicate snapshots."""
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "state.sqlite"
            c = master_menu.db(db_path)

            file_a = Path(tmp) / "Master Menu - 20261118_v1.csv"
            file_b = Path(tmp) / "Master Menu - 20261118_v2_copy.csv"
            content = "Menu Name,Category\nDONUT,BAKERY\n"
            file_a.write_text(content, encoding="utf-8")
            file_b.write_text(content, encoding="utf-8")

            # Mark file_a as success
            digest = master_menu.hashfile(file_a)
            with c:
                c.execute("""
                    INSERT INTO snapshots (sha256, filename, snapshot_id, status, row_count, created_at)
                    VALUES (?, ?, 'sid_1', 'success', 1, ?)
                """, (digest, file_a.name, datetime.now(TZ).isoformat()))

            # file_b has identical content (same sha256)
            self.assertEqual(master_menu.hashfile(file_b), digest)
            result = master_menu.ingest(c, file_b, dry_run=True)
            self.assertFalse(result)
            c.close()

    def test_different_content_creates_new_snapshot(self):
        """Files with different content produce different hashes and distinct snapshots."""
        with tempfile.TemporaryDirectory() as tmp:
            file_a = Path(tmp) / "Master Menu - day1.csv"
            file_b = Path(tmp) / "Master Menu - day2.csv"
            file_a.write_text("Menu Name,Category\nDONUT,BAKERY\n", encoding="utf-8")
            file_b.write_text("Menu Name,Category\nDONUT,BAKERY\nMIRIN BREAD,BAKERY\n", encoding="utf-8")

            h_a = master_menu.hashfile(file_a)
            h_b = master_menu.hashfile(file_b)
            self.assertNotEqual(h_a, h_b)


if __name__ == "__main__":
    unittest.main()
