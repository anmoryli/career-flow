# V1 用户流程测试矩阵 · 2026-10-24

范围：本次交互改进。业务路径覆盖、源码语句覆盖和源码分支覆盖是不同指标；不得以 E2E 通过宣称任意输入、全部浏览器或全部源码分支均已验证。最新结果在 `output/pytest-native.xml`、`output/coverage/index.html` 和 `output/browser-report/index.html`。

| 路径 | 正常 / 失败 / 边界 | 自动化证据 |
|---|---|---|
| 注册登录 | 真实本地邮件、单邮箱、注册、登录、会话替换；重发限流、失效验证码、SMTP/TLS、错误密码、撤销 | `test_mysql.py`、`test_runtime_paths.py` |
| 简历保存 | 自动保存、重试、刷新恢复、标题；超长、CSRF、XSS、未登录、跨用户、版本冲突 | `test_career.py`、`test_career_paths.py`、浏览器 draft/failure/conflict |
| 编辑结构 | 经历新增/删除/上下移；数量限制、删除确认、空内容、模块显示 | Schema 测试、浏览器编辑器 |
| 模板照片 | 三套模板、真实图片解码、尺寸/类型拒绝、版式设置保存 | 模板/照片用例、浏览器模板与版式 |
| 版本副本 | 载入历史、另存、基础简历保留；旧 revision、幂等键内容/来源冲突 | MySQL save/copy、浏览器 history/conflict |
| 打印 | 版本快照、浏览器 A4 PDF；示例/联系方式确认、空模块隐藏 | 浏览器导出实际 PDF、print API |
| PDF 导入 | 上传/RQ/提取/人工确认/保存；非PDF、损坏、无文字、超大、页数/文字限额、队列故障、越权 | PDF 服务/API、真实 RQ、浏览器 PDF |
| 岗位 | 保存 JD、版本关联；空内容、无效链接、越权、幂等冲突、删除限制 | job/API 用例、浏览器完整流程 |
| 费用 | 预估/确认/冻结；未配模型、过期、余额不足、状态变化、重复与并发确认 | billing/state/concurrent 用例 |
| 模型执行 | RQ/结构校验/原文校验/结算；超时、非法 JSON、虚构证据、路径、费用缺失、一次重试 | 失败参数化、真实 RQ、MockTransport 协议 |
| 取消中断 | 释放、忽略迟到结果；重复取消、崩溃恢复、队列故障 | cancel/recovery、worker、并发用例 |
| 追问 | 单问题、持久化、跳过、十轮限制；重复回答、旧 revision、只读 | answer/state 用例 |
| 报告优化 | 五维、证据、编辑/选择建议、核实后副本；无效编号、未确认、原文不符、跨用户、只读 | Schema/服务/API、浏览器完整流程 |
| 工作台账本 | 真实最近简历、岗位、报告、流水；空状态、未配置模型、零余额 | 页面/主题矩阵、credits API |
| 响应式主题 | 1440/820/390；浅色/深色/系统；键盘、抽屉焦点、横向溢出 | Playwright desktop/tablet/mobile |
| 数据并发 | MySQL8.4、外键、事务、迁移；认证旧快照下并发创建/冻结、重复 worker | MySQL + `test_concurrent_workflows.py` |
| 恢复 | 隔离库升级/降级、mysqldump、恢复中文/emoji与迁移版本 | `verify-db-lifecycle.py` |

## 真实性边界

- MySQL 测试仅用 `careerflow_test`；恢复仅用 `careerflow_restore_test`，不清空应用库。
- 浏览器测试服务器仅在 `scripts/e2e-server.py` 提供测试会话与明确标记的输出，不注册到正式应用。端口 8011、Redis DB15。
- 模型协议使用 HTTPX MockTransport；业务错误使用仅 TESTING 可用适配器，不代表真实模型、供应商网络或真实计价验收。
- 真实 AI 等待供应商/模型/服务端密钥与测试费用上限。
- PDF 目前仅文字提取与人工核对；OCR、照片提取、完整经历自动结构化、服务器 PDF 引擎未实现。浏览器打印不是服务器导出。
- 会员、购买积分分类、真实支付、管理端、生产部署不在本次已交付范围。
- 浏览器为 Chromium；Safari/Firefox、真实手机硬件和任意长简历版面尚不能宣称全部兼容。
