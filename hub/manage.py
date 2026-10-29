import argparse
import datetime as dt
import json
import os
from pathlib import Path
import secrets
import sqlite3
import subprocess
import sys
import time
import urllib.request
from werkzeug.security import generate_password_hash
from hub.app import ROOT, initialize, ingest, connection

PRIVATE=ROOT/'.private'
def require_collection_success(source):
    status=json.loads((source/'收件箱/status.json').read_text())
    if not any(s.get('status') in ('ok','empty','not_modified','cache_interval') for s in status.get('sources',[])):
        raise RuntimeError('All collection sources failed; retry later')

def load_config():
    path=PRIVATE/'config.json'
    if path.exists():
        for k,v in json.loads(path.read_text()).items():os.environ.setdefault(k,str(v))
def export_source(source):
    snapshot=json.loads((source/'收件箱/snapshot.json').read_text())
    current={x['id']:x for x in snapshot['items']}
    rows={}
    for x in json.loads((source/'收件箱/review-packet.json').read_text()):
        rows[x['id']]={'id':x['id'],'title':x['title'],'url':x['url'],'published_at':x.get('published_at'),'collected_at':snapshot['generated_at'],'expires_at':snapshot['expires_at'],'source':', '.join(s['name'] for s in x['sources']),'sources':x['sources'],'topic':x.get('selected_lane','main'),'summary':x.get('summary',''),'verification_status':'candidate','scope':x['scope'],'verification_notes':'订阅元数据，尚未核验原文','learning_value':x.get('note',''),'evidence':[]}
    for path in sorted((source/'成果').glob('*-编辑记录.json')):
        review=json.loads(path.read_text())
        for c in review['cards']:
            x=current.get(c['id'],{})
            # Durable editorial records already carry evidence even after the feed window moves on.
            url=x.get('url') or c['evidence'][0]['url']
            rows[c['id']]={'id':c['id'],'title':c['title'],'url':url,'published_at':c['published_at'],'collected_at':x.get('fetched_at'),'source':', '.join(s['name'] for s in x.get('sources',[])) or '编辑核验','sources':x.get('sources',[]),'topic':c['type'],'summary':c['what'],'verification_status':'reviewed','scope':c['scope'],'verification_notes':c['limits'],'learning_value':c['why'],'evidence':c['evidence'],'next':c['next'],'reviewed_at':review['date'],'task':{'title':'低消耗与质量对照','status':'待执行','body':(source/'成果/深入任务-低消耗与质量.md').read_text() if (source/'成果/深入任务-低消耗与质量.md').exists() else review['deep_task']}}
    status=json.loads((source/'收件箱/status.json').read_text()) if (source/'收件箱/status.json').exists() else {}
    return {'schema':1,'items':list(rows.values()),'source_status':status}

def import_feedback(source,events):
    path=source/'收件箱/feedback.json'
    old=json.loads(path.read_text()) if path.exists() else []
    keys={(x['id'],x['label'],x['at']) for x in old}
    known={x['id'] for x in json.loads((source/'收件箱/snapshot.json').read_text())['items']}
    reviewed_path=source/'收件箱/reviewed.json'
    if reviewed_path.exists():known.update(json.loads(reviewed_path.read_text()))
    for x in events:
        if x['id'] in known and (x['id'],x['label'],x['at']) not in keys:
            old.append(x);keys.add((x['id'],x['label'],x['at']))
    if old:
        temp=path.with_suffix('.tmp');temp.write_text(json.dumps(sorted(old,key=lambda x:dt.datetime.fromisoformat(x['at'])),ensure_ascii=False,indent=2));temp.replace(path)

def get_feedback(url):
    if url:
        req=urllib.request.Request(url.rstrip('/')+'/api/sync-feedback',headers={'Authorization':'Bearer '+os.environ['HUB_INGEST_TOKEN']})
        with urllib.request.urlopen(req,timeout=30) as response:return json.load(response)['events']
    initialize(os.environ['HUB_DB'])
    with connection(os.environ['HUB_DB']) as db:rows=db.execute('SELECT id,body FROM personal').fetchall()
    events=[]
    for row in rows:
        v=json.loads(row['body'])
        if v.get('feedback') and v.get('feedback_at'):events.append({'id':row['id'],'label':v['feedback'],'at':v['feedback_at'],'note':'网页显式反馈'})
    return events

def backup(db,target):
    target.parent.mkdir(parents=True,exist_ok=True)
    with connection(db) as src,sqlite3.connect(target) as dest:src.backup(dest)
    os.chmod(target,0o600)
    with sqlite3.connect(target) as c:assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'

