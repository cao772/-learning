"""Offline V6 report + review packet. Reads the existing ledger, no collection."""
import argparse
import csv
import datetime as dt
import hashlib
import json
import resource
import sqlite3
import time
from pathlib import Path
from hub.v6.events import candidates, approved_groups, RULE_VERSION
from hub.v6.embedding import encode, MODEL
from hub.v6.scoring import score


def load_items(db):
    c=sqlite3.connect('file:'+str(Path(db).resolve())+'?mode=ro',uri=True)
    try:
        from hub.v6.ledger import APP_ID
        if c.execute('PRAGMA application_id').fetchone()[0]!=APP_ID or c.execute('PRAGMA user_version').fetchone()[0]!=2:
            raise ValueError('V6 schema 2 required; migrate explicitly first')
        rows=[]
        for url,body,fp in c.execute('SELECT url,body,fingerprint FROM articles ORDER BY url'):
            x=json.loads(body);x['url']=url;x['fingerprint']=fp
            # Include the complete public evidence set in the revision hash, but
            # never observation timestamps or private state.
            observations=c.execute('SELECT source,body FROM observations WHERE url=? ORDER BY source',(url,)).fetchall()
            x['fingerprint']=hashlib.sha256(json.dumps(observations,ensure_ascii=False).encode()).hexdigest()
            rows.append(x)
        return rows
    finally:c.close()


def atomic_json(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(data,ensure_ascii=False,indent=2));temp.replace(path)


def analyze(db,model,revision,out,as_of,reviews=None):
    started=time.perf_counter();out=Path(out);out.mkdir(parents=True,exist_ok=True)
    items=load_items(db)
    vectors,cached=encode(items,model,revision,out/'vectors')
    encoded=time.perf_counter()
    import numpy as np
    # Explicit reduction avoids platform BLAS floating-point status warnings.
    similarities=np.einsum('ik,jk->ij',vectors,vectors,optimize=False)
    if not np.isfinite(similarities).all():
        raise ValueError('Non-finite cosine similarities; refuse scoring')
    pairs=candidates(items,np.clip(similarities,-1,1))
    grouped=approved_groups(items,pairs,reviews or {})
    lookup={x['url']:x for x in items}
    scores=[]
    for group in grouped:
        scores.append({'event_id':hashlib.sha256('\n'.join(group).encode()).hexdigest()[:24],
                       'members':group,**score([lookup[u] for u in group],as_of)})
    scores.sort(key=lambda x:(-x['score'],x['event_id']))
    report={'rule_version':RULE_VERSION,'model':MODEL,'revision':revision,'as_of':as_of.isoformat(),
            'items':items,'pairs':pairs,'scores':scores,
            'quality':{'status':'blocked_pending_human_labels','precision':None,'recall':None,'p_at_10':None},
            'performance':{'items':len(items),'dimensions':384,'device':'cpu','threads':2,'batch_size':16,
                           'embedding_cache_hit':cached,'embedding_seconds':round(encoded-started,3),
                           'total_seconds':round(time.perf_counter()-started,3),
                           'max_rss_native_units':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                           'rss_unit_note':'bytes on macOS; KiB on Linux','paid_api_calls':0}}
    report['report_id']=hashlib.sha256(json.dumps([revision,[(x['url'],x['fingerprint']) for x in items],pairs,scores],sort_keys=True).encode()).hexdigest()
    packet(report,out)
    atomic_json(out/'report.json',report)
    return report


