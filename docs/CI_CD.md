# CI/CD 与容器化

2026-10-31 起项目带 GitHub Actions 流水线与容器交付路径。原生（Windows + WSL）运行方式保持不变，两种方式并存。

## 流水线（`.github/workflows/ci.yml`）

每次 push（任意分支）、PR 与手动触发都会运行，6 个 job：

| Job | 内容 | 关键门槛 |
| --- | --- | --- |
| lint | `ruff check app tests scripts`、`git diff --check` | 0 error |
| unit | `pytest`（不含 `tests/integration`） | 全部通过 |
| integration | MySQL 8.4 + Redis service 容器，`scripts/test-integration.py`（迁移 → schema 漂移检查 → 全量 pytest + 覆盖率） | 250+ 通过、无漂移 |
| browser | Playwright 三视口（1440/820/390）：现行维护用例 + 新增性能预算用例 | 全部通过 |
| performance | gunicorn 起服务，`scripts/perf-smoke.py` 压测 8 个端点 | p95/错误率/RPS 预算内 |
| image | 多阶段构建镜像 → 容器自检（`/health/live` 探针）→ push 到 GHCR | 仅 push 事件发布 |

- 镜像：`ghcr.io/<owner>/<repo>`，tag 规则：分支名、`pr-N`、`sha-<full>`、默认分支附加 `latest`、语义化版本（打 `v*` tag 时）。
- 构建缓存：`type=gha`；平台：`linux/amd64`。
- 测试密钥（`SECRET_KEY` 等）只是 CI 运行期的固定测试值，生产密钥一律由部署环境注入，不入仓库。

## 浏览器用例分层

`tests/browser/` 顶层只保留**当前界面**的维护用例；针对重构前旧模板树的 spec 已移入 `tests/browser/legacy/`（Playwright 配置里 `testIgnore` 排除），等按新前端重写后再回迁。移动用 `git mv`，历史可追溯。

## 性能测试

- `scripts/perf-smoke.py`：标准库实现的 HTTP 冒烟压测（线程 + 百分位统计），显式绕过系统代理。端点、时长、并发、阈值全部可用环境变量/参数覆盖。输出 `output/perf/report.json`；在 CI 中会写 `GITHUB_STEP_SUMMARY`。
  - 默认阈值（本地更严）：HTML p95 ≤ 500ms、静态 p95 ≤ 150ms、ready p95 ≤ 800ms、错误率 ≤ 1%、RPS ≥ 10。CI 里放宽到 800/300/1500ms、RPS ≥ 5（共享 runner 噪声大）。
  - 本机复现：
    ```powershell
    $env:DATABASE_URL="...careerflow_test..."; $env:APP_ENV="testing"
    uv run flask --app wsgi run --port 8021
    uv run python scripts/perf-smoke.py --base-url http://127.0.0.1:8021 --duration 8
    ```
- `tests/browser/performance.spec.cjs`：真实 Chromium 里测 TTFB / FCP / LCP / CLS（预算 1200 / 2000 / 3000ms / 0.1），覆盖首页、登录、指南与工作台；结果写 `output/perf/frontend-vitals.json`。

## 容器

- `Dockerfile`：两阶段。`node:22-slim` 构建 Tailwind/vendor 资源 → `python:3.12-slim` 运行时，按 `requirements.txt` 哈希安装依赖，非 root 用户运行，`HEALTHCHECK` 打 `/health/live`。
- 入口 `docker/entrypoint.sh`：可选等待数据库并执行 `flask db upgrade`（`RUN_MIGRATIONS=false` 可关，worker 用），随后 `flask db check`（`RUN_MIGRATION_CHECK=false` 可关）。
- `docker/gunicorn.conf.py`：gthread，worker 数 = `min(CPU*2+1, 8)`，超时 65s 与 Nginx 对齐。
- `docker-compose.yml`：一键起 app + rq worker + MySQL 8.4 + Redis + Mailpit + Nginx（8080 反代 8000）。首次使用：
  ```bash
  cp .env.docker.example .env   # 按需修改密钥
  docker compose up --build
  # 应用 http://127.0.0.1:8080（Nginx）或 8000（直连）
  ```
  compose 默认值只用于本机演示；生产必须：`APP_ENV=production`、TLS MySQL（URL 带 `ssl_ca`）、TLS SMTP、`COOKIE_SECURE=true`、独立随机双密钥（`config.py` 会强制校验）。
- Windows 注意：gunicorn 依赖 `fcntl`，无法在 Windows 原生运行；本机开发仍用 Flask dev server，Linux/容器用 gunicorn。

## 仓库侧需要的一次性配置

1. GitHub 仓库 Settings → Actions → General → Workflow permissions 建议设为默认只读（workflow 已按 job 请求 `packages: write`）。
2. 首次发布后，GHCR 包默认 private；如需公开在 package settings 里调整。
3. 无需额外 secrets：GHCR 用内置 `GITHUB_TOKEN`。

## 本轮基线数字（2026-10-31）

- ruff：0 error；单元 100 passed；MySQL 集成 250 passed（覆盖率见 `output/coverage.json`）。
- 压测（Flask dev server、4 并发、3s/端点）：8 端点全部 p95 < 90ms、RPS 55–95、错误率 0。
- 浏览器维护用例：desktop 全绿（craft 3、discoverability 2、editor_drag 3、editor_sections 4、frontend_assets 3、frontend_experience 5、frontend_refactor 4、frontend_workflows 5、landing 4、product_completion 3、job_description 1、performance 5）。
- 遗留旧 UI spec：见 `tests/browser/legacy/README.md`。
