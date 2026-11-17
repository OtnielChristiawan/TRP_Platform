
import os
from pyspark.sql import SparkSession
from pyspark.sql import functions as F

spark = SparkSession.builder.appName("LihatBronze").getOrCreate()
spark.sparkContext.setLogLevel("ERROR")

hconf = spark.sparkContext._jsc.hadoopConfiguration()
hconf.set("fs.s3a.endpoint", "http://minio:9000")
hconf.set("fs.s3a.access.key", os.environ["MINIO_ROOT_USER"])
hconf.set("fs.s3a.secret.key", os.environ["MINIO_ROOT_PASSWORD"])
hconf.set("fs.s3a.path.style.access", "true")
hconf.set("fs.s3a.connection.ssl.enabled", "false")
hconf.set("fs.s3a.aws.credentials.provider",
          "org.apache.hadoop.fs.s3a.SimpleAWSCredentialsProvider")

df = spark.read.parquet("s3a://bakery-bronze/transactions/")

# Ambil kolom transaksi dari JSON Bronze
tabel = df.select(
    "event_id",
    "bill_number",
    "event_time",
    "bronze_ingested_at",
    "offset",
    F.get_json_object("raw_payload", "$.items").alias("items")
)

print("\n========== TRANSAKSI DI MINIO BRONZE ==========")
print("Total event:", df.count())

# Urutkan menurut waktu transaksi asli
tabel.orderBy(["event_time", "offset"], ascending=[False, False]).show(
    10, truncate=False
)

spark.stop()