def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=['init','docker-env','serve','sync','backup','restore']);p.add_argument('--source',type=Path,default=ROOT/'AI信息整合');p.add_argument('--target',type=Path);p.add_argument('--url');p.add_argument('--collect',action='store_true');p.add_argument('--port',type=int,default=8787);args=p.parse_args()
    os.umask(0o077)
    PRIVATE.mkdir(exist_ok=True,mode=0o700);load_config()
    if args.command=='init':
        path=PRIVATE/'config.json'
        if path.exists():print('Existing private config preserved.');return
        password=secrets.token_urlsafe(18)
        config={'HUB_SECRET':secrets.token_urlsafe(48),'HUB_PASSWORD_HASH':generate_password_hash(password,method='pbkdf2:sha256:600000'),'HUB_INGEST_TOKEN':secrets.token_urlsafe(48),'HUB_SECURE':'0','HUB_DB':str(PRIVATE/'hub.sqlite')}
        path.write_text(json.dumps(config));path.chmod(0o600)
        (PRIVATE/'login.txt').write_text('本地私人站点口令（请妥善保存）\n'+password+'\n');(PRIVATE/'login.txt').chmod(0o600)
        print('Private config created. Login password is in .private/login.txt (never committed).')
    elif args.command=='docker-env':
        path=ROOT/'.env'
        if path.exists():print('Existing .env preserved');return
        keys=('HUB_SECRET','HUB_PASSWORD_HASH','HUB_INGEST_TOKEN')
        path.write_text('\n'.join(k+'='+os.environ[k].replace('$','$$') for k in keys)+'\n')
        path.chmod(0o600);print('Private Docker environment created')
    elif args.command=='serve':
        from hub.app import create_app
        create_app().run(host='127.0.0.1',port=args.port,debug=False)
    elif args.command=='sync':
        import fcntl
        for log in PRIVATE.glob('sync*.log'):
            if log.stat().st_size>2_000_000:log.write_text('')
        with (args.source/'收件箱/.hub-sync.lock').open('w') as lock:
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:print('Sync already running');sys.exit(75)
            try:
                url=args.url or os.environ.get('HUB_SYNC_URL')
                if url and not (url.startswith('https://') or url.startswith('http://127.0.0.1:')):raise ValueError('Remote sync requires HTTPS')
                import_feedback(args.source,get_feedback(url))
                if args.collect:
                    subprocess.run([sys.executable,str(args.source/'运行/inbox.py'),'collect'],check=True,stdout=subprocess.DEVNULL,timeout=180)
                    require_collection_success(args.source)
                payload=export_source(args.source)
                url=args.url or os.environ.get('HUB_SYNC_URL')
                if url:
                    if not url.startswith('https://') and not url.startswith('http://127.0.0.1:'):raise ValueError('Remote sync requires HTTPS')
                    request=urllib.request.Request(url.rstrip('/')+'/api/ingest',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+os.environ['HUB_INGEST_TOKEN']})
                    for attempt in range(3):
                        try:
                            with urllib.request.urlopen(request,timeout=30) as response: result=json.load(response)
                            break
                        except Exception:
                            if attempt==2:raise
                            time.sleep(2**attempt)
                else:
                    initialize(os.environ['HUB_DB']);result=ingest(os.environ['HUB_DB'],payload)
                (PRIVATE/'sync-status.json').write_text(json.dumps({'at':dt.datetime.now(dt.timezone.utc).isoformat(),'ok':True,**result}))
                print(json.dumps(result))
            except Exception as ex:
                (PRIVATE/'sync-status.json').write_text(json.dumps({'at':dt.datetime.now(dt.timezone.utc).isoformat(),'ok':False,'error':type(ex).__name__}))
                raise
    elif args.command=='backup':
        target=args.target or Path(os.environ['HUB_DB']).parent/'backups'/('hub-'+dt.datetime.now().strftime('%Y%m%d-%H%M%S')+'.sqlite')
        backup(os.environ['HUB_DB'],target);print('Backup verified:',target)
    elif args.command=='restore':
        if not args.target:raise ValueError('--target backup file required; stop the service before restoring')
        with sqlite3.connect(args.target) as c:
            if c.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('invalid backup')
        backup(os.environ['HUB_DB'],Path(os.environ['HUB_DB']).parent/'backups'/'before-restore.sqlite')
        with sqlite3.connect(args.target) as src,connection(os.environ['HUB_DB']) as dest:src.backup(dest)
        print('Restored; restart the service.')
if __name__=='__main__':main()
