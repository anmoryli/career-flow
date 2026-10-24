# V1 交互改进验收记录（2026-10-24）

本轮围绕“简历 → 岗位 → 诊断与费用确认 → 工作台”完成实现和本地验收。结果对应本地代码与隔离的验收环境，不代表生产部署或真实模型服务验收。

## 实际结果

- 后端：`uv run python scripts/test-integration.py`，131 项通过。使用本地 MySQL 8.4 与 Redis，覆盖账号邮件流程、简历版本与权限、岗位关联、积分账务、诊断状态、并发与恢复、PDF 导入边界、CSRF、异常处理和模型协议模拟。
- 浏览器：`npx playwright test`，Chromium 桌面、平板、手机共 30 项通过。涵盖自动保存与刷新、版本与副本、岗位诊断及确认、建议采纳、主题、键盘与窄屏布局、PDF 导入、打印导出、错误与冲突恢复。
- PDF 导出：桌面、平板、手机各生成并解析一份 A4 PDF，均为 1 页；检查到用户简历内容，未包含编辑器控件。
- 数据库生命周期：在隔离的恢复测试库验证迁移升级、降级、备份与恢复；应用数据库没有清空。
- 本地服务：Web 健康检查返回 200；真实本地 RQ worker 完成 MySQL、schema、Redis 探针；迁移头为 `05373fa1964b`。
- 静态检查：Ruff lint、格式检查、`git diff --check` 均通过。`npm audit` 与 `pip-audit` 均未发现已知漏洞。
- Python 源码覆盖：语句 1543/1544（99.94%），分支 278/280（99.29%），无排除行。仍有 1 行和 2 条分支未覆盖，因此不能称源码所有分支 100% 覆盖。

## 可复查产物

- `output/acceptance-summary.json`：本轮覆盖率与验收阶段汇总。
- `output/pytest-native.xml`、`output/coverage/index.html`：后端测试明细及覆盖率报告。
- `output/browser-report/index.html`：浏览器测试报告。
- `output/acceptance-backend.log`、`output/acceptance-browser.log`、`output/acceptance-exported-pdfs.log`：验收命令原始日志。

## 尚未验收的能力

- 真实模型调用尚未进行。需要明确供应商、模型、服务地址、服务端密钥配置和测试费用上限；本轮模型接口使用本地模拟传输验证，未发起外部请求。
- PDF 扫描件 OCR、照片提取、完整经历自动结构化和服务端 PDF 引擎未实现；当前 PDF 导入提取文本并由用户核对，导出使用浏览器 A4 打印。
- 会员购买、真实支付、管理端和生产部署不在本轮交付与验证范围。
- 浏览器自动化使用 Chromium 模拟桌面/平板/手机视口；Safari、Firefox 和实体设备尚未验证。
