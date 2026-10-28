2026-10-26 AI 收费交互调整：用户点击即启动简历润色、粘贴整理或岗位报告；前端不再显示积分预估或费用二次确认，完成后显示实际扣分。`npx.cmd playwright test --grep "resume to job to report|paid resume suggestion|pasted facts"` 使用隔离 MySQL 测试库、每轮新建测试用户和明确标记的测试 Provider，在桌面/平板/手机验证完整岗位报告及实际扣分、逐条润色、首次粘贴简历整理，共 9 passed。测试输出不代表真实模型供应商验收，未触发真实支付。

2026-10-27 ????????? MySQL ?????? 5 ?????????? 61 ????126 ?????????????????????????????????????????????????????

# 测试方法

2026-10-25 简历编辑交接任务回归：`uv run python scripts/test-integration.py` 在原生 MySQL/Redis 上为 173 passed、1 skipped，覆盖率 93%；随后新增的跨用户 AI 任务状态校验、队列不可用退款与未确认报价允许删简历用例，定向运行 `uv run python scripts/test-focus.py tests/integration/test_resume_ai.py -q` 为 7 passed。`npx.cmd playwright test` 为 64 passed、2 skipped；弹窗居中调整后定向运行 6 passed，覆盖桌面、平板、手机的逐条建议及接受/保留原文。`npm.cmd run build`、`uv run ruff check app tests scripts/e2e-server.py scripts/verify-db-lifecycle.py` 和 `git diff --check` 通过。`uv run python scripts/verify-db-lifecycle.py` 在隔离恢复库完成新迁移升降级和备份恢复，开发库升级后 `flask db check` 无差异。简历改写只使用明确标记的测试模型，未调用真实模型、未进行生产部署。

2026-10-25 本地实测：`uv run python scripts/test-integration.py` 156 passed，覆盖报告 96%；`uv run python scripts/verify-db-lifecycle.py` 在隔离 MySQL 库完成升级、降级、备份与恢复；`npx playwright test` 最终显示 39 passed，涵盖桌面、平板和手机。Ruff 检查与格式检查、`npm run build` 通过。真实 QQ SMTP、MiMo 收费任务端到端、生产部署和全部路径 100% 覆盖尚未验证。

同日随后使用已配置的 MiMo 接口和合成英文简历/JD，完成一次结构化诊断输出及服务端证据校验，实际使用 1822 token；另一次普通文本请求返回 49 token。两次复杂结构化尝试曾因输出未符合 Schema 失败；现有执行路径会按规则重试并释放失败任务的冻结积分。该联调未使用真实用户简历、未走积分确认/冻结任务，不能视为收费端到端验收。

OCR 增量验证：加入 Tesseract 后完整 MySQL/Redis 集成套件 158 passed；新增真实扫描 PDF 用例后定向运行 `tests/test_pdf_limits.py` 5 passed。另用独立合成中文扫描页实测识别到“产品”一词。完整套件的 158 项是在最后新增原生 OCR 用例前运行，不能将其算入该次完整回归。

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


## 2026-10-26 PDF 导入与 A4 导出

- `uv run pytest tests/test_pdf_limits.py -q`（使用项目内 `.tools/tesseract`）：10 passed。覆盖文字 PDF、扫描页 OCR、中文扫描简历字段、文字与嵌入头像混合 PDF、结构化字段、协议前缀清理、损坏/空 PDF、图片误识别过滤与资源限制。
- Playwright PDF 导入/导出定向回归：桌面 4 passed；简历工作流在桌面、平板、手机 3 passed。实测较多内容压为 A4 单页，极长内容触到压缩下限后保留分页。
- 本机 MySQL 账户 `anmory` 的原 PDF 经前端重新导入并更新现有简历版本；确认头像保存并显示、教育/项目/技能/荣誉字段入库、主页和 GitHub 不含 `https://`，列表与历史仍可见。该手动流程未替代完整 MySQL 集成套件。
