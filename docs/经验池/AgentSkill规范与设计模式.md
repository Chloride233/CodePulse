# Agent Skill 规范与设计模式

## 来源

- 阿里云开发者 "Agent Skill规范、构建与设计模式"（2026-05-12）
- Anthropic Skill 规范（2025-12 发布，33+ Agent 产品采用）
- Skill-Creator（Anthropic 官方 Skill 构建方法论）

---

## 核心概念

> Skill 不是 Prompt——它是以任务、工具、流程、输出边界为中心的结构化行为设计。

Agent Skill 是可复用的"Prompt 增强包"，通过渐进加载机制注入领域知识和工作流到 AI Agent。

---

## SKILL.md 格式

### YAML Frontmatter（元数据）

| 字段 | 必填 | 说明 |
|------|------|------|
| name | ✅ | 唯一标识，≤64 字符，小写字母/数字/连字符 |
| description | ✅ | 功能和触发场景，≤1024 字符，包含关键词 |
| license | ❌ | 许可证 |
| compatibility | ❌ | 环境要求，≤500 字符 |
| metadata | ❌ | 自定义键值对 |
| allowed-tools | ❌ | 预授权工具列表（实验性） |

### Markdown 正文

核心指令，建议 ≤500 行。更长的参考资料应拆分为独立文件。

### 可选目录结构

```
skill-name/
├── SKILL.md          # 核心
├── scripts/          # 可执行代码
├── references/       # 补充文档
└── assets/           # 静态资源
```

---

## 三层渐进加载机制

| 层 | 加载内容 | 时机 | Token 成本 |
|----|---------|------|-----------|
| L1（目录） | name + description | 会话启动 | ~50-100 token/Skill |
| L2（指令） | 完整 SKILL.md 正文 | Skill 激活时 | 建议 <5000 token |
| L3（资源） | scripts/、references/、assets/ | 指令引用时按需 | 按文件大小 |

**关键价值：** 20 个 Skill 安装后，初始加载仅 1000-2000 token，比单体 prompt 减少约 90%。

触发机制完全是**模型驱动激活**（非关键词匹配）。模型自主判断用户任务是否匹配 Skill 的 description。

---

## Skill-Creator 方法论（Anthropic）

### 核心原则

1. **泛化，不要过拟合**：Skill 会被无数次使用。针对特定测试用例的定向修复会降低 Skill。顽固问题尝试不同隐喻或工作流，而非加硬约束。
2. **解释"为什么"而非堆砌"必须"**：最重要的一条洞察。现代 LLM 有良好的心智理论；解释为什么更重要比写一堆 ALWAYS 和 NEVER 更有效。
3. **提取重复模式**：如果每个测试用例都让 Agent 独立写类似辅助脚本，强烈信号应该放进 scripts/ 目录直接复用。

### 六阶段开发生命周期

1. **需求捕获**：理解意图、定义触发场景、确定输出格式、区分客观可验证 vs 主观创造性任务
2. **编写 Skill**：起草 SKILL.md + 辅助资源
3. **测试执行**：设计 2-3 测试用例，跑并行 A/B 测试（with_skill vs without_skill），起草定量断言，捕获时序数据
4. **评估审查**：Grader 评分，聚合基准数据，Analyzer 识别模式，生成 Eval Viewer 供人工审查，收集 feedback.json
5. **迭代改进**：分析反馈，泛化改进（避免过拟合），重写 Skill，新迭代目录，回到阶段 3
6. **优化发布**：description 优化（run_loop.py），训练/测试集分割，自动迭代 description，验证，打包为 .skill 文件

### 三个专门评估 Agent

**Grader Agent：**
- 评估断言是否通过
- 关键设计：评估断言本身的质量
- "自我批评"：弱断言上的通过比无用更糟（制造虚假信心）
- 评分标准要求真正完成任务的证据，而非表面合规

**Comparator Agent：**
- 盲比——看到输出 A 和 B，不知道哪个来自哪个 Skill（双盲医学试验灵感）
- 双维度评分：内容维度（正确性、完整性、准确性）+ 结构维度（组织、格式、可用性），各 1-5 分，合成 1-10 总分

**Analyzer Agent：**
- 角色 A：事后分析——解盲后分析为什么赢家赢了，比较指令差异和执行模式，生成优先级改进建议（高/中/低）
- 角色 B：基准分析——识别聚合统计中的模式（哪些断言两配置都 100% 通过、哪些高方差、时间/token 异常值）

---

## 五种设计模式（Google ADK）

### 1. Tool Wrapper

按需加载领域特定知识。SKILL.md 本身不含完整规范，告诉 Agent 去哪里加载。

**适用：** 框架/库编码标准、团队代码风格指南

### 2. Generator

填空式文档生成，用模板 + 风格指南强制输出一致性。Agent 主动询问缺失信息而非猜测。

**适用：** 标准化技术文档、API 文档、项目脚手架

### 3. Reviewer

分离"检查什么"和"怎么检查"。清单独立维护，Agent 执行评分。聚焦解释 WHY 而非只是 WHAT。

**适用：** 自动 PR 审查、安全扫描、风格检查

### 4. Inversion

翻转传统交互模型。不是用户 prompt / Agent 执行，而是 Agent 先面试用户，收集完整需求，再行动。

**适用：** 新项目规划、架构设计、需求澄清

### 5. Pipeline

多步骤工作流 + 检查点。复杂任务拆为严格有序的步骤，每步有明确输入/输出和通过条件。硬约束如"无用户确认不继续"强制执行。

**适用：** 代码到文档生成、多阶段内容生产

**可组合：** Pipeline + Reviewer（文档生成后自动质检）；Generator + Inversion（需要用户输入的结构化文档）

---

## 评测方法

- **JSON Schema 数据管道**：7 个 JSON 数据结构形成完整管道
- **A/B 测试**：每个用例同时跑 with_skill 和 without_skill
- **Eval Viewer**：浏览器工具，Outputs 标签页（逐用例审查）+ Benchmark 标签页（with vs without 对比通过率、延迟、token 用量）
- **Description 优化**：run_loop.py + 训练/测试集分割，迭代优化 description 的触发准确率
- **SkillsBench**：外部评测基准（skillsbench.ai）

---

## 已知局限

1. **Token 消耗极高且成本不透明**：20 个评测查询 ×3 次运行 = 60 个会话，消耗 5 小时时间块的 ~69%，零可操作结果
2. **流程冗长需大量用户确认**：简单 Skill 的开销远超 Skill 本身价值
3. **子任务爆炸**：3 个测试用例一轮产生 10+ 子 Agent
4. **Description 优化对"操作性"Skill 无效**：模型直接处理，不咨询 Skill，recall 0%
5. **Skill 膨胀风险**：迭代改进倾向添加指令，5KB→50KB
6. **学习曲线陡峭**

---

## 关键洞察

1. **Description 比指令正文更关键**：写好 description 决定 Skill 是否被触发
2. **渐进加载解决上下文膨胀**：三层加载是 Agent 系统最优雅的设计
3. **做 Prompt Engineering 要像做 ML**：训练集、测试集、评估指标、迭代优化、反过拟合
