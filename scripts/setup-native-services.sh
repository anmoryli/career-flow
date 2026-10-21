#!/usr/bin/env bash
# Ubuntu/WSL native services. Run as root; no containers are used.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y mysql-server redis-server curl python3-venv
version=$(mysqld --version)
if [[ $version != *"8.4."* ]]; then
  printf 'MySQL 8.4 LTS is required; installed: %s\n' "$version" >&2
  exit 1
fi
cat > /etc/mysql/mysql.conf.d/careerflow.cnf <<'EOF'
[mysqld]
bind-address=127.0.0.1
port=3310
mysqlx-bind-address=127.0.0.1
mysqlx-port=33160
character-set-server=utf8mb4
collation-server=utf8mb4_0900_ai_ci
EOF
systemctl restart mysql
install -d -m 750 -o redis -g redis /var/lib/redis-careerflow
cat > /etc/redis/redis-careerflow.conf <<'EOF'
bind 127.0.0.1
port 6390
protected-mode yes
daemonize no
supervised systemd
dir /var/lib/redis-careerflow
appendonly yes
appenddirname appendonlydir
maxmemory 256mb
maxmemory-policy noeviction
logfile ""
EOF
cat > /etc/systemd/system/redis-careerflow.service <<'EOF'
[Unit]
Description=CareerFlow native Redis
After=network.target
[Service]
Type=notify
User=redis
Group=redis
ExecStart=/usr/bin/redis-server /etc/redis/redis-careerflow.conf
Restart=on-failure
NoNewPrivileges=yes
PrivateTmp=yes
[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl start redis-careerflow
mysql --protocol=socket -Nse 'SELECT VERSION()'
redis-cli -p 6390 ping
