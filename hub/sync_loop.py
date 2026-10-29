"""Local Docker scheduler: daily collection, minute-level editorial export."""
import datetime as dt
import json
from pathlib import Path
import subprocess
import sys
import time


def tick(marker, now=None):
    now = now or dt.datetime.now(dt.timezone(dt.timedelta(hours=8)))
    day = now.date().isoformat()
    try:
        previous = json.loads(marker.read_text()).get('day')
    except (OSError, ValueError, AttributeError):
        previous = None
    collect = now.hour >= 2 and previous != day
    args = [sys.executable, '-m', 'hub.manage', 'sync', '--source', '/upstream']
    if collect:
        args.append('--collect')
    try:
        result = subprocess.run(args, timeout=240)
    except (subprocess.TimeoutExpired, OSError):
        return False
    if result.returncode != 0:
        return False
    if collect:
        # Replace atomically so interruption cannot leave a partial JSON marker.
        temporary = marker.with_suffix('.tmp')
        temporary.write_text(json.dumps({'day': day}))
        temporary.replace(marker)
    return True


def main():
    marker = Path('/app/.private/last-collection.json')
    while True:
        try:
            ok = tick(marker)
        except OSError:
            ok = False
        time.sleep(60 if ok else 300)


if __name__ == '__main__':
    main()
