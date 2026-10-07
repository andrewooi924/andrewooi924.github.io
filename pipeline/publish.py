"""Upload all data first, update the pointer last. No account data enters this bucket."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
import gzip
import json
import os
from pathlib import Path
from .storage import client

def main():
    p=argparse.ArgumentParser();p.add_argument('--input',default='artifacts/api');p.add_argument('--restore',action='store_true');a=p.parse_args()
    s3=client();bucket=os.environ['R2_DATA_BUCKET'];root=Path(a.input);root.mkdir(parents=True,exist_ok=True)
    if a.restore:
        try:
            pointer=json.loads(s3.get_object(Bucket=bucket,Key='published.json')['Body'].read())
            data=s3.get_object(Bucket=bucket,Key=f"snapshots/{pointer['version']}/state.json.gz")['Body'].read()
            (root/'previous.json').write_bytes(gzip.decompress(data))
        except s3.exceptions.NoSuchKey:(root/'previous.json').write_text('{}')
        return
    manifest=json.loads((root/'published.json').read_text());version=manifest['version'];prefix=f'snapshots/{version}/'
    files=list((root/'snapshots'/version).rglob('*.json'))
    if not files or len(files)>100000:raise ValueError('Unexpected snapshot size')
    def upload(path):s3.put_object(Bucket=bucket,Key=path.relative_to(root).as_posix(),Body=path.read_bytes(),ContentType='application/json',CacheControl='public,max-age=31536000,immutable')
    with ThreadPoolExecutor(max_workers=8) as pool:list(pool.map(upload,files))
    state=gzip.compress((root/'state.json').read_bytes(),mtime=0)
    s3.put_object(Bucket=bucket,Key=prefix+'state.json.gz',Body=state,ContentType='application/gzip')
    # One full compressed archive/day; replaced on same-day reruns. Configure archive retention separately.
    day=datetime.now(timezone.utc).date().isoformat()
    s3.put_object(Bucket=bucket,Key=f'archives/{day}.json.gz',Body=state,ContentType='application/gzip')
    s3.put_object(Bucket=bucket,Key='published.json',Body=(root/'published.json').read_bytes(),ContentType='application/json',CacheControl='no-cache')
    # Retain seven days of old snapshots; never delete the published version.
    cutoff=datetime.now(timezone.utc)-timedelta(days=7)
    for page in s3.get_paginator('list_objects_v2').paginate(Bucket=bucket,Prefix='snapshots/'):
        keys=[{'Key':o['Key']} for o in page.get('Contents',[]) if not o['Key'].startswith(prefix) and o['LastModified']<cutoff]
        for i in range(0,len(keys),1000):s3.delete_objects(Bucket=bucket,Delete={'Objects':keys[i:i+1000]})
    print('Published',version)
if __name__=='__main__':main()
