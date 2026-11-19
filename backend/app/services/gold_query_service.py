"""Gold Layer analytical query service powered by DuckDB against MinIO Parquet."""
import json
import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import settings
from app.db.duckdb_connection import get_db_manager
from app.schemas.responses import (
    CategoryPerformanceItem,
    DailySalesItem,
    FilterOptionsResponse,
    FreshnessResponse,
    HourlySalesItem,
    PaymentSummaryItem,
    SummaryKPI,
    TopMenuItem,
)

logger = logging.getLogger("bakery.service")

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Asia/Jakarta")
except Exception:
    TZ = timezone(timedelta(hours=7))


def to_float(val: Any) -> float:
    if val is None:
        return 0.0
    return float(val)


def to_int(val: Any) -> int:
    if val is None:
        return 0
    return int(val)


class GoldQueryService:
    def __init__(self):
        self.db = get_db_manager()
        self.bucket = settings.GOLD_BUCKET

    def _parquet_path(self, mart_name: str) -> str:
        return f"s3://{self.bucket}/{mart_name}/**/*.parquet"

    def get_freshness(self) -> FreshnessResponse:
        """Resolve current manifest and determine data freshness."""
        now_str = datetime.now(TZ).isoformat()
        batch_id = None
        published_at = None
        marts_status = {}
        status = "HEALTHY"

        # Try to read manifest via MinIO client or direct S3
        try:
            from minio import Minio
            s3_ep = settings.S3_ENDPOINT.replace("http://", "").replace("https://", "").rstrip("/")
            client = Minio(
                s3_ep,
                access_key=settings.MINIO_ROOT_USER,
                secret_key=settings.MINIO_ROOT_PASSWORD,
                secure=settings.MINIO_SECURE,
            )
            obj = client.get_object(self.bucket, "metadata/current_manifest.json")
            manifest = json.loads(obj.read().decode("utf-8"))
            batch_id = manifest.get("batch_id")
            published_at = manifest.get("published_at")
            marts_status = manifest.get("marts", {})
            status = manifest.get("status", "HEALTHY")
        except Exception as e:
            logger.warning(f"Could not read current_manifest.json: {e}")

        # Query latest transaction date available in gold
        latest_date = None
        try:
            sql = f"""
                SELECT MAX(sales_date) as max_date 
                FROM read_parquet('{self._parquet_path("gold_sales_daily")}', hive_partitioning = true, union_by_name = true)
            """
            rows = self.db.query(sql)
            if rows and rows[0]["max_date"]:
                latest_date = str(rows[0]["max_date"])
        except Exception as e:
            logger.error(f"Error querying max sales date: {e}")

        return FreshnessResponse(
            batch_id=batch_id,
            published_at=published_at,
            latest_transaction_date=latest_date,
            last_refresh_at=now_str,
            status=status,
            marts_status=marts_status,
        )

    def get_filter_options(self) -> FilterOptionsResponse:
        """Fetch distinct filter values (branches, min/max dates, categories, payment methods)."""
        branches = []
        min_date = None
        max_date = None
        categories = []
        payments = []

        try:
            daily_sql = f"""
                SELECT 
                    MIN(sales_date) as min_date,
                    MAX(sales_date) as max_date,
                    LIST(DISTINCT branch ORDER BY branch) as branch_list
                FROM read_parquet('{self._parquet_path("gold_sales_daily")}', hive_partitioning = true, union_by_name = true)
            """
            res = self.db.query(daily_sql)
            if res:
                min_date = str(res[0]["min_date"]) if res[0]["min_date"] else None
                max_date = str(res[0]["max_date"]) if res[0]["max_date"] else None
                raw_branches = res[0].get("branch_list")
                if raw_branches:
                    branches = [str(b) for b in raw_branches if b]
        except Exception as e:
            logger.warning(f"Error fetching daily filter options: {e}")

        try:
            cat_sql = f"""
                SELECT DISTINCT menu_category 
                FROM read_parquet('{self._parquet_path("gold_category_performance_daily")}', hive_partitioning = true, union_by_name = true)
                WHERE menu_category IS NOT NULL
                ORDER BY menu_category
            """
            rows = self.db.query(cat_sql)
            categories = [r["menu_category"] for r in rows if r["menu_category"]]
        except Exception as e:
            logger.warning(f"Error fetching category options: {e}")

        try:
            pay_sql = f"""
                SELECT DISTINCT payment_method 
                FROM read_parquet('{self._parquet_path("gold_payment_daily")}', hive_partitioning = true, union_by_name = true)
                WHERE payment_method IS NOT NULL
                ORDER BY payment_method
            """
            rows = self.db.query(pay_sql)
            payments = [r["payment_method"] for r in rows if r["payment_method"]]
        except Exception as e:
            logger.warning(f"Error fetching payment options: {e}")

        return FilterOptionsResponse(
            branches=branches,
            min_date=min_date,
            max_date=max_date,
            categories=categories,
            payment_methods=payments,
        )

    def get_dashboard_summary(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        branch: Optional[str] = None,
    ) -> SummaryKPI:
        """Calculate KPI summary metrics and optional period-over-period comparison."""
        where_clauses = ["1=1"]
        params: List[Any] = []

        if start_date:
            where_clauses.append("sales_date >= TRY_CAST(? AS DATE)")
            params.append(start_date)
        if end_date:
            where_clauses.append("sales_date <= TRY_CAST(? AS DATE)")
            params.append(end_date)
        if branch:
            where_clauses.append("branch = ?")
            params.append(branch)

        where_stmt = " AND ".join(where_clauses)

        sql = f"""
            SELECT 
                COALESCE(SUM(net_sales), 0) as total_net_sales,
                COALESCE(SUM(gross_sales), 0) as total_gross_sales,
                COALESCE(SUM(total_discount), 0) as total_discount,
                COALESCE(SUM(total_bills), 0) as total_bills,
                COALESCE(SUM(total_qty_sold), 0) as total_qty_sold,
                COALESCE(SUM(total_item_rows), 0) as total_item_rows,
                COALESCE(SUM(zero_price_item_count), 0) as zero_price_item_count,
                MAX(last_updated_at) as last_updated_at
            FROM read_parquet('{self._parquet_path("gold_sales_daily")}', hive_partitioning = true, union_by_name = true)
            WHERE {where_stmt}
        """
        rows = self.db.query(sql, params)
        r = rows[0] if rows else {}

        net_sales = to_float(r.get("total_net_sales"))
        gross_sales = to_float(r.get("total_gross_sales"))
        discount = to_float(r.get("total_discount"))
        bills = to_int(r.get("total_bills"))
        qty = to_float(r.get("total_qty_sold"))
        item_rows = to_int(r.get("total_item_rows"))
        zero_price = to_int(r.get("zero_price_item_count"))
        last_updated = str(r.get("last_updated_at")) if r.get("last_updated_at") else None

        aov = round(net_sales / bills, 2) if bills > 0 else 0.0

        # Calculate comparison with prior period if dates are provided
        prev_net_sales = None
        sales_growth = None
        bills_growth = None

        if start_date and end_date:
            try:
                s_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
                e_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
                delta_days = (e_dt - s_dt).days + 1
                prev_e = s_dt - timedelta(days=1)
                prev_s = prev_e - timedelta(days=delta_days - 1)

                p_where = ["sales_date >= TRY_CAST(? AS DATE)", "sales_date <= TRY_CAST(? AS DATE)"]
                p_params = [prev_s.strftime("%Y-%m-%d"), prev_e.strftime("%Y-%m-%d")]
                if branch:
                    p_where.append("branch = ?")
                    p_params.append(branch)

                prev_sql = f"""
                    SELECT 
                        COALESCE(SUM(net_sales), 0) as prev_net_sales,
                        COALESCE(SUM(total_bills), 0) as prev_bills
                    FROM read_parquet('{self._parquet_path("gold_sales_daily")}', hive_partitioning = true, union_by_name = true)
                    WHERE {" AND ".join(p_where)}
                """
                p_rows = self.db.query(prev_sql, p_params)
                if p_rows:
                    p_net = to_float(p_rows[0].get("prev_net_sales"))
                    p_b = to_int(p_rows[0].get("prev_bills"))
                    if p_net > 0:
                        prev_net_sales = p_net
                        sales_growth = round(((net_sales - p_net) / p_net) * 100.0, 2)
                    if p_b > 0:
                        bills_growth = round(((bills - p_b) / p_b) * 100.0, 2)
            except Exception as exc:
                logger.debug(f"Growth calculation skipped: {exc}")

        return SummaryKPI(
            total_net_sales=net_sales,
            total_gross_sales=gross_sales,
            total_discount=discount,
            total_bills=bills,
            total_qty_sold=qty,
            total_item_rows=item_rows,
            average_order_value=aov,
            zero_price_item_count=zero_price,
            last_updated_at=last_updated,
            previous_period_net_sales=prev_net_sales,
            sales_growth_pct=sales_growth,
            bills_growth_pct=bills_growth,
        )

    def get_daily_sales(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        branch: Optional[str] = None,
    ) -> List[DailySalesItem]:
        """Fetch daily sales timeseries."""
        where_clauses = ["1=1"]
        params: List[Any] = []

        if start_date:
            where_clauses.append("sales_date >= TRY_CAST(? AS DATE)")
            params.append(start_date)
        if end_date:
            where_clauses.append("sales_date <= TRY_CAST(? AS DATE)")
            params.append(end_date)
        if branch:
            where_clauses.append("branch = ?")
            params.append(branch)

        sql = f"""
            SELECT 
                sales_date,
                branch,
                total_bills,
                total_item_rows,
                total_qty_sold,
                gross_sales,
                total_discount,
                net_sales,
                average_order_value,
                zero_price_item_count
            FROM read_parquet('{self._parquet_path("gold_sales_daily")}', hive_partitioning = true, union_by_name = true)
            WHERE {" AND ".join(where_clauses)}
            ORDER BY sales_date ASC, branch ASC
        """
        rows = self.db.query(sql, params)
        results = []
        for r in rows:
            results.append(
                DailySalesItem(
                    sales_date=str(r["sales_date"]),
                    branch=str(r["branch"]),
                    total_bills=to_int(r["total_bills"]),
                    total_item_rows=to_int(r["total_item_rows"]),
                    total_qty_sold=to_float(r["total_qty_sold"]),
                    gross_sales=to_float(r["gross_sales"]),
                    total_discount=to_float(r["total_discount"]),
                    net_sales=to_float(r["net_sales"]),
                    average_order_value=to_float(r["average_order_value"]),
                    zero_price_item_count=to_int(r["zero_price_item_count"]),
                )
            )
        return results

    def get_hourly_sales(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        branch: Optional[str] = None,
    ) -> List[HourlySalesItem]:
        """Fetch hourly distribution aggregated across selected period."""
        where_clauses = ["1=1"]
        params: List[Any] = []

        if start_date:
            where_clauses.append("sales_date >= TRY_CAST(? AS DATE)")
            params.append(start_date)
        if end_date:
            where_clauses.append("sales_date <= TRY_CAST(? AS DATE)")
            params.append(end_date)
        if branch:
            where_clauses.append("branch = ?")
            params.append(branch)

        sql = f"""
            SELECT 
                sales_hour,
                SUM(total_bills) as total_bills,
                SUM(total_item_rows) as total_item_rows,
                SUM(total_qty_sold) as total_qty_sold,
                SUM(gross_sales) as gross_sales,
                SUM(net_sales) as net_sales,
                ROUND(SUM(net_sales) / NULLIF(SUM(total_bills), 0), 2) as average_order_value
            FROM read_parquet('{self._parquet_path("gold_sales_hourly")}', hive_partitioning = true, union_by_name = true)
            WHERE {" AND ".join(where_clauses)}
            GROUP BY sales_hour
            ORDER BY sales_hour ASC
        """
        rows = self.db.query(sql, params)
        results = []
        for r in rows:
            results.append(
                HourlySalesItem(
                    sales_hour=to_int(r["sales_hour"]),
                    total_bills=to_int(r["total_bills"]),
                    total_item_rows=to_int(r["total_item_rows"]),
                    total_qty_sold=to_float(r["total_qty_sold"]),
                    gross_sales=to_float(r["gross_sales"]),
                    net_sales=to_float(r["net_sales"]),
                    average_order_value=to_float(r["average_order_value"]),
                )
            )
        return results

    def get_top_menus(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        branch: Optional[str] = None,
        limit: int = 10,
        sort_by: str = "quantity",
        category: Optional[str] = None,
    ) -> List[TopMenuItem]:
        """Fetch menu performance ranked by quantity or sales."""
        # Sanitize parameters
        sort_col = "SUM(net_sales)" if sort_by.lower() == "sales" else "SUM(qty_sold)"
        safe_limit = max(1, min(limit, 100))

        where_clauses = ["1=1"]
        params: List[Any] = []

        if start_date:
            where_clauses.append("sales_date >= TRY_CAST(? AS DATE)")
            params.append(start_date)
        if end_date:
            where_clauses.append("sales_date <= TRY_CAST(? AS DATE)")
            params.append(end_date)
        if branch:
            where_clauses.append("branch = ?")
            params.append(branch)
        if category:
            where_clauses.append("menu_category = ?")
            params.append(category)

        sql = f"""
            SELECT 
                menu_key,
                menu_name,
                menu_category,
                menu_category_detail,
                SUM(qty_sold) as total_qty,
                SUM(total_bills) as total_bills,
                SUM(gross_sales) as total_gross,
                SUM(net_sales) as total_net,
                SUM(zero_price_qty) as total_zero_qty,
                BOOL_OR(is_master_matched) as is_matched,
                MAX(master_match_status) as match_status
            FROM read_parquet('{self._parquet_path("gold_menu_performance_daily")}', hive_partitioning = true, union_by_name = true)
            WHERE {" AND ".join(where_clauses)}
            GROUP BY menu_key, menu_name, menu_category, menu_category_detail
            ORDER BY {sort_col} DESC
            LIMIT {safe_limit}
        """
        rows = self.db.query(sql, params)
        results = []
        for idx, r in enumerate(rows, start=1):
            results.append(
                TopMenuItem(
                    rank=idx,
                    menu_key=str(r["menu_key"]),
                    menu_name=str(r["menu_name"]),
                    menu_category=str(r["menu_category"]) if r["menu_category"] else None,
                    menu_category_detail=str(r["menu_category_detail"]) if r["menu_category_detail"] else None,
                    qty_sold=to_float(r["total_qty"]),
                    total_bills=to_int(r["total_bills"]),
                    gross_sales=to_float(r["total_gross"]),
                    net_sales=to_float(r["total_net"]),
                    zero_price_qty=to_float(r["total_zero_qty"]),
                    is_master_matched=bool(r["is_matched"]),
                    master_match_status=str(r["match_status"]) if r["match_status"] else "UNMATCHED",
                )
            )
        return results

    def get_category_performance(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        branch: Optional[str] = None,
    ) -> List[CategoryPerformanceItem]:
        """Fetch category performance and calculate contribution %."""
        where_clauses = ["1=1"]
        params: List[Any] = []

        if start_date:
            where_clauses.append("sales_date >= TRY_CAST(? AS DATE)")
            params.append(start_date)
        if end_date:
            where_clauses.append("sales_date <= TRY_CAST(? AS DATE)")
            params.append(end_date)
        if branch:
            where_clauses.append("branch = ?")
            params.append(branch)

        sql = f"""
            WITH cat_totals AS (
                SELECT 
                    COALESCE(menu_category, 'OTHERS') as menu_category,
                    SUM(qty_sold) as qty_sold,
                    SUM(total_bills) as total_bills,
                    SUM(total_item_rows) as total_item_rows,
                    SUM(gross_sales) as gross_sales,
                    SUM(net_sales) as net_sales
                FROM read_parquet('{self._parquet_path("gold_category_performance_daily")}', hive_partitioning = true, union_by_name = true)
                WHERE {" AND ".join(where_clauses)}
                GROUP BY menu_category
            ),
            overall AS (
                SELECT SUM(net_sales) as overall_net FROM cat_totals
            )
            SELECT 
                c.menu_category,
                c.qty_sold,
                c.total_bills,
                c.total_item_rows,
                c.gross_sales,
                c.net_sales,
                ROUND(
                    CASE WHEN o.overall_net > 0 THEN (c.net_sales * 100.0) / o.overall_net ELSE 0.0 END,
                    2
                ) as sales_contribution_pct
            FROM cat_totals c, overall o
            ORDER BY c.net_sales DESC
        """
        rows = self.db.query(sql, params)
        results = []
        for r in rows:
            results.append(
                CategoryPerformanceItem(
                    menu_category=str(r["menu_category"]),
                    qty_sold=to_float(r["qty_sold"]),
                    total_bills=to_int(r["total_bills"]),
                    total_item_rows=to_int(r["total_item_rows"]),
                    gross_sales=to_float(r["gross_sales"]),
                    net_sales=to_float(r["net_sales"]),
                    sales_contribution_pct=to_float(r["sales_contribution_pct"]),
                )
            )
        return results

    def get_payment_summary(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        branch: Optional[str] = None,
    ) -> List[PaymentSummaryItem]:
        """Fetch payment method breakdown from bill-grain gold_payment_daily."""
        where_clauses = ["1=1"]
        params: List[Any] = []

        if start_date:
            where_clauses.append("sales_date >= TRY_CAST(? AS DATE)")
            params.append(start_date)
        if end_date:
            where_clauses.append("sales_date <= TRY_CAST(? AS DATE)")
            params.append(end_date)
        if branch:
            where_clauses.append("branch = ?")
            params.append(branch)

        sql = f"""
            WITH pay_totals AS (
                SELECT 
                    COALESCE(payment_method, 'UNKNOWN') as payment_method,
                    SUM(total_bills) as total_bills,
                    SUM(net_sales) as net_sales
                FROM read_parquet('{self._parquet_path("gold_payment_daily")}', hive_partitioning = true, union_by_name = true)
                WHERE {" AND ".join(where_clauses)}
                GROUP BY payment_method
            ),
            overall AS (
                SELECT SUM(net_sales) as overall_net FROM pay_totals
            )
            SELECT 
                p.payment_method,
                p.total_bills,
                p.net_sales,
                ROUND(
                    CASE WHEN o.overall_net > 0 THEN (p.net_sales * 100.0) / o.overall_net ELSE 0.0 END,
                    2
                ) as payment_contribution_pct
            FROM pay_totals p, overall o
            ORDER BY p.net_sales DESC
        """
        rows = self.db.query(sql, params)
        results = []
        for r in rows:
            results.append(
                PaymentSummaryItem(
                    payment_method=str(r["payment_method"]),
                    total_bills=to_int(r["total_bills"]),
                    net_sales=to_float(r["net_sales"]),
                    payment_contribution_pct=to_float(r["payment_contribution_pct"]),
                )
            )
        return results


_service_instance: Optional[GoldQueryService] = None


def get_gold_service() -> GoldQueryService:
    global _service_instance
    if _service_instance is None:
        _service_instance = GoldQueryService()
    return _service_instance
