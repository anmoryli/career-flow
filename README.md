# 职序 CareerFlow V1

当前已有工程、认证、个人记录和用户求职流程实现，**不是全部 V1 功能已完成或全部外部能力已验收**。2026-10-24 的实现范围与测试矩阵见 [交互实现](docs/UX_IMPLEMENTATION_2026-10-24.md) 和 [测试矩阵](docs/UX_TEST_MATRIX.md)。

## 当前可用

- Python 3.12、Flask 应用工厂、SQLAlchemy 2.x、MySQL **8.4 LTS** 与 Alembic 迁移。
- 邮箱六位验证码注册（10 分钟、5 次尝试）、密码哈希、Redis 限流。
- 可撤销的 30 天登录会话，单设备退出与全部设备退出。
- 对话创建/列表/详情/删除、消息保存与重复请求幂等、明确确认的事实记忆。
- 用户隔离、XSS 转义、CSRF、CSP、请求编号、服务异常脱敏。
- 共享视觉 Token、浅色/深色/跟随系统、响应式布局与登录用户主题同步。
- Redis + RQ 原生 Worker；Windows 使用 SpawnWorker，Linux 使用 Worker。

- 简历账号保存、版本/副本、动态经历、模板/照片/排版保存、浏览器 A4 打印；冲突恢复和本地备份。
- 文本与扫描版 PDF 上传、RQ 提取；写入可识别的简历字段、人像与无协议前缀的网址，核对后保存；扫描件 OCR 需 Tesseract 语言包。浏览器 A4 导出按内容自适应压缩。
- 诊断/报告持久化、十轮追问、建议核实与副本；费用预估/确认/冻结/结算/释放及失败恢复。
- PydanticAI 的 OpenAI 兼容适配器已实现；默认关闭。真实模型质量、网络、费用仍需供应商配置和费用授权后验收，不把测试适配器当作真实 AI。

**尚未交付或验收**：完整经历 AI 自动结构化、服务器 PDF 引擎、自动摘要/长期偏好、完整会员支付、管理端其他模块及生产上线。已有个人记录不会伪造 AI 回复。

管理端目前包含独立权限、概览、用户只读列表、邮箱与模型配置草稿/发布/回滚及操作审计。首个管理员通过本地 `uv run flask --app wsgi bootstrap-admin <邮箱>` 创建，临时密码只写入忽略提交的 `instance/admin-first-login.txt`。服务密钥仅从本地环境或加密配置读取，真实模型默认关闭。

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
npx playwright test
```


集成测试只使用 `careerflow_test`；备份恢复与降级测试只使用 `careerflow_restore_test`。两个数据库由原生初始化脚本创建，不会清空应用库。测试 XML、扫描结果与浏览器截图位于 `output/`，不提交用户数据或凭证。

文档入口：[实际架构](docs/ARCHITECTURE.md) · [数据库](docs/DATABASE.md) · [安全](docs/SECURITY.md) · [测试](docs/TESTING.md) · [实施状态](docs/PROGRESS.md)

ai 简历优化与岗位分析使用会员权益，不再按积分计费。月付¥39/30天，季付¥99/90天；免费用户有2份简历、5次简历AI优化总额度和0次岗位分析，可编辑保存但不能导出PDF。全部账号最多保存10份简历。
