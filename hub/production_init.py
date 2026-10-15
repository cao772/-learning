"""Run explicitly in an approved server setup directory, never during build."""
import os
from pathlib import Path
import secrets
from werkzeug.security import generate_password_hash
root=Path('/setup');path=root/'.env'
if path.exists():raise SystemExit('Existing .env preserved; rotate deliberately')
os.umask(0o077)
password=secrets.token_urlsafe(24)
values={'HUB_SECRET':secrets.token_urlsafe(48),'HUB_PASSWORD_HASH':generate_password_hash(password,method='pbkdf2:sha256:600000'),'HUB_INGEST_TOKEN':secrets.token_urlsafe(48),'HUB_IMAGE_TAG':os.environ['RELEASE_TAG']}
path.write_text('\n'.join(k+'='+v.replace('$','$$') for k,v in values.items())+'\n')
(root/'.private').mkdir(exist_ok=True,mode=0o700)
(root/'.private/production-login.txt').write_text(password+'\n')
print('Production config prepared; retrieve login locally, never paste it into chat.')
