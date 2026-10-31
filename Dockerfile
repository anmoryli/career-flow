# syntax=docker/dockerfile:1.7
# 前端资源在独立的 Node 阶段构建，运行镜像不携带 node_modules 与构建工具。
FROM node:22-bookworm-slim AS assets

WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY scripts/build-assets.cjs scripts/build-frontend.cjs ./scripts/
COPY app/static ./app/static
# Tailwind input.css 通过 source(../../../templates/frontend) 扫描模板里的类名
COPY app/templates ./app/templates
RUN node scripts/build-frontend.cjs


FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN groupadd --gid 10001 careerflow \
    && useradd --uid 10001 --gid careerflow --create-home --shell /usr/sbin/nologin careerflow

WORKDIR /app

# 依赖先于源码复制，源码改动不会让 pip 层失效。
COPY requirements.txt ./
RUN pip install --require-hashes -r requirements.txt

COPY --chown=careerflow:careerflow app ./app
COPY --chown=careerflow:careerflow migrations ./migrations
COPY --chown=careerflow:careerflow scripts ./scripts
COPY --chown=careerflow:careerflow docker ./docker
COPY --chown=careerflow:careerflow pyproject.toml wsgi.py ./
COPY --from=assets --chown=careerflow:careerflow /build/app/static ./app/static

RUN chmod +x docker/entrypoint.sh \
    && mkdir -p /app/instance /app/output \
    && chown -R careerflow:careerflow /app/instance /app/output

ENV APP_ENV=production \
    PORT=8000 \
    GUNICORN_WORKERS=3 \
    RUN_MIGRATIONS=true

USER careerflow
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=40s --retries=4 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=3).status == 200 else 1)"

ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["gunicorn", "--config", "docker/gunicorn.conf.py", "wsgi:app"]
