# MySQL 8.4 LTS

当前修订：`0001_foundation`。7 张业务表及 `alembic_version`。

| 表 | 主要约束/用途 |
|---|---|
| users | 邮箱唯一、主题、显示名、UTC 创建时间 |
| auth_identities | 用户唯一外键、密码哈希 |
| user_sessions | Token 摘要唯一、用户和过期时间索引 |
| email_verification_codes | 邮箱唯一、HMAC、尝试次数与有效期 |
| conversations | 用户外键索引、状态 |
| conversation_messages | 对话外键索引；对话/请求键联合唯一 |
| conversation_memories | 对话外键索引；对话/事实名联合唯一；JSON 值与来源 |

业务表均 InnoDB、utf8mb4、utf8mb4_0900_ai_ci，用户与对话外键采用 CASCADE。未引入余额、支付等未经实现的账务表。

```powershell
uv run flask --app wsgi db upgrade
uv run flask --app wsgi db check
uv run flask --app wsgi db current
```

原生数据库初始化只建库、账户与权限，不替代迁移。请求结束时 Flask-SQLAlchemy 释放会话；连接池使用 pre_ping、回收和有限连接/读写超时。迁移为 MySQL 非事务 DDL，生产执行前须备份并恢复验证。

初始迁移的降级会删除全部业务表，**只在保留的恢复测试库上自动执行**；应用数据库不得直接照搬测试降级命令。外键依赖表先删除，不单独删除支撑外键的索引。

## 原生备份和恢复验证

`uv run python scripts/verify-db-lifecycle.py` 在 `careerflow_restore_test` 执行升级→降级→升级→插入中文/emoji→mysqldump→降级→恢复→验证 8 张表/版本/内容→返回 base。备份为 `output/restore-test.sql`，不接触应用库，重复执行前必须保证测试库无业务表。

正式备份用 `mysqldump --single-transaction --no-tablespaces --set-gtid-purged=OFF --default-character-set=utf8mb4 careerflow`，凭证从受保护客户端配置读取。当前 Windows/WSL 开发验证使用本地 root socket，不把密码放入命令行。

生产还需：定期全量、binlog 增量、加密存储、访问控制、异机恢复演练与业务留存策略。当前的开发库恢复测试不代表完成生产灾备。
