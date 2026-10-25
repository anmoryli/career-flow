# 测试方法

2026-10-25 本地实测：`uv run python scripts/test-integration.py` 156 passed，覆盖报告 96%；`uv run python scripts/verify-db-lifecycle.py` 在隔离 MySQL 库完成升级、降级、备份与恢复；`npx playwright test` 最终显示 39 passed，涵盖桌面、平板和手机。Ruff 检查与格式检查、`npm run build` 通过。真实 QQ SMTP、付费 MiMo 调用、生产部署和全部路径 100% 覆盖尚未验证。

2026-10-24新增用户流程矩阵见 `UX_TEST_MATRIX.md`。`scripts/test-integration.py` 升级真实MySQL测试库、检查迁移差异并执行包含分支统计的完整pytest，输出XML/HTML/JSON覆盖报告。Playwright通过 `npx playwright test` 运行，测试服务器限定8011/测试数据库，使用明确标记的测试模型，不代表真实供应商验收。

管理员配置新增权限、密钥脱敏、草稿发布/回滚、真实本地 Mailpit 发信、CLI 初始账号和三种屏幕尺寸浏览器用例。当前阶段的实际数字和限制见 `ADMIN_STATUS_2026-10-24.md`；旧的 `UX_ACCEPTANCE_2026-10-24.md` 是上一阶段快照。

结构化诊断追问新增 MySQL 表单定义/提交状态测试；密码修改测试覆盖当前密码、重复密码和全设备会话失效。密码找回测试覆盖未知邮箱统一反馈、验证码单次使用、五次错误后失效以及全部会话撤销。管理端可从已配置模型服务的 `/models` 读取列表，也允许手填 ID；本地网络把该服务域名解析到保留地址，故真实模型列表及模型调用没有完成外部联调。模型列表用 MockTransport 验证协议与错误处理。

新增测试依赖安装后执行 `npx playwright install chromium`。浏览器覆盖1440/820/390宽度、三种主题与各工作台页面，输出实际PDF及截图。正式应用没有测试登录入口；`scripts/e2e-server.py` 仅在隔离测试时使用。

## 自动化

- `uv run pytest tests/test_foundation.py -q`：不连接真实数据库的配置、首页、CSRF、脱敏、主题/结构化 Schema、生产约束测试。
- `uv run python scripts/test-integration.py`：连接原生 MySQL 8.4 和原生 Redis，升级测试库、检查模型迁移差异后运行全部 pytest；输出 `output/pytest-native.xml`。
- `uv run python scripts/verify-db-lifecycle.py`：隔离恢复库的真实迁移升降级与 mysqldump 恢复。
- `uv run python scripts/verify-worker.py`：原生 Worker 执行无用户参数的内部健康检查作业；等待结果并核对 MySQL/schema/Redis。
- `npm run build`：可重复构建并复制本地前端资源；`uv run ruff check ...` / `ruff format --check ...` 检查 Python。

集成用例覆盖 MySQL 8.4/字符集/引擎/外键、会话 Cookie/过期/撤销、登录失败/限流、注册验证码次数/有效期/单次使用、跨用户访问、XSS、主题同步、删除级联、真实并发消息幂等、唯一约束回滚、只读状态、重启后的上下文与推测排除。

没有 TEST_DATABASE_URL 时，直接 pytest 会跳过集成测试；这是未执行，不能记为通过。推荐总是使用集成脚本，避免误把单元测试当作 MySQL 验收。

## 浏览器

使用 Playwright CLI 对本机页面执行真实操作，检查注册邮件、注册、工作空间、消息、事实、主题同步、手机/桌面、刷新恢复、删除与退出。截图放 `output/playwright/`。截图名称不能代替实际检查结果。

## 扫描

`uv run pip-audit --disable-pip --no-deps -r requirements.txt --format json -o output/pip-audit.json` 与 `npm audit --json`。扫描是执行时的已知公告快照，不等于全部供应链风险都已消除。

已知待测：真实模型输出与计费、完整结构化交互、PDF/OCR、管理端、生产 Nginx/PM2、数据库断连/恢复与大规模负载。
