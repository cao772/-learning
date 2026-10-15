#!/bin/sh
# Private access only; does not start Caddy or publish HTTP ports.
set -eu
cd "$(dirname "$0")/.."
[ -f .env ] || { echo 'Initialize private server .env first'; exit 1; }
docker compose --env-file .env -f deploy/compose.production.yaml -f deploy/compose.preflight.yaml config --quiet
docker compose --env-file .env -f deploy/compose.production.yaml -f deploy/compose.preflight.yaml up -d --wait hub backup
