import json
import tempfile
import unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path
from pipeline.build import build,reference,identity,official_fields,link_official
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
class OfficialFields(unittest.TestCase):
 ROW={'source_id':'ST01-001','code':'ST01-001','rarity':'L','category':'LEADER','color':'色 赤/緑','power':'パワー 5000',
      'cost':'ライフ 5','counter':'カウンター -','feature':'特徴 超新星/麦わらの一味','effect':'テキスト 【起動メイン】効果',
      'release':'入手情報 麦わらの一味【ST-01】 カードリスト 商品情報'}
 def test_strips_labels_and_maps_colors_type_set(self):
  f=official_fields(self.ROW)
  self.assertEqual((f['colors'],f['type'],f['set'],f['variant']),(['red','green'],'Leader','ST01','Normal'))
  self.assertEqual((f['power'],f['life'],f['cost'],f['counter']),('5000','5','',''))
  self.assertEqual((f['feature'],f['effect']),('超新星/麦わらの一味','【起動メイン】効果'))
 def test_reprint_set_comes_from_release_and_parallels_are_marked(self):
  f=official_fields({**self.ROW,'source_id':'OP05-119_p2','code':'OP05-119','rarity':'SEC','category':'CHARACTER','cost':'コスト 10',
                     'release':'入手情報 プレミアムブースター【PRB-01】'})
  self.assertEqual((f['set'],f['variant'],f['type'],f['cost'],f['printingId']),('PRB01','Parallel','Character','10','OP05-119_p2'))
 def test_promos_without_a_product_code_use_promo_set(self):
  self.assertEqual(official_fields({**self.ROW,'code':'P-001','release':'入手情報 ファミリーデッキセット'})['set'],'PROMO')
 def test_missing_category_falls_back_only_for_leaders(self):
  self.assertEqual(official_fields({**self.ROW,'category':''})['type'],'Leader')
  self.assertEqual(official_fields({**self.ROW,'category':'','rarity':'C','cost':'コスト 2'})['type'],'')

if __name__=='__main__':unittest.main()
class OfficialLinks(unittest.TestCase):
 def official(self,pid,code='OP01-001'):return {'id':'b_'+pid,'code':code,'printingId':pid,'img':f'https://o/{pid}.png'}
 def test_unique_match_takes_official_image_and_hides_duplicate(self):
  cat={'y1':{'id':'y1','code':'OP01-001','variant':'Parallel','img':'https://y/1.jpg'},
       'b_OP01-001':self.official('OP01-001'),'b_OP01-001_p1':self.official('OP01-001_p1')}
  self.assertEqual(link_official(cat,{}),1)
  self.assertEqual(cat['y1']['img'],'https://o/OP01-001_p1.png');self.assertEqual(cat['y1']['imgAlt'],'https://y/1.jpg')
  self.assertEqual(cat['b_OP01-001_p1']['aliasOf'],'y1');self.assertNotIn('aliasOf',cat['b_OP01-001'])
 def test_mirrored_image_is_preferred(self):
  cat={'y1':{'id':'y1','code':'OP01-001','variant':'Normal','img':'https://y/1.jpg'},'b_OP01-001':self.official('OP01-001')}
  link_official(cat,{'https://o/OP01-001.png':{'uploaded':True,'url':'https://r2/x.webp'}})
  self.assertEqual([cat['y1'][k] for k in ('img','imgAlt','imgAlt2')],['https://r2/x.webp','https://o/OP01-001.png','https://y/1.jpg'])
 def test_ambiguous_parallels_are_not_guessed(self):
  cat={'y1':{'id':'y1','code':'OP01-001','variant':'Parallel','img':'https://y/1.jpg'},
       'b_OP01-001_p1':self.official('OP01-001_p1'),'b_OP01-001_p2':self.official('OP01-001_p2')}
  self.assertEqual(link_official(cat,{}),0);self.assertEqual(cat['y1']['img'],'https://y/1.jpg')
 def test_image_verified_links_resolve_ambiguous_parallels(self):
  cat={'y1':{'id':'y1','code':'OP01-001','variant':'Super Parallel','img':'https://y/1.jpg'},
       'b_OP01-001_p1':self.official('OP01-001_p1'),'b_OP01-001_p2':self.official('OP01-001_p2')}
  self.assertEqual(link_official(cat,{},{'y1':{'printingId':'OP01-001_p2'}}),1)
  self.assertEqual(cat['y1']['printingId'],'OP01-001_p2');self.assertEqual(cat['b_OP01-001_p2']['aliasOf'],'y1')
 def test_link_to_another_code_is_ignored(self):
  cat={'y1':{'id':'y1','code':'OP01-002','variant':'Parallel','img':'https://y/1.jpg'},'b_OP01-001_p1':self.official('OP01-001_p1')}
  self.assertEqual(link_official(cat,{},{'y1':{'printingId':'OP01-001_p1'}}),0)
