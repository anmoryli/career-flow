#!/bin/sh
# 容器入口：可选等待数据库就绪并执行迁移，然后交棒给 gunicorn / 任务 worker。
set -eu

if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
    attempt=1
    until flask --app wsgi db upgrade; do
        if [ "$attempt" -ge "${MIGRATION_MAX_ATTEMPTS:-30}" ]; then
            echo "数据库迁移失败：已重试 ${attempt} 次" >&2
            exit 1
        fi
        echo "等待数据库就绪（第 ${attempt} 次），2 秒后重试" >&2
        attempt=$((attempt + 1))
        sleep 2
    done
    if [ "${RUN_MIGRATION_CHECK:-true}" = "true" ]; then
        flask --app wsgi db check
    fi
fi

exec "$@"
