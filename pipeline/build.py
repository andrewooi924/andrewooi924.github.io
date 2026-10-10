"""Build immutable API snapshots. Legacy IDs remain aliases; matching is explicit."""
import argparse
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import re
import statistics
import uuid

NAMESPACE=uuid.UUID('e9b35f91-f42d-4161-81a0-c1b327d8d54f')
def identity(source_id):return str(uuid.uuid5(NAMESPACE,source_id))
COLOR_JA={'赤':'red','緑':'green','青':'blue','紫':'purple','黒':'black','黄':'yellow'}
TYPE_EN={'LEADER':'Leader','CHARACTER':'Character','EVENT':'Event','STAGE':'Stage','DON':'DON'}
def _value(text,label):
    """Official fields arrive as '<label> <value>'; '-' means not applicable."""
    text=str(text or '').strip()
    if text.startswith(label):text=text[len(label):].strip()
    return '' if text in ('','-') else text
def official_fields(row):
    """Normalize one official card-list row into catalog fields."""
    colors=[COLOR_JA[c] for c in re.split(r'[/／]',_value(row.get('color'),'色')) if c in COLOR_JA]
    category=TYPE_EN.get(str(row.get('category','')).upper(),'')
    cost=str(row.get('cost') or '')
    if not category and (row.get('rarity')=='L' or cost.startswith('ライフ')):category='Leader'
    product=re.search(r'【([A-Z]+)-?(\d+)】',str(row.get('release') or ''))
    prefix=str(row.get('code','')).split('-')[0]
    card_set=f'{product[1]}{product[2]}' if product else ('PROMO' if prefix=='P' else prefix)
    return {'colors':colors,'type':category,'set':card_set,
            'variant':'Parallel' if re.search(r'_p\d+$',str(row.get('source_id',''))) else 'Normal',
            'printingId':row.get('source_id',''),
            'power':_value(row.get('power'),'パワー'),'cost':_value(cost,'コスト') if cost.startswith('コスト') else '',
            'life':_value(cost,'ライフ') if cost.startswith('ライフ') else '','counter':_value(row.get('counter'),'カウンター'),
            'feature':_value(row.get('feature'),'特徴'),'effect':_value(row.get('effect'),'テキスト')}

def load(path,default):return json.loads(Path(path).read_text()) if Path(path).is_file() else default

def reference(offers,now):
    eligible={}
    for x in offers:
        try:age=now-datetime.fromisoformat(x['observed_at'])
        except (KeyError,TypeError,ValueError):continue
        if age<timedelta(0) or age>timedelta(hours=48):continue
        if x.get('in_stock') is not True or x.get('condition')!='standard' or x.get('currency')!='JPY':continue
        price=x.get('price')
        if isinstance(price,bool) or not isinstance(price,(int,float)) or not 0<price<1_000_000_000:continue
        source=x['source']
        if source not in eligible or price<eligible[source]:eligible[source]=price
    return {'price':statistics.median(eligible.values()) if eligible else None,'sources':sorted(eligible),'method':'median-retail-v1','currency':'JPY'}

