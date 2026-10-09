"""python -m pipeline.run: bounded read-only crawl into local artifacts; never publish partial runs implicitly."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from .http import Fetcher
from . import adapters

def main():
    p=argparse.ArgumentParser();p.add_argument('--config',default='pipeline/sources.json');p.add_argument('--output',default='artifacts/ingestion');args=p.parse_args()
    cfg=json.loads(Path(args.config).read_text());out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    fetch=Fetcher(min(cfg['max_requests'],300),max(cfg['delay_seconds'],1));report={}
    for source,settings in cfg['sources'].items():
        if not settings.get('enabled'):report[source]={'status':'disabled','reason':settings.get('reason','')};continue
        rows=[];errors=[];urls=settings.get('urls',[]);observed=datetime.now(timezone.utc).isoformat()
        try:
            if settings.get('discover'):
                html=fetch.get(settings['index']).decode('utf-8','replace')
                urls=getattr(adapters,'discover_'+('official' if source=='bandai' else source))(html)
                if not urls:raise ValueError('No series discovered')
            for url in urls:
                try:
                    html=fetch.get(url).decode('utf-8','replace')
                    parsed=getattr(adapters,'official' if source=='bandai' else source)(html,url)
                    if not parsed:raise ValueError('No records parsed')
                    rows.extend({**r,'observed_at':observed} for r in parsed)
                except Exception as e:errors.append({'url':url,'error':str(e)[:200]})
        except Exception as e:errors.append({'error':str(e)[:200]})
        report[source]={'status':'ok' if rows and not errors else 'failed','records':len(rows),'pages':len(urls),'errors':errors}
        # Failed sources are saved for diagnosis, but are not eligible to replace good offers.
        (out/(source+'.json')).write_text(json.dumps(rows,ensure_ascii=False),encoding='utf-8')
    (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    summary=os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        with Path(summary).open('a',encoding='utf-8') as f:
            f.write('### Catalog source health\n\n| Source | Status | Records | Pages |\n| --- | --- | ---: | ---: |\n')
            for source,health in report.items():
                f.write(f"| {source} | {health['status']} | {health.get('records',0)} | {health.get('pages',0)} |\n")
    for source,health in report.items():
        if health['status']=='failed':print(f'::warning title={source} ingestion failed::See ingestion-review artifact for details')
    print(json.dumps(report,indent=2))
    if not any(x['status']=='ok' for x in report.values()):raise SystemExit('No source completed successfully')
if __name__=='__main__':main()
