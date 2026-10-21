# 职序 CareerFlow V1

当前是实际可运行的首批实现，**不是全部 V1 功能已完成**。依照 `PROMPT.md` 的实施顺序，先交付工程基础、认证与对话持久化。

## 当前可用

- Python 3.12、Flask 应用工厂、SQLAlchemy 2.x、MySQL **8.4 LTS** 与 Alembic 迁移。
- 邮箱六位验证码注册（10 分钟、5 次尝试）、密码哈希、Redis 限流。
- 可撤销的 30 天登录会话，单设备退出与全部设备退出。
- 对话创建/列表/详情/删除、消息保存与重复请求幂等、明确确认的事实记忆。
- 用户隔离、XSS 转义、CSRF、CSP、请求编号、服务异常脱敏。
- 共享视觉 Token、浅色/深色/跟随系统、响应式布局与登录用户主题同步。
- Redis + RQ 原生 Worker；Windows 使用 SpawnWorker，Linux 使用 Worker。

**尚未交付**：真实 AI 接入、自动摘要/长期记忆、完整动态表单、简历/PDF/OCR、JD/诊断/报告、积分会员支付、管理端及最终上线验收。当前记录模式不会伪造 AI 回复，也不产生模型费用。

## 本机运行：Windows + WSL Ubuntu 原生服务

按用户最新要求，运行、测试和部署均不使用 Docker。MySQL/Redis 原生运行于已有的 WSL Ubuntu；Flask/RQ/Mailpit 原生运行于 Windows。数据库始终为 MySQL，不使用 SQLite。

已验证环境：Windows、WSL Ubuntu 26.04、Python 3.12.13、MySQL 8.4.11、Redis 8.0.5、Mailpit 1.27.10。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup-native.ps1
# ????????????????
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start-native.ps1
```

路径不在 `D:\code\career-flow` 时，将上述 WSL 脚本路径替换为实际挂载路径。`setup-native-services.sh` 会安装系统软件包并配置本开发环境的 MySQL 监听端口；不要对已有生产数据库执行它。

- 应用：<http://127.0.0.1:8000>
- 开发收件箱：<http://127.0.0.1:8026>（注册邮件只进入本地收件箱）
- MySQL：`127.0.0.1:3310`；Redis：`127.0.0.1:6390`；SMTP：`127.0.0.1:1026`。
- `.env` 使用随机生成的本地密码，已加入忽略规则；不要提交或分享。
- WSL 守护进程维持发行版存活，避免 systemd 服务随 WSL 空闲退出。

```powershell
# 停止本项目开发进程，不删除 MySQL 数据
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/stop-native.ps1
```

Windows 本地使用 Flask 开发服务器，仅供开发。Linux 生产运行使用 Gunicorn + PM2 + Nginx，参见 [部署说明](docs/DEPLOYMENT.md)。

## 检查与测试

```powershell
uv run ruff check app tests scripts wsgi.py
uv run ruff format --check app tests scripts wsgi.py migrations
uv run pytest tests/test_foundation.py -q
uv run python scripts/test-integration.py
uv run python scripts/verify-db-lifecycle.py
uv run python scripts/verify-worker.py
uv run flask --app wsgi check-services
```

集成测试只使用 `careerflow_test`；备份恢复与降级测试只使用 `careerflow_restore_test`。两个数据库由原生初始化脚本创建，不会清空应用库。测试 XML、扫描结果与浏览器截图位于 `output/`，不提交用户数据或凭证。

文档入口：[实际架构](docs/ARCHITECTURE.md) · [数据库](docs/DATABASE.md) · [安全](docs/SECURITY.md) · [测试](docs/TESTING.md) · [实施状态](docs/PROGRESS.md)
