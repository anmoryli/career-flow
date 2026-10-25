# 原生部署 · V1

用户明确要求不使用 Docker。开发采用 Windows + WSL 原生服务，生产采用原生 Linux 服务，不需要容器运行时。

## Linux 生产准备

1. 安装 Python 3.12、MySQL 8.4 LTS、Redis、Node/npm/PM2、Nginx、Tesseract OCR 及 `chi_sim`/`eng` 语言包；不要把开发初始化脚本直接应用到已有生产服务器。
2. 使用最小权限应用账户、独立测试库、MySQL TLS、SMTP TLS、HTTPS 证书和受保护 `.env`。
3. 设置 APP_ENV=production、COOKIE_SECURE=true、MOCK_PAYMENT_ENABLED=false，提供独立随机秘密；DATABASE_URL 添加正确 `ssl_ca` 参数。
4. `uv sync --frozen --no-dev`、`npm ci`、`npm run build`。
5. 完成备份/恢复演练，然后 `flask --app wsgi db upgrade`，再运行 `check-services`。
6. `pm2 start ecosystem.config.cjs`，确认 Web 与 Worker 日志后 `pm2 save`。使用 `pm2 startup` 输出的服务安装指令配置开机自启。
7. 将 `deploy/nginx.conf` 的 location 放入已配置证书的 HTTPS server 内，运行 `nginx -t` 再 reload。

脚本 `start.sh/restart.sh/stop.sh/status.sh/deploy.sh` 面向 Linux；Gunicorn 不作为 Windows 本地执行方式。`deploy.sh` 要求显式确认已完成备份验证，不自动从远程拉代码，也不执行真实付款。

应用、MySQL 和 Redis 默认回环监听，公网只暴露 Nginx HTTPS。开发 Mailpit 不进入生产架构。

## 当前验收边界

已验证 Windows + WSL 原生 MySQL/Redis 开发链路。Linux 生产 PM2/Nginx/HTTPS 尚未正式验收；配置文件存在不等于已完成上线。
