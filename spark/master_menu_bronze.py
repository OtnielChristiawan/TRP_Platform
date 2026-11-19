"""Write one immutable Master Menu snapshot of raw parsed fields to MinIO Parquet.
Snapshots are append-only, partitioned/organized by snapshot_id, compressed with Snappy.
"""
import os
import sys
from pyspark.sql import SparkSession

spark = (
    SparkSession.builder.appName("bakery-master-menu-snapshot")
    .config("spark.sql.session.timeZone", "Asia/Jakarta")
    .config("spark.hadoop.fs.s3a.endpoint", os.getenv("S3_ENDPOINT", "http://minio:9000"))
    .config("spark.hadoop.fs.s3a.access.key", os.getenv("MINIO_ROOT_USER", "bakeryadmin"))
    .config("spark.hadoop.fs.s3a.secret.key", os.getenv("MINIO_ROOT_PASSWORD", "bakerydemo123"))
    .config("spark.hadoop.fs.s3a.path.style.access", "true")
    .config("spark.hadoop.fs.s3a.connection.ssl.enabled", "false")
    .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")
    .getOrCreate()
)
spark.sparkContext.setLogLevel("WARN")

if len(sys.argv) < 3:
    print("Usage: master_menu_bronze.py <jsonl_path> <snapshot_id>", file=sys.stderr)
    sys.exit(1)

jsonl_path = sys.argv[1]
snapshot_id = sys.argv[2]

df = spark.read.json(jsonl_path)
row_count = df.count()

base_path = os.getenv("MENU_BRONZE_PATH", "s3a://bakery-bronze/master_menu/").rstrip("/")
out_dir = f"{base_path}/snapshot_id={snapshot_id}/"

# Write immutable Parquet snapshot with Snappy compression; errorifexists ensures append-only safety
df.write.mode("errorifexists").option("compression", "snappy").parquet(out_dir)

print(f"Spark Master Menu Bronze WROTE: {out_dir} (rows: {row_count})", flush=True)
spark.stop()
