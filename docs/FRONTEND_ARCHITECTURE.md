# CareerFlow V1 前端架构

## 单一活动前端

活动模板：`app/templates/frontend/`。共享入口为 `frontend/base.html`，页面树分为 `public`、`account`、`admin`、`resume`、`analysis`；公共首页与登录后入口共用 `_landing.html`，不再独立呈现控制台总览。`app/web/frontend.py` 维护工作空间视图映射，其余 HTML 路由明确指向对应新模板。

原有 UI 模板、`app.css`/`refresh.css`/`interface.css` 覆盖栈、`app.js`/`career.js`/`studio.js` 等旧全局事件不参与新页面的资源加载或渲染。旧文件留在原处以保留用户已有未提交工作，不是另一套可切换的产品版本。稳定的 `resume/_document.html` 和 `_sample.html` 继续用于安全的服务端文档/示例渲染。

## 共享与功能模块

- `css/frontend/tokens.css`：浅色/深色、字体、间距、强调色和表面。
- `components.css`：按钮、表单、复选框、单选框、表格、标签、弹窗和状态。
- `shell.css`：基础页面尺寸与响应式；`landing.css` 定义当前产品任务导航、Landing 和管理横向导航。
- `document.css`：文档与 PDF 的独立排版，不包含旧工作台主题。
- `public/account/admin/resume/analysis.css`：按实际页面加载的功能布局，不再建立重复覆盖栈。
- `js/frontend/runtime.js`：同源请求、CSRF、主题、弹窗生命周期和文档缩略图；不保存业务状态。GET 与带 request_key 的幂等操作可在网络失败时有限重试一次，普通账号或无幂等保障的操作不会自动重试。
- `auth.js`：登录/注册、验证码、可继续原操作的登录弹窗。跳转目标使用 URL 查询参数，避免违反严格账号 Schema；登录后重新获取 CSRF，再执行原操作。
- `resume-core.js`：结构化文档、Markdown 安全渲染与模型任务读取；`resume-editor.js`：唯一编辑状态、保存/冲突、板块、照片、AI 审阅、岗位入口与导出；`resume-library/import/templates.js`：对应独立功能。
- `analysis.js`：岗位输入、任务轮询、重试/取消、追问、结果和记录筛选；`analysis_review.js`：逐段选择/编辑/AI 比较与岗位版本保存。
- `admin.js`：既有受保护配置激活接口的表单序列化。

所有业务 API、权限、会员、队列与不可变版本仍在原服务层。此次没有数据库迁移或计费规则变更。

## 构建与验收

`npm run build` → `scripts/build-frontend.cjs`：复制已锁定的 HTMX/Alpine 资源，按新模板树生成 Tailwind utilities；不再构建旧 app.css。没有引入新依赖。

浏览器入口验收：`tests/browser/frontend_refactor.spec.cjs`、`frontend_workflows.spec.cjs`。检查全页路由、新资产独占、桌面/平板/手机、主题、弹窗、文档变更、AI 核对、PDF 与真实测试账号登录。模型与支付使用明确测试提供器；真实账户登录和 CSRF 流程仍走既有后端。

服务端验收：`tests/test_frontend_manifest.py` 防止活动路由或共享壳重新依赖旧 UI；相关权限、段落审阅、会员失败和基础测试使用 MySQL 测试库。

## 体验层补充（2026-10-29）

共享 Token 统一文字层级、动效时长与触控区域；`runtime.js` 提供渐进增强的 `[data-reveal]` 入场及 `cfFieldErrors(form,error)` 字段提示/焦点，减少动效偏好改变时取消入场。默认内容可见，不依赖动画才显示。

登录后 Landing 使用真实已有工作推导下一步；首页流程说明使用原生 details；编辑器的示例标识、预览焦点，以及岗位/审阅/记录的就绪与筛选状态留在所属 feature 控制器中。

本轮设计及逐页审计见 `FRONTEND_REDESIGN_2026-10-29.md` 和 `FRONTEND_EXPERIENCE_AUDIT_2026-10-29.md`。新增 `tests/browser/frontend_experience.spec.cjs` 覆盖三种尺寸下逐页浅/深/系统主题、准备路径、键盘、减少动效、示例与真实内容边界及无效上传。

## 当前 Landing 主导架构

最新入口、导航与逐任务重排见 `FRONTEND_LANDING_ARCHITECTURE.md`。`select.js` 在保留原字段协议的前提下提供全站自定义 combobox/listbox，动态选项和程序赋值可同步。管理/分析不再使用垂直侧栏，编辑器板块定位改为横向。`landing.spec.cjs` 验证统一入口与真实自定义下拉的键盘、指针和状态同步。

## 共享视觉契约

`UI_CRAFT_2026-10-30.md` 对应用户十条高定 UI 规则。`craft.css` 位于功能样式之后，仅定义共享表面、焦点、Grid折叠与流式状态；`craft.js` 提供逐字渲染、两类物理弹簧、原生details增强与复制反馈。应用权重统一映射到主题变量；A4文档排版保持独立。没有更换当前任务入口、自定义下拉或后端业务。

## 产品叙事与任务衔接

见 `PRODUCT_NARRATIVE_2026-10-30.md`。`landing.js` 仅控制标明示例的四步产品演示，键盘可操作，不创建AI任务或写数据；真实操作仍通过原任务页。登录后首页GET进入个性化Landing，最近工作提前；`shell/task_path.html` 为核心页面提供当前位置和审阅/保存入口，编辑器保持紧凑工作区。

## 操作可发现性

见 `ACTION_DISCOVERABILITY_2026-10-30.md`：高频目的地直接导航，简历行内显示分析入口，编辑器所有尺寸保留动作文字并突出保存；岗位使用同一个吸底提交区，长审阅页通过选择数量与锚点衔接原确认保存区。未改变API或内容采用规则。

## 编辑板块状态

见 `EDITOR_SECTIONS_2026-10-31.md`。`hidden_sections` 同时控制定位、表单和文档展示，恢复仍使用设计/板块设置。编辑折叠单独存于控制器局部Set，用Grid与inert同步显示和键盘状态，不写入简历版本。板块设置菜单不参与内容折叠包装。添加操作在标题与列表末尾均有入口，执行后聚焦新增条目。
