---
name: RedBookSkills
description: |
  通过指定Chrome扩展进行小红书研究、完整图文生产、预览与后台反馈；保留显式授权的旧CDP兼容入口。
  默认用于绑定页的素材采集、写作、预览和指标观察；扩展不提交正式发布或互动。
metadata:
  trigger: 发布内容到小红书
  source: Angiin/Post-to-xhs
---

# 小红书运营与图文生产

当前主入口为本项目 `run_xhs.py`，使用方法与实际边界以 `README.md` 为准。默认通过 Chrome 扩展连接用户明确绑定并开启接管的标签页，不启动另一个浏览器、不复制 Cookie、不调用 Playwright。工作台、MCP 与本地 HTTP API 使用同一业务接口和资料库。

后台执行器持有唯一标签页绑定。开启接管后切换标签页、最小化或关闭侧栏仍可继续，侧栏重开仅显示状态。显式停止、账号变化、平台提示、连接中断或页面冻结时暂停；浏览器关闭与电脑休眠无法运行。停止后不得通过换入口恢复旧授权；未完成上传不自动重放。

Agent 可使用 MCP 的 `xhs_browser` 列表、搜索、打开、读取、返回和滚动动作逐篇研究。卡片不是精读来源；弹层出现不表示详情已加载，需等完整详情记录再读取；只有标题与封面的占位缓存必须拒绝。`read_note` 核对笔记 ID 后保存真实详情并返回 `source_id`。图片必须实际读取，可通过 `xhs_source_image` 或任务包附件获取；下载失败、未读图、评论样本和历史时效如实保留。停止接管、账号变化或平台提示时立即停止，保留已得材料，不换工具绕过。

内容提供器可选当前 AI 客户端、官方 Codex CLI 订阅或用户明确配置的兼容 API，不隐式切换或使用备用密钥。Agent 通过 `packet <任务ID>` 或 MCP 读取资料/schema/实际图片，生成完整图文并用 `complete` 接回待审稿。图文在本地渲染，提示词、占位图或纯文本不能算完整交付。模型生成的观察可修正，不是用户已确认的规则。

外部 AI 接口不开放批准与正式发布；扩展仅填写用户已打开的空白编辑器预览，正式发布由用户在 Chrome 最终核对并点击。原专用 CDP 仍是用户明确选择时的兼容入口，发布须逐篇当前版本确认，旧平台暂停继续有效。不要替用户执行 `approve` 或 `publish`，除非本篇当前版本已有明确授权。

通过 `xhs_feedback` 回收当前账号列表与审核指标；全量分页需保持Chrome展开，部分覆盖如实说明。受限创作者调研和自制测试稿见 `docs/creator-platform.md`，操作测试稿须另有明确授权。

下文是原平台执行层的分步接口参考；本项目默认预览，正式发布需要逐篇确认。

你是“小红书发布助手”。目标是在用户确认后，调用本 Skill 的脚本完成发布或互动操作。

## 风险提示（重要）

**使用本 Skill 进行小红书自动化，存在被平台风控、限流、封号或封禁账号的风险。**

默认提醒用户优先使用测试号、小流量运行，并对最终内容进行人工复核。使用者需自行评估并承担相关风险。

## 输入判断

优先按以下顺序判断：
1. 用户明确要求"测试浏览器 / 启动浏览器 / 检查登录 / 获取登录二维码 / 只打开不发布"：进入测试浏览器流程。
2. 用户要求“首页推荐 / 搜索笔记 / 找内容 / 查看某篇笔记详情 / 查看内容数据表 / 给帖子评论 / 回复评论 / 点赞收藏互动 / 查看用户主页 / 查看评论和@通知”：进入内容检索与互动流程（`list-feeds` / `search-feeds` / `get-feed-detail` / `post-comment-to-feed` / `respond-comment` / `note-upvote` / `note-unvote` / `note-bookmark` / `note-unbookmark` / `profile-snapshot` / `notes-from-profile` / `get-notification-mentions` / `content-data`）。
3. 用户已提供 `标题 + 正文 + 视频(本地路径或 URL)`：直接进入视频发布流程。
4. 用户已提供 `标题 + 正文 + 图片(本地路径或 URL)`：直接进入图文发布流程。
5. 用户只提供网页 URL：先提取网页内容与图片/视频，再给出可发布草稿，等待用户确认。
6. 信息不全：先补齐缺失信息，不要直接发布。

## 必做约束

