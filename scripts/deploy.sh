#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ${BACKUP_VERIFIED:-} != yes ]]; then
  echo 'Take and restore-verify a database backup, then set BACKUP_VERIFIED=yes.' >&2
  exit 1
fi
uv sync --frozen --no-dev
npm ci
npm run build
.venv/bin/flask --app wsgi db upgrade
.venv/bin/flask --app wsgi check-services --wait 30
pm2 startOrReload ecosystem.config.cjs --update-env
pm2 save
