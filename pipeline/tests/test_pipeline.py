import json
import tempfile
import unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path
from pipeline.build import build,reference,identity
from pipeline.adapters import official,discover_official,cardrush

NOW=datetime(2026,9,17,tzinfo=timezone.utc)
def offer(source,price,**kw):return dict(source=source,price=price,currency='JPY',in_stock=True,condition='standard',observed_at=NOW.isoformat(),**kw)
class Prices(unittest.TestCase):
 def test_median_one_vote_per_source(self):
  rows=[offer('a',100),offer('a',200),offer('b',300),offer('c',500)]
  self.assertEqual(reference(rows,NOW)['price'],300)
 def test_excludes_stale_unknown_condition_out_of_stock_and_zero(self):
  rows=[offer('a',100),{**offer('b',900),'in_stock':False},{**offer('c',2000),'condition':'unknown'},
        {**offer('d',700),'observed_at':(NOW-timedelta(days=3)).isoformat()},offer('e',0)]
  self.assertEqual(reference(rows,NOW)['sources'],['a'])
 def test_no_eligible_is_unknown_not_zero(self):self.assertIsNone(reference([],NOW)['price'])
 def test_official_duplicate_codes_remain_distinct(self):
  html=''.join(f'<dl class="modalCol" id="OP01-001{s}"><div class="infoCol"><span>OP01-001</span></div><div class="frontCol"><img data-src="../images/{s}.png"></div></dl>' for s in ['','_p1'])
  rows=official(html,'https://www.onepiece-cardgame.com/cardlist/');self.assertEqual(len(rows),2);self.assertNotEqual(rows[0]['source_id'],rows[1]['source_id'])
 def test_discover_series_not_hardcoded(self):
  self.assertEqual(discover_official('<option value="550199">Future</option><option value="bad">x</option>'),['https://www.onepiece-cardgame.com/cardlist/?series=550199'])
 def test_cardrush_does_not_apply_another_products_price(self):
  html='<div><a href="/product/1">OP01-001</a><a href="/product/2">OP01-002</a>1,000円</div>'
  self.assertEqual(cardrush(html,'https://www.cardrush-op.jp/'),[])
 def test_build_preserves_alias_and_does_not_fabricate_history(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);(root/'catalog.json').write_text(json.dumps([{'id':'op01_1','code':'OP01-001','price':100}]))
   out=root/'out';m=build(root,out,now=NOW);folder=out/'snapshots'/m['version']
   self.assertEqual(json.loads((folder/'history.json').read_text()).get('op01_1',[]),[])
   self.assertEqual(json.loads((folder/'catalog.json').read_text())[0]['variantId'],identity('migration:op01_1'))
   self.assertEqual(json.loads((folder/'catalog.json').read_text())[0]['priceStatus'],'legacy-undated')
if __name__=='__main__':unittest.main()
