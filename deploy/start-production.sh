#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
[ "${CONFIRM_PRODUCTION:-}" = yanhaoo.com ] || { echo 'Production gate closed: owner authorization, server, DNS and applicable filing must be confirmed first.'; exit 1; }
[ -f .env ] || { echo 'Initialize private production .env first'; exit 1; }
docker compose --env-file .env -f deploy/compose.production.yaml config --quiet
docker compose --env-file .env -f deploy/compose.production.yaml up -d --wait