- 发布前必须让用户确认最终标题、正文和图片/视频。
- 图文发布时，没有图片不得发布（小红书发图文必须有图片）。
- 视频发布时，没有视频不得发布。图片和视频不可混合使用（二选一）。
- 默认使用无头模式；若检测到未登录，切换有窗口模式登录。
- 标题长度不超过 38（中文/中文标点按 2，英文数字按 1）。
- 用户要求"仅测试浏览器"时，不得触发发布命令。
- 如使用文件路径，优先使用绝对路径；若用户给的是相对路径，先转换为绝对路径再执行命令。
- 若发布页结构异常，优先检查 `scripts/cdp_publish.py` 里的 `SELECTORS`、多图上传等待、正文编辑器与发布按钮点击逻辑；这些是最容易被小红书网页改版影响的区域。

## 测试浏览器流程（不发布）

1. 启动 post-to-xhs 专用 Chrome（默认有窗口模式，便于人工观察）。
2. 如用户要求静默运行，再使用无头模式。
3. 可选：执行登录状态检查并回传结果。
4. 结束后如用户要求，关闭测试浏览器实例。

## 图文发布流程

1. 准备输入（标题、正文、图片 URL 或本地图片）。
2. 如需文件输入，先写入 `title.txt`、`content.txt`。
3. 执行发布命令（默认无头）。
4. 回传执行结果（成功/失败 + 关键信息）。

## 视频发布流程

1. 准备输入（标题、正文、视频文件路径或 URL）。
2. 如需文件输入，先写入 `title.txt`、`content.txt`。
3. 执行视频发布命令（默认无头）。视频上传后需等待处理完成。
4. 回传执行结果（成功/失败 + 关键信息）。

## 内容检索与互动流程（搜索/详情/评论/内容数据）

1. 先检查小红书主页登录状态（`XHS_HOME_URL`，非创作者中心）。
2. 若用户需要首页推荐流，执行 `list-feeds` 获取首页推荐笔记列表。
3. 若用户需要关键词搜索，执行 `search-feeds` 获取笔记列表（默认会先抓取搜索下拉推荐词，结果字段为 `recommended_keywords`；当前返回页面可提取结果，如只需前 N 条由调用方自行截断，暂无单独 `--limit` 控制搜索结果条数）。
4. 若用户需要详情，从搜索结果中取 `id` + `xsecToken` 再执行 `get-feed-detail`；如用户明确要更多评论，可加 `--load-all-comments` 等参数。
5. 若用户需要发表评论，执行 `post-comment-to-feed`（一级评论；必填 `feed_id` / `xsec_token` / `content`）。
6. 若用户需要回复某条评论，执行 `respond-comment`（可用 `comment_id` / `comment_author` / `comment_snippet` 定位目标评论）。
7. 若用户需要点赞/收藏互动，执行 `note-upvote` / `note-unvote` / `note-bookmark` / `note-unbookmark`。
8. 若用户需要用户主页信息，执行 `profile-snapshot` 或 `notes-from-profile`。
9. 若用户需要“评论和@通知”，执行 `get-notification-mentions` 抓取 `/notification` 页面对应的 `you/mentions` 接口返回。
10. 若用户需要“笔记基础信息表”，执行 `content-data` 获取曝光/观看/点赞等指标。
11. 回传结构化结果（数量、核心字段、链接）。

## 常用命令

### 参数顺序提醒（`cdp_publish.py` / `publish_pipeline.py`）

请严格按下面顺序写命令，避免 `unrecognized arguments`：

- 全局参数放在子命令前：`--host --port --headless --account --timing-jitter --reuse-existing-tab`
- 子命令参数放在子命令后：如 `search-feeds` 的 `--keyword --sort-by --note-type`
- 常见可选全局参数：`--host 10.0.0.12 --port 9222 --reuse-existing-tab --account NAME`

示例（正确）：

```bash
python scripts/cdp_publish.py --reuse-existing-tab search-feeds --keyword "春招" --sort-by 最新 --note-type 图文
```

### 0) 启动 / 测试浏览器（不发布）

默认 CDP 地址为 `127.0.0.1:9222`；可按需叠加 `--host` / `--port` 指向远程 Chrome。

```bash
# 启动测试浏览器（有窗口，推荐）
python scripts/chrome_launcher.py

# 可选：无头启动
python scripts/chrome_launcher.py --headless

# 检查当前登录状态
python scripts/cdp_publish.py check-login

# 常见变体：优先复用已有标签页
python scripts/cdp_publish.py --reuse-existing-tab check-login

# 远程 CDP 检查登录
python scripts/cdp_publish.py --host 10.0.0.12 --port 9222 check-login

# 获取登录二维码（返回 Base64，可供远程前端展示扫码）
python scripts/cdp_publish.py get-login-qrcode

# 重启 / 关闭测试浏览器
python scripts/chrome_launcher.py --restart
python scripts/chrome_launcher.py --kill
```

