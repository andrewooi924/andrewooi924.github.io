"""Optimize existing images or discover official assets. Dry-run unless --upload."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
from urllib.parse import urlparse
from PIL import Image
from .storage import client
from .http import Fetcher

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',default='images');p.add_argument('--official');p.add_argument('--limit',type=int,default=100);p.add_argument('--upload',action='store_true');p.add_argument('--refresh',action='store_true');a=p.parse_args()
    if not 1<=a.limit<=6000:raise ValueError('Image limit must be 1..6000')
    output=Path('artifacts/assets.json');output.parent.mkdir(exist_ok=True)
    mapping=json.loads(output.read_text()) if output.exists() else {}
    bucket=os.getenv('R2_ASSETS_BUCKET');base=os.getenv('ASSETS_BASE_URL','').rstrip('/')
    if a.upload and (not bucket or not base.startswith('https://')):raise ValueError('R2_ASSETS_BUCKET and HTTPS ASSETS_BASE_URL required')
    s3=client() if a.upload else None
    if s3:
        try:mapping={**json.loads(s3.get_object(Bucket=bucket,Key='asset-index.json')['Body'].read()),**mapping}
        except s3.exceptions.NoSuchKey:pass
    fetch=Fetcher(max_requests=a.limit+10)
    if a.official:
        rows=json.loads(Path(a.official).read_text());sources={r['image']:r['image'] for r in rows}
    else:sources={p.as_posix():p for p in Path(a.root).rglob('*') if p.suffix.lower() in ('.png','.jpg','.jpeg','.webp')}
    count=0
    for key,path in sorted(sources.items()):
        if key in mapping and not a.refresh and (not a.upload or mapping[key].get('uploaded')):continue
        if count>=a.limit:break
        raw=fetch.get(path) if isinstance(path,str) else path.read_bytes()
        if len(raw)>10_000_000:raise ValueError('Image too large')
        with Image.open(io.BytesIO(raw)) as img:
            if img.width*img.height>20_000_000:raise ValueError('Image dimensions too large')
            img.load();img=img.convert('RGB');variants={}
            for name,width in [('thumb',240),('detail',720)]:
                copy=img.copy();copy.thumbnail((width,width*2));buff=io.BytesIO();copy.save(buff,'WEBP',quality=85)
                data=buff.getvalue();digest=hashlib.sha256(data).hexdigest();object_key=f'cards/{digest}/{name}.webp'
                if s3:s3.put_object(Bucket=bucket,Key=object_key,Body=data,ContentType='image/webp',CacheControl='public,max-age=31536000,immutable')
                public_key=object_key.removeprefix('cards/')
                variants[name]=f'{base}/{public_key}' if base else object_key
            mapping[key]={'url':variants['detail'],'thumbnail':variants['thumb'],'sourceHash':hashlib.sha256(raw).hexdigest(),'uploaded':bool(s3)}
        count+=1
    if s3:s3.put_object(Bucket=bucket,Key='asset-index.json',Body=json.dumps(mapping).encode(),ContentType='application/json',CacheControl='no-cache')
    output.write_text(json.dumps(mapping,indent=2))
    print(('Uploaded' if s3 else 'Prepared without upload'),count,'images;',len(mapping),'mapped')
if __name__=='__main__':main()
