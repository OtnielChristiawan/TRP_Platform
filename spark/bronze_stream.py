"""Kafka -> MinIO s3a Parquet Bronze, append-only raw events with Kafka offsets."""
import os
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, current_timestamp, get_json_object, to_date, to_timestamp

spark = (SparkSession.builder.appName('bakery-esb-bronze-stream')
 .config('spark.sql.session.timeZone','Asia/Jakarta')
 .config('spark.hadoop.fs.s3a.endpoint', os.getenv('S3_ENDPOINT','http://minio:9000'))
 .config('spark.hadoop.fs.s3a.access.key',os.getenv('MINIO_ROOT_USER','bakeryadmin'))
 .config('spark.hadoop.fs.s3a.secret.key',os.getenv('MINIO_ROOT_PASSWORD','bakerydemo123'))
 .config('spark.hadoop.fs.s3a.path.style.access','true')
 .config('spark.hadoop.fs.s3a.connection.ssl.enabled','false')
 .config('spark.hadoop.fs.s3a.impl','org.apache.hadoop.fs.s3a.S3AFileSystem')
 .getOrCreate())
spark.sparkContext.setLogLevel('WARN')

source = (spark.readStream.format('kafka')
    .option('kafka.bootstrap.servers',os.getenv('KAFKA_BOOTSTRAP','redpanda:9092'))
    .option('subscribe',os.getenv('KAFKA_TOPIC','bakery.transactions.v1'))
    .option('startingOffsets','earliest')
    .option('failOnDataLoss','true')
    .load())
bronze = (source.selectExpr('CAST(key AS STRING) AS kafka_key', 'CAST(value AS STRING) AS raw_payload',
                            'topic','partition','offset','timestamp AS kafka_timestamp')
    .withColumn('event_id',get_json_object(col('raw_payload'),'$.event_id'))
    .withColumn('event_time',get_json_object(col('raw_payload'),'$.event_time'))
    .withColumn('bill_number',get_json_object(col('raw_payload'),'$.bill_number'))
    .withColumn('source_event_date',to_date(to_timestamp(col('event_time'))))
    .withColumn('bronze_ingested_at',current_timestamp()))

query=(bronze.writeStream.format('parquet').outputMode('append')
    .option('path',os.getenv('BRONZE_PATH','s3a://bakery-bronze/transactions/'))
    .option('checkpointLocation',os.getenv('CHECKPOINT_PATH','/opt/spark-checkpoints/bakery-bronze'))
    .trigger(processingTime='10 seconds').start())
print('Spark Bronze streaming RUNNING; waiting for Kafka events',flush=True)
query.awaitTermination()
