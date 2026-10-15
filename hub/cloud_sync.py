"""Export the existing local inbox through authenticated SSH; no public HTTP required."""
import fcntl
import json
import os
from pathlib import Path
import subprocess
import time
from hub.manage import export_source, import_feedback

SOURCE = Path('/upstream')
REMOTE = '''import json,os,sys,urllib.request
path=sys.argv[1]
data=sys.stdin.buffer.read() if path=='/api/ingest' else None
req=urllib.request.Request('http://127.0.0.1:8000'+path,data=data,headers={'Authorization':'Bearer '+os.environ['HUB_INGEST_TOKEN'],'Content-Type':'application/json'})
with urllib.request.urlopen(req,timeout=30) as response:print(response.read().decode())
'''

def exchange(path, payload=None):
    import shlex
    command = 'sudo docker exec -i xunxu-hub-hub-1 python -c ' + shlex.quote(REMOTE) + ' ' + shlex.quote(path)
    result = subprocess.run(['ssh','-i','/keys/identity','-o','UserKnownHostsFile=/keys/known_hosts',
        '-o','StrictHostKeyChecking=yes','-o','BatchMode=yes','-o','ConnectTimeout=15',
        '-o','ServerAliveInterval=15','-o','ServerAliveCountMax=2',os.environ['CLOUD_SSH_TARGET'],command],
        input=json.dumps(payload) if payload is not None else '', text=True,capture_output=True,timeout=90,check=True)
    return json.loads(result.stdout)

def tick():
    with (SOURCE/'收件箱/.hub-sync.lock').open('w') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return
        import_feedback(SOURCE, exchange('/api/sync-feedback')['events'])
        result = exchange('/api/ingest', export_source(SOURCE))
        Path('/state/status.json').write_text(json.dumps({'ok':True,'at':time.time(),**result}))
        print(json.dumps(result),flush=True)

def main():
    while True:
        try:
            tick()
            time.sleep(60)
        except Exception as ex:
            Path('/state/status.json').write_text(json.dumps({'ok':False,'at':time.time(),'error':type(ex).__name__}))
            print('cloud sync failed: '+type(ex).__name__,flush=True)
            time.sleep(300)
if __name__=='__main__':main()
