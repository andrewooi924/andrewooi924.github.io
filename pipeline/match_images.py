"""Match retailer rows to official printings by comparing card images. Run locally:
python -m pipeline.match_images --calibrate 150     # score known links to pick thresholds
python -m pipeline.match_images --max-score 0.35 --min-margin 0.15
Confident matches go to pipeline/image_links.json; the rest go to artifacts/image-review.html."""
import argparse
import hashlib
import html
import io
import json
import re
import time
from pathlib import Path
from urllib.parse import urlparse
import requests
from PIL import Image
from .http import Fetcher

API='https://most-wanted-api.optcg-wanted.workers.dev'
CACHE=Path('artifacts/image-cache');LINKS=Path('pipeline/image_links.json');REVIEW=Path('artifacts/image-review.html')
PAR=re.compile(r'_p\d+$');SIZE=(16,22);SET_BONUS=.3
fetcher=Fetcher(max_requests=20000,delay=.8)

def image(url):
    """Download once, keep on disk; our own API host is fetched directly."""
    path=CACHE/(hashlib.sha256(url.encode()).hexdigest()+'.img')
    if not path.exists():
        CACHE.mkdir(parents=True,exist_ok=True)
        if urlparse(url).hostname==urlparse(API).hostname:
            for wait in (0,2,5,15,30):
                time.sleep(wait or .3);r=requests.get(url,timeout=30)
                if r.status_code!=429:break
            r.raise_for_status();raw=r.content
        else:raw=fetcher.get(url)
        path.write_bytes(raw)
    return path.read_bytes()

def signature(url):
    """Small colour thumbnail, normalised per channel so brightness and scan differences cancel out."""
    with Image.open(io.BytesIO(image(url))) as img:
        px=list(img.convert('RGB').resize(SIZE,Image.LANCZOS).getdata())
    out=[]
    for ch in range(3):
        v=[p[ch] for p in px];m=sum(v)/len(v);sd=(sum((x-m)**2 for x in v)/len(v))**.5 or 1
        out+=[(x-m)/sd for x in v]
    return out

def score(a,b):return sum(abs(x-y) for x,y in zip(a,b))/len(a)

def retailer_image(c):
    """The row's own picture: a retailer scan or the owner's HD upload, never an official image."""
    for url in (c.get('imgRetailer'),c.get('img'),c.get('imgAlt'),c.get('imgAlt2')):
        if url and 'onepiece-cardgame.com' not in url and 'noimage' not in url:return url

def candidates(catalog):
    free={}
    for c in catalog:
        if c['id'].startswith('b_') and not c.get('aliasOf') and c.get('printingId'):
            free.setdefault((c['code'],'par' if PAR.search(c['printingId']) else 'base'),[]).append(c)
    return free

def safe_sig(url,errors):
    try:return signature(url)
    except Exception as e:errors.append(f'{url}: {e}');return None

def calibrate(catalog,n):
    by_id={c['id']:c for c in catalog};right=[];wrong=[];errors=[]
    linked=[c for c in catalog if c.get('officialId') and c.get('variant')=='Parallel'][:n]
    for c in linked:
        src=retailer_image(c);o=by_id[c['officialId']]
        others=[x for x in catalog if x['id'].startswith('b_') and x['code']==c['code'] and x['id']!=o['id']]
        if not src or not others:continue
        a=safe_sig(src,errors);b=safe_sig(o['img'],errors)
        if a is None or b is None:continue
        right.append(score(a,b))
        for x in others:
            s=safe_sig(x['img'],errors)
            if s:wrong.append(score(a,s))
    q=lambda v,p:sorted(v)[int(p*(len(v)-1))] if v else None
    print(f'right n={len(right)} p50={q(right,.5):.3f} p95={q(right,.95):.3f} max={max(right):.3f}')
    print(f'wrong n={len(wrong)} min={min(wrong):.3f} p05={q(wrong,.05):.3f} p50={q(wrong,.5):.3f}')
    print(len(errors),'errors')

