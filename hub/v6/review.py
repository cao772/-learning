"""Owner-driven offline review; no service, no public write endpoint."""
import argparse
import json
from pathlib import Path
from hub.v6.offline import atomic_json


def decide(report,store,pair_id,decision,reviewer):
    if decision not in ('merge','reject') or not isinstance(reviewer,str) or not reviewer.strip() or len(reviewer)>100:
        raise ValueError('Explicit decision and reviewer required')
    pairs={x['id']:x for x in report['pairs']}
    p=pairs[pair_id]
    if p['kind'] not in ('possible_event','possible_reprint'):raise ValueError('Not an eligible event candidate')
    items={x['url']:x for x in report['items']}
    store=Path(store)
    import fcntl
    store.parent.mkdir(parents=True,exist_ok=True)
    with store.with_suffix('.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        state=json.loads(store.read_text()) if store.exists() else {}
        state[pair_id]={'decision':decision,'reviewer':reviewer,
                       'left_fingerprint':items[p['left']]['fingerprint'],'right_fingerprint':items[p['right']]['fingerprint']}
        atomic_json(store,state)
    return state[pair_id]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('report','store','pair','decision','reviewer'):p.add_argument('--'+name,required=True)
    a=p.parse_args();decide(json.loads(Path(a.report).read_text()),a.store,a.pair,a.decision,a.reviewer)
    print('Saved private review. Re-run offline analysis with --reviews to apply; stale fingerprints are ignored.')
if __name__=='__main__':main()
