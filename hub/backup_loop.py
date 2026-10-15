import os
from pathlib import Path
import time
from hub.manage import backup
while True:
    try:
        path=Path('/backups')/('hub-'+time.strftime('%Y%m%d-%H%M%S')+'.sqlite')
        backup(os.environ['HUB_DB'],path)
        for old in sorted(path.parent.glob('hub-*.sqlite'))[:-14]:old.unlink()
        print('backup verified',flush=True)
    except Exception as ex:print('backup failed: '+type(ex).__name__,flush=True)
    time.sleep(86400)
