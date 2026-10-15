"""Stream a verified SQLite snapshot to stdout for encrypted off-host transfer.

Run only via an approved SSH session and pipe directly into recipient-side encryption.
Never emit diagnostics or database contents to stderr/logs.
"""
import os
from pathlib import Path
import sys
import tempfile
from hub.manage import backup

def stream_backup(database, output, scratch_dir=None):
    scratch = Path(scratch_dir) if scratch_dir is not None else Path(database).parent
    with tempfile.TemporaryDirectory(prefix='offsite-backup-', dir=str(scratch)) as tmp:
        snapshot = Path(tmp) / 'snapshot.sqlite'
        backup(database, snapshot)
        with snapshot.open('rb') as f:
            while True:
                chunk = f.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
        output.flush()

if __name__ == '__main__':
    stream_backup(os.environ['HUB_DB'], sys.stdout.buffer)
