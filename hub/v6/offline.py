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
    """An auditable, proposal-inclusive 160-article/160-pair human packet.

    A pair's sampling stratum is NOT a positive/negative truth label.
    Do not destroy filled labels when regenerating packets.
    """
    from hub.v6.sampling import sample_pairs
    chosen, pairs, manifest = sample_pairs(report['items'], report['pairs'])
    selected={x['url'] for x in chosen}
    lookup={x['url']:x for x in report['items']}
    top10={s['event_id'] for s in report['scores'][:10]}
    preserve=set()
    for filename,field in [('pair-labels.csv','label'),('relevance-labels.csv','relevant')]:
        path=out/filename
        if path.exists():
            with path.open() as f:
                old=list(csv.DictReader(f))
            if any(r.get(field) or r.get('annotator') for r in old):
                if any(r.get('report_id')!=report['report_id'] for r in old):
                    raise ValueError('Existing labels belong to a different report; use a new --out directory')
                if filename=='pair-labels.csv' and {r['pair_id'] for r in old}!={p['id'] for p in pairs}:
                    raise ValueError('Review sampling changed after labeling; use a new --out directory')
                preserve.add(filename)
    if 'pair-labels.csv' not in preserve:
        with (out/'pair-labels.csv').open('w',newline='') as f:
            writer=csv.writer(f)
            writer.writerow(['report_id','pair_id','left','right','left_title','right_title',
                             'sampling_stratum','candidate_kind','cosine','blockers',
                             'label','annotator','provenance'])
            for p in pairs:
                writer.writerow([report['report_id'],p['id'],p['left'],p['right'],
                                 lookup[p['left']]['title'],lookup[p['right']]['title'],
                                 p['sampling_stratum'],p['kind'],p.get('cosine',''),
                                 json.dumps(p.get('blockers',[]),ensure_ascii=False),
                                 '','',''])
    if 'relevance-labels.csv' not in preserve:
        with (out/'relevance-labels.csv').open('w',newline='') as f:
            writer=csv.writer(f)
            writer.writerow(['report_id','event_id','urls','title','top10','relevant','annotator','provenance'])
            for s in report['scores']:
                if s['event_id'] in top10 or set(s['members']) & selected:
                    title=lookup[s['members'][0]].get('title','') if s['members'] else ''
                    writer.writerow([report['report_id'],s['event_id'],' '.join(s['members']),
                                     title, int(s['event_id'] in top10),'','',''])
    atomic_json(out/'annotation-sample.json',{
        'articles':chosen,
        'sampling':manifest,
        'report_id':report['report_id'],
        'warning':'No human labels yet. Sampling strata are hypotheses, not ground truth. Corpus recall cannot be inferred.'
    })


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
