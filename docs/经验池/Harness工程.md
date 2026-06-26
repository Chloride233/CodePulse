# Harness 工程

## 来源

- 阿里云开发者 "深度解析 Claude Code 在 Prompt / Context / Harness 的设计与实践"（2026-04-20）
- 阿里云开发者 "AI 不缺智商缺纪律：我的 Harness 工程化实践"（2026-06-16）
- 阿里云开发者 "Harness Engineering实践，做了一个平台让AI一晚上自动评测和优化你的系统"（2026-04-29）
- 阿里云开发者 "都是 AI Coding，为什么 Java 体验差了一个量级？五条方法论帮你构建自己的 Harness 环境"（2026-05-21）

---

## 核心理念

> 模型的智能够了，缺的是纪律。纪律必须来自外部确定性基础设施，而不是更好的 prompt。

**Prompt 是一次性说服，Harness 是结构性约束。**

把规则堆进 prompt（像不断增长的 CLAUDE.md）是负债——规则最终溢出上下文窗口，模型遗忘或自相矛盾，合规概率性下降。Harness 方法将纪律外化为确定性基础设施。

---

## Prompt / Context / Harness 三层递进

| 层级 | 解决什么 | 效果 |
|------|---------|------|
| Prompt Engineering | "怎么跟模型说话" | ~70 分 |
| Context Engineering | "模型看到什么" | ~80-85 分 |
| Harness Engineering | "运行时环境和约束" | ~90-95 分 |

**关键洞察：** Claude Code 的优势不仅来自 Claude 模型本身，更来自周围的工程——在 Claude Code 之外用同样的 Claude API，效果明显更差。

---

## Claude Code 架构解析

### Prompt 动态组装（6 步）

1. `QueryEngine.ask()` 入口
2. `fetchSystemPromptParts()` 并行获取三部分：默认系统 prompt、系统上下文（Git 状态）、用户上下文（CLAUDE.md + 当前日期）
3. `getSystemPrompt()` 组合静态和动态部分
4. `buildEffectiveSystemPrompt()` 优先级选择（自定义覆盖默认）
5. 上下文注入：Git 状态附加到系统 prompt；CLAUDE.md 作为 `<system-reminder>` 消息前置
6. `splitSysPromptPrefix()` 分块用于 KV Cache 优化

**静态模块：** 身份/介绍、工具定义、行为指南、安全规则
**动态模块：** 会话特定指导、Skill 列表、Agent 列表、MCP 服务器配置、用户设置

### 三层渐进压缩系统

**Layer 1: MicroCompact（规则驱动，无 LLM 调用）**
- 可压缩工具白名单（Bash、Read、Grep、Glob）
- Edit/Write 输出保留（安全考虑）
- 图片按 2000 token 固定估算
- 两种路径：时间驱动（截断旧输出）和缓存边界感知

**Layer 2: Session Memory Compact（复用已有摘要）**
- 用之前的会话记忆摘要替换旧消息
- 触发条件：上下文超过 10,000 token 且 5+ 消息
- 每次最多压缩 40,000 token
- 保留最近消息以维持近因效应

**Layer 3: Full LLM Compact（调用 LLM 生成结构化摘要）**
- 强制 9 段结构模板
- 隐式 CoT：模型在 `<analysis>` 标签中推理（返回前剥离），然后输出 `<summary>`
- 防工具调用保护（`NO_TOOLS_PREAMBLE`）

**AutoCompact 触发：** 剩余上下文低于 13,000 token 时。先尝试 Session Memory（便宜），再回退到 Full LLM（贵但可靠）。

### Memdir 结构化记忆系统

四种记忆类型：User（偏好）、Feedback（纠正）、Project（架构决策）、Reference（文档/代码模式）

记忆加载使用预算感知过滤器，动态裁剪内容以适应上下文窗口。语义检索使用 Sonnet 模型作为"图书管理员"选择 top 5 最相关记忆。

### 六个内置 Agent（加一个隐藏）

| Agent | 模型 | 权限 | 用途 |
|-------|------|------|------|
| General-Purpose | 父模型 | 全部工具 | 默认工人 |
| Explore | Haiku（快/便宜） | 只读 | 代码侦察，不加载 CLAUDE.md |
| Plan | 父模型 | 只读 | 结构化方案设计 |
| Verification | 父模型 | 只读 + /tmp | 红队思维验证 |
| Guide | Haiku | 只读 | 自文档化 |
| Statusline | Sonnet | Read/Edit | 终端状态栏配置 |
| Fork Sub（隐藏） | 父模型 | 全部 | 分叉父 Agent，共享 prompt cache |

**Verification Agent 最复杂：**
- 红蓝对抗："你的工作不是确认它能用——而是尝试破坏它"
- 反懒惰：明确指出 AI 自欺模式（"代码看起来对"不是验证；"实现者的测试通过了"——实现者也是 AI）
- 严格权限：只读，/tmp 除外（用于测试脚本）
- 变更类型特定策略：前端、后端/API、CLI、基础设施、bug 修复、数据库迁移、重构、移动端各有不同验证方法