def match(catalog,max_score,min_margin):
    free=candidates(catalog);errors=[];confident={};review=[]
    links=json.loads(LINKS.read_text()) if LINKS.exists() else {}
    rows=[c for c in catalog if not c['id'].startswith('b_') and not c.get('officialId') and c['id'] not in links]
    groups={}
    for c in rows:
        kind='base' if c.get('variant')=='Normal' else 'par'
        if free.get((c['code'],kind)) and retailer_image(c):groups.setdefault((c['code'],kind),[]).append(c)
    for i,(key,group) in enumerate(sorted(groups.items())):
        opts=[(o,safe_sig(o['img'],errors)) for o in free[key]];opts=[x for x in opts if x[1]]
        pairs=[]
        for c in group:
            sig=safe_sig(retailer_image(c),errors)
            if sig is None:continue
            ranked=sorted(((score(sig,s),o) for o,s in opts),key=lambda x:x[0])
            pairs+=[(sc,c,o,ranked) for sc,o in ranked]
        # Reprints share identical art, so the retailer's set code breaks near-ties.
        fit=lambda sc,c,o:sc-(SET_BONUS if o.get('set') and o.get('set')==c.get('set') else 0)
        # One official printing per retailer row, best scores claimed first.
        taken=set();done=set()
        for sc,c,o,ranked in sorted(pairs,key=lambda p:fit(*p[:3])):
            if c['id'] in done or o['id'] in taken:continue
            rest=[fit(s,c,x) for s,x in ranked if x['id']!=o['id'] and x['id'] not in taken]
            margin=(min(rest)-fit(sc,c,o)) if rest else 1
            done.add(c['id']);taken.add(o['id'])
            entry={'printingId':o['printingId'],'score':round(sc,3),'margin':round(margin,3)}
            if sc<=max_score and margin>=min_margin:confident[c['id']]=entry
            else:review.append((c,o,ranked,entry))
        if i%50==0:print(f'{i}/{len(groups)} groups, {len(confident)} confident, {len(review)} to review',flush=True)
    links.update(confident)
    LINKS.write_text(json.dumps(dict(sorted(links.items())),indent=1)+'\n')
    write_review(review)
    print(f'{len(confident)} confident links written, {len(review)} for review, {len(errors)} image errors')
    for e in errors[:5]:print(' ',e)

def write_review(review):
    cells=[]
    for c,o,ranked,entry in review:
        opts=''.join(f'<figure class="{"pick" if x["id"]==o["id"] else ""}"><img src="{html.escape(x["img"])}"><figcaption>{html.escape(x["printingId"])} · {s:.2f}</figcaption></figure>' for s,x in ranked)
        cells.append(f'<section><figure><img src="{html.escape(retailer_image(c))}"><figcaption>{html.escape(c["id"])}<br>{html.escape(c["code"])} {html.escape(c.get("variant",""))}</figcaption></figure><span>→</span>{opts}</section>')
    REVIEW.parent.mkdir(exist_ok=True)
    REVIEW.write_text('<!doctype html><meta charset=utf-8><title>Image review</title><style>body{font:13px system-ui;margin:16px}section{display:flex;gap:10px;align-items:center;padding:10px 0;border-bottom:1px solid #ddd}img{width:110px}figure{margin:0}.pick{outline:3px solid #D6A23E}</style>'+''.join(cells))

def main():
    p=argparse.ArgumentParser();p.add_argument('--calibrate',type=int);p.add_argument('--max-score',type=float,default=.35);p.add_argument('--min-margin',type=float,default=.15);a=p.parse_args()
    catalog=requests.get(API+'/v1/catalog',timeout=60).json()
    catalog=catalog if isinstance(catalog,list) else catalog['catalog']
    if a.calibrate:calibrate(catalog,a.calibrate)
    else:match(catalog,a.max_score,a.min_margin)
if __name__=='__main__':main()
