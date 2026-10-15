#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
[ -x .venv/bin/python ] || python3 -m venv .venv
.venv/bin/pip install -q -r requirements.txt
.venv/bin/python -m hub.manage init
.venv/bin/python -m hub.manage docker-env
if [ ! -f 'AI信息整合/运行/inbox.py' ]; then
  docker compose up -d --build --wait hub
  echo 'Website started with no upstream mount. Import with authenticated API.'
else
  docker compose up -d --build --wait
fi
echo 'Open http://127.0.0.1:8788 ; login password is in .private/login.txt'
