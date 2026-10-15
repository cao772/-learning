#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
[ -x .venv/bin/python ] || python3 -m venv .venv
.venv/bin/pip install -q -r requirements.txt
.venv/bin/python -m hub.manage init
exec .venv/bin/python -m hub.manage serve
