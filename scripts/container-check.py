"""Exercise the local container without printing credentials; never targets production."""
import http.cookiejar
import json
import re
import subprocess
import time
import urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
BASE='http://127.0.0.1:8788'
config=json.loads((ROOT/'.private/config.json').read_text())
password=(ROOT/'.private/login.txt').read_text().splitlines()[1]
jar=http.cookiejar.CookieJar();opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
def req(path,body=None,method=None,headers=None):
 request=urllib.request.Request(BASE+path,data=body,method=method,headers=headers or {})
 with opener.open(request,timeout=15) as r:return r.read().decode()
page=req('/login');csrf=re.search(r'name="csrf" value="([^"]+)"',page)[1]
import urllib.parse
req('/login',urllib.parse.urlencode({'csrf':csrf,'password':password}).encode())
page=req('/');csrf=re.search(r'name="csrf" content="([^"]+)"',page)[1]
items=json.loads(req('/api/items'))['items'];assert len([x for x in items if x['verification_status']=='reviewed'])==4
key='acceptance-container-state'
current=json.loads(req('/api/state/'+key))
body=json.dumps({'revision':current['revision'],'value':{'note':'synthetic persistence check','saved':True}}).encode()
req('/api/state/'+key,body,'PUT',{'Content-Type':'application/json','X-CSRF-Token':csrf})
subprocess.run(['docker','compose','restart','hub'],cwd=ROOT,check=True,capture_output=True)
for _ in range(30):
 try:
  if json.loads(req('/healthz'))['ok']:break
 except Exception:time.sleep(1)
assert json.loads(req('/api/state/'+key))['value']['note']=='synthetic persistence check'
# SQLite online backup and independent restore into a disposable file in the volume.
code="""import sqlite3, os
from hub.manage import backup
from pathlib import Path
backup('/data/hub.sqlite',Path('/data/acceptance-backup.sqlite'))
with sqlite3.connect('/data/acceptance-backup.sqlite') as src,sqlite3.connect('/data/acceptance-restore.sqlite') as dst:src.backup(dst)
with sqlite3.connect('/data/acceptance-restore.sqlite') as c:
 assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
 assert 'synthetic persistence check' in c.execute('SELECT body FROM personal WHERE id=?',('acceptance-container-state',)).fetchone()[0]
with sqlite3.connect('/data/hub.sqlite') as c:c.execute('DELETE FROM personal WHERE id=?',('acceptance-container-state',))
for p in ['/data/acceptance-backup.sqlite','/data/acceptance-restore.sqlite']:os.unlink(p)
print('container restart, session, state, backup and restore: PASS')
"""
r=subprocess.run(['docker','compose','exec','-T','hub','python','-c',code],cwd=ROOT,capture_output=True,text=True,check=True)
print(r.stdout.strip());print('real reviewed cards: 4; API candidates:',sum(x['verification_status']=='candidate' for x in items))
