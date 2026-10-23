---
name: xhs-content-factory-orchestration
description: |
  小红书通用内容工厂 A 类主控调度规则。
  协调 7 个独立 Skill 模块完成从调研到发布的全链路内容生产。
  pipeline: 资料输入 → 调研 → 选题诊断 → 初稿 → 人话改稿 → 图文设计 → 视觉补充 → 质量门 → 发布 → 复盘
producer: claude-code
producer_role: foreground-worker
producer_evidence: "2026-06-16 agentv2 xhs-a-class-skills installer bundle deployment"
review_owner: codex-controller
review_state: candidate
canonical_status: candidate
---

# 小红书内容工厂 A 类 — 主控调度规则

当前工作台入口为项目根 `run_xhs.py`，使用与验收边界见项目根 `README.md` 的“小红书创作工作台”。下文保留模块职责参考；工作台不要求每篇机械串行调用全部七个外部模块。资料、任务、成稿与运营观察统一保存在 `data/operator/`，外部资料不晋升到个人记忆。

## 核心原则

1. **模块独立**：7 个 Skill 各自独立，不合并源码，不互相覆盖
2. **顺序不可跳**：先研究后选题，先改稿后设计，先预览后发布
3. **发布工具不反控内容**：平台执行层只做执行，不决定选题/写作/视觉
4. **质量门硬停**：任一步不通过，停止后续流程

## 模块清单

| 编号 | 模块 | 路径 | 角色 |
|---|---|---|---|
| A1 | XiaohongshuSkills | `../` (项目根) | 平台执行层 |
| A2 | Deep-Research-skills | `skills/02-research-engine/` | 研究层 |
| A3 | dbskill | `skills/03-topic-diagnosis/` | 选题诊断层 |
| A4 | Humanizer-zh | `skills/04-humanizer/` | 中文编辑层 |
| A5 | guizang-social-card-skill | `skills/05-social-card-renderer/` | 图文设计层 |
| A6 | awesome-gpt-image-2 | `skills/06-image-prompt-library/` | 视觉提示词层 |
| A7 | baoyu-skills | `skills/07-visual-toolbox/` | 视觉工具箱层 |

## 标准流水线

### Step 0: 资料输入
用户提供：项目资料、网页链接、PDF、竞品笔记、产品说明、口述想法、评论区反馈
→ 存入 `data/research/<YYYYMMDD>-<topic>/raw/`

### Step 1: A2 调研
调用 Deep-Research-skills + XiaohongshuSkills search-feeds/get-feed-detail
- 输入：关键词 + 原始资料
- 输出：原始数据(JSON) + 5文件分析产物（按 `orchestration/research-quality-gate.md` 标准）
- 产物路径：`data/research/<YYYYMMDD>-<topic>/raw/` + `analysis/`
- 门禁：research-quality-gate.md 全部 15 规则通过 + 5 文件齐全

### Step 2: A3 选题诊断
调用 dbskill
- 输入：调研分析产物
- 输出：评分报告 + 选题推荐
- 产物路径：`data/research/<YYYYMMDD>-<topic>/analysis/`

### Step 3: 初稿生成
外部 Agent 或主控 Agent 执行
- 输入：调研报告 + 选题诊断 + 规则包 `docs/publishing-rules/`
- 输出：初稿
- 产物路径：`data/production/external-agent/<name>-<topic>/`

### Step 4: A4 人话改稿
调用 Humanizer-zh
- 输入：初稿
- 输出：去 AI 味的定稿
- 产物路径：`data/production/local-agent/<YYYYMMDD>-<topic>/title.txt` + `content.txt`

### Step 5: A5 图文设计
调用 guizang-social-card-skill
- 输出：封面 + 轮播卡片 HTML/PNG
- 产物路径：`data/production/local-agent/<YYYYMMDD>-<topic>/cards/`

### Step 6: A6 + A7 视觉补充
视觉提示词 + 工具箱
- 产物路径：`data/production/local-agent/<YYYYMMDD>-<topic>/images/`

### Step 7: 质量门
按 `orchestration/research-quality-gate.md` 标准检查
- 通过后复制到 `data/quality-gate/passed/<YYYYMMDD>-<topic>/` + `qc-report.md`
- 产物路径：`data/quality-gate/passed/`

### Step 8: 人工审核 ← 你
- 待审核：`data/review/pending/`
- 审核通过：移到 `data/review/approved/`
- **这是发布前的最后一道关，只有你可以放行**

### Step 9: A1 发布
从 `data/review/approved/<YYYYMMDD>-<topic>/` 读取内容
- 默认仅填写预览；确认本篇完整图文后才使用 `--auto-publish`。`--headless` 只控制浏览器显示，不代表发布授权。
- 发布后：移到 `data/published/<YYYYMMDD>-<topic>/`

### Step 10: 数据复盘
- 发布 24-48h 后 `cdp_publish.py content-data` 获取数据
- 回到 Step 1，进入下一轮

## 调用约定

每个模块独立读取，不修改其他模块的源码。主控 Agent 负责在各模块间传递数据文件（Markdown、JSON、图片），模块之间不直接耦合。

## Chrome 进程回收规则（硬约束）

- **只能杀 CDP Chrome**：永远使用 `chrome_launcher.py --kill`（按端口 9222 精确杀），**严禁** `Get-Process chrome \| Stop-Process`（会杀死用户日常 Chrome）
- **batch_feed_detail.py 自动回收**：脚本结束时 `finally` 块调用 `chrome_launcher.py --kill`，加 `--no-cleanup` 可跳过（用于链式调用）
- **batch_image_download.py 不需要回收**：纯 HTTP 下载，不涉及 Chrome
- **后台任务被 kill 后**：Chrome 进程不会自动回收，需手动 `chrome_launcher.py --kill` 或重启电脑
- **内存警戒**：每个 headless Chrome 约 200-600MB，批量 60+ 帖子的 CDP 会话累计可达 2-4GB。建议每批 ≤ 20 条，批次间 `--no-cleanup` 跳过回收以减少 Chrome 重启开销

## 故障处理

- 任一步骤失败，记录到 `logs/` 并报告
- A1 发布失败不阻塞内容生产（积压在 pending-posts）
- 图文设计失败须修复并重新导出，不能将纯文字或不完整图片包作为完整图文交付。
- 上游仓库更新通过 `git pull` 各自独立处理
