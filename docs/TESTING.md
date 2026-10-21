# 测试方法

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
