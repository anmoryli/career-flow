# MySQL 8.4 LTS

初始修订 `0001_foundation` 建立了 7 张业务表；当前修订及后续表见下方迁移记录。

| 表 | 主要约束/用途 |
|---|---|
| users | 邮箱唯一、主题、显示名、UTC 创建时间 |
| auth_identities | 用户唯一外键、密码哈希 |
| user_sessions | Token 摘要唯一、用户和过期时间索引 |
| email_verification_codes | 邮箱唯一、HMAC、尝试次数与有效期 |
| conversations | 用户外键索引、状态 |
| conversation_messages | 对话外键索引；对话/请求键联合唯一 |
| conversation_memories | 对话外键索引；对话/事实名联合唯一；JSON 值与来源 |

业务表均使用 InnoDB、utf8mb4、utf8mb4_0900_ai_ci。后续迁移已加入积分账户及冻结/结算/释放流水；真实支付尚未实现。

```powershell
uv run flask --app wsgi db upgrade
uv run flask --app wsgi db check
uv run flask --app wsgi db current
```

原生数据库初始化只建库、账户与权限，不替代迁移。请求结束时 Flask-SQLAlchemy 释放会话；连接池使用 pre_ping、回收和有限连接/读写超时。迁移为 MySQL 非事务 DDL，生产执行前须备份并恢复验证。

初始迁移的降级会删除全部业务表，**只在保留的恢复测试库上自动执行**；应用数据库不得直接照搬测试降级命令。外键依赖表先删除，不单独删除支撑外键的索引。

## 原生备份和恢复验证

`uv run python scripts/verify-db-lifecycle.py` 在 `careerflow_restore_test` 执行升级→降级→升级→插入中文/emoji→mysqldump→降级→恢复→验证 21 张表（含迁移表）/版本/内容→返回 base。备份为 `output/restore-test.sql`，不接触应用库，重复执行前必须保证测试库无业务表。

正式备份用 `mysqldump --single-transaction --no-tablespaces --set-gtid-purged=OFF --default-character-set=utf8mb4 careerflow`，凭证从受保护客户端配置读取。当前 Windows/WSL 开发验证使用本地 root socket，不把密码放入命令行。

生产还需：定期全量、binlog 增量、加密存储、访问控制、异机恢复演练与业务留存策略。当前的开发库恢复测试不代表完成生产灾备。
# 2026-10-24 新增迁移

此前 head `05373fa1964b`：`c1282dd22221` 新增简历/版本/岗位，`066d81b874d1` 新增积分账户/诊断/回答/AI任务/流水，`05373fa1964b` 新增PDF导入，当时共16业务表。均使用InnoDB/utf8mb4，保留原7表和历史数据，无删除原表或数据重写。

2026-10-24 新增 `a8f6d92b37e1`：`users.is_admin` 默认关闭；增加 `config_revisions`、`active_configs`、`admin_audit_entries`。当前 head 为 `a8f6d92b37e1`，共19业务表。配置版本及审计与管理员账户受外键约束，删除管理员前须按数据保留策略处理其历史记录。服务密钥仅以 Fernet 密文存于配置版本，独立加密密钥来自本地环境变量。

后续 `9c75e89d41a0` 新增 `structured_interactions`，按对话和 AI 操作关联经过验证的结构化表单、状态与提交结果；当前 head 为该版本，共20业务表。测试库已验证升级及 Alembic 差异检查；开发库升级前备份保存于忽略提交的 `output/careerflow-before-interactions-*.sql`。

简历版本文档为不可变JSON快照，其他业务关联为独立外键；岗位指向具体版本。用户行锁串行化账务和幂等写入，关键读取使用MySQL当前读，避免认证查询建立的旧快照导致并发重扣。账本的冻结/结算/释放分别记录，任务/流水有唯一约束。

PDF二进制仅在受限导入任务完成前暂存在MEDIUMBLOB；完成/失败/恢复后清空，提取文字和核实后的简历单独保存。应用不在启动时create_all。

新增迁移的升降级和备份恢复使用原有隔离恢复库脚本。降级会删除新增功能数据，只能在已备份且明确授权的环境执行；本次验证仅操作保留的测试库。
