#!/bin/sh
set -eu
cd "$(dirname "$0")"
. .private/cloud/sync.env
if ! curl -fsS --max-time 2 http://127.0.0.1:18788/healthz >/dev/null 2>&1; then
  ssh -fN -i .private/cloud/yanhaoo_ed25519 \
    -o UserKnownHostsFile=.private/cloud/known_hosts -o StrictHostKeyChecking=yes \
    -o BatchMode=yes -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 \
    -o ServerAliveCountMax=3 -L 127.0.0.1:18788:127.0.0.1:8788 "$CLOUD_SSH_TARGET"
fi
open http://127.0.0.1:18788