### 0.5) 首次登录 / 重新登录

```bash
# 本地 Chrome 登录
python scripts/cdp_publish.py login

# 远程 CDP 登录（不会自动重启远程 Chrome）
python scripts/cdp_publish.py --host 10.0.0.12 --port 9222 login
```

### 1) 准备 title.txt / content.txt

若用户给的是标题和正文，可先写入临时文件再执行命令：

```bash
printf '%s\n' '这里是标题' > /abs/path/title.txt
printf '%s\n' '这里是正文' > /abs/path/content.txt
```

### 2) 无头发布 or 有头预览 —— 使用图片 URL 发布

```bash
# 默认只填写预览；本篇确认后才加 --auto-publish
python scripts/publish_pipeline.py --headless \
  --title-file /abs/path/title.txt \
  --content-file /abs/path/content.txt \
  --image-urls "https://example.com/1.jpg" "https://example.com/2.jpg"

# 仅预览：停留在发布页人工确认
python scripts/publish_pipeline.py \
  --preview \
  --title-file /abs/path/title.txt \
  --content-file /abs/path/content.txt \
  --image-urls "https://example.com/1.jpg" "https://example.com/2.jpg"

# 常见变体：远程 CDP / 复用已有标签页
python scripts/publish_pipeline.py --host 10.0.0.12 --port 9222 --reuse-existing-tab \
  --title-file /abs/path/title.txt \
  --content-file /abs/path/content.txt \
  --image-urls "https://example.com/1.jpg"
```

说明：当 `--host` 不是 `127.0.0.1/localhost` 时，脚本会跳过本地 `chrome_launcher.py` 的自动启动/重启逻辑。
说明：`publish_pipeline.py` 默认仅填写预览；仅在本篇获确认后使用 `--auto-publish`。`--headless` 只控制窗口显示，不授予发布权限。

### 3) 无头发布 or 有头预览 —— 使用本地图片发布

```bash
# 本地图片发布
python scripts/publish_pipeline.py --headless \
  --title-file /abs/path/title.txt \
  --content-file /abs/path/content.txt \
  --images "/abs/path/pic1.jpg" "/abs/path/pic2.jpg"

# WSL/远程 CDP + Windows/UNC 路径：跳过本地文件预校验
python scripts/publish_pipeline.py --headless \
  --title-file /abs/path/title.txt \
  --content-file /abs/path/content.txt \
  --images "\\\\wsl.localhost\\Ubuntu\\home\\user\\pic1.jpg" \
  --skip-file-check
```

说明：当控制端在 WSL 运行，且传入 Windows/UNC 路径（如 `\\wsl.localhost\...`）时，可加 `--skip-file-check`，避免 Linux 侧 `os.path.isfile()` 误判不存在。
说明：脚本会自动识别 `C:\...`、`\\wsl.localhost\...` 等 Windows/UNC 路径，并在传给 `DOM.setFileInputFiles` 时保留原始路径形态。
说明：若需要强制保留原始路径，也可显式加 `--preserve-upload-paths`。

### 3.5) 视频发布（本地视频文件 / 视频 URL）

```bash
# 本地视频文件
python scripts/publish_pipeline.py --headless \
  --title-file /abs/path/title.txt \
  --content-file /abs/path/content.txt \
  --video "/abs/path/my_video.mp4"

# 视频 URL
python scripts/publish_pipeline.py --headless \
  --title-file /abs/path/title.txt \
  --content-file /abs/path/content.txt \
  --video-url "https://example.com/video.mp4"
```

### 4) 多账号发布 / 切换

```bash
python scripts/cdp_publish.py list-accounts
python scripts/cdp_publish.py add-account work --alias "工作号"
python scripts/cdp_publish.py --port 9223 --account work login
python scripts/publish_pipeline.py --port 9223 --account work --headless --title-file /abs/path/title.txt --content-file /abs/path/content.txt --image-urls "https://example.com/1.jpg"
```

### 5) 搜索内容 / 获取笔记详情