def packet(report,out):
    """Deterministic stratified 160-article pool; labels deliberately blank."""
    from hub.content_category import classify_item
    from hub.v6.events import pair_id
    buckets={}
    for x in report['items']:
        cat=classify_item(x)['category'];lang='zh' if any('\u4e00'<=c<='\u9fff' for c in x['title']) else 'other'
        buckets.setdefault((cat,lang),[]).append(x)
    chosen=[]
    # Include top-10 ranking units for P@10, then round-robin strata.
    urls={u for x in report['scores'][:10] for u in x['members']}
    for x in report['items']:
        if x['url'] in urls:chosen.append(x)
    for values in buckets.values():values.sort(key=lambda x:x['url'])
    while len(chosen)<min(160,len(report['items'])):
        before=len(chosen)
        for key in sorted(buckets):
            while buckets[key] and buckets[key][0]['url'] in urls:buckets[key].pop(0)
            if buckets[key] and len(chosen)<160:
                x=buckets[key].pop(0);chosen.append(x);urls.add(x['url'])
        if len(chosen)==before:break
    selected={x['url'] for x in chosen};lookup={x['url']:x for x in report['items']}
    proposals=sorted(report['pairs'],key=lambda p:(p['kind']=='same_topic',-p['cosine'],p['id']))
    pair_lookup={p['id']:p for p in proposals}
    pairs=[];seen=set();ordered=sorted(selected)
    # Cover every sampled article before filling with hard candidate pairs.
    for a,b in zip(ordered[::2],ordered[1::2]):
        key=pair_id(a,b);pairs.append(pair_lookup.get(key,{'id':key,'left':a,'right':b,'kind':'unproposed'}));seen.add(key)
    for p in proposals:
        if len(pairs)>=160:break
        if p['left'] in selected and p['right'] in selected and p['id'] not in seen:
            pairs.append(p);seen.add(p['id'])
    import itertools
    for a,b in itertools.combinations(ordered,2):
        if len(pairs)>=160:break
        key=pair_id(a,b)
        if key not in seen:pairs.append({'id':key,'left':a,'right':b,'kind':'unproposed'});seen.add(key)
    preserve=set()
    for filename,field in [('pair-labels.csv','label'),('relevance-labels.csv','relevant')]:
        path=out/filename
        if path.exists():
            with path.open() as f:
                old=list(csv.DictReader(f))
            if any(r.get(field) or r.get('annotator') for r in old):
                if any(r.get('report_id')!=report['report_id'] for r in old):
                    raise ValueError('Existing labels belong to a different report; use a new --out directory')
                preserve.add(filename)
    if 'pair-labels.csv' not in preserve:
      with (out/'pair-labels.csv').open('w',newline='') as f:
        writer=csv.writer(f);writer.writerow(['report_id','pair_id','left','right','left_title','right_title','label','annotator','provenance'])
        for p in pairs:writer.writerow([report['report_id'],p['id'],p['left'],p['right'],lookup[p['left']]['title'],lookup[p['right']]['title'],'','',''])
    if 'relevance-labels.csv' not in preserve:
      with (out/'relevance-labels.csv').open('w',newline='') as f:
        writer=csv.writer(f);writer.writerow(['report_id','event_id','urls','relevant','annotator','provenance'])
        for s in report['scores']:
            if set(s['members']) & selected:writer.writerow([report['report_id'],s['event_id'],' '.join(s['members']),'','',''])
    atomic_json(out/'annotation-sample.json',{'articles':chosen,'sampling':'top10 plus category/language round-robin; deterministic',
                                           'warning':'No human labels yet. Do not call automated labels ground truth.'})


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('db','model','revision','out','as-of'):p.add_argument('--'+name,required=True)
    p.add_argument('--reviews')
    a=p.parse_args();as_of=dt.datetime.fromisoformat(a.as_of.replace('Z','+00:00'))
    if as_of.tzinfo is None:raise ValueError('as-of requires timezone')
    reviews=json.loads(Path(a.reviews).read_text()) if a.reviews else {}
    r=analyze(a.db,a.model,a.revision,a.out,as_of,reviews)
    print(json.dumps({'performance':r['performance'],'pairs':len(r['pairs']),'review_candidates':sum(x['review_status']=='pending' for x in r['pairs']),'quality':r['quality']},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
