"""Local Docker scheduler: daily collection, minute-level editorial export."""
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys
import time
marker=Path('/app/.private/last-collection.json')
while True:
    now=dt.datetime.now(dt.timezone(dt.timedelta(hours=8)))
    day=now.date().isoformat()
    previous=json.loads(marker.read_text()).get('day') if marker.exists() else None
    collect=now.hour>=9 and previous!=day
    args=[sys.executable,'-m','hub.manage','sync','--source','/upstream']
    if collect:args.append('--collect')
    result=subprocess.run(args,timeout=240)
    if collect and result.returncode==0:
        marker.write_text(json.dumps({'day':day}))
    time.sleep(60 if result.returncode==0 else 300)
