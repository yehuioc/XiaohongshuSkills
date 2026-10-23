---
producer: claude-code
producer_role: foreground-worker
producer_evidence: "Extracted from state/ChatGPT-高考志愿内容交付.md — ChatGPT xiaohongshu-operator multi-round delivery methodology"
source: "ChatGPT xiaohongshu-operator 高考志愿 v1→v2→v2.1 迭代实录"
review_state: candidate
canonical_status: candidate
---

# 内容生产流水线

## Phase 0: 源边界与完整性审计

进入生产前必须确认：
- 使用哪个调研包（精确到 zip 路径）
- 使用哪个约束包
- 明确排除哪些旧材料
- JSON 数量、图片数量、已去重帖子数、评论数

产出文件：
- `source_inventory.csv` — 每条源文件路径、类型、行数/大小
- `source_completeness_report.md` — 缺口标注
- `post_asset_scan.csv` — 每篇帖子是否已有正文、storyboard、image_plan、quality_gate

门禁：源材料齐备且无空表，方可进入 Phase 1。

## Phase 1: 证据验证与盲点复读

不改稿。先验证内容主张是否被原始数据支持。

检查项：
1. 每篇正文中的具体主张（数据、案例、结论）是否在原始 JSON/评论中出现
2. 是否存在"听起来像干货但实际是常识推断"的内容
3. 评论区高频问题是否已转化为正文选题
4. 盲点：哪些用户需求在现有帖子中没有被覆盖

产出文件：
- `claim_evidence_matrix.csv` — 每篇帖子 × 每条主张 × 原始来源
- `validation_report.md` — 验证结论 + 不可验证的主张列表
- `blindspot_review.md` — 未被覆盖的用户需求

门禁：至少 80% 的内容主张有原始数据支撑。

## Phase 2: 参考结构审计

对每篇参考爆款做逐层拆解，不能只写标题。

每个参考样本必须拆解：
- 标题 hook 机制（反常识/错误问法/风险警告/流程承诺）
- 正文结构（开头场景 → 中间方法 → 结尾 CTA）
- 封面视觉类型（大字警告/流程图/人物出镜/截图/手写笔记）
- 轮播页数、每页功能和信息密度
- 评论区高频追问方向
- 收藏/评论触发点
- 哪些可迁移、哪些不可迁移

产出文件：
- `sample_structure_audit.md` — 每个参考样本的完整拆解
- `reference_contact_sheets/` — 关键参考样本封面+轮播接触图

## Phase 3: 逐篇生产（每篇独立文件夹）

每篇帖子包含以下文件：

```
posts/<post-id>/
  title.txt              ← 标题（≤38计数）
  content.txt            ← 正文500-900字
  hashtags.txt           ← 8-12个标签（大流量+精准搜索+场景+问题+受众）
  metadata.json          ← 作者、日期、版本
  storyboard.md          ← 10页轮播卡片逐页文案
  image_plan.md          ← 图片设计执行说明
  post_blueprint.md      ← 本篇内容架构
  reference_mapping.md   ← 本篇参考了哪些爆款结构
  quality_gate.md        ← 本篇质量门
```

### storyboard.md 每页必含字段

- `Visible title` — 读者看到的卡片标题
- `Visible body` — 读者看到的卡片正文（60-120字）
- `Layout intent` — 本页职责（钩子/场景/错误问法/解释/清单/模板/CTA）
- `Information density` — 本页是否值得保存/截图

### reference_mapping.md 模板

```
本贴参考:
- R08: 借"流程图封面+步骤页+6步结构"
- R11: 借"长正文+位次解释+评论区焦虑问法"
不借:
- R08 的"过短正文（<200字）"
- R07 的"只有情绪没有方法"

改造:
- 第1页 → R08 的封面大字警告
- 第3页 → R11 的错误问法页
- 第5页 → 新增模板页（参考R06的清单节奏）
- 第9页 → R08 的CTA留言页
```

## Phase 4: 逐帖质量门（8维度）

| 维度 | 检查内容 |
|---|---|
| 标题张力 | 有数字/情绪词/反常识/错误问法？ |
| 正文信息密度 | ≥500字？有场景+判断路径+反例？ |
| 评论承接 | 封面/正文/尾页是否承接评论区高频问法？ |
| 标签结构 | ≥8个？覆盖大流量/精准搜索/场景/问题/受众？ |
| 参考映射有效性 | 每篇能否追溯到具体爆款结构？ |
| 轮播页节奏 | 10页是否有钩子→错误→解释→清单→CTA节奏？ |
| 单页信息密度 | 每页可见正文≥60字？值得保存？ |
| 收藏/评论触发 | 有值得截图的结构化信息？有CTA提问模板？ |

每项标 `PASS/WARN/FAIL`。任一 FAIL 不可进入发布。

## Phase 5: 逐帖薄弱点诊断

产出 `post_weakness_matrix.csv`：

| 帖子 | 薄弱点 | 修复动作 |
|---|---|---|
| P03 | 标题写8个坑，正文只展开6个 | 补齐正文8个坑+每页改"错误做法+后果+替代" |

## Phase 6: 图片审计

单独主线，逐页检查：
- 不看正文只看图片，读者能否理解核心方法
- 封面是不是小红书风格（不是PPT句式）
- 页面间是否有节奏（不是10页都在说一件事）
- 每页是否有可保存的具体信息

产出 `image_audit_report.md`。

## Phase 7: 打包

交付包结构：

```
<topic>_delivery_pack_v<version>_<date>.zip
  posts/
    P01_<slug>/ (title.txt + content.txt + ... + quality_gate.md)
    ...
  sample_structure_audit.md
  reference_mapping.md
  post_weakness_matrix.csv
  image_audit_report.md
  quality_gate_summary.csv
  10_posts_preview.md
  revision_log.md
```

质量门状态：`PASS_WITH_MANUAL_REVIEW`（教育/金融/医疗等决策场景必须人工复核）
