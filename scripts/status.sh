#!/usr/bin/env bash
set -euo pipefail
pm2 status
pm2 logs careerflow-web careerflow-worker --nostream --lines 30
