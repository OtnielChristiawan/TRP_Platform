import os
from pyspark.sql import SparkSession

spark = SparkSession.builder.appName("CheckDates").getOrCreate()
spark.sparkContext.setLogLevel("ERROR")

hconf = spark.sparkContext._jsc.hadoopConfiguration()
hconf.set("fs.s3a.endpoint", "http://minio:9000")
hconf.set("fs.s3a.access.key", os.environ["MINIO_ROOT_USER"])
hconf.set("fs.s3a.secret.key", os.environ["MINIO_ROOT_PASSWORD"])
hconf.set("fs.s3a.path.style.access", "true")
hconf.set("fs.s3a.connection.ssl.enabled", "false")
hconf.set("fs.s3a.aws.credentials.provider", "org.apache.hadoop.fs.s3a.SimpleAWSCredentialsProvider")

df = spark.read.parquet("s3a://bakery-bronze/transactions/")
df.groupBy("source_event_date").count().orderBy("source_event_date").show()
spark.stop()
