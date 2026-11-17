import csv,sys,tempfile,unittest
from datetime import date
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'producer'))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'batch'))
import replay,master_menu
class PipelineTests(unittest.TestCase):
 def test_extract_schedule_and_duplicate_file(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);d=root/'incoming';d.mkdir()
   p=d/'Sales Recapitulation Detail Report_sample.csv'
   with p.open('w',newline='') as f:
    w=csv.writer(f);w.writerow(['Sales Number','Bill Number','Sales Date Out','Menu','Qty','Price'])
    w.writerow(['S1','B1','2026-10-18 08:01:00','ROTI A','1','22.000,00'])
    w.writerow(['S1','B1','2026-10-18 08:01:00','ROTI B','2','15.000,00'])
   events=replay.extract(p)
   self.assertEqual(len(events),1);self.assertEqual(len(next(iter(events.values()))['items']),2)
   c=replay.db(root/'state.sqlite')
   self.assertEqual(replay.scan(c,d,'Sales Recapitulation Detail Report_',date(2026,10,18),date(2026,11,17))[1],1)
   self.assertEqual(replay.scan(c,d,'Sales Recapitulation Detail Report_',date(2026,10,18),date(2026,11,17))[1],0)
   c.close()
 def test_master_rows(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'Master Menu Template Data - sample.csv'
   p.write_text('report title\nMenu Template Name,Menu Category,Menu Name,Status\nTAKEAWAY,PASTRY,BREAD A,ACTIVE\n',encoding='utf-8')
   x=list(master_menu.rows(p));self.assertEqual(len(x),1);self.assertEqual(x[0]['Menu Name'],'BREAD A')
 def test_late_prior_source_date(self):
  t=replay.schedule('2026-10-17 08:01:00',date(2026,10,18),date(2026,11,17))
  self.assertEqual(t.date(),date(2026,11,16))
if __name__=='__main__':unittest.main()
