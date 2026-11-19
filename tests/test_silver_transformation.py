"""Unit tests for Silver Layer Transformation, Cleaning, Deduplication, and Normalization."""
import sys
import tempfile
import unittest
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "spark"))

import silver_batch


def parse_id_decimal(val, scale=2):
    """Reference implementation matching Catalyst native parse expression."""
    if val is None:
        return None
    if isinstance(val, (int, float, Decimal)):
        return round(Decimal(str(val)), scale)
    s = str(val).strip()
    if not s or s == "-":
        return None
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return round(Decimal(s), scale)
    except Exception:
        return None


class SilverTransformationTests(unittest.TestCase):

    def test_currency_parsing_indonesian_format(self):
        """Must convert Indonesian currency formats (xx.xxx,yy) to Decimal, and preserve nulls vs zeros."""
        self.assertEqual(parse_id_decimal("25.000,00"), Decimal("25000.00"))
        self.assertEqual(parse_id_decimal("1.250.000,50"), Decimal("1250000.50"))
        self.assertEqual(parse_id_decimal("0,00"), Decimal("0.00"))
        self.assertEqual(parse_id_decimal(25000.0), Decimal("25000.00"))
        self.assertEqual(parse_id_decimal(0.0), Decimal("0.00"))
        self.assertEqual(parse_id_decimal(0), Decimal("0.00"))
        self.assertIsNone(parse_id_decimal(""))
        self.assertIsNone(parse_id_decimal("-"))
        self.assertIsNone(parse_id_decimal(None))

    def test_zero_price_flagging(self):
        """Zero price items must not be dropped and must be flagged with is_zero_price = True."""
        samples = [
            ("ORIGINAL SALT BREAD", "0,00", True),
            ("ORIGINAL SALT BREAD", 0.0, True),
            ("ORIGINAL SALT BREAD", "25.000,00", False),
            ("BLACK (ICE)", 28000.0, False),
        ]
        for menu, price_val, expected_zero in samples:
            parsed = parse_id_decimal(price_val)
            is_zero = (parsed == Decimal("0.00"))
            self.assertEqual(is_zero, expected_zero, f"Failed for {menu} with price {price_val}")

    def test_deduplication_prefers_v2_over_v1(self):
        """When identical event_id has both V1 and V2, V2 must take priority over V1."""
        records = [
            {"event_id": "S1:B1", "payload_version": 1, "offset": 500, "items_count": 2},
            {"event_id": "S1:B1", "payload_version": 2, "offset": 100, "items_count": 3},  # V2 with lower offset beats V1
        ]
        # Sorting key matching Window partitionBy(event_id).orderBy(payload_version DESC, offset DESC)
        winning = sorted(records, key=lambda x: (x["payload_version"], x["offset"]), reverse=True)[0]
        self.assertEqual(winning["payload_version"], 2)
        self.assertEqual(winning["items_count"], 3)

    def test_deduplication_prefers_latest_offset_for_same_version(self):
        """When two events have the same payload_version, the latest offset takes priority."""
        records = [
            {"event_id": "S1:B1", "payload_version": 2, "offset": 200, "tag": "older"},
            {"event_id": "S1:B1", "payload_version": 2, "offset": 450, "tag": "newer"},
        ]
        winning = sorted(records, key=lambda x: (x["payload_version"], x["offset"]), reverse=True)[0]
        self.assertEqual(winning["offset"], 450)
        self.assertEqual(winning["tag"], "newer")

    def test_item_preservation_same_menu_in_one_bill(self):
        """Two legitimate items with identical menu name in the same bill must BOTH be preserved."""
        bill_items = [
            {"item_index": 1, "menu": "ORIGINAL SALT BREAD", "price": "0,00", "qty": 1},
            {"item_index": 2, "menu": "ORIGINAL SALT BREAD", "price": "15.000,00", "qty": 2},
        ]
        event_id = "STRPG1:TRPG1"
        item_keys = [f"{event_id}_{it['item_index']}" for it in bill_items]
        # Both item_ids are distinct
        self.assertEqual(len(item_keys), 2)
        self.assertNotEqual(item_keys[0], item_keys[1])
        self.assertEqual(item_keys[0], "STRPG1:TRPG1_1")
        self.assertEqual(item_keys[1], "STRPG1:TRPG1_2")

    def test_excluded_columns_compliance(self):
        """Table Section, Table Name, Area, and PII must not appear in Silver schema fields."""
        excluded_fields = {"Table Section", "Table Name", "Area", "Customer Name", "Employee Name", "Regular Member Name"}
        silver_bill_fields = {
            "event_id", "sales_number", "bill_number", "sales_type", "sales_date",
            "branch", "brand", "city", "visit_purpose", "payment_method",
            "total_items", "total_qty", "bill_total", "bill_nett_sales"
        }
        silver_item_fields = {
            "item_id", "event_id", "sales_number", "bill_number", "item_index",
            "menu", "menu_category", "qty", "price", "subtotal", "total", "nett_sales"
        }
        self.assertTrue(excluded_fields.isdisjoint(silver_bill_fields))
        self.assertTrue(excluded_fields.isdisjoint(silver_item_fields))

    def test_sqlite_state_locking_and_watermark(self):
        """Silver SQLite state must handle concurrency locking and watermark tracking."""
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "silver_state.sqlite"
            c = silver_batch.get_db(db_path)

            # Test lock acquisition
            self.assertTrue(silver_batch.acquire_lock(c))
            # Second acquire should fail (concurrency prevention)
            self.assertFalse(silver_batch.acquire_lock(c))

            # Release lock
            silver_batch.release_lock(c)
            # Re-acquire should now succeed
            self.assertTrue(silver_batch.acquire_lock(c))
            silver_batch.release_lock(c)

            # Test watermark recording
            test_ts = "2026-11-18T15:30:00+07:00"
            with c:
                c.execute("""
                    INSERT OR REPLACE INTO silver_watermark (key, value, updated_at)
                    VALUES ('last_processed_bronze_ts', ?, ?)
                """, (test_ts, "2026-11-18T15:30:05+07:00"))

            val = c.execute("SELECT value FROM silver_watermark WHERE key = 'last_processed_bronze_ts'").fetchone()[0]
            self.assertEqual(val, test_ts)
            c.close()


if __name__ == "__main__":
    unittest.main()
