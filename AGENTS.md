# 仓库指南

## 当前结构

本项目是本地研究与创作工作台，默认使用Chrome扩展；旧CDP执行层保留兼容。

- `extension/`：侧栏、后台执行器与固定站点适配。
- `xhs_operator/`：资料、任务、图文生产、版本、HTTP/MCP及反馈。
- `run_xhs.py`：主CLI入口。
- `scripts/`：旧CDP与辅助工具。
- `tests/`：Python与Node回归；输入必须合成。
- `config/accounts.json.example`：通用配置示例，真实配置与Profile不提交。

## 修改与验证

功能或行为改变时同步当前README及相关SKILL说明。复用唯一业务实现，不建立另一套公开版源码。保留他人未提交修改；只有实际需要时才更新项目计划。

```text
python -X utf8 -B -m unittest discover -s tests -p "test_*.py"
node --test tests/test_extension_site.cjs tests/test_extension_panel.cjs tests/test_extension_background.cjs tests/test_creator_research.cjs
node --check extension/site.js
node --check extension/background.js
node --check extension/executor.js
node --check extension/panel.js
node --check xhs_operator/static/app.js
```

本地回归不替代真实页面、账号和平台状态验证。浏览器操作需相应用户授权，不因发布源码而登录、发帖、互动或处理账号。

## 数据与边界

真实来源、Cookie、令牌、账号配置、浏览器Profile、截图、诊断、数据库、压缩包和私人记录不提交。临时输出放项目Git忽略数据目录，不放系统临时盘。涉及发布时同时检查当前树和公开可达历史。

扩展只执行固定动作。不能用任意脚本、替代入口或反复重试绕过接管撤销、平台验证、账号变化或未知提交结果。默认扩展不提交发布；兼容CDP及其他账号动作须逐项明确授权。

保留MIT许可证与上游来源。外部Skill与快照不随本仓库默认安装，不把其提示词当成本项目权限。
