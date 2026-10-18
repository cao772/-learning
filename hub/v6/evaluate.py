"""Human-label evaluation gate. Missing truth returns null metrics, never zero."""
import argparse
import csv
import json
from pathlib import Path


def evaluate(report,pair_labels,relevance):
    with Path(pair_labels).open() as f:
        labels=list(csv.DictReader(f))
    with Path(relevance).open() as f:
        relevant=list(csv.DictReader(f))
    valid=[r for r in labels if r.get('label') in ('same_event','different_event') and r.get('annotator','').strip() and r.get('provenance')=='human']
    if any(r.get('report_id')!=report.get('report_id') for r in valid):raise ValueError('Labels belong to a different report')
    if len({r['pair_id'] for r in valid})!=len(valid):raise ValueError('Duplicate pair labels')
    known={x['url'] for x in report['items']}
    from hub.v6.events import pair_id
    if any(r['left'] not in known or r['right'] not in known or r['pair_id']!=pair_id(r['left'],r['right']) for r in valid):raise ValueError('Unknown or mismatched labels')
    coverage=len({u for r in valid for u in (r['left'],r['right'])})
    positives=sum(r['label']=='same_event' for r in valid)
    if len(valid)<100 or coverage<100 or positives==0 or positives==len(valid):
        return {'status':'blocked_pending_human_labels','labeled_pairs':len(valid),'article_coverage':coverage,
                'precision':None,'recall':None,'false_merge_rate':None,'p_at_10':None,
                'reason':'Require >=100 distinct human-labeled pairs covering >=100 articles, with positive and negative examples.'}
    proposed={x['id'] for x in report['pairs'] if x['kind'] in ('possible_event','possible_reprint')}
    tp=sum(r['pair_id'] in proposed and r['label']=='same_event' for r in valid)
    fp=sum(r['pair_id'] in proposed and r['label']=='different_event' for r in valid)
    fn=sum(r['pair_id'] not in proposed and r['label']=='same_event' for r in valid)
    valid_rel=[r for r in relevant if r.get('relevant') in ('0','1') and r.get('annotator','').strip() and r.get('provenance')=='human']
    if any(r.get('report_id')!=report.get('report_id') for r in valid_rel):raise ValueError('Relevance labels belong to a different report')
    if len({r['event_id'] for r in valid_rel})!=len(valid_rel):raise ValueError('Duplicate relevance labels')
    rel={r['event_id']:r['relevant']=='1' for r in relevant if r.get('relevant') in ('0','1') and r.get('annotator','').strip() and r.get('provenance')=='human'}
    top=[s['event_id'] for s in report['scores'][:10]]
    return {'status':'evaluated_on_labeled_sample','labeled_pairs':len(valid),'article_coverage':coverage,
            'precision':tp/(tp+fp) if tp+fp else None,'recall':tp/(tp+fn),
            'false_merge_rate':fp/(tp+fp) if tp+fp else None,
            'p_at_10':sum(rel[x] for x in top)/10 if len(top)==10 and all(x in rel for x in top) else None,
            'scope':'candidate pair quality on labeled sample, not corpus-wide cluster quality; no automatic semantic merging'}


def main():
    p=argparse.ArgumentParser()
    for n in ('report','pairs','relevance'):p.add_argument('--'+n,required=True)
    a=p.parse_args();r=evaluate(json.loads(Path(a.report).read_text()),a.pairs,a.relevance)
    print(json.dumps(r,indent=2));raise SystemExit(2 if r['status'].startswith('blocked') else 0)
if __name__=='__main__':main()
