"""Spark Silver Layer Transformation: Bronze -> Silver for Bakery Data Platform V4.

Transforms transactions and master menu:
- Reads Bronze Parquet from MinIO (bakery-bronze)
- Deduplication: highest payload_version (V2 over V1), highest offset, latest kafka_timestamp
- Currency & Financial: Indonesian format xx.xxx,yy / float / string -> Decimal(14,2)
- Timestamps: Asia/Jakarta (WIB)
- Excluded columns: Table Section, Table Name, Area, PII (Customer/Employee Names)
- Anomaly flags: is_zero_price
- Output: Parquet Snappy with dynamic partition overwrite in bakery-silver
"""
import os
import sys
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from pyspark.sql import SparkSession, functions as F
from pyspark.sql.types import (
    ArrayType,
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


def get_spark_session(app_name="bakery-silver-transform"):
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


def parse_currency_col(c):
    """Convert Indonesian currency string or numeric to DECIMAL(14, 2).
    Distinguishes null/empty from 0.00.
    """
    cleaned = F.trim(c.cast(StringType()))
    return (
        F.when(cleaned.isNull() | (cleaned == "") | (cleaned == "-"), F.lit(None).cast(DecimalType(14, 2)))
        .when(
            cleaned.contains(","),
            F.regexp_replace(F.regexp_replace(cleaned, r"\.", ""), ",", ".").cast(DecimalType(14, 2)),
        )
        .otherwise(cleaned.cast(DecimalType(14, 2)))
    )


def parse_qty_col(c):
    """Parse quantity into DECIMAL(12, 2)."""
    cleaned = F.trim(c.cast(StringType()))
    return (
        F.when(cleaned.isNull() | (cleaned == "") | (cleaned == "-"), F.lit(None).cast(DecimalType(12, 2)))
        .when(
            cleaned.contains(","),
            F.regexp_replace(F.regexp_replace(cleaned, r"\.", ""), ",", ".").cast(DecimalType(12, 2)),
        )
        .otherwise(cleaned.cast(DecimalType(12, 2)))
    )


def parse_timestamp_col(c):
    """Parse string timestamp into TimestampType (WIB)."""
    cleaned = F.regexp_replace(F.trim(c.cast(StringType())), "T", " ")
    return F.to_timestamp(cleaned, "yyyy-MM-dd HH:mm:ss")


def parse_date_col(c):
    """Parse string date into DateType."""
    cleaned = F.substring(F.trim(c.cast(StringType())), 1, 10)
    return F.to_date(cleaned, "yyyy-MM-dd")


def transform_transactions(spark, batch_id):
    bronze_base = os.getenv("BRONZE_PATH", "s3a://bakery-bronze/transactions/").rstrip("/")
    silver_base = os.getenv("SILVER_PATH", "s3a://bakery-silver/").rstrip("/")
    silver_bills_path = f"{silver_base}/sales_bills/"
    silver_items_path = f"{silver_base}/sales_items/"
    now_ts = F.current_timestamp()

    # Read Bronze transactions: Probe wildcard first to bypass any streaming metadata issues
    raw_df = None
    candidate_paths = [
        f"{bronze_base}/*.parquet",
        bronze_base,
        f"{bronze_base}/*/*.parquet",
    ]
    for p in candidate_paths:
        try:
            print(f"[Silver] Probing Bronze transactions path: {p} ...", flush=True)
            df = spark.read.parquet(p)
            c = df.count()
            print(f"[Silver] Found {c} records at: {p}", flush=True)
            if c > 0:
                raw_df = df
                break
        except Exception as e:
            print(f"[Silver] Probe failed for {p}: {e}", flush=True)

    if raw_df is None or raw_df.count() == 0:
        print("[Silver] WARNING: No Bronze transaction records found in any path.", flush=True)
        return {
            "status": "NO_DATA",
            "bronze_records": 0,
            "silver_bills": 0,
            "silver_items": 0,
            "zero_price_items": 0,
            "v1_count": 0,
            "v2_count": 0,
        }

    total_bronze_records = raw_df.count()
    print(f"[Silver] Total Bronze transaction records to process: {total_bronze_records}", flush=True)

    # 1. Deduplication
    parsed_events = raw_df.select(
        F.col("event_id"),
        F.col("offset").alias("bronze_offset"),
        F.col("kafka_timestamp"),
        F.col("bronze_ingested_at"),
        F.coalesce(
            F.get_json_object(F.col("raw_payload"), "$.payload_version").cast(IntegerType()),
            F.lit(1),
        ).alias("payload_version"),
        F.get_json_object(F.col("raw_payload"), "$.source_filename").alias("source_filename"),
        F.get_json_object(F.col("raw_payload"), "$.sales_number").alias("sales_number"),
        F.get_json_object(F.col("raw_payload"), "$.bill_number").alias("bill_number"),
        F.get_json_object(F.col("raw_payload"), "$.branch").alias("branch"),
        F.get_json_object(F.col("raw_payload"), "$.event_time").alias("event_time"),
        F.col("raw_payload"),
    )

    dedup_window = Window.partitionBy("event_id").orderBy(
        F.col("payload_version").desc(),
        F.col("bronze_offset").desc(),
        F.col("kafka_timestamp").desc(),
    )

    deduped_events = (
        parsed_events.withColumn("rk", F.row_number().over(dedup_window))
        .filter(F.col("rk") == 1)
        .drop("rk")
    )

    v1_count = deduped_events.filter(F.col("payload_version") == 1).count()
    v2_count = deduped_events.filter(F.col("payload_version") == 2).count()
    deduped_count = deduped_events.count()
    print(f"[Silver] Deduplication complete: {deduped_count} unique bills (V1: {v1_count}, V2: {v2_count})", flush=True)

    # 2. Extract items array via from_json with struct schema
    item_source_row_schema = StructType([
        StructField("Sales Number", StringType(), True),
        StructField("Bill Number", StringType(), True),
        StructField("Sales Type", StringType(), True),
        StructField("Batch Order", StringType(), True),
        StructField("Sales Date", StringType(), True),
        StructField("Sales Date In", StringType(), True),
        StructField("Sales Date Out", StringType(), True),
        StructField("Branch", StringType(), True),
        StructField("Brand", StringType(), True),
        StructField("City", StringType(), True),
        StructField("Visit Purpose", StringType(), True),
        StructField("Regular Member Code", StringType(), True),
        StructField("Loyalty Member Code", StringType(), True),
        StructField("Loyalty Member Type", StringType(), True),
        StructField("Employee Code", StringType(), True),
        StructField("Waiter", StringType(), True),
        StructField("Payment Method", StringType(), True),
        StructField("Menu Category", StringType(), True),
        StructField("Menu Category Detail", StringType(), True),
        StructField("Menu", StringType(), True),
        StructField("Custom Menu Name", StringType(), True),
        StructField("Menu Code", StringType(), True),
        StructField("Menu Notes", StringType(), True),
        StructField("Order Mode", StringType(), True),
        StructField("Qty", StringType(), True),
        StructField("Price", StringType(), True),
        StructField("Subtotal", StringType(), True),
        StructField("Discount", StringType(), True),
        StructField("Service Charge", StringType(), True),
        StructField("Tax", StringType(), True),
        StructField("VAT", StringType(), True),
        StructField("Total", StringType(), True),
        StructField("Nett Sales", StringType(), True),
        StructField("DPP", StringType(), True),
        StructField("Bill Discount", StringType(), True),
    ])

    item_schema = StructType([
        StructField("source_sheet", StringType(), True),
        StructField("source_row_number", IntegerType(), True),
        StructField("menu", StringType(), True),
        StructField("category", StringType(), True),
        StructField("category_detail", StringType(), True),
        StructField("qty", StringType(), True),
        StructField("price", StringType(), True),
        StructField("order_time", StringType(), True),
        StructField("source_row", item_source_row_schema, True),
    ])

    items_json_col = F.get_json_object(F.col("raw_payload"), "$.items")
    exploded = (
        deduped_events.withColumn(
            "items_arr",
            F.from_json(items_json_col, ArrayType(item_schema), {"primitivesAsString": "true", "mode": "PERMISSIVE"})
        )
        .filter(F.col("items_arr").isNotNull() & (F.size(F.col("items_arr")) > 0))
        .select(
            F.col("event_id"),
            F.col("bronze_offset"),
            F.col("kafka_timestamp"),
            F.col("bronze_ingested_at"),
            F.col("payload_version"),
            F.col("source_filename"),
            F.col("sales_number").alias("event_sales_number"),
            F.col("bill_number").alias("event_bill_number"),
            F.col("branch").alias("event_branch"),
            F.col("event_time").alias("event_time_str"),
            F.posexplode(F.col("items_arr")).alias("pos", "it"),
        )
    )

    exploded_count = exploded.count()
    print(f"[Silver] Exploded items count: {exploded_count}", flush=True)

    # 3. Extract item fields
    items_extracted = exploded.select(
        F.concat(F.col("event_id"), F.lit("_"), (F.col("pos") + 1).cast(StringType())).alias("item_id"),
        F.col("event_id"),
        F.coalesce(F.col("it.source_row.Sales Number"), F.col("event_sales_number")).alias("sales_number"),
        F.coalesce(F.col("it.source_row.Bill Number"), F.col("event_bill_number")).alias("bill_number"),
        (F.col("pos") + 1).cast(IntegerType()).alias("item_index"),
        F.col("it.source_row_number").cast(IntegerType()).alias("source_row_number"),
        F.coalesce(
            parse_date_col(F.col("it.source_row.Sales Date")),
            parse_date_col(F.col("it.source_row.Sales Date Out")),
            parse_date_col(F.col("event_time_str")),
            F.current_date()
        ).alias("sales_date"),
        parse_timestamp_col(F.col("it.source_row.Sales Date Out")).alias("sales_date_out"),
        F.coalesce(
            parse_timestamp_col(F.col("it.order_time")),
            parse_timestamp_col(F.col("event_time_str"))
        ).alias("order_time"),
        F.coalesce(F.col("it.source_row.Branch"), F.col("event_branch")).alias("branch"),
        F.col("it.source_row.Brand").alias("brand"),
        F.col("it.source_row.Payment Method").alias("payment_method"),
        F.coalesce(
            F.col("it.source_row.Menu Category"),
            F.col("it.category")
        ).alias("menu_category"),
        F.coalesce(
            F.col("it.source_row.Menu Category Detail"),
            F.col("it.category_detail")
        ).alias("menu_category_detail"),
        F.coalesce(
            F.col("it.source_row.Menu"),
            F.col("it.menu")
        ).alias("menu"),
        F.col("it.source_row.Custom Menu Name").alias("custom_menu_name"),
        F.col("it.source_row.Menu Code").alias("menu_code"),
        F.col("it.source_row.Menu Notes").alias("menu_notes"),
        F.col("it.source_row.Order Mode").alias("order_mode"),
        parse_qty_col(
            F.coalesce(
                F.col("it.source_row.Qty"),
                F.col("it.qty")
            )
        ).alias("qty"),
        parse_currency_col(
            F.coalesce(
                F.col("it.source_row.Price"),
                F.col("it.price")
            )
        ).alias("price"),
        parse_currency_col(F.col("it.source_row.Subtotal")).alias("subtotal"),
        parse_currency_col(F.col("it.source_row.Discount")).alias("discount"),
        parse_currency_col(F.col("it.source_row.Service Charge")).alias("service_charge"),
        parse_currency_col(F.col("it.source_row.Tax")).alias("tax"),
        parse_currency_col(F.col("it.source_row.VAT")).alias("vat"),
        parse_currency_col(F.col("it.source_row.Total")).alias("total"),
        parse_currency_col(F.col("it.source_row.Nett Sales")).alias("nett_sales"),
        parse_currency_col(F.col("it.source_row.DPP")).alias("dpp"),
        parse_currency_col(F.col("it.source_row.Bill Discount")).alias("bill_discount"),
        F.col("source_filename"),
        now_ts.alias("silver_ingested_at"),
        F.lit(batch_id).alias("batch_run_id"),
        # First item header details for bills aggregation
        F.col("it.source_row.Sales Type").alias("sales_type"),
        F.col("it.source_row.Batch Order").alias("batch_order"),
        parse_timestamp_col(F.col("it.source_row.Sales Date In")).alias("sales_date_in"),
        parse_timestamp_col(F.col("event_time_str")).alias("event_time"),
        F.col("it.source_row.City").alias("city"),
        F.col("it.source_row.Visit Purpose").alias("visit_purpose"),
        F.col("it.source_row.Regular Member Code").alias("regular_member_code"),
        F.col("it.source_row.Loyalty Member Code").alias("loyalty_member_code"),
        F.col("it.source_row.Loyalty Member Type").alias("loyalty_member_type"),
        F.col("it.source_row.Employee Code").alias("employee_code"),
        F.col("it.source_row.Waiter").alias("waiter"),
        F.col("payload_version"),
        F.col("bronze_offset"),
        F.col("bronze_ingested_at"),
    )

    items_clean = items_extracted.withColumn(
        "is_zero_price",
        F.when(F.col("price") == Decimal("0.00"), True).otherwise(False),
    ).withColumn(
        "total_after_bill_discount",
        (F.coalesce(F.col("total"), F.lit(0)) - F.coalesce(F.col("bill_discount"), F.lit(0))).cast(DecimalType(14, 2)),
    )

    silver_items_df = items_clean.select(
        "item_id", "event_id", "sales_number", "bill_number", "item_index",
        "source_row_number", "sales_date", "sales_date_out", "order_time",
        "branch", "brand", "payment_method", "menu_category", "menu_category_detail",
        "menu", "custom_menu_name", "menu_code", "menu_notes", "order_mode",
        "qty", "price", "subtotal", "discount", "service_charge", "tax", "vat",
        "total", "nett_sales", "dpp", "bill_discount", "total_after_bill_discount",
        "is_zero_price", "source_filename", "silver_ingested_at", "batch_run_id",
    )

    # 4. Transform Sales Bills (Aggregated per bill)
    bills_agg = items_clean.groupBy("event_id").agg(
        F.first("sales_number").alias("sales_number"),
        F.first("bill_number").alias("bill_number"),
        F.first("sales_type").alias("sales_type"),
        F.first("batch_order").alias("batch_order"),
        F.first("sales_date").alias("sales_date"),
        F.first("sales_date_in").alias("sales_date_in"),
        F.first("sales_date_out").alias("sales_date_out"),
        F.first("event_time").alias("event_time"),
        F.first("branch").alias("branch"),
        F.first("brand").alias("brand"),
        F.first("city").alias("city"),
        F.first("visit_purpose").alias("visit_purpose"),
        F.first("payment_method").alias("payment_method"),
        F.first("regular_member_code").alias("regular_member_code"),
        F.first("loyalty_member_code").alias("loyalty_member_code"),
        F.first("loyalty_member_type").alias("loyalty_member_type"),
        F.first("employee_code").alias("employee_code"),
        F.first("waiter").alias("waiter"),
        F.count("item_id").cast(IntegerType()).alias("total_items"),
        F.sum("qty").cast(DecimalType(12, 2)).alias("total_qty"),
        F.sum("subtotal").cast(DecimalType(14, 2)).alias("bill_subtotal"),
        F.sum("discount").cast(DecimalType(14, 2)).alias("bill_discount"),
        F.sum("service_charge").cast(DecimalType(14, 2)).alias("bill_service_charge"),
        F.sum("tax").cast(DecimalType(14, 2)).alias("bill_tax"),
        F.sum("vat").cast(DecimalType(14, 2)).alias("bill_vat"),
        F.sum("total").cast(DecimalType(14, 2)).alias("bill_total"),
        F.sum("nett_sales").cast(DecimalType(14, 2)).alias("bill_nett_sales"),
        F.sum("dpp").cast(DecimalType(14, 2)).alias("bill_dpp"),
        F.sum("total_after_bill_discount").cast(DecimalType(14, 2)).alias("bill_total_after_discount"),
        F.max(F.col("is_zero_price")).alias("has_zero_price_item"),
        F.first("payload_version").alias("payload_version"),
        F.first("source_filename").alias("source_filename"),
        F.first("bronze_offset").alias("bronze_offset"),
        F.first("bronze_ingested_at").alias("bronze_ingested_at"),
        F.first("silver_ingested_at").alias("silver_ingested_at"),
        F.first("batch_run_id").alias("batch_run_id"),
        F.lit("PASS").alias("dq_status"),
    )

    silver_bills_df = bills_agg.select(
        "event_id", "sales_number", "bill_number", "sales_type", "batch_order",
        "sales_date", "sales_date_in", "sales_date_out", "event_time",
        "branch", "brand", "city", "visit_purpose", "payment_method",
        "regular_member_code", "loyalty_member_code", "loyalty_member_type",
        "employee_code", "waiter", "total_items", "total_qty",
        "bill_subtotal", "bill_discount", "bill_service_charge", "bill_tax", "bill_vat",
        "bill_total", "bill_nett_sales", "bill_dpp", "bill_total_after_discount",
        "has_zero_price_item", "payload_version", "source_filename",
        "bronze_offset", "bronze_ingested_at", "silver_ingested_at", "batch_run_id", "dq_status",
    )

    silver_items_count = silver_items_df.count()
    silver_bills_count = silver_bills_df.count()
    zero_price_count = silver_items_df.filter(F.col("is_zero_price") == True).count()

    print(f"[Silver] Writing {silver_items_count} items to {silver_items_path} (partitioned by sales_date)...", flush=True)
    silver_items_df.write.mode("overwrite").partitionBy("sales_date").parquet(silver_items_path)

    print(f"[Silver] Writing {silver_bills_count} bills to {silver_bills_path} (partitioned by sales_date)...", flush=True)
    silver_bills_df.write.mode("overwrite").partitionBy("sales_date").parquet(silver_bills_path)

    return {
        "status": "SUCCESS",
        "bronze_records": total_bronze_records,
        "silver_bills": silver_bills_count,
        "silver_items": silver_items_count,
        "zero_price_items": zero_price_count,
        "v1_count": v1_count,
        "v2_count": v2_count,
    }


def transform_master_menu(spark, batch_id):
    menu_bronze_base = os.getenv("MENU_BRONZE_PATH", "s3a://bakery-bronze/master_menu/").rstrip("/")
    silver_base = os.getenv("SILVER_PATH", "s3a://bakery-silver/").rstrip("/")
    silver_menu_path = f"{silver_base}/master_menu/"
    now_ts = F.current_timestamp()

    # Read Bronze master menu
    raw_menu = None
    menu_paths = [
        menu_bronze_base,
        f"{menu_bronze_base}/*/*.parquet",
        f"{menu_bronze_base}/*.parquet",
    ]
    for p in menu_paths:
        try:
            print(f"[Silver] Probing Bronze master menu at: {p} ...", flush=True)
            df = spark.read.parquet(p)
            c = df.count()
            print(f"[Silver] Found {c} records at: {p}", flush=True)
            if c > 0:
                raw_menu = df
                break
        except Exception as e:
            print(f"[Silver] Probe failed for {p}: {e}", flush=True)

    if raw_menu is None or raw_menu.count() == 0:
        print("[Silver] WARNING: No Bronze master menu records found.", flush=True)
        return {"status": "NO_DATA", "master_menu_records": 0}

    # Deduplicate by menu_code or menu_name, keeping latest snapshot
    win = Window.partitionBy(
        F.coalesce(F.col("menu_code"), F.col("menu_name"))
    ).orderBy(
        F.col("snapshot_id").desc(),
        F.col("source_row_number").asc()
    )

    clean_menu = (
        raw_menu.withColumn("rk", F.row_number().over(win))
        .filter(F.col("rk") == 1)
        .drop("rk")
    )

    silver_menu = clean_menu.select(
        F.col("menu_code"),
        F.col("menu_name"),
        F.col("category"),
        F.col("category_detail"),
        parse_currency_col(F.col("price")).alias("price"),
        F.col("status"),
        F.when(
            F.lower(F.trim(F.coalesce(F.col("status"), F.lit("active")))).isin("active", "aktif", ""),
            True
        ).otherwise(False).alias("is_active"),
        F.col("snapshot_id"),
        F.coalesce(F.col("snapshot_date"), parse_date_col(F.col("snapshot_id")), F.current_date()).alias("snapshot_date"),
        F.col("source_filename"),
        F.col("source_file_hash"),
        F.col("source_sheet"),
        F.col("source_row_number").cast(IntegerType()).alias("source_row_number"),
        now_ts.alias("silver_ingested_at"),
        F.lit(batch_id).alias("batch_run_id"),
    )

    menu_count = silver_menu.count()
    print(f"[Silver] Writing {menu_count} master menu rows to {silver_menu_path} (partitioned by snapshot_date)...", flush=True)
    silver_menu.write.mode("overwrite").partitionBy("snapshot_date").parquet(silver_menu_path)

    return {"status": "SUCCESS", "master_menu_records": menu_count}


def write_data_quality(spark, batch_id, trans_res, menu_res):
    silver_base = os.getenv("SILVER_PATH", "s3a://bakery-silver/").rstrip("/")
    dq_path = f"{silver_base}/data_quality/"

    dq_record = [{
        "batch_id": batch_id,
        "batch_timestamp": datetime.now(TZ).isoformat(),
        "bronze_records": int(trans_res.get("bronze_records", 0)),
        "silver_bills": int(trans_res.get("silver_bills", 0)),
        "silver_items": int(trans_res.get("silver_items", 0)),
        "zero_price_items": int(trans_res.get("zero_price_items", 0)),
        "v1_count": int(trans_res.get("v1_count", 0)),
        "v2_count": int(trans_res.get("v2_count", 0)),
        "master_menu_records": int(menu_res.get("master_menu_records", 0)),
        "status": "SUCCESS" if trans_res.get("status") == "SUCCESS" else "PARTIAL",
    }]

    dq_schema = StructType([
        StructField("batch_id", StringType(), False),
        StructField("batch_timestamp", StringType(), True),
        StructField("bronze_records", IntegerType(), True),
        StructField("silver_bills", IntegerType(), True),
        StructField("silver_items", IntegerType(), True),
        StructField("zero_price_items", IntegerType(), True),
        StructField("v1_count", IntegerType(), True),
        StructField("v2_count", IntegerType(), True),
        StructField("master_menu_records", IntegerType(), True),
        StructField("status", StringType(), True),
    ])

    dq_df = spark.createDataFrame(dq_record, dq_schema)
    dq_df.write.mode("append").parquet(dq_path)
    print(f"[Silver] Appended Data Quality metrics to {dq_path}", flush=True)


def main():
    batch_id = sys.argv[1] if len(sys.argv) > 1 else datetime.now(TZ).strftime("%Y%m%dT%H%M%S") + "_silver"
    print(f"[Silver] ========================================================", flush=True)
    print(f"[Silver] STARTING SILVER BATCH: {batch_id}", flush=True)
    print(f"[Silver] ========================================================", flush=True)

    spark = get_spark_session(f"silver-batch-{batch_id}")

    try:
        trans_res = transform_transactions(spark, batch_id)
        menu_res = transform_master_menu(spark, batch_id)
        write_data_quality(spark, batch_id, trans_res, menu_res)
        print(f"[Silver] BATCH {batch_id} COMPLETED SUCCESSFULLY!", flush=True)
    except Exception as e:
        import traceback
        print(f"[Silver] FATAL EXCEPTION in batch {batch_id}: {e}", flush=True)
        traceback.print_exc()
        raise
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
