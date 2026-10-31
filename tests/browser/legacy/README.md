# 归档：重构前旧界面的浏览器用例

2026-10-31 分类取证后归档（`git mv`，历史可追溯）。这 5 个文件断言的选择器（`.workspace-home-greeting`、`.overview-orbit-a`、`.billing-plan-card`、`data-ui-form="auth"` 等）只存在于已停止渲染的旧模板树（`templates/workspace/*`），在当前单一生效前端树（`app/templates/frontend/**`）下必然失败：

| 文件 | 归档前桌面端结果 |
| --- | --- |
| workflow.spec.cjs | 2 passed / 42 failed |
| studio.spec.cjs | 0 passed / 5 failed |
| paragraph-review.spec.cjs | 0 passed / 3 failed |
| redesign.spec.cjs | 0 passed / 2 failed |
| overview-detail.spec.cjs | 0 passed / 2 failed |

对照基线（origin/main 254dc75，仅桌面端）同样失败，属重构遗留而非本轮回归。

其中被新用例覆盖的能力：
- 旧 `overview-detail` 的「岗位描述安全 Markdown」→ `tests/browser/job_description.spec.cjs`（新界面结构）。
- 其余流程（登录弹窗、工作台首页、逐条建议审阅等）已由 `frontend_*`、`editor_*`、`craft`、`landing`、`product_completion` 覆盖。

后续计划：按新前端重写仍有价值的场景（如管理端操作路径），重写一个、回迁一个；不整批复活。
