"""Daily Master Menu snapshot ingestion: archive original + Spark Bronze Parquet.
Run under the batch container; each change creates a distinct snapshot, never overwrites.
"""
import argparse,csv,hashlib,json,os,sqlite3,subprocess,tempfile,time
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
TZ=ZoneInfo('Asia/Jakarta')
REQ={'Menu Name','Menu Category'}
def clean(x):return '' if x is None else str(x).strip()
def hashfile(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def rows(path):
 if path.suffix.lower()=='.xlsx':
  from openpyxl import load_workbook
  wb=load_workbook(path,read_only=True,data_only=True)
  try:
   for ws in wb:
    headers=None
    for r in ws.values:
     if headers is None:
      if REQ.issubset({clean(v) for v in r}):headers=[clean(v) for v in r]
      continue
     if any(clean(v) for v in r):
      d={k:clean(v) for k,v in zip(headers,r) if k}
      if d.get('Menu Name'):yield d
  finally:wb.close()
 else:
  with path.open(encoding='utf-8-sig',newline='') as f:
   reader=csv.reader(f);headers=None
   for r in reader:
    if headers is None:
     if REQ.issubset({clean(v) for v in r}):headers=[clean(v) for v in r]
     continue
    d={k:clean(v) for k,v in zip(headers,r) if k}
    if d.get('Menu Name'):yield d

def db(path):
 path.parent.mkdir(parents=True,exist_ok=True)
 c=sqlite3.connect(path)
 c.execute('CREATE TABLE IF NOT EXISTS snapshots (sha256 TEXT PRIMARY KEY,filename TEXT NOT NULL,snapshot_id TEXT NOT NULL,ingested_at TEXT NOT NULL,row_count INT NOT NULL)')
 c.commit();return c

def ingest(c,path,bronze_bucket,spark_submit,packages):
 from minio import Minio
 digest=hashfile(path)
 if c.execute('SELECT 1 FROM snapshots WHERE sha256=?',(digest,)).fetchone():return False
 entries=list(rows(path))
 if not entries:raise ValueError(f'No Master Menu records in {path}')
 # filename timestamp is not authoritative; use ingestion timestamp + file hash.
 sid=datetime.now(TZ).strftime('%Y%m%dT%H%M%S')+'_'+digest[:12]
 client=Minio(os.environ.get('MINIO_HOST','minio:9000'),access_key=os.environ.get('MINIO_ROOT_USER','bakeryadmin'),secret_key=os.environ.get('MINIO_ROOT_PASSWORD','bakerydemo123'),secure=False)
 if not client.bucket_exists(bronze_bucket):client.make_bucket(bronze_bucket)
 client.fput_object(bronze_bucket,f'originals/master_menu/{sid}/{path.name}',str(path))
 with tempfile.TemporaryDirectory(prefix='menu_') as td:
  input_path=Path(td)/'menu.jsonl'
  with input_path.open('w',encoding='utf-8') as out:
   for n,item in enumerate(entries,1):
    out.write(json.dumps({'snapshot_id':sid,'source_filename':path.name,'source_sha256':digest,'source_row':n,
       'snapshot_ingested_at':datetime.now(TZ).isoformat(),'menu':item},ensure_ascii=False)+'\n')
  cmd=[spark_submit,'--master','local[2]','--driver-memory','2g','--packages',packages,
       '/opt/bakery/spark/master_menu_bronze.py',str(input_path),sid]
  subprocess.run(cmd,check=True)
 with c:c.execute('INSERT INTO snapshots VALUES (?,?,?,?,?)',(digest,path.name,sid,datetime.now(TZ).isoformat(),len(entries)))
 print(f'BATCH SUCCESS {path.name}, rows={len(entries)}, snapshot={sid}',flush=True)
 return True

def main():
 p=argparse.ArgumentParser();p.add_argument('--folder',default='/opt/bakery/data/master_menu/incoming')
 p.add_argument('--state',default='/opt/bakery/state/master_menu.sqlite');p.add_argument('--once',action='store_true')
 p.add_argument('--interval',type=int,default=3600);p.add_argument('--at',default='06:00',help='daily job time WIB')
 args=p.parse_args();c=db(Path(args.state));last_day=None
 spark_submit=os.getenv('SPARK_SUBMIT','/opt/spark/bin/spark-submit')
 packages='org.apache.hadoop:hadoop-aws:3.3.4'
 def process():
  for file in sorted(Path(args.folder).glob('*')):
   if file.suffix.lower() not in ('.xlsx','.csv') or not file.name.startswith('Master Menu Template Data') or file.name.startswith('~$'):continue
   try:ingest(c,file,'bakery-bronze',spark_submit,packages)
   except Exception as exc:print(f'BATCH FAILED {file.name}: {exc}',flush=True) # retry later, no success registry
 try:
  while True:
   now=datetime.now(TZ)
   if args.once or (now.strftime('%H:%M')>=args.at and last_day!=now.date()):
    process();last_day=now.date()
   if args.once:break
   time.sleep(max(10,args.interval))
 finally:c.close()
if __name__=='__main__':main()