def build(root,output,ingestion=None,previous=None,now=None):
    root=Path(root);output=Path(output);now=now or datetime.now(timezone.utc)
    previous=previous or {};catalog={c['id']:dict(c) for c in load(root/'catalog.json',[])}
    old_by_id={c['id']:c for c in previous.get('catalog',[])}
    catalog.update(old_by_id)
    assets=load(root/'artifacts/assets.json',{})
    imgmap=load(root/'image_map.json',{})
    mappings=load(root/'pipeline/mappings.json',{'mappings':[]})['mappings']
    approved={}
    for m in mappings:
        if not m.get('reviewed_by') or not m.get('evidence'):raise ValueError('Mappings require reviewer and evidence')
        key=(m['source'],m['source_id'])
        if key in approved:raise ValueError('Duplicate mapping')
        approved[key]=m
    offers=previous.get('offers',{});history=previous.get('history',{});report={};unmatched=[];official=[]
    if ingestion:
        ingestion=Path(ingestion);report=load(ingestion/'report.json',{})
        if report.get('bandai',{}).get('status')=='ok':
            official=load(ingestion/'bandai.json',[])
            # Official variants do not automatically merge with legacy retailer records.
            for row in official:
                id='b_'+identity('bandai:ja:'+row['source_id']).replace('-','')
                catalog[id]={**catalog.get(id,{}),'id':id,'variantId':identity('bandai:ja:'+row['source_id']),
                 'code':row['code'],'name':row['name'],'rarity':row['rarity'],**official_fields(row),
                 'img':row['image'],'price':None,'mappingStatus':'official-unmatched'}
        for source,health in report.items():
            if source=='bandai' or health['status']!='ok':continue
            rows=load(ingestion/(source+'.json'),[])
            # A catastrophic count drop is quarantined instead of replacing good data.
            previous_count=previous.get('sourceCounts',{}).get(source,0)
            if previous_count and len(rows)<previous_count*.7:
                health['status']='quarantined';health['reason']='Record count fell by more than 30%';continue
            for row in rows:
                if source=='yuyutei' and row['source_id'] in catalog:
                    id=row['source_id'];mapping=None
                else:
                    mapping=approved.get((source,row['source_id']));id=mapping.get('legacy_id') if mapping else None
                if not id or id not in catalog or row['code']!=catalog[id]['code']:
                    unmatched.append(row);continue
                if mapping:row={**row,'condition':mapping.get('condition','unknown')}
                # Replace observations only for this source+listing, never erase absent listings.
                existing=[o for o in offers.get(id,[]) if (o['source'],o['source_id'])!=(source,row['source_id'])]
                offers[id]=existing+[row]
    for id,c in catalog.items():
        c.setdefault('variantId',identity('migration:'+id));c.setdefault('mappingStatus','legacy-provisional')
        local=imgmap.get(id) or c.get('img')
        if local and local in assets and assets[local].get('uploaded') and assets[local].get('url','').startswith('https://'):
            c['imgAlt2']=c.get('imgAlt','');c['imgAlt']=c.get('img','');c['img']=assets[local]['url']
        ref=reference(offers.get(id,[]),now)
        c['reference']=ref
        if id in offers:
            c['price']=ref['price'];c['priceStatus']='fresh' if ref['price'] is not None else 'unavailable'
        else:c['priceStatus']='legacy-undated' if c.get('price') is not None else 'unavailable'
        c['priceUpdatedAt']=max((o.get('observed_at','') for o in offers.get(id,[])),default=None)
        if ref['price'] is not None:
            daily={'date':now.date().isoformat(),**ref}
            history[id]=[p for p in history.get(id,[]) if p['date']!=daily['date']]+[daily]
        # Full observations are archived separately on publish; live chart history is bounded.
        history[id]=sorted(history.get(id,[]),key=lambda x:x['date'])[-365:]
    state={'catalog':list(catalog.values()),'offers':offers,'history':history,
       'sourceCounts':{**previous.get('sourceCounts',{}),**{k:v['records'] for k,v in report.items() if v['status']=='ok'}},'report':report}
    packed=json.dumps(state,ensure_ascii=False,separators=(',',':')).encode();version=hashlib.sha256(b'compact-v2:'+packed).hexdigest()[:24]
    dest=output/'snapshots'/version;dest.mkdir(parents=True,exist_ok=True)
    def write(path,data):
        target=dest/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    write(Path('catalog.json'),state['catalog'])
    write(Path('price-history.json'),{id:[[p['date'],p['price']] for p in points[-90:]] for id,points in history.items()})
    write(Path('offers.json'),offers)
    write(Path('history.json'),history)
    manifest={'version':version,'publishedAt':now.isoformat(),'variantCount':len(catalog),'sources':report,
              'valuationMethod':'median-retail-v1','historyDays':365,'unmatchedCount':len(unmatched)}
    write(Path('manifest.json'),manifest)
    output.mkdir(parents=True,exist_ok=True)
    (output/'published.json').write_text(json.dumps({'version':version}))
    (output/'state.json').write_bytes(packed)
    (output/'unmatched.json').write_text(json.dumps(unmatched,ensure_ascii=False,indent=2))
    (output/'official.json').write_text(json.dumps(official,ensure_ascii=False))
    return manifest

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',default='.');p.add_argument('--output',default='artifacts/api');p.add_argument('--ingestion');p.add_argument('--previous');a=p.parse_args()
    result=build(a.root,a.output,a.ingestion,load(a.previous,{}) if a.previous else {})
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
