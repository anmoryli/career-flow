# 真实模型质量验收 · 2026-11-03

Q03（基于评测改进提示词）与 Q04（真实模型质量验收结果与限制）的验收记录。
所有用例均为合成简历，未使用任何真实用户数据；模型调用只发生在本地开发环境。

## 1. 结论摘要

| 项 | 结果 |
|---|---|
| 编排链路（deepagents + Qwen2.5-7B 免费版） | 6 个合成用例 **4 通过 / 2 失败** |
| 单发链路（同一评测集，2026-10-31，pydantic-ai 栈） | 6 个用例 **4 通过 / 2 失败** |
| 提示词改进带来的变化 | 从 0/6（链路崩溃）到 4/6；失败项与单发不同 |
| 生产模型（deepseek-flash） | **未评测**：产品策略中未配置单价，预算护栏按设计拒绝运行 |
| 真实用户样本质量 | 未验证（需真实用户与运营样本，X03） |

**不能声称**：编排链路优于单发链路；当前结果证明的是"编排在免费 7B 模型上可用（4/6），但质量与成本均未达到上线标准"。

## 2. 环境与版本

| 项 | 值 |
|---|---|
| 时间 | 2026-11-03 20:25–20:35（GMT+8） |
| 模型 | `Qwen/Qwen2.5-7B-Instruct`（SiliconFlow 免费额度） |
| 模型配置 | `active_configs.model` v7（revision 11），主 Qwen，备 deepseek-flash / deepseek-v4-pro |
| 提示词配置 | prompt v1（无覆盖指令），有效提示 = `agent_orchestrator` 内编排 + 分板块 + 撰写三段提示 |
| 编排栈 | deepagents 0.7.32 / LangGraph 1.2.19 / langchain-openai 1.7.3 |
| 评测工具 | `scripts/evaluate-product-model.py --live --orchestrated --budget-cny 5 --pace-seconds 70` |
| 结果文件 | `output/product-model-orchestrated-final.json`（另有 v1–v4 过程留痕） |
| 费用 | ¥0（免费模型）；价格预检记录在报告 `pricing_preflight`，含页面 SHA-256 |

## 3. 评测集与门禁

6 个合成用例：社招（experienced）、应届（graduate）、转行（transition）、缺证据（missing_evidence）、中英双语 JD（bilingual）、多段深度证据（deep_evidence）。每个用例经 6 项确定性检查，全部通过才算 pass：

1. `schema_and_exact_evidence` — 结构合法、证据必须逐字来自原文
2. `all_requirements_checked` — JD 的每条要求都有结论
3. `related_original_located` — 该有原文的用例至少要引出简历原文
4. `single_question` — 最多一个追问
5. `no_forbidden_new_claim` — 建议中不得出现用例预设的编造词（如"精通SQL""提升30%"）
6. `insertable_replacements` — 建议文本可直接替换原文

## 4. 结果（编排链路，免费 Qwen 7B）

| 用例 | 结果 | 模型调用 | tokens | 耗时 |
|---|---|---|---|---|
| experienced | 通过 | 12 | 44 881 | 54.9s |
| graduate | 通过 | 13 | 49 219 | 80.6s |
| transition | 通过 | 7 | 24 433 | 31.8s |
| missing_evidence | 失败（ValueError） | — | — | 25.6s |
| bilingual | 失败（ValueError） | — | — | 31.0s |
| deep_evidence | 通过 | 5 | 19 875 | 32.9s |

- 通过的 4 例：五项维度齐全、要求全覆盖、有原文引用、追问单条、建议可直接插入。
- 失败 2 例：编排层结构化输出未通过校验（`ValueError`）。两例在单独复跑时均通过（missing_evidence 6 次调用 / 21 974 tokens；bilingual 曾在 v4 通过），说明失败是小模型输出的**非确定性**，不是稳定复现的缺陷。
- 成本量级：单次分析 5–13 次模型调用、2–5 万 tokens；单发链路约 1 次调用、2–3 千 tokens。**同质量下编排贵约 10–20 倍**。

