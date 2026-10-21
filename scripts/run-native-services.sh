#!/usr/bin/env bash
set -euo pipefail
systemctl start mysql redis-careerflow
redis-cli -p 6390 ping
# WSL systemd services alone do not keep the distribution alive.
exec sleep infinity
