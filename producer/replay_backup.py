"""ESB multi-file XLSX/CSV watcher -> durable SQLite replay queue -> Kafka.
Immutable source files. One Kafka record per bill, containing all item rows.
"""
import argparse, csv, hashlib, json, sqlite3, time
from datetime import datetime, date, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from decimal import Decimal
TZ=ZoneInfo('Asia/Jakarta')
NEEDED={'Sales Number','Bill Number','Sales Date Out','Menu','Qty'}

def s(x): return '' if x is None else str(x).strip()
def dt(x):
    if isinstance(x,datetime): return x.replace(tzinfo=TZ) if x.tzinfo is None else x.astimezone(TZ)
    t=datetime.fromisoformat(' '.join(s(x).split()))
    return t.replace(tzinfo=TZ) if t.tzinfo is None else t.astimezone(TZ)
def num(x):
    if isinstance(x,(int,float,Decimal)): return str(Decimal(str(x)))
    v=s(x).replace(' ','')
    if not v: return '0'
    return str(Decimal(v.replace('.','').replace(',','.') if ',' in v else v))
def file_hash(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def iter_rows(path):
    if path.suffix.lower()=='.xlsx':
        from openpyxl import load_workbook
        wb=load_workbook(path,read_only=True,data_only=True)
        try:
            for ws in wb:
                header=None
                for line,values in enumerate(ws.values,1):
                    a=[s(v) for v in values]
                    if header is None:
                        if NEEDED.issubset(set(a)): header=a
                        continue
                    if any(s(v) for v in values): yield line,dict(zip(header,values))
        finally:wb.close()
    else:
        with path.open('r',encoding='utf-8-sig',newline='') as f:
            r=csv.reader(f); header=None
            for line,values in enumerate(r,1):
                a=[s(v) for v in values]
                if header is None:
                    if NEEDED.issubset(set(a)):header=a
                    continue
                if any(s(v) for v in values):yield line,dict(zip(header,values))
def extract(path):
    bills={}
    for n,row in iter_rows(path):
        sales=s(row.get('Sales Number')); bill=s(row.get('Bill Number')); menu=s(row.get('Menu'))
        if not sales and not bill:continue
        if not sales or not bill or not menu:raise ValueError(f'{path}:{n} missing sales/bill/menu')
        key=f'{sales}:{bill}'; event_time=dt(row['Sales Date Out']).isoformat()
        if key not in bills:
            bills[key]={'event_id':key,'sales_number':sales,'bill_number':bill,'event_time':event_time,
                        'event_type':'sale.completed','payload_version':1,'branch':s(row.get('Branch')),'items':[]}
        event=bills[key]
        if event['event_time']!=event_time:raise ValueError(f'{path}:{n} conflicting bill event_time')
        event['items'].append({'menu':menu,'category':s(row.get('Menu Category')),
          'category_detail':s(row.get('Menu Category Detail')),'qty':num(row.get('Qty')),
          'price':num(row.get('Price')),'order_time':s(row.get('Order Time'))})
    return bills

def canonical(e):
    # Preserve multiple legitimate identical lines; sorting removes source row ordering differences.
    clean={k:v for k,v in e.items() if k!='items'}
    clean['items']=sorted(e['items'],key=lambda x:json.dumps(x,sort_keys=True,ensure_ascii=False))
    return json.dumps(clean,sort_keys=True,ensure_ascii=False,separators=(',',':'))
def db(path):
    path.parent.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(path)
    c.execute('PRAGMA journal_mode=WAL')
    c.executescript('''CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY,value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS files (sha256 TEXT PRIMARY KEY,filename TEXT NOT NULL,scanned_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS events (event_id TEXT PRIMARY KEY, content_hash TEXT NOT NULL,payload TEXT NOT NULL,
       source_filename TEXT NOT NULL, scheduled_at TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'pending', sent_at TEXT);
    CREATE TABLE IF NOT EXISTS conflicts (event_id TEXT,filename TEXT,reason TEXT,detected_at TEXT);
    ''');c.commit();return c
def get_anchor(c,first_date,replay_date):
    cur=c.execute("SELECT value FROM config WHERE key='source_anchor'").fetchone()
    if cur:return date.fromisoformat(cur[0]),date.fromisoformat(c.execute("SELECT value FROM config WHERE key='replay_anchor'").fetchone()[0])
    # If file arrives later with an earlier historical date, its scheduled time is in the past (catch-up).
    # Prefer explicit --source-anchor-date for reproducible replay.
    d=date.fromisoformat(first_date);r=date.fromisoformat(replay_date)
    c.execute("INSERT INTO config VALUES ('source_anchor',?)",(d.isoformat(),))
    c.execute("INSERT INTO config VALUES ('replay_anchor',?)",(r.isoformat(),));c.commit()
    return d,r
def schedule(when,src,replay):
    x=dt(when);return datetime.combine(replay+timedelta(days=(x.date()-src).days),x.timetz().replace(tzinfo=None),TZ)
def scan(c,folder,prefix,source_anchor,replay_anchor):
    scanned=new=conflicts=0
    for p in sorted(folder.glob('*')):
        if not p.is_file() or p.suffix.lower() not in ('.csv','.xlsx') or not p.name.startswith(prefix) or p.name.startswith('~$'):continue
        # Require atomic upload via .tmp -> .xlsx/.csv rename, otherwise partially copied files can fail parsing.
        sha=file_hash(p)
        if c.execute('SELECT 1 FROM files WHERE sha256=?',(sha,)).fetchone():continue
        events=extract(p) # full parse before file registry registration
        with c:
            for e in events.values():
                eid=e['event_id'];payload=canonical(e); digest=hashlib.sha256(payload.encode()).hexdigest()
                existing=c.execute('SELECT content_hash FROM events WHERE event_id=?',(eid,)).fetchone()
                if existing:
                    if existing[0]!=digest:
                        c.execute('INSERT INTO conflicts VALUES (?,?,?,?)',(eid,p.name,'Same bill with differing contents',datetime.now(TZ).isoformat()));conflicts+=1
                    continue
                when=schedule(e['event_time'],source_anchor,replay_anchor)
                c.execute('INSERT INTO events(event_id,content_hash,payload,source_filename,scheduled_at,status) VALUES(?,?,?,?,?,?)',
                  (eid,digest,payload,p.name,when.isoformat(),'pending'));new+=1
            c.execute('INSERT INTO files VALUES(?,?,?)',(sha,p.name,datetime.now(TZ).isoformat()))
        scanned+=1
        print(f'SCANNED {p.name}: bills={len(events)} new={new} conflicts={conflicts}',flush=True)
    return scanned,new,conflicts

def send_due(c,producer,topic,limit=200):
    now=datetime.now(TZ).isoformat()
    rows=c.execute("SELECT event_id,payload,scheduled_at,source_filename FROM events WHERE status='pending' AND scheduled_at<=? ORDER BY scheduled_at,event_id LIMIT ?",(now,limit)).fetchall()
    for eid,payload,scheduled,filename in rows:
        event=json.loads(payload)
        event['replay_scheduled_at']=scheduled;event['producer_sent_at']=datetime.now(TZ).isoformat();event['source_filename']=filename
        errors=[]
        def ack(err,msg):
            if err:errors.append(str(err))
        producer.produce(topic,key=eid.encode(),value=json.dumps(event,ensure_ascii=False).encode(),on_delivery=ack)
        if producer.flush(30) or errors:raise RuntimeError(f'Kafka ack failed for {eid}: {errors}')
        with c:c.execute('UPDATE events SET status=?,sent_at=? WHERE event_id=?',('sent',datetime.now(TZ).isoformat(),eid))
        print(f'SENT {eid} scheduled={scheduled} items={len(event["items"])}',flush=True)
    return len(rows)
def main():
    a=argparse.ArgumentParser()
    a.add_argument('--folder',default='data/transactions/incoming');a.add_argument('--prefix',default='Sales Recapitulation Detail Report_')
    a.add_argument('--state',default='state/replay.sqlite');a.add_argument('--source-anchor-date',default='2026-10-18')
    a.add_argument('--replay-date',default=None,help='Map source anchor date onto this replay date (WIB); fixed across restarts')
    a.add_argument('--interval',type=int,default=15);a.add_argument('--bootstrap',default='localhost:19092')
    a.add_argument('--topic',default='bakery.transactions.v1');a.add_argument('--once',action='store_true')
    a.add_argument('--dry-run',action='store_true')
    args=a.parse_args();c=db(Path(args.state));day=args.replay_date or datetime.now(TZ).date().isoformat()
    src,rep=get_anchor(c,args.source_anchor_date,day)
    print(f'SOURCE ANCHOR={src} REPLAY ANCHOR={rep} (persistent)',flush=True)
    producer=None
    if not args.dry_run:
        from confluent_kafka import Producer
        producer=Producer({'bootstrap.servers':args.bootstrap,'acks':'all','enable.idempotence':True})
    try:
        while True:
            scan(c,Path(args.folder),args.prefix,src,rep)
            if producer:send_due(c,producer,args.topic)
            remaining=c.execute("SELECT COUNT(*) FROM events WHERE status='pending'").fetchone()[0]
            sent = c.execute("SELECT COUNT(*) FROM events WHERE status='sent'").fetchone()[0]
            print(f'REPLAY pending={remaining} sent={sent}', flush=True)
            if args.once:break
            time.sleep(max(1,args.interval))
    finally:c.close()
if __name__=='__main__':main()
