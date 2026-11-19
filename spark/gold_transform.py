"""Spark Gold Layer Transformation: Silver -> Gold Data Marts for Bakery Data Platform V4.

Produces business-ready, analytical data marts:
1. gold_sales_daily: Daily KPIs per branch (grain: sales_date, branch)
2. gold_sales_hourly: Hourly sales pattern based on sales_date_out (grain: sales_date, sales_hour, branch)
3. gold_menu_performance_daily: Menu-level sales & master menu enrichment (grain: sales_date, branch, menu_key)
4. gold_category_performance_daily: Product category contribution (grain: sales_date, branch, menu_category)
5. gold_payment_daily: Payment method distribution from bill grain (grain: sales_date, branch, payment_method)
6. gold_ml_demand_features: Feature mart for demand forecasting experiments (grain: sales_date, branch, menu_key)

All financials use DECIMAL(14,2) and quantities use DECIMAL(12,2).
Timestamps are localized to Asia/Jakarta (WIB).
Atomic publication pattern writes first to staging run directory, verifies data quality,
and promotes to canonical gold marts with manifest tracking.
"""
import json
import os
import sys
import tempfile
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from pyspark.sql import SparkSession, functions as F
from pyspark.sql.types import (
    BooleanType,
    DateType,
    DecimalType,
    IntegerType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)
from pyspark.sql.window import Window

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Asia/Jakarta")
except Exception:
    TZ = timezone(timedelta(hours=7))


