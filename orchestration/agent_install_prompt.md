# 给本地 Agent 的安装提示词

仅在用户明确要求安装这些外部仓库时使用；这不是主工作台的默认安装步骤，也不授予浏览器、账号或发布权限。各仓库须另行审阅来源、许可证和依赖。

你现在要安装并整理一套通用小红书内容工厂 A 类 Skills。请不要把这些仓库合并成一个 Skill，也不要改写上游源码。请把它们作为互相独立的模块安装，并建立一个外层主控调度规则。

请在可访问 GitHub 的本地环境执行以下任务：

1. 读取 `orchestration/a_class_repositories.json`，按本次授权选择所需仓库，保留 `.git`、README、SKILL.md、scripts、assets、references 等原始结构。
2. 把 `white0dew/XiaohongshuSkills` 放在平台执行层，负责小红书搜索、详情读取、图文/视频发布、评论互动、账号与数据导出，不允许它接管写作、选题或视觉设计。
3. 把 `Weizhena/Deep-Research-skills` 放在研究层，负责资料搜集、证据卡、调研大纲、竞品/同类内容分析和研究报告。
4. 把 `dontbesilent2025/dbskill` 放在选题诊断层，负责判断选题是否有点击理由、读者收益、hook、标题潜力、小红书适配度和 AI 痕迹风险。
5. 把 `op7418/Humanizer-zh` 放在中文编辑层，负责把初稿改成人话，去掉 AI 味、PPT 腔、空话、模板句和过度营销表达。
6. 把 `op7418/guizang-social-card-skill` 放在小红书图文设计层，负责轮播卡片、封面、HTML 版式、PNG 渲染和视觉校验。
7. 把 `freestylefly/awesome-gpt-image-2` 放在视觉提示词层，负责生图提示词、封面场景、插图、海报、信息图和视觉风格参考，不负责图文排版。
8. 把 `JimLiu/baoyu-skills` 放在视觉工具箱层，作为封面、信息图、图解和视觉包装的补充模块，不覆盖 guizang-social-card 的主卡片职责。
9. 运行 `scripts/verify_a_class_skills.py`，生成 `verification_report.json`。如果有任何仓库下载失败、README 缺失或不是 Git 仓库，请停止并报告，不要继续假装安装完成。
10. 生成最终压缩包，并保留下载状态、commit 信息和职责说明。

安装完成后，请按这个主流程使用：

资料输入 → Deep-Research 调研 → dbskill 选题/标题诊断 → 初稿生成 → Humanizer-zh 人话改稿 → guizang-social-card 设计图文 → awesome-gpt-image-2/baoyu-skills 补充视觉 → 质量门检查 → white0dew/XiaohongshuSkills 预览发布 → 数据复盘。

核心约束：小红书内容生产必须先做研究和选题判断，再写稿，再做人话改稿，再做图文视觉，最后才进入发布执行。发布工具不能反向决定内容结构。
