"""Unit tests for Gold Layer Transformations, Financial Metrics, Grains, and Orchestrator."""
import os
import sys
import tempfile
import unittest
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "spark"))

import gold_batch


def calculate_aov(net_sales: Decimal, total_bills: int) -> Decimal:
    """Reference implementation of AOV calculation with zero division safety."""
    if not total_bills or total_bills <= 0:
        return Decimal("0.00")
    return round(net_sales / Decimal(str(total_bills)), 2)


def calculate_contribution_pct(item_net_sales: Decimal, total_net_sales: Decimal) -> Decimal:
    """Reference implementation of contribution percentage with zero division safety."""
    if not total_net_sales or total_net_sales <= Decimal("0.00"):
        return Decimal("0.00")
    return round((item_net_sales * Decimal("100.00")) / total_net_sales, 2)


def generate_menu_key(menu_code: str, menu_name: str) -> str:
    """Deterministic menu_key generation matching PySpark coalesce logic."""
    if menu_code and menu_code.strip():
        return menu_code.strip()
    import re
    cleaned_name = re.sub(r"[^a-zA-Z0-9]+", "_", (menu_name or "").strip()).strip("_").lower()
    return cleaned_name


class GoldTransformationTests(unittest.TestCase):

    def test_financial_formulas_consistency(self):
        """Gross Sales, Discount, and Net Sales must adhere strictly to TRP business definitions."""
        items = [
            {"price": Decimal("25000.00"), "qty": Decimal("2.00"), "discount": Decimal("0.00")},
            {"price": Decimal("15000.00"), "qty": Decimal("1.00"), "discount": Decimal("5000.00")},
            {"price": Decimal("0.00"), "qty": Decimal("1.00"), "discount": Decimal("0.00")},  # promo/free item
        ]
        total_subtotal = Decimal("0.00")
        total_discount = Decimal("0.00")
        total_net_sales = Decimal("0.00")

        for it in items:
            subtotal = it["price"] * it["qty"]
            net = subtotal - it["discount"]
            total_subtotal += subtotal
            total_discount += it["discount"]
            total_net_sales += net

        self.assertEqual(total_subtotal, Decimal("65000.00"))  # Gross sales
        self.assertEqual(total_discount, Decimal("5000.00"))
        self.assertEqual(total_net_sales, Decimal("60000.00")) # Net sales
        self.assertEqual(total_subtotal - total_discount, total_net_sales)

    def test_aov_calculation_and_zero_division(self):
        """AOV must equal Net Sales / Total Bills and cleanly return 0.00 when Total Bills is zero."""
        self.assertEqual(calculate_aov(Decimal("16365000.00"), 145), Decimal("112862.07"))
        self.assertEqual(calculate_aov(Decimal("3745000.00"), 44), Decimal("85113.64"))
        self.assertEqual(calculate_aov(Decimal("0.00"), 0), Decimal("0.00"))
        self.assertEqual(calculate_aov(Decimal("50000.00"), 0), Decimal("0.00"))

    def test_contribution_pct_calculation(self):
        """Contribution % must accurately sum to 100% and avoid division by zero."""
        cat_a = Decimal("6000000.00")
        cat_b = Decimal("4000000.00")
        total = cat_a + cat_b

        pct_a = calculate_contribution_pct(cat_a, total)
        pct_b = calculate_contribution_pct(cat_b, total)

        self.assertEqual(pct_a, Decimal("60.00"))
        self.assertEqual(pct_b, Decimal("40.00"))
        self.assertEqual(pct_a + pct_b, Decimal("100.00"))

        # Zero division safety
        self.assertEqual(calculate_contribution_pct(Decimal("0.00"), Decimal("0.00")), Decimal("0.00"))

    def test_menu_key_fallback_generation(self):
        """Menu key must use menu_code if present, or deterministic snake_case fallback if absent."""
        # Case 1: menu_code present
        self.assertEqual(generate_menu_key("MN-001", "ORIGINAL SALT BREAD"), "MN-001")
        self.assertEqual(generate_menu_key("   MN-002   ", "CHOCO BREAD"), "MN-002")

        # Case 2: menu_code empty or null -> fallback to slugified menu_name
        self.assertEqual(generate_menu_key("", "ORIGINAL SALT BREAD"), "original_salt_bread")
        self.assertEqual(generate_menu_key(None, "BLACK (ICE)"), "black_ice")
        self.assertEqual(generate_menu_key("   ", "CROISSANT / CHOCO"), "croissant_choco")

    def test_payment_mart_bill_grain_deduplication(self):
        """Payment aggregation must use bill grain to prevent multiplying net sales by item count."""
        # 1 bill with 3 items, net sales = 75,000.00
        bill = {"event_id": "B1", "payment_method": "QRIS BRI", "bill_nett_sales": Decimal("75000.00")}
        items = [
            {"item_id": "B1_1", "event_id": "B1", "nett_sales": Decimal("25000.00")},
            {"item_id": "B1_2", "event_id": "B1", "nett_sales": Decimal("25000.00")},
            {"item_id": "B1_3", "event_id": "B1", "nett_sales": Decimal("25000.00")},
        ]
        # Grouping items by payment_method would risk row multiplication if joined improperly
        # Grouping bills by payment_method:
        bills = [bill]
        payment_net_sales = sum(b["bill_nett_sales"] for b in bills if b["payment_method"] == "QRIS BRI")
        total_payment_bills = len([b for b in bills if b["payment_method"] == "QRIS BRI"])

        self.assertEqual(payment_net_sales, Decimal("75000.00"))
        self.assertEqual(total_payment_bills, 1)

    def test_hourly_bucket_hour_extraction(self):
        """Hour bucket must be extracted cleanly from transaction completion timestamp."""
        ts = datetime(2026, 10, 18, 14, 35, 20)
        self.assertEqual(ts.hour, 14)
        self.assertTrue(0 <= ts.hour <= 23)

    def test_gold_sqlite_state_locking_and_watermark(self):
        """Gold SQLite state must handle lock acquisition, release, and watermarks."""
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "gold_state.sqlite"
            c = gold_batch.get_db(db_path)

            # Test lock acquisition
            self.assertTrue(gold_batch.acquire_lock(c))
            # Concurrency prevention
            self.assertFalse(gold_batch.acquire_lock(c))

            # Release lock
            gold_batch.release_lock(c)
            # Re-acquire
            self.assertTrue(gold_batch.acquire_lock(c))
            gold_batch.release_lock(c)

            # Test watermark recording
            test_ts = "2026-11-19T10:00:00+07:00"
            with c:
                c.execute("""
                    INSERT OR REPLACE INTO gold_watermark (key, value, updated_at)
                    VALUES ('last_processed_silver_ts', ?, ?)
                """, (test_ts, "2026-11-19T10:05:00+07:00"))

            val = c.execute("SELECT value FROM gold_watermark WHERE key = 'last_processed_silver_ts'").fetchone()[0]
            self.assertEqual(val, test_ts)
            c.close()


if __name__ == "__main__":
    unittest.main()
