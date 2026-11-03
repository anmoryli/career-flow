# 实际架构 · V1

2026-10-26：工作区历史页由所属用户的 Resume、JobTarget、已完成 AIOperation 和 Conversation 组合展示；积分页从成功操作读取实际消费，服务端账本仍保持冻结、结算、释放；用户点击 AI 操作后直接启动，完成后才显示实际消耗。粘贴文字与 PDF 提取文字走既有简历 AI 操作表和队列，生成待核对的 ResumeDocument，用户应用后才触发简历保存。个人显示名称通过 `/settings/profile` 的 Pydantic 校验和现有 CSRF/会话保护更新，无数据库结构变更。

2026-10-27：诊断积分冻结上限以字符长度保守估算输入 Token，并使用服务端 max_tokens 上限，覆盖所有配置模型及每模型两次尝试。会员与积分套餐由版本化管理员配置保存；开发/测试可在显式开关下完成本地测试购买并立即入账，生产仍禁止模拟支付。年度会员最后一个部分周期按天折算，不新增账务表或数据库迁移。


模块化单体，尚未实现的业务不预先宣称完成。

| 目录 | 职责 |
|---|---|
| `app/__init__.py` | 应用工厂、安全响应头、错误与请求上下文 |
| `app/config.py` | 统一 DATABASE_URL 配置、连接池、生产启动约束 |
| `app/models/` | 19 个 SQLAlchemy 2.x 模型：认证/记录、简历/版本/岗位、诊断/任务/账本、导入、管理员配置/审计 |
| `app/services/auth.py` | 验证码、密码认证、可撤销长期会话 |
| `app/services/admin_config.py` | 管理员配置版本、密钥加密、发布回滚与运行时读取 |
| `app/services/conversations.py` | 所属权、消息幂等、事实记忆、受限上下文 |
| `app/services/infrastructure.py` | MySQL/Alembic/Redis 就绪检查与原子限流 |
| `app/web/` | Blueprint，输入 Schema 校验，服务调用和响应组织 |
| `app/schemas.py` | 严格输入模型及结构化消息协议的初始子集 |
| `app/templates/` | Jinja2 服务端页面，默认 HTML 转义 |
| `app/static/` | 统一 CSS Token、Tailwind 构建、本地 HTMX/Alpine CSP 资源 |
| `app/worker.py` | RQ 原生 Worker 入口 |
| `migrations/` | Alembic 修订，不使用启动时 create_all |

MySQL 是唯一业务数据源。Redis 承担限流和队列，不作为消息/记忆的权威存储。匿名首页不依赖数据库；有会话 Cookie 时，业务资源访问先查询服务器会话。

请求链：CSRF/身份 → Pydantic 输入 → 所属权 → 服务事务 → HTML 或 JSON 响应。所有错误响应不返回原始异常、SQL 参数或连接字符串。

消息写入锁定当前对话行，用 `(conversation_id, request_key)` 唯一约束消除重试重复；同一请求键携带不同内容返回 409。对话删除采用数据库级联，消息和记忆同步失效。

个人记录上下文只包含所属用户当前对话、确认记忆和近期历史，按预算裁剪并封装为 `untrusted_user_data`。诊断独立保存JD/简历版本/真实回答的快照，经PydanticAI适配器输出并校验；没有自动摘要/长期偏好或任意AI工具。服务边界、账务和真实性限制见 `UX_IMPLEMENTATION_2026-10-24.md`。

简历逐条 AI 建议使用 `app/services/resume_ai.py`：操作关联用户简历与保存修订号，引用同一积分冻结/结算/释放流水；RQ Worker 只处理已入队操作，调用模型期间不持有 MySQL 事务。输出经 Pydantic 校验后作为待确认建议存储，用户在弹窗中确认才触发普通简历版本保存。简历板块顺序、显隐和 Markdown 原文都保存在版本 JSON 文档中。

应用工厂和 MySQL 表选项实现分别参考 [Flask 官方说明](https://flask.palletsprojects.com/en/stable/patterns/appfactories/) 与 [SQLAlchemy MySQL 方言说明](https://docs.sqlalchemy.org/en/20/dialects/mysql.html)。


## 2026-10-27 Membership and billing

The user-facing plans are monthly CNY 39 and quarterly CNY 99. AI operations use membership entitlements and free usage limits; they do not debit points. Existing credit ledger tables and fields are legacy compatibility structures, not the basis for plans or user-facing billing.

## 2026-11-11 deepagents 编排（岗位诊断与简历 AI）

`app/services/agent_orchestrator.py` 基于 deepagents 0.7 / LangGraph 实现岗位诊断与简历 AI 的多代理编排，分别由 `DIAGNOSIS_AGENT_ENABLED`、`RESUME_AGENT_ENABLED`（默认均关闭）控制；编排仅对会员任务生效，免费匹配与注入 provider 的测试路径保持单发不变。

- 诊断编排：主代理用 `write_todos` 规划并分派 → `section-analyst` 子代理按简历板块分组核对证据（`response_format=SectionFindings`）→ `diagnosis-writer` 子代理合并产出 `ReferencedDiagnosis`。模型经 `langchain-openai` 适配现有管理员模型配置与多模型路由。
- 简历编排：单条改写由主代理分派 `rewrite-writer` 子代理（`response_format=ResumeAIOutput`）；简历整理（compose）由主代理分派四个板块起草子代理（profile/experience/project/credential，各自结构化输出）再由 `compose-compiler` 合并为 `ResumeComposeOutput`。
- 准确性不变式：编排层零自由度——子代理强制结构化输出；诊断走既有 `resolve_references`（J/E/T 编号锚定）与 `validate_output`；简历改写/整理走 `resume_ai._build_result`（字段长度上限、照片/技能数/体积限制、未经确认数字子集校验）。编排与单发共用同一份确定性门禁，任何违规都让该次编排失败。
- 降级链：编排失败自动重试 1 次；两次均失败则降级到确定性单发管线（原多模型 fallback × 2 次尝试），会员任务绝不因编排层故障而失败。
- 资源上限：诊断板块分组最多 24 组（超出尾部合并）、每次编排 480 秒超时、`recursion_limit` 诊断 120 / 简历 60；每次 LLM 调用经 callback 收集 input/output/total tokens，与单发路径一样写入 `ModelCallUsage` 计费流水，`attempts` 语义一致。
- 测试：`tests/test_agent_orchestrator.py` 覆盖分组/合并/用量收集/结构化提取/flag 默认值；`tests/integration/test_diagnosis_transport.py` 与 `tests/integration/test_resume_ai.py` 覆盖编排成功记账与失败降级。编排分支要求测试环境无 provider 注入，存量测试不受影响。
