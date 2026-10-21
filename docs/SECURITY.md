# 安全模型与当前边界

## 已实现

- 严格 MySQL/PyMySQL/utf8mb4 校验，独立随机配置秘密，生产强制 Secure Cookie、MySQL TLS、SMTP TLS，模拟支付生产禁用。
- 密码 scrypt 哈希；随机长会话 Token 仅在 HttpOnly/SameSite=Lax Cookie 中，数据库只保存摘要；单会话与全部会话撤销。
- 注册码六位随机数字、HMAC 存储、10 分钟失效、最多五次错误、单次使用、邮箱发送间隔和 IP/账户频率限制。
- Redis Lua 原子限流并设置 TTL，Redis 故障时认证服务返回 503，不绕过保护。
- 注册、登录、消息、事实、删除、主题写操作均检查 CSRF；SQLAlchemy 参数化查询与服务端资源所属权。
- Jinja2 默认转义、同源资源 CSP；Alpine CSP 构建与 HTMX 禁止 eval/内联指示器样式。
- 不记录密码、验证码、Cookie、数据库连接串或完整对话；错误仅记录分类和请求编号。
- 只有明确确认的记忆进入上下文；对话删除级联清除消息与记忆，不使用缓存恢复删除数据。

## 边界与尚未完成项

- 未实现密码重置、账户注销、管理员 RBAC、审计体系；上线前必须补齐。
- 当前无模型调用、收费业务、文件上传、外部 JD 抓取或任意工具执行入口；对应阶段必须落实完整规范，不能只依靠提示词。
- 本地 SMTP/Mailpit 为开发捕获用途，不投递互联网邮件；开发收件箱仅绑定回环地址。
- Windows Worker 是 SimpleWorker + TimerDeathPenalty 开发模式，没有 Linux Worker 的子进程隔离；生产和资源密集任务必须使用 Linux 原生 Worker。
- 会话设置 Secure=False 仅供本机 HTTP；生产配置校验阻止这一设置。
- WSL 初始安装使用 root 修改系统开发服务配置，生产环境应由运维独立配置并使用最小权限账户。
- 原生 Mailpit 从固定官方 HTTPS release 下载，记录 SHA256、验证 ZIP CRC；该 release 无上游校验文件，不宣称验证过发布者签名。
- Nginx HTTPS、生产备份策略、依赖更新策略和性能压力测试尚未上线验收。