```bash
# 首页推荐笔记
python scripts/cdp_publish.py list-feeds

# 搜索笔记
python scripts/cdp_publish.py search-feeds --keyword "春招"

# 常见变体：带筛选 + 复用标签页
python scripts/cdp_publish.py --reuse-existing-tab search-feeds --keyword "春招" --sort-by 最新 --note-type 图文

# 获取笔记详情（feed_id 与 xsec_token 来自搜索结果）
python scripts/cdp_publish.py get-feed-detail \
  --feed-id 67abc1234def567890123456 \
  --xsec-token XSEC_TOKEN

# 可选：滚动加载更多一级评论，并尝试展开二级回复
python scripts/cdp_publish.py get-feed-detail \
  --feed-id 67abc1234def567890123456 \
  --xsec-token XSEC_TOKEN \
  --load-all-comments \
  --limit 20 \
  --click-more-replies \
  --reply-limit 10 \
  --scroll-speed normal
```

说明：`list-feeds` 返回首页推荐 feed 列表。
说明：`search-feeds` 输出中包含 `recommended_keywords_count` 与 `recommended_keywords`，表示回车前搜索框下拉推荐词。
说明：`search-feeds` 返回当前页面可提取到的结果，不提供单独的 `--limit` 条数控制；若只需前 N 条，请在调用方截断返回列表。
说明：`get-feed-detail --load-all-comments` 会先滚动评论区，并可选点击“更多回复”后再提取详情，同时额外返回 `comment_loading`。
说明：`check-login` 与主页登录检查默认启用本地缓存（12h，仅缓存“已登录”），到期后自动重新网页校验。

### 6) 给笔记发表评论（一级评论）

```bash
# 直接传评论文本
python scripts/cdp_publish.py post-comment-to-feed \
  --feed-id 67abc1234def567890123456 \
  --xsec-token XSEC_TOKEN \
  --content "写得很实用，感谢分享"

# 使用文件传评论（适合多行文本）
python scripts/cdp_publish.py post-comment-to-feed \
  --feed-id 67abc1234def567890123456 \
  --xsec-token XSEC_TOKEN \
  --content-file "/abs/path/comment.txt"
```

### 7) 获取内容数据表（content_data）

```bash
# 获取笔记基础信息表（曝光/观看/封面点击率/点赞/评论/收藏/涨粉/分享/人均观看时长/弹幕）
python scripts/cdp_publish.py content-data

# 下划线别名
python scripts/cdp_publish.py content_data

# 可选：导出 CSV
python scripts/cdp_publish.py --reuse-existing-tab content-data --csv-file "/abs/path/content_data.csv"
```

### 8) 获取评论和@通知（notification mentions）

```bash
# 抓取 /notification 页面触发的 you/mentions 接口数据
python scripts/cdp_publish.py get-notification-mentions

# 下划线别名
python scripts/cdp_publish.py get_notification_mentions
```

### 9) 评论回复 / 点赞收藏 / 用户主页信息

```bash
# 回复评论（支持按评论 ID / 作者 / 文本片段定位）
python scripts/cdp_publish.py respond-comment \
  --feed-id 67abc1234def567890123456 \
  --xsec-token XSEC_TOKEN \
  --comment-id COMMENT_ID \
  --content "感谢反馈～"

# 点赞 / 取消点赞
python scripts/cdp_publish.py note-upvote --feed-id 67abc1234def567890123456 --xsec-token XSEC_TOKEN
python scripts/cdp_publish.py note-unvote --feed-id 67abc1234def567890123456 --xsec-token XSEC_TOKEN

# 收藏 / 取消收藏
python scripts/cdp_publish.py note-bookmark --feed-id 67abc1234def567890123456 --xsec-token XSEC_TOKEN
python scripts/cdp_publish.py note-unbookmark --feed-id 67abc1234def567890123456 --xsec-token XSEC_TOKEN

# 用户主页快照 / 用户主页笔记
python scripts/cdp_publish.py profile-snapshot --user-id USER_ID
python scripts/cdp_publish.py notes-from-profile --user-id USER_ID --limit 20 --max-scrolls 3
```

补充：更完整的背景说明、安装说明与面向人工阅读的示例可参考 `README.md`，但本文件中的命令样例应优先作为 agent 执行基线。

## 失败处理

- 登录失败：提示用户重新扫码登录并重试；若用户需要远程展示二维码，可改用 `get-login-qrcode`。
- 图片/视频下载失败：提示更换 URL 或改用本地文件。
- 本地路径不可用：优先改用绝对路径；若为 WSL/远程 CDP 的 Windows/UNC 路径，可先尝试 `--skip-file-check`，必要时再加 `--preserve-upload-paths`。
- 评论/回复目标未定位成功：提示补充 `comment_id`，或改用 `comment_author` / `comment_snippet` 再试。
- 页面选择器失效：提示检查 `scripts/cdp_publish.py` 中选择器并更新。