### 权限引擎

三行为模型：Allow（低风险自动批准）、Deny（高风险自动阻止）、Ask（中风险，提示用户）
多源规则配置，严格优先级：settings.json > CLI 参数 > 命令规则 > 会话规则

### 沙箱隔离

Linux 上使用 `bubblewrap (bwrap)`（~986 行实现）：
- 只读根文件系统挂载，白名单目录
- 网络和 PID 命名空间隔离
- 非 root 用户强制
- `shouldUseSandbox` 智能检测不兼容沙箱的命令

### Hook 系统

20+ 事件类型：
- 工具生命周期：PreToolUse、PostToolUse、ToolError
- 会话生命周期：Start、End、Pause、Resume
- 消息生命周期：PreSampling、PostSampling、UserPromptSubmit
- 文件操作：PreFileEdit、PostFileEdit、PreFileWrite、PostFileWrite

Hook 返回结构化 JSON：执行阻断（`{"blocked": true}`）、输入/输出修改、消息注入。10 分钟超时防止挂起。

---

## 五层 Harness 架构（实践版）

| 层 | 内容 | Token 预算 |
|----|------|-----------|
| Layer 1: Resident Entry | CLAUDE.md + CLAUDE.local.md | ≤8K |
| Layer 2: Atomic Rules | rules/（7 个文件，每个单一职责） | 按需 |
| Layer 3: Role Agent | dispatcher / orchestrator / 三角色审查 / 执行链 | 按需 |
| Layer 4: On-demand Context | context/（10 个文件，按需加载） | 按需 |
| Layer 5: Execution Support | skills/（22 项）+ commands/（12 项）+ evals/ | 按需 |

### Agent 角色分工

- **dispatcher**：读 state.json 和 workflow.yaml，决定下一个运行哪个 Agent（交通警察，无业务逻辑）
- **orchestrator**：读三个审查 Agent 写入 phases/*.md 的意见，综合结论，与用户确认
- **三角色审查**（requirement-analyst、tech-architect、quality-guardian）：各自独立写意见，互不可见，提供对抗性审查
- **执行链**：plan-generator → developer → verifier → deployer → tester，各有不同系统 prompt 和工具权限

### 三条铁律

1. 主会话只听 dispatcher
2. 主会话禁止直接读 phases/*.md 或 evidence.json
3. 只有 orchestrator 能写 state.json（通过 Hook 强制）

### G1-G8 Gate Wall

每个 Gate 是确定性 Python 函数，检查工件是否存在、编译是否通过、测试是否通过。任何 Gate FAIL 就回到 DEVELOPING——这是"阻断"，不是"建议"。

### 动态流程路由

完整管道 19 个节点，但不是每个任务都跑 19 个。按 **意图 × 风险** 动态裁剪：
- QUERY：0 个节点
- BUG_FIX/LOW：快速路径 5 个节点
- FEATURE/MEDIUM：加设计和对抗辩论
- FEATURE/HIGH：完整 19 个节点 + ADR

---

## 自动化评测平台

### 闭环流程

1. 发布评测任务到平台
2. AI 生成评测集（覆盖多维度）
3. 对真实系统运行评测（每个用例约 1 分钟）
4. 读评测报告
5. 自动修改代码解决报告中的问题
6. 重新评测
7. 重复

### 实测结果

- 每轮约 1 小时
- 晚上启动，早上完成 3 轮：
  - v1：90.7/100
  - v2：97.4/100
  - v3：99.1/100
- 分数在所有五个评测维度上稳步提升

### 评分方法

- **标准评测**：二元通过/失败
- **Rubric 评测**：多级标准（excellent / good / acceptable / poor）

---

## 经验三级进化

| 级别 | 定义 | 触发条件 |
|------|------|---------|
| Lesson | 单次记录 | 首次发生 |
| Pattern | 跨项目泛化 | 第二次在不同项目发生 |
| Instinct | 自动注入新项目 | 第三次验证后，需人工确认 |

**示例：** mvn -am 挂起 → Lesson → Pattern（"Mac + system-scope 依赖 = 禁用 -am"）→ Instinct（自动注入所有新项目的 build.md）

---

## 关键论文

- Lost in the Middle（Stanford TACL 2024）：LLM 注意力 U 型分布
- NVIDIA RULER：声称 32K+ 上下文的模型只有一半时间保持可靠
- arxiv 2605.29682：验证反馈质量（R²=0.94-0.99）比 token 消耗（R²=0.33-0.42）更能解释 Agent 成功

---

## 四个演进阶段

1. **开箱即用**：用社区项目 oh-my-claudecode；通用规范无法覆盖特定开发流程时触顶
2. **Prompt 堆砌**：所有规则写进 CLAUDE.md；三天后因上下文溢出崩溃
3. **精简+分层加载**：常驻 prompt 缩到 8K，深层内容放按需上下文层；长会话仍漂移
4. **Agent 调度编排**：不同 Agent 隔离职责，dispatcher 唯一大脑，文件交接，状态外化到 state.json

**核心教训：** "Prompt 约束是说服，不是强制。"
