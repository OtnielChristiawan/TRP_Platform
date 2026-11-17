"""Write one immutable menu snapshot of raw parsed fields to MinIO Parquet."""
import os,sys
from pyspark.sql import SparkSession
from pyspark.sql.functions import col
sp=(SparkSession.builder.appName('bakery-menu-snapshot')
 .config('spark.hadoop.fs.s3a.endpoint',os.getenv('S3_ENDPOINT','http://minio:9000'))
 .config('spark.hadoop.fs.s3a.access.key',os.getenv('MINIO_ROOT_USER','bakeryadmin'))
 .config('spark.hadoop.fs.s3a.secret.key',os.getenv('MINIO_ROOT_PASSWORD','bakerydemo123'))
 .config('spark.hadoop.fs.s3a.path.style.access','true')
 .config('spark.hadoop.fs.s3a.connection.ssl.enabled','false').getOrCreate())
path,snapshot=sys.argv[1:3]
df=sp.read.json(path)
# menu is a MAP/STRUCT containing original ESB column values; no product upsert in Bronze.
out=os.getenv('MENU_BRONZE_PATH','s3a://bakery-bronze/master_menu/')+'snapshot_id='+snapshot+'/'
df.write.mode('errorifexists').parquet(out)
print('WROTE',out,df.count(),flush=True);sp.stop()
