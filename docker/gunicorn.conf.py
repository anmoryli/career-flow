"""Gunicorn 配置：容器内以 gthread 工作模式运行，超时与 Nginx 的 65s 对齐。"""

import multiprocessing
import os


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


bind = f"0.0.0.0:{os.getenv('PORT', '8000')}"
workers = _int("GUNICORN_WORKERS", min(multiprocessing.cpu_count() * 2 + 1, 8))
threads = _int("GUNICORN_THREADS", 4)
worker_class = "gthread"
timeout = _int("GUNICORN_TIMEOUT", 65)
graceful_timeout = _int("GUNICORN_GRACEFUL_TIMEOUT", 30)
keepalive = _int("GUNICORN_KEEPALIVE", 5)
accesslog = "-"
errorlog = "-"
loglevel = os.getenv("GUNICORN_LOG_LEVEL", "info")
# 仅信任容器/内网反代写入的转发头；公网直连时请改为具体代理地址。
forwarded_allow_ips = os.getenv("FORWARDED_ALLOW_IPS", "*")
