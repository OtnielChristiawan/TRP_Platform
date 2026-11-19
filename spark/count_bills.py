import os
from pyspark.sql import SparkSession

spark = SparkSession.builder.appName("CountBills").getOrCreate()
spark.sparkContext.setLogLevel("ERROR")

hconf = spark.sparkContext._jsc.hadoopConfiguration()
hconf.set("fs.s3a.endpoint", "http://minio:9000")
hconf.set("fs.s3a.access.key", os.environ["MINIO_ROOT_USER"])
hconf.set("fs.s3a.secret.key", os.environ["MINIO_ROOT_PASSWORD"])
hconf.set("fs.s3a.path.style.access", "true")
hconf.set("fs.s3a.connection.ssl.enabled", "false")
hconf.set("fs.s3a.aws.credentials.provider", "org.apache.hadoop.fs.s3a.SimpleAWSCredentialsProvider")

df = spark.read.parquet("s3a://bakery-bronze/transactions/")
print("================ RESULT ================")
print("TOTAL ROWS IN BRONZE:", df.count())
print("DISTINCT BILLS IN BRONZE:", df.select("bill_number").distinct().count())
print("MIN BILL:", df.selectExpr("min(bill_number)").collect()[0][0])
print("MAX BILL:", df.selectExpr("max(bill_number)").collect()[0][0])
print("========================================")
spark.stop()
