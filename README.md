---
git_mode: independent
---

# 小红书研究与创作工作台

Chrome 扩展连接你指定的小红书标签页，在本地保存正文、图片、评论样本与来源，再生产可审阅的完整图文。当前版本 **0.2.7**。

扩展、本地资料库与内容模型分离。支持 MCP 客户端、已有 Codex CLI 登录或明确配置的兼容模型 API；默认不替用户点击正式发布。无需复制 Chrome Cookie，也不经过第三方中转服务。

本项目基于 [white0dew/XiaohongshuSkills](https://github.com/white0dew/XiaohongshuSkills) 的 MIT 执行层继续开发，保留原作者版权与来源；不是小红书官方产品。来源与许可证见 [THIRD_PARTY.md](THIRD_PARTY.md)。

## 能做什么

- **研究与留存**：在绑定页搜索、打开指定笔记、核对笔记ID、读取正文与已加载评论，保存实际取得的图片。列表卡片不冒充完整详情，缺图与覆盖范围分别记录。
- **完整图文生产**：本地图文卡片、纯文案与原生文字配图；支持写作提示词、参考文案、编辑、版本审阅及完整图文包下载。原生配图短文合计最多500字符，发布正文独立保留。
- **只调研／找机会**：保存需求条目、来源、时间和待核实条件；不强制生成文章，不自动联系、投递或接单。
- **创作者平台预览**：核对同一账号，在空白编辑器填写并检查图文；已有不同内容拒绝覆盖。支持受限的笔记管理、草稿和四类发布入口检查。
- **后台数据回收**：按笔记ID读取列表、审核标签、浏览、赞、收藏、评论与分享，保存为本地观察，供后续创作参考。不推断未取得的曝光或公开展示状态。
- **可中止的接管**：你自己浏览时可随手收集；主动开启接管后AI才可操作。停止、账号变化、断连、平台验证或页面失效时暂停，不自动重放未完成上传。

默认扩展没有评论、点赞、私信、删除、批准或正式提交发布工具。原 CDP 脚本保留额外能力，仅在使用者明确选择并授权时使用；两条入口的能力不能混同。

## 安装与启动

需要 Python 3.11+、Chrome 116+。运行模型还需相应客户端／CLI／API；本地工作台本身不要求 API Key。Node.js 18+ 仅用于扩展回归测试。

```powershell
git clone https://github.com/yehuioc/XiaohongshuSkills.git
cd XiaohongshuSkills
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -X utf8 -B run_xhs.py serve --port 8914
```

macOS／Linux 使用 `.venv/bin/python` 替换上面的 Python 路径；真实浏览器验收主要覆盖 Windows Chrome，其他系统兼容性仍需自行核对。本地中文卡片需要中文字体；当前渲染器识别Windows中文系统字体或 `/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc`，未找到时明确报错。

打开 <http://127.0.0.1:8914/>。服务仅监听本机；扩展的本机主机权限固定为8914端口。

1. 打开 `chrome://extensions`，开启开发者模式，加载本项目 `extension/` 目录。工作台也可下载扩展ZIP，解压后加载。
2. 在工作台“浏览器连接”生成十分钟单次配对码，输入扩展侧栏。
3. 在已登录的小红书标签页点击“绑定当前小红书页”。在工作台设置中核对当前账号。
4. 手动浏览时使用“收集当前打开的笔记”；让AI研究时另行开启“允许AI操作这个标签页”。
5. 在“今日创作”选择任务，或通过MCP操作同一工作台。稿件审阅与最终平台预览分别核对。

后台代码升级需重新加载扩展；普通关闭／重开侧栏不更新后台。同一账号正常切换编辑器不应重复配对或绑定。连接中断、浏览器重启、电脑休眠等情况需要检查页面后重新开启接管。

## 内容模型

在“账号与运行”选择：

- **当前AI客户端**：读取任务包和实际附图，生成后通过 `xhs_complete` 接回。内部兼容状态名 `awaiting_codex` 表示等待外部AI，不限定某个客户端。
- **Codex CLI订阅**：安装官方CLI并自行完成登录。工作台复用CLI自己的认证，不复制令牌；未确认登录时停止，不回退到API Key。
- **兼容API**：填写明确的 `/v1` 地址、模型与密钥环境变量名。启动工作台的进程提供该变量。提供商须支持 `chat/completions`、结构化JSON schema和图片输入；只有选中并运行任务时才发送所选材料，可能计费。

图文包包含标题、正文、话题、排版图片、证据与限制。图片引用必须保留实际来源；生成的运营观察可以修正，不自动成为永久偏好。定时研究默认关闭，需要本机服务运行，永不自动发布。

## MCP与本地API

先在工作台“浏览器连接”生成本机AI接口凭据。MCP stdio读取 `data/operator/api-token.txt`，调用同一个正在运行的服务，不启动第二套浏览器或资料库。

```json
{
  "mcpServers": {
    "xiaohongshu": {
      "command": "python",
      "args": ["-X", "utf8", "-B", "<项目绝对路径>/run_xhs.py", "mcp"]
    }
  }
}
```

将 `command` 改为虚拟环境Python的绝对路径，并替换项目路径；工作台可生成当前安装位置的配置。凭据只交给受信任的本机客户端。

工具包括状态、素材／任务／稿件读取、实际来源图片、站内研究、任务包、接回成稿、预览和 `xhs_feedback`。`xhs_browser.read_note` 会保存素材并返回 `source_id`。

本地HTTP入口为 `POST /api/v1`，使用 `Authorization: Bearer <本机凭据>` 和JSON正文，例如：

```json
{"action":"browser","args":{"operation":"search","keyword":"内容创作"}}
```

常用action：`status`、`list`、`get`、`source_image`、`create_task`、`run`、`cancel`、`packet`、`complete`、`preview`、`feedback`。外部接口不开放设置、配对、批准和正式发布；浏览操作仍要求用户接管。

## 创作者平台与反馈

“运营札记 → 回收最新后台数据”保存当前账号的列表观察。**全量分页时请保持Chrome展开**；最小化可能延迟平台的列表加载，返回结果会标明部分覆盖，不自动抢回前台。

“已发布”不等于公开展示，审核状态与可见范围分别保留。缺少私密标签不能推断为公开，列表标题也可能截短。指标是观察快照，不代表完整曝光、全部评论或传播因果。

受限接口、四类编辑器和自制测试稿的使用说明见 [创作者平台说明](docs/creator-platform.md)。测试素材不随源码分发；生成与操作测试稿均需明确授权，不要在自己的正式稿上试验。

## 数据与隐私

所有运行数据默认留在项目内，重启服务不会清空资料：

| 位置 | 内容 |
| --- | --- |
| `data/operator/` | SQLite、接口凭据、素材、图文包、预览与诊断 |
| `data/chrome-profiles/` | 可选旧CDP入口的独立浏览器资料 |
| `config/accounts.json` | 可选旧入口的本机账号配置 |
| Chrome扩展存储 | 配对与绑定／接管状态 |

这些目录和文件不进入Git。`state/`、研究资料、私有问题记录、截图、原帖、数据库、压缩包、来源快照、依赖与生成物也不随源码发布。本机私人原件仍应单独备份；Git不能恢复未提交的数据。

扩展仅申请指定小红书／图片CDN／本机服务的主机权限，以及 `activeTab`、`scripting`、`storage`、`sidePanel`、`alarms`；不申请全站、Cookie、历史、书签或调试器权限。页面适配只开放固定动作，不接受模型任意脚本、选择器或系统命令。

模型API会收到你明确选入该轮的材料；公开源码并不授权公开采集内容。遇到登录、安全验证、平台限制或身份不符时停止，不绕过验证。平台页面会变更，自动化不能保证长期兼容或没有账号限制。

## 开发与验证

```powershell
python -X utf8 -B -m unittest discover -s tests -p "test_*.py"
node --test tests/test_extension_site.cjs tests/test_extension_panel.cjs tests/test_extension_background.cjs tests/test_creator_research.cjs
node --check extension/site.js
node --check extension/background.js
node --check extension/executor.js
node --check extension/panel.js
node --check xhs_operator/static/app.js
```

测试输入为合成内容，临时文件写入项目的Git忽略数据目录。测试覆盖账号漂移、停止竞态、迟到响应、版本／文件保全、原生多卡片保存与换行、接管恢复、设置回读及部分列表处理。它们不证明所有账号、模板、平台状态和长期无人值守都已验证。

可选生成明确标记“勿发布”的自制测试素材：

```powershell
python -m pip install -r requirements-dev.txt
python scripts/create_creator_test_fixtures.py
```

生成图片、20秒视频和10分1秒音频到 `data/operator/diagnostics/creator-research/fixtures/`，不使用私人媒体。不要在没有明确授权的情况下上传或提交测试稿。

发布前应从干净检出验证安装、回归、CLI和服务；本版实页覆盖研究／预览／存稿、部分创作者设置和现有笔记反馈，未进行新笔记正式发布，兼容API也未使用付费账户验收。

## 目录与上游

- `extension/`：Chrome侧栏、唯一后台执行器与页面适配。
- `xhs_operator/`：本地资料、任务、生产、HTTP/MCP、预览与反馈。
- `scripts/`：保留的CDP兼容层、批量研究与自制测试素材工具。
- `orchestration/`：可选外部Skill目录与流程参考，不是主工作台必需依赖。
- `docs/`：通用说明；`SKILL.md` 提供Agent入口。

许可证为MIT，保留上游版权。外部Skill、上游研究快照、私人素材和账号数据没有打包进本仓库，使用外部项目时分别遵守其许可证。