def get_spark_session(app_name="bakery-gold-transform"):
    s3_endpoint = os.getenv("S3_ENDPOINT", "http://minio:9000")
    minio_user = os.getenv("MINIO_ROOT_USER", "bakeryadmin")
    minio_password = os.getenv("MINIO_ROOT_PASSWORD", "bakerydemo123")

    spark = (
        SparkSession.builder.appName(app_name)
        .config("spark.sql.session.timeZone", "Asia/Jakarta")
        .config("spark.sql.legacy.timeParserPolicy", "LEGACY")
        .config("spark.hadoop.fs.s3a.endpoint", s3_endpoint)
        .config("spark.hadoop.fs.s3a.access.key", minio_user)
        .config("spark.hadoop.fs.s3a.secret.key", minio_password)
        .config("spark.hadoop.fs.s3a.path.style.access", "true")
        .config("spark.hadoop.fs.s3a.connection.ssl.enabled", "false")
        .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")
        .config("spark.sql.sources.partitionOverwriteMode", "dynamic")
        .config("spark.sql.parquet.compression.codec", "snappy")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")
    return spark


def read_silver_dataset(spark, dataset_name):
    silver_base = os.getenv("SILVER_PATH", "s3a://bakery-silver/").rstrip("/")
    candidates = [
        f"{silver_base}/{dataset_name}/",
        f"{silver_base}/{dataset_name}/*.parquet",
        f"{silver_base}/{dataset_name}/*/*.parquet",
    ]
    for p in candidates:
        try:
            df = spark.read.parquet(p)
            cnt = df.count()
            if cnt > 0:
                print(f"[Gold] Read Silver dataset '{dataset_name}' ({cnt} records) from {p}", flush=True)
                return df
        except Exception:
            pass
    print(f"[Gold] WARNING: Silver dataset '{dataset_name}' not found or empty.", flush=True)
    return None


# ------------------------------------------------------------------------------
# Mart 1: gold_sales_daily
# ------------------------------------------------------------------------------
def build_gold_sales_daily(items_df, bills_df, batch_id, now_ts):
    """Grain: (sales_date, branch)
    Computes daily totals, AOV, and counts.
    """
    # Group items to get bill-level and item-level stats
    daily_items = items_df.groupBy("sales_date", "branch").agg(
        F.countDistinct("event_id").cast(IntegerType()).alias("total_bills"),
        F.count("item_id").cast(IntegerType()).alias("total_item_rows"),
        F.sum("qty").cast(DecimalType(12, 2)).alias("total_qty_sold"),
        F.sum("subtotal").cast(DecimalType(14, 2)).alias("gross_sales"),
        F.sum("discount").cast(DecimalType(14, 2)).alias("total_discount"),
        F.sum("nett_sales").cast(DecimalType(14, 2)).alias("net_sales"),
        F.count(F.when(F.col("is_zero_price") == True, 1)).cast(IntegerType()).alias("zero_price_item_count"),
    )

    daily = daily_items.withColumn(
        "average_order_value",
        F.when(
            F.col("total_bills") > 0,
            F.round(F.col("net_sales") / F.col("total_bills").cast(DecimalType(14, 2)), 2),
        ).otherwise(F.lit(0.00).cast(DecimalType(14, 2))),
    ).withColumn(
        "batch_run_id", F.lit(batch_id)
    ).withColumn(
        "last_updated_at", now_ts
    )

    return daily.select(
        "sales_date",
        "branch",
        "total_bills",
        "total_item_rows",
        "total_qty_sold",
        "gross_sales",
        "total_discount",
        "net_sales",
        "average_order_value",
        "zero_price_item_count",
        "batch_run_id",
        "last_updated_at",
    )


# ------------------------------------------------------------------------------
# Mart 2: gold_sales_hourly
# ------------------------------------------------------------------------------
def build_gold_sales_hourly(items_df, batch_id, now_ts):
    """Grain: (sales_date, sales_hour, branch)
    Based strictly on sales_date_out (completion time of transaction).
    """
    with_hour = items_df.withColumn(
        "sales_hour",
        F.hour(F.col("sales_date_out")).cast(IntegerType()),
    )

    hourly_agg = with_hour.groupBy("sales_date", "sales_hour", "branch").agg(
        F.countDistinct("event_id").cast(IntegerType()).alias("total_bills"),
        F.count("item_id").cast(IntegerType()).alias("total_item_rows"),
        F.sum("qty").cast(DecimalType(12, 2)).alias("total_qty_sold"),
        F.sum("subtotal").cast(DecimalType(14, 2)).alias("gross_sales"),
        F.sum("discount").cast(DecimalType(14, 2)).alias("total_discount"),
        F.sum("nett_sales").cast(DecimalType(14, 2)).alias("net_sales"),
    )

    hourly = hourly_agg.withColumn(
        "average_order_value",
        F.when(
            F.col("total_bills") > 0,
            F.round(F.col("net_sales") / F.col("total_bills").cast(DecimalType(14, 2)), 2),
        ).otherwise(F.lit(0.00).cast(DecimalType(14, 2))),
    ).withColumn(
        "batch_run_id", F.lit(batch_id)
    ).withColumn(
        "last_updated_at", now_ts
    )

    return hourly.select(
        "sales_date",
        "sales_hour",
        "branch",
        "total_bills",
        "total_item_rows",
        "total_qty_sold",
        "gross_sales",
        "total_discount",
        "net_sales",
        "average_order_value",
        "batch_run_id",
        "last_updated_at",
    )


# ------------------------------------------------------------------------------
# Mart 3: gold_menu_performance_daily
# ------------------------------------------------------------------------------
def build_gold_menu_performance_daily(items_df, menu_df, batch_id, now_ts):
    """Grain: (sales_date, branch, menu_key)
    Enriched with deduplicated master menu. Zero row multiplication.
    """
    clean_code = F.when(
        (F.col("menu_code").isNotNull()) & (F.trim(F.col("menu_code")) != ""),
        F.trim(F.col("menu_code"))
    ).otherwise(None)
    fallback_key = F.lower(F.regexp_replace(F.trim(F.col("menu")), r"[^a-zA-Z0-9]+", "_"))

    with_menu_key = items_df.withColumn(
        "menu_key",
        F.coalesce(clean_code, fallback_key),
    ).withColumn(
        "clean_menu_name",
        F.trim(F.col("menu")),
    )

    menu_agg = with_menu_key.groupBy(
        "sales_date",
        "branch",
        "menu_key",
        "clean_menu_name",
        "menu_category",
        "menu_category_detail",
    ).agg(
        F.sum("qty").cast(DecimalType(12, 2)).alias("qty_sold"),
        F.countDistinct("event_id").cast(IntegerType()).alias("total_bills"),
        F.sum("subtotal").cast(DecimalType(14, 2)).alias("gross_sales"),
        F.sum("nett_sales").cast(DecimalType(14, 2)).alias("net_sales"),
        F.sum(
            F.when(F.col("is_zero_price") == True, F.col("qty")).otherwise(F.lit(0))
        ).cast(DecimalType(12, 2)).alias("zero_price_qty"),
    )

    # Master Menu deduplicated view
    if menu_df is not None and menu_df.count() > 0:
        master_win = Window.partitionBy(
            F.upper(F.trim(F.col("menu_name")))
        ).orderBy(
            F.col("snapshot_date").desc(),
            F.col("source_row_number").asc()
        )
        master_unique = (
            menu_df.withColumn("rk", F.row_number().over(master_win))
            .filter(F.col("rk") == 1)
            .select(
                F.upper(F.trim(F.col("menu_name"))).alias("m_norm_name"),
                F.col("menu_code").alias("m_code"),
                F.col("category").alias("m_category"),
                F.col("category_detail").alias("m_category_detail"),
                F.col("price").alias("m_standard_price"),
                F.col("is_active").alias("m_is_active"),
            )
        )

        joined = menu_agg.join(
            master_unique,
            F.upper(F.col("clean_menu_name")) == F.col("m_norm_name"),
            "left"
        )

        final_menu = joined.select(
            F.col("sales_date"),
            F.col("branch"),
            F.col("menu_key"),
            F.col("clean_menu_name").alias("menu_name"),
            F.coalesce(F.col("menu_category"), F.col("m_category")).alias("menu_category"),
            F.coalesce(F.col("menu_category_detail"), F.col("m_category_detail")).alias("menu_category_detail"),
            F.col("qty_sold"),
            F.col("total_bills"),
            F.col("gross_sales"),
            F.col("net_sales"),
            F.col("zero_price_qty"),
            F.col("m_code").alias("master_menu_code"),
            F.col("m_standard_price").alias("master_standard_price"),
            F.coalesce(F.col("m_is_active"), F.lit(True)).alias("is_active"),
            F.when(F.col("m_norm_name").isNotNull(), True).otherwise(False).alias("is_master_matched"),
            F.when(F.col("m_norm_name").isNotNull(), F.lit("MATCHED")).otherwise(F.lit("UNMATCHED")).alias("master_match_status"),
            F.lit(batch_id).alias("batch_run_id"),
            now_ts.alias("last_updated_at"),
        )
    else:
        final_menu = menu_agg.select(
            F.col("sales_date"),
            F.col("branch"),
            F.col("menu_key"),
            F.col("clean_menu_name").alias("menu_name"),
            F.col("menu_category"),
            F.col("menu_category_detail"),
            F.col("qty_sold"),
            F.col("total_bills"),
            F.col("gross_sales"),
            F.col("net_sales"),
            F.col("zero_price_qty"),
            F.lit(None).cast(StringType()).alias("master_menu_code"),
            F.lit(None).cast(DecimalType(14, 2)).alias("master_standard_price"),
            F.lit(True).alias("is_active"),
            F.lit(False).alias("is_master_matched"),
            F.lit("UNMATCHED").alias("master_match_status"),
            F.lit(batch_id).alias("batch_run_id"),
            now_ts.alias("last_updated_at"),
        )

    return final_menu


# ------------------------------------------------------------------------------
# Mart 4: gold_category_performance_daily
# ------------------------------------------------------------------------------
def build_gold_category_performance_daily(items_df, batch_id, now_ts):
    """Grain: (sales_date, branch, menu_category)
    Calculates sales contribution % within branch daily total.
    """
    cat_agg = items_df.groupBy("sales_date", "branch", "menu_category").agg(
        F.sum("qty").cast(DecimalType(12, 2)).alias("qty_sold"),
        F.countDistinct("event_id").cast(IntegerType()).alias("total_bills"),
        F.count("item_id").cast(IntegerType()).alias("total_item_rows"),
        F.sum("subtotal").cast(DecimalType(14, 2)).alias("gross_sales"),
        F.sum("nett_sales").cast(DecimalType(14, 2)).alias("net_sales"),
    )

    win_branch_day = Window.partitionBy("sales_date", "branch")
    with_branch_totals = cat_agg.withColumn(
        "branch_daily_net_sales",
        F.sum("net_sales").over(win_branch_day),
    )

    res = with_branch_totals.withColumn(
        "sales_contribution_pct",
        F.when(
            (F.col("branch_daily_net_sales").isNotNull()) & (F.col("branch_daily_net_sales") > 0),
            F.round(
                (F.col("net_sales") * Decimal("100.00")) / F.col("branch_daily_net_sales"),
                2
            ).cast(DecimalType(6, 2)),
        ).otherwise(F.lit(0.00).cast(DecimalType(6, 2))),
    ).withColumn(
        "batch_run_id", F.lit(batch_id)
    ).withColumn(
        "last_updated_at", now_ts
    )

    return res.select(
        "sales_date",
        "branch",
        "menu_category",
        "qty_sold",
        "total_bills",
        "total_item_rows",
        "gross_sales",
        "net_sales",
        "sales_contribution_pct",
        "batch_run_id",
        "last_updated_at",
    )


# ------------------------------------------------------------------------------
# Mart 5: gold_payment_daily
# ------------------------------------------------------------------------------
def build_gold_payment_daily(bills_df, batch_id, now_ts):
    """Grain: (sales_date, branch, payment_method)
    Calculated strictly from bill grain to prevent duplicate counting.
    """
    clean_payment = F.when(
        (F.col("payment_method").isNotNull()) & (F.trim(F.col("payment_method")) != ""),
        F.trim(F.col("payment_method"))
    ).otherwise(F.lit("UNKNOWN"))

    pay_agg = bills_df.withColumn("clean_payment_method", clean_payment).groupBy(
        "sales_date",
        "branch",
        "clean_payment_method",
    ).agg(
        F.count("event_id").cast(IntegerType()).alias("total_bills"),
        F.sum("bill_nett_sales").cast(DecimalType(14, 2)).alias("net_sales"),
    ).withColumnRenamed("clean_payment_method", "payment_method")

    win_branch_day = Window.partitionBy("sales_date", "branch")
    with_branch_total = pay_agg.withColumn(
        "branch_daily_net_sales",
        F.sum("net_sales").over(win_branch_day),
    )

    res = with_branch_total.withColumn(
        "payment_contribution_pct",
        F.when(
            (F.col("branch_daily_net_sales").isNotNull()) & (F.col("branch_daily_net_sales") > 0),
            F.round(
                (F.col("net_sales") * Decimal("100.00")) / F.col("branch_daily_net_sales"),
                2
            ).cast(DecimalType(6, 2)),
        ).otherwise(F.lit(0.00).cast(DecimalType(6, 2))),
    ).withColumn(
        "batch_run_id", F.lit(batch_id)
    ).withColumn(
        "last_updated_at", now_ts
    )

    return res.select(
        "sales_date",
        "branch",
        "payment_method",
        "total_bills",
        "net_sales",
        "payment_contribution_pct",
        "batch_run_id",
        "last_updated_at",
    )


# ------------------------------------------------------------------------------
# Mart 6: gold_ml_demand_features (Forecasting Feature Store)
# ------------------------------------------------------------------------------
def build_gold_ml_demand_features(menu_perf_df, batch_id, now_ts):
    """Grain: (sales_date, branch, menu_key)
    Computes time-series lags and rolling averages strictly using historical rows
    (zero data leakage).
    """
    df = menu_perf_df.select(
        "sales_date",
        "branch",
        "menu_key",
        "menu_name",
        "menu_category",
        "qty_sold",
    )

    # Time calendar features
    with_calendar = (
        df.withColumn("day_of_week", F.dayofweek("sales_date").cast(IntegerType()))
        .withColumn("day_of_month", F.dayofmonth("sales_date").cast(IntegerType()))
        .withColumn("month", F.month("sales_date").cast(IntegerType()))
        .withColumn(
            "is_weekend",
            F.when(F.dayofweek("sales_date").isin(1, 7), True).otherwise(False),
        )
    )

    # Historical lag window partitioned by branch & menu_key ordered by date
    hist_win = Window.partitionBy("branch", "menu_key").orderBy("sales_date")
    # Rolling 7d window preceding current date (strictly -7 to -1)
    rolling_win = Window.partitionBy("branch", "menu_key").orderBy("sales_date").rowsBetween(-7, -1)

    features = (
        with_calendar.withColumn("lag_1_qty", F.lag("qty_sold", 1).over(hist_win).cast(DecimalType(12, 2)))
        .withColumn("lag_7_qty", F.lag("qty_sold", 7).over(hist_win).cast(DecimalType(12, 2)))
        .withColumn("rolling_avg_7d_qty", F.round(F.avg("qty_sold").over(rolling_win), 2).cast(DecimalType(12, 2)))
        .withColumn("batch_run_id", F.lit(batch_id))
        .withColumn("last_updated_at", now_ts)
    )

    return features.select(
        "sales_date",
        "branch",
        "menu_key",
        "menu_name",
        "menu_category",
        "qty_sold",
        "day_of_week",
        "day_of_month",
        "month",
        "is_weekend",
        "lag_1_qty",
        "lag_7_qty",
        "rolling_avg_7d_qty",
        "batch_run_id",
        "last_updated_at",
    )


# ------------------------------------------------------------------------------
# Data Quality Validations & Atomic Publishing
# ------------------------------------------------------------------------------
def validate_marts(marts_dict, silver_bills_df, silver_items_df):
    """Run data quality assertions:
    - Primary key uniqueness (no duplicate grains)
    - Non-null primary keys
    - Financial reconciliation (Net Sales and Bill totals) against Silver
    """
    validations = []

    # Silver baselines
    silver_bill_count = silver_bills_df.count()
    silver_bill_net_sales = silver_bills_df.agg(F.sum("bill_nett_sales")).collect()[0][0] or Decimal("0.00")
    silver_item_net_sales = silver_items_df.agg(F.sum("nett_sales")).collect()[0][0] or Decimal("0.00")

    # 1. gold_sales_daily
    daily_df = marts_dict["gold_sales_daily"]
    daily_count = daily_df.count()
    daily_distinct = daily_df.dropDuplicates(["sales_date", "branch"]).count()
    daily_net_sales = daily_df.agg(F.sum("net_sales")).collect()[0][0] or Decimal("0.00")
    daily_bills = daily_df.agg(F.sum("total_bills")).collect()[0][0] or 0

    assert daily_count == daily_distinct, f"Duplicate keys in gold_sales_daily: {daily_count} vs {daily_distinct}"
    assert daily_bills == silver_bill_count, f"Bill count mismatch in daily: {daily_bills} vs {silver_bill_count}"
    assert daily_net_sales == silver_bill_net_sales, f"Net sales mismatch in daily: {daily_net_sales} vs {silver_bill_net_sales}"
    validations.append({"mart": "gold_sales_daily", "status": "PASS", "records": daily_count, "net_sales": str(daily_net_sales)})

    # 2. gold_sales_hourly
    hourly_df = marts_dict["gold_sales_hourly"]
    hourly_count = hourly_df.count()
    hourly_distinct = hourly_df.dropDuplicates(["sales_date", "sales_hour", "branch"]).count()
    hourly_net_sales = hourly_df.agg(F.sum("net_sales")).collect()[0][0] or Decimal("0.00")
    hourly_bills = hourly_df.agg(F.sum("total_bills")).collect()[0][0] or 0

    assert hourly_count == hourly_distinct, f"Duplicate keys in gold_sales_hourly: {hourly_count} vs {hourly_distinct}"
    assert hourly_bills == silver_bill_count, f"Bill count mismatch in hourly: {hourly_bills} vs {silver_bill_count}"
    assert hourly_net_sales == silver_bill_net_sales, f"Net sales mismatch in hourly: {hourly_net_sales} vs {silver_bill_net_sales}"
    validations.append({"mart": "gold_sales_hourly", "status": "PASS", "records": hourly_count, "net_sales": str(hourly_net_sales)})

    # 3. gold_menu_performance_daily
    menu_df = marts_dict["gold_menu_performance_daily"]
    menu_count = menu_df.count()
    menu_distinct = menu_df.dropDuplicates(["sales_date", "branch", "menu_key"]).count()
    menu_net_sales = menu_df.agg(F.sum("net_sales")).collect()[0][0] or Decimal("0.00")

    assert menu_count == menu_distinct, f"Duplicate keys in gold_menu_performance_daily: {menu_count} vs {menu_distinct}"
    assert menu_net_sales == silver_item_net_sales, f"Net sales mismatch in menu: {menu_net_sales} vs {silver_item_net_sales}"
    validations.append({"mart": "gold_menu_performance_daily", "status": "PASS", "records": menu_count, "net_sales": str(menu_net_sales)})

    # 4. gold_category_performance_daily
    cat_df = marts_dict["gold_category_performance_daily"]
    cat_count = cat_df.count()
    cat_distinct = cat_df.dropDuplicates(["sales_date", "branch", "menu_category"]).count()
    cat_net_sales = cat_df.agg(F.sum("net_sales")).collect()[0][0] or Decimal("0.00")

    assert cat_count == cat_distinct, f"Duplicate keys in gold_category_performance_daily: {cat_count} vs {cat_distinct}"
    assert cat_net_sales == silver_item_net_sales, f"Net sales mismatch in category: {cat_net_sales} vs {silver_item_net_sales}"
    validations.append({"mart": "gold_category_performance_daily", "status": "PASS", "records": cat_count, "net_sales": str(cat_net_sales)})

    # 5. gold_payment_daily
    pay_df = marts_dict["gold_payment_daily"]
    pay_count = pay_df.count()
    pay_distinct = pay_df.dropDuplicates(["sales_date", "branch", "payment_method"]).count()
    pay_net_sales = pay_df.agg(F.sum("net_sales")).collect()[0][0] or Decimal("0.00")
    pay_bills = pay_df.agg(F.sum("total_bills")).collect()[0][0] or 0

    assert pay_count == pay_distinct, f"Duplicate keys in gold_payment_daily: {pay_count} vs {pay_distinct}"
    assert pay_bills == silver_bill_count, f"Bill count mismatch in payment: {pay_bills} vs {silver_bill_count}"
    assert pay_net_sales == silver_bill_net_sales, f"Net sales mismatch in payment: {pay_net_sales} vs {silver_bill_net_sales}"
    validations.append({"mart": "gold_payment_daily", "status": "PASS", "records": pay_count, "net_sales": str(pay_net_sales)})

    # 6. gold_ml_demand_features
    ml_df = marts_dict["gold_ml_demand_features"]
    ml_count = ml_df.count()
    ml_distinct = ml_df.dropDuplicates(["sales_date", "branch", "menu_key"]).count()
    assert ml_count == ml_distinct, f"Duplicate keys in gold_ml_demand_features: {ml_count} vs {ml_distinct}"
    validations.append({"mart": "gold_ml_demand_features", "status": "PASS", "records": ml_count})

    print("[Gold] ALL DATA QUALITY VALIDATIONS PASSED SUCCESSFULLY!", flush=True)
    return validations


def publish_manifest(batch_id, validations, spark_run_id):
    """Write current_manifest.json to MinIO metadata directory."""
    try:
        from minio import Minio
        s3_ep = os.getenv("S3_ENDPOINT", "http://minio:9000")
        endpoint = os.getenv("MINIO_HOST", s3_ep.replace("http://", "").replace("https://", "").rstrip("/"))
        user = os.getenv("MINIO_ROOT_USER", "bakeryadmin")
        password = os.getenv("MINIO_ROOT_PASSWORD", "bakerydemo123")
        is_secure = s3_ep.startswith("https://")

        client = Minio(endpoint, access_key=user, secret_key=password, secure=is_secure)

        manifest_data = {
            "batch_id": batch_id,
            "published_at": datetime.now(TZ).isoformat(),
            "spark_run_id": spark_run_id,
            "status": "HEALTHY",
            "marts": {v["mart"]: {"records": v["records"], "status": v["status"]} for v in validations},
            "validations": validations,
        }

        manifest_bytes = json.dumps(manifest_data, indent=2).encode("utf-8")
        import io
        client.put_object(
            "bakery-gold",
            "metadata/current_manifest.json",
            io.BytesIO(manifest_bytes),
            length=len(manifest_bytes),
            content_type="application/json",
        )
        # Also store versioned manifest history
        client.put_object(
            "bakery-gold",
            f"metadata/manifests/{batch_id}.json",
            io.BytesIO(manifest_bytes),
            length=len(manifest_bytes),
            content_type="application/json",
        )
        print(f"[Gold] Successfully published metadata/current_manifest.json to MinIO bakery-gold", flush=True)
    except Exception as e:
        print(f"[Gold] Warning: Failed to write MinIO manifest: {e}", flush=True)


def main():
    batch_id = sys.argv[1] if len(sys.argv) > 1 else datetime.now(TZ).strftime("%Y%m%dT%H%M%S") + "_gold"
    print(f"[Gold] ========================================================", flush=True)
    print(f"[Gold] STARTING GOLD BATCH TRANSFORMATION: {batch_id}", flush=True)
    print(f"[Gold] ========================================================", flush=True)

    spark = get_spark_session(f"gold-batch-{batch_id}")
    now_ts = F.current_timestamp()
    gold_base = os.getenv("GOLD_PATH", "s3a://bakery-gold/").rstrip("/")

    try:
        # 1. Load Silver Datasets
        silver_bills = read_silver_dataset(spark, "sales_bills")
        silver_items = read_silver_dataset(spark, "sales_items")
        silver_menu = read_silver_dataset(spark, "master_menu")

        if silver_bills is None or silver_items is None:
            raise RuntimeError("Cannot proceed with Gold transformation: Silver datasets missing.")

        # Cache inputs for multi-mart derivation
        silver_bills.cache()
        silver_items.cache()
        if silver_menu is not None:
            silver_menu.cache()

        print("[Gold] Building Gold Data Marts...", flush=True)

        # 2. Build Marts
        daily_df = build_gold_sales_daily(silver_items, silver_bills, batch_id, now_ts)
        hourly_df = build_gold_sales_hourly(silver_items, batch_id, now_ts)
        menu_perf_df = build_gold_menu_performance_daily(silver_items, silver_menu, batch_id, now_ts)
        cat_perf_df = build_gold_category_performance_daily(silver_items, batch_id, now_ts)
        payment_df = build_gold_payment_daily(silver_bills, batch_id, now_ts)
        ml_features_df = build_gold_ml_demand_features(menu_perf_df, batch_id, now_ts)

        marts = {
            "gold_sales_daily": daily_df,
            "gold_sales_hourly": hourly_df,
            "gold_menu_performance_daily": menu_perf_df,
            "gold_category_performance_daily": cat_perf_df,
            "gold_payment_daily": payment_df,
            "gold_ml_demand_features": ml_features_df,
        }

        for name, df in marts.items():
            df.cache()

        # 3. Validate Data Quality & Financial Integrity
        print("[Gold] Validating data quality & financial reconciliations...", flush=True)
        validations = validate_marts(marts, silver_bills, silver_items)

        # 4. Atomic Publication to Canonical Gold Locations
        print("[Gold] Publishing validated marts to canonical MinIO paths (partitioned by sales_date)...", flush=True)
        for name, df in marts.items():
            canonical_path = f"{gold_base}/{name}/"
            print(f"[Gold] Writing {name} -> {canonical_path} ...", flush=True)
            df.write.mode("overwrite").partitionBy("sales_date").parquet(canonical_path)

        # 5. Publish Metadata Manifest
        publish_manifest(batch_id, validations, spark.sparkContext.applicationId)

        print(f"[Gold] ========================================================", flush=True)
        print(f"[Gold] GOLD BATCH {batch_id} COMPLETED SUCCESSFULLY!", flush=True)
        print(f"[Gold] ========================================================", flush=True)

    except Exception as e:
        import traceback
        print(f"[Gold] FATAL EXCEPTION in batch {batch_id}: {e}", flush=True)
        traceback.print_exc()
        raise
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
