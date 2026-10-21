#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
.venv/bin/flask --app wsgi check-services --wait 30
pm2 start ecosystem.config.cjs
pm2 save
