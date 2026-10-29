# 岗位诊断超时修复 · 2026-10-29

## 依据与边界

任务 34 原日志显示两次 ModelAPIError，分别约 31 秒和 30 秒，没有保存原始异常原因，因此不能追溯断言是连接还是读取超时。原调用使用非流式完整 JSON、30 秒网络超时。硅基流动建议长输出采用流式请求以避免等待完整结果超时；HTTPX 的 read timeout 是两次接收数据之间的等待时限，而非总生成时间。

- https://docs.siliconflow.cn/docs/userguide/faqs/misc
- https://docs.siliconflow.cn/docs/userguide/capabilities/text-generation
- https://www.python-httpx.org/advanced/timeouts/
- https://pydantic.dev/docs/ai/core-concepts/output/

## 修改

诊断改用 PydanticAI run_stream/get_output，完整接收、校验后返回；不持久化部分结果。连接/写入各 10 秒，连接池等待 5 秒，读空闲 45 秒，单次完整尝试硬上限 90 秒。

解包 ModelAPIError → SDK → HTTPX 异常，恢复既有每模型最多两次及备用切换策略；认证和余额错误仍不切换。失败日志仅记录类型、状态、尝试号、模型序号及耗时，不输出异常正文、凭证或简历。错误提示可正确识别被包装的读取超时。

RQ 时限为候选模型去重数量 × 2 × 90 秒 + 30 秒结算余量；运行中超时回收再留 30 秒余量，避免还没尝试备用模型就被旧 120 秒任务时限或 5 分钟回收规则终止。排队回收与简历任务保持原规则。无数据库迁移、无 API 字段变更。

## 验证

- 单元回归 37 passed，含本地真实 HTTP SSE 分块传输总时长超过读空闲时限仍成功、整体截止时间、完整结构化结果与用量、包装异常识别。
- 真实隔离 MySQL 定向集成 45 passed，含主模型两次包装超时后备用成功、全部六次失败不扣费、运行中任务回收边界，以及现有诊断和简历任务回归。
- 扩大边界回归 40 passed、1 failed：现有报告页面未提交修改删掉“稍后回来可接着查看”，与 test_running_report_stays_visible_and_diagnosis_shows_progress 的文案断言不符；本次没有修改该页面或删除断言。
- 仅检出 Git 暂存区文件到隔离目录再次运行适配器及 MySQL 回归，22 passed，确认不依赖其他未提交实现。
- 本地 Web 与空闲 Worker 已重启加载修复；未自动重跑失败任务。
- Ruff 通过。供应商模型列表此前 GET 验证成功；本轮没有发起收费生成请求，不能视为真实供应商生成成功验收。