### 与单发链路对照（不是同一技术栈，仅作参考）

2026-10-31 的 `output/product-model-live.json`（pydantic-ai 单发，同 6 用例）同样是 4/6，失败项为 transition 与 bilingual。本次编排在 transition 上通过、在 missing_evidence 上失败，属于互换，**整体通过率没有提升**。

## 5. Q03 提示词迭代记录

| 轮次 | 结果 | 主要问题 | 处理 |
|---|---|---|---|
| v1 | 0/6 | 每次运行在首次模型调用前崩溃 | 用量收集器不是真的 `BaseCallbackHandler`，改用基类 + `run_inline` |
| v2 | 0/6 | 400 报错、429 限流、单次调用超时 | SiliconFlow 非流式请求不能带 `stream_options`；子代理改为串行（`max_concurrency=1`）；单次调用超时 60→120s |
| v3 | 1/6 | 写入者编造 requirement 编号（J3/J4/J5） | 每次运行动态注入**实际存在的编号清单**，并给出第一个不存在编号作反例 |
| v4 | 1/6 | 建议引用不存在的 target 编号；要求覆盖不全；有原文却判 missing；单例 45 次调用 | 注入 target 编号；要求"每条要求恰好一条结论，无原文以 missing 补齐"；说明 education/projects/summary 同样算证据；限制每板块只调用一次，`recursion_limit` 120→80 |
| final | 4/6 | 小模型非确定性 | 见上表；保留为当前基线 |

迭代中修复的**产品代码缺陷**（非提示词）：

1. `_UsageCollector` 鸭子类型回调在 langchain-core 1.x 下使每次编排立即失败。
2. 编排模型沿用单发的 `stream_options` 设置，SiliconFlow 对非流式请求直接 400。
3. 进程级缓存的 httpx 连接池被跨事件循环复用，连续运行时出现 `Event loop is closed` / `client has been closed`；改为每次调用独立客户端并显式关闭。
4. 子代理并发触发供应商限流；改为串行。
5. 编排模型单次调用 60s 超时偏紧；提高到 120s。
6. 编号越界会让整次诊断作废，而模型看不到编号边界；提示词动态注入编号空间。
7. 写入者可以丢证据、漏要求；提示词加入覆盖与证据保留规则。

## 6. 限制与未验证项

- **生产模型未评测**：`deepseek-flash` 在产品策略里没有配置单价，`--allow-paid-model` 会拒绝运行（预算无法核算）。要评测需先在管理端配置该模型的真实单价，再由授权人确认。
- **免费 7B 不稳定**：失败用例单独复跑可通过；不能把 4/6 当作"编排质量达标"。
- **LangGraph checkpoint 不可用**：本机 Redis 无 RediSearch（`FT.INFO`），`RedisSaver` 降级为无持久化，仅记录告警；编排中途崩溃只能靠整次重试恢复。
- **成本**：编排单次 2–5 万 tokens，免费额度下还会触发 TPM 限流（本评测用 70 秒/例的间隔规避）。生产使用付费模型前应评估单次成本与会员额度。
- **质量维度有限**：只覆盖真实性、证据、可插入性、结构、单问题与禁止编造；不含真实招聘方反馈、ATS 实测或录用结果。
- 未对 `deepseek-v4-pro`（推理模型）跑编排评测；历史记录显示其单发诊断易超时。

## 7. 建议

1. 上生产前先用**生产模型**重跑本评测，并把单价配好让预算护栏可核算。
2. 若 7B/免费模型仍是主要供应商，建议默认回落单发链路（一次调用、成本低 10 倍），编排仅用于高价值会员任务。
3. 编排稳定性继续收敛：写入者输出可考虑服务端确定性合并（分析师结论直接合并，写入者只产出评分与建议），减少小模型改写编号的机会。
