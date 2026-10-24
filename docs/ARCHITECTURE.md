# 实际架构 · V1

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

应用工厂和 MySQL 表选项实现分别参考 [Flask 官方说明](https://flask.palletsprojects.com/en/stable/patterns/appfactories/) 与 [SQLAlchemy MySQL 方言说明](https://docs.sqlalchemy.org/en/20/dialects/mysql.html)。
