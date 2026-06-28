# 公众号文章方法论提炼：Agent 评测、Harness、Skill 与工程化闭环

来源目录：`F:\Resume\公众号文章\md\公号三刀导出-20260626-172948`  
阅读日期：2026-06-28  
范围：18 篇主文章，排除 `assets` 下的导出素材。

## 一句话结论

这批文章共同指向同一个判断：Agent 产品不能只靠模型能力和 prompt 调参，需要被设计成一个可评测、可观测、可回归、可控成本、可沉淀经验的工程系统。真正可借鉴的不是某个单点技巧，而是“Spec 定义任务 → Harness 执行任务 → Trace 捕获过程 → Grader 评分 → Report 归因 → Skill/Prompt/Model 迭代 → Baseline 回归”的闭环。

## 文章清单与核心贡献

| 来源 | 文章 | 最值得借鉴的东西 |
|---|---|---|
| Feisky | Anthropic 万字长文：AI Agent 评估体系全解析 | Agent eval 术语、三类评分器、能力评估 vs 回归评估、pass@k/pass^k、任务/评分器维护原则 |
| 阿里云开发者 | 自动化评测的九九归一——评测agent | 评测 Agent 学习标注文档、样本学习、人审预验收、badcase 分析、多模态识图-推理解耦、训练评估闭环 |
| 阿里云开发者 | ABACI内核缺陷智能体：让模糊测试真正“自动化” | 缺陷智能体的工作区、崩溃上下文、Cause/Fix Bisect、修复模式库、验证驱动补丁生成 |
| 阿里云开发者 | 企业级 Agent 多智能体架构与选型指南 | 先单 Agent + 工具，达到复杂度阈值后再多 Agent；Pipeline、Routing、Skills、Subagents、Supervisor、Handoffs 等模式选型 |
| 阿里云开发者 | 2026 年 AI 编码的“渐进式 Spec”实战指南 | Spec 作为上下文锚点，需求、任务拆分、变更摘要、变更日志、审查 Agent 的文件化协作模式 |
| 阿里云开发者 | 从聊天窗口到多 Agent 控制台 | 编程协作从单聊天窗口转向多 Agent 控制台：任务拆分、状态可见、并行协作、角色化执行 |
| 阿里云开发者 | 深度解析 Claude Code 在 Prompt / Context / Harness 的设计与实践 | 静态/动态 Prompt 分层、上下文注入、MicroCompact/Session Compact/Full Compact、权限引擎、沙箱、Hook、Agent 分工 |
| 阿里云开发者 | Ontological Engineering | 本体工程把“数据驱动”推进到“决策中心”：实体、关系、动作、业务语义、决策闭环 |
| 阿里云开发者 | Harness Engineering实践 | AI First 评测平台：AI 创建评测任务、生成评测集、运行评测、提交报告、再自动优化系统 |
| 阿里云开发者 | AGENTS.md 实践指南 | 用一个文件固化项目上下文、开发规则、命令、目录、测试与协作约束，减少重复解释和错误探索 |
| 阿里云开发者 | ANOLISA Token 账单 | Agent 成本可观测：逐笔记录 token、模型、工具、会话、时间维度，形成成本归因 |
| 阿里云开发者 | LoongSuite GenAI 可观测语义规范 | Entry/Step Span、Skill 语义、Token 级推理观测、统一 Invocation 数据类 + Context Manager 插桩 |
| 阿里云开发者 | Agent Skill规范、构建与设计模式 | Skill 的命名、description、正文、文件引用、测试、评审、TDD/RED-GREEN-REFACTOR 迭代 |
| 阿里云开发者 | Agent从一问一答到自主执行面临哪些挑战？ | 从问答助手到自主执行者的挑战：长程任务、工具可靠性、自我校验、安全边界 |
| 阿里云开发者 | Java Harness 方法论 | AI Coding 体验差异来自 Harness：可测试性、可观测性、工具 AI 化、隔离性、本地一键启动 |
| 阿里云开发者 | Agent核心技术概念与范式演变 | Prompt、Planning、Memory、Tools、Workflow、Environment 六个模块的工程化演进 |
| 腾讯技术工程 | AI Coding Agent Token 成本控制 | 五类成本、Prompt Cache、Topic 切分、Skill/MCP 成本、CLI 优先、模型路由、输出压缩 |
| 腾讯技术工程 | AI Agent & Skill 测评方案及落地实践 | 三类评委、五大维度、用例集设计、评分规则、用例基线、执行测评的可复用模板 |

## 可借鉴的设计方法论

### 1. Eval-Driven Development：先定义可验证目标，再优化 Agent

Agent 的研发不应从“调 prompt 看感觉”开始，而应从 eval 开始：

1. 把真实任务拆成独立 Task。
2. 为每个 Task 写清输入、环境、成功标准、参考解或可验收状态。
3. 配置确定性评分器、Rubric 评分器和人工校准机制。
4. 跑固定评估套件，持续比较模型、prompt、工具和 skill 的变化。
5. 将线上失败、人工验收、badcase 分析不断回灌为新用例。

对 CodePulse 的启发：评测不是附属模块，而是奖励信号和产品主循环。新增能力应先落成任务与评分器，再进入优化。

### 2. 能力评估和回归评估分离

能力评估回答“Agent 现在能挑战什么难任务”，允许低通过率，目的是提供改进信号。回归评估回答“以前会做的事有没有退化”，通过率应接近 100%，目的是守住稳定性。

实践规则：

- 新难题先进入能力套件。
- 能力题通过率稳定后，再提升为回归套件。
- 回归套件一旦下降，优先阻断发布。
- 已经 100% 饱和的能力套件只适合做回归，不再适合作为优化奖励。

### 3. 评结果优先，评路径谨慎

文章反复强调：Agent 可能找到设计者没想到但有效的路径，因此评分器应优先检查最终状态，而不是强制固定步骤。路径检查只在安全、权限、必须调用某工具、必须留下审计痕迹等场景使用。

可落地规则：

- 结果类：文件存在、测试通过、数据库状态、API 返回、UI 状态。
- 过程类：必要工具调用、越权行为、重试次数、上下文使用、是否读了关键文档。
- 质量类：代码质量、解释质量、推理合理性、用户体验。

### 4. Spec 是长程协作的上下文锚点

“渐进式 Spec”和 AGENTS.md 的共同思想是：不要把需求、约束和历史决策挂在聊天记录里，而要文件化、结构化、可审查。

推荐文件体系：

- `AGENTS.md`：项目级规则、目录、命令、测试、禁区。
- `spec.md`：需求背景、目标、非目标、验收标准。
- `tasks.md`：任务拆分、状态、依赖、验证方式。
- `change-summary.md`：本轮变更摘要。
- `decision-log.md`：关键取舍和原因。
- `review-rubric.md`：审查标准和评分规则。

### 5. 渐进式披露优于巨型 Prompt

Prompt/Context 的演进方向是动静分离：

- System Prompt 保持短、稳定、通用。
- 业务知识、工作流、示例、工具说明放到文件或 Skill。
- Agent 先看名称和 description，必要时再加载完整内容。
- 稳定前缀前置，变化内容后置，以提高 Prompt Cache 命中率。

这套方法同时改善准确率、维护性和成本。

### 6. Harness 是 Agent 能力的放大器

AI Coding 体验差异往往不是模型差异，而是 Harness 差异。优秀 Harness 提供：

- 可测试性：一条命令启动、一条命令验证、确定性数据。
- 可观测性：Trace、日志、指标、产物快照。
- 工具 AI 化：输出面向 Agent 压缩和结构化，而非面向人类 UI。
- 隔离性：沙箱、临时工作区、权限边界、可重放环境。
- 回归能力：固定用例集、基线、趋势比较。

### 7. Workflow 与 Skill 采用混合架构

文章给出的成熟判断是：不要在 Workflow 和 Skill 之间二选一。

- 标准化、可复用、知识密集的子任务封装为 Skill。
- 稳定性要求极高、流程不可跳步的主干保留 Workflow。
- 需要精确控制的步骤写成脚本，由 Skill 调用。
- 多 Agent 只在上下文、职责、权限、流程复杂度达到阈值后引入。

### 8. CLI/Script 往往比 MCP 更适合 Agent

MCP 适合跨系统编排、权限统一、结构化资源访问，但每个 MCP 都带来工具定义、选择空间和上下文成本。CLI/Script 的优势是：

- 大模型天然熟悉命令行模式。
- `--help` 可即时学习，按需披露。
- 输出可定制为 Markdown/JSON，减少 token。
- 鉴权和复杂协议可以封装在脚本内部。

可借鉴原则：先提供轻量 CLI 和脚本；只有当需要跨系统治理、统一权限、资源订阅时再上 MCP。

### 9. 多智能体不是默认答案

企业级多智能体文章给出清晰门槛：绝大多数任务先用单 Agent + 精准工具。只有出现以下阈值才引入多 Agent：

- 上下文太大，必须按步骤或角色选择性呈现。
- 职责和权限需要独立维护。
- 业务流程要求结构化流转。
- 需要专家协作、批评、优化、交接或并行处理。

模式选型：

- `Pipeline`：固定顺序、并行、循环流程。
- `Routing`：分类后交给专家，再合并结果。
- `Skills`：单 Agent 多专长，按需加载说明。
- `Subagents`：上下文隔离，适合独立子任务。
- `Supervisor`：监督者把专家当工具调用。
- `Handoffs`：状态驱动的角色移交。
- `StateGraph`：需要显式状态机和自定义流程时使用。

### 10. 本体工程用于把 AI 从“生成答案”推向“驱动决策”

Ontology 文章可借鉴的不是具体数据库，而是建模方式：

- 用实体、关系、动作、指标、约束描述业务世界。
- 把数据表映射为业务对象，把流程映射为可执行动作。
- 让 Agent 不只检索数据，而是在业务语义层做推理、影响分析和决策建议。
- 对复杂企业系统，知识图谱和语义层是降低幻觉、增强可解释性的关键。

## 可复用评估标准

### 三类评分器

| 评分器 | 适用 | 优点 | 风险 |
|---|---|---|---|
| 确定性评分器 | 测试、Lint、AST、文件、数据库、状态、权限、成本 | 快、便宜、可复现 | 对有效变体不够宽容 |
| Rubric 评分器 | 代码质量、推理质量、解释清晰度、体验、开放式产物 | 灵活、能处理语义 | 非确定性，需要校准 |
| 人工评分器 | 黄金标准、边缘场景、红队、安全、高价值样本 | 最可信 | 慢、贵、不可规模化 |

优先级：确定性 > Rubric > 人工。人工主要用于校准 LLM 评委、诊断 0%/100% 异常、建立前 20-50 个 ground truth。

### 五大维度

| 维度 | 子项 | 推荐指标 | 优先级 |
|---|---|---|---|
| 功能正确性 | 结果正确、状态一致、任务完成 | pass@1、pass@k、pass^k、测试通过率、状态断言 | P0 |
| 过程质量 | 推理合理、步骤有效、上下文利用、自我纠错 | Rubric 分、关键步骤覆盖率、纠错成功率、Trace 审查 | P1 |
| 效率成本 | Token、工具调用、延迟、重试、单任务费用 | avg/p95 tokens、tool calls、latency、retry rate、cost/task | P1 |
| 鲁棒安全 | 故障恢复、抗注入、越权、拒绝合理性 | 故障注入通过率、越权次数、攻击成功率、误拒/漏拒 | P0 |
| 体验对齐 | 清晰度、语气、主动澄清、可解释性 | 清晰度评分、澄清率、用户反馈、A/B | P2 |

### 用例集设计

用例至少覆盖四类：

1. 触发条件用例：该调用时调用，不该调用时不调用。
2. 核心逻辑用例：主要能力路径和高频业务路径。
3. 产物质量用例：报告、代码、文档、UI、图片等开放式产物。
4. 异常容错用例：工具失败、超时、权限不足、脏数据、恶意输入。

每个用例应包含：

- 任务输入。
- 初始环境或夹具。
- 期望结果。
- 允许的变体。
- 评分器配置。
- 参考解或人工验收依据。
- 成本和耗时阈值。

### 非确定性指标

- `pass@k`：k 次尝试至少成功一次，衡量能力上限。
- `pass^k`：k 次尝试全部成功，衡量稳定性。
- 对面向用户的生产 Agent，`pass^k` 比 `pass@k` 更重要。
- 同一个任务多次运行可帮助发现偶发成功、偶发失败和工具链波动。

### 基线机制

基线不只是分数，而是可比较快照：

- 输入、环境版本、模型版本、prompt/skill 版本。
- Trace：工具调用、参数、返回、错误、耗时。
- 产物：文件、报告、截图、数据库状态。
- 指标：token、成本、延迟、重试。
- 评分：各维度得分和失败原因。

基线更新时机：

- 业务规则变化。
- 标准答案确实过时。
- 评分器 bug 修复。
- 能力题转入回归题。

## 可复用工程模式

### 1. Evaluation Harness

最小闭环：

```text
Task Suite
  -> isolated workspace
  -> agent runner
  -> tool / browser / CLI execution
  -> trace capture
  -> deterministic graders
  -> rubric graders
  -> human calibration
  -> report and trend
```

关键设计：

- 每次试验从干净环境开始。
- 真实执行，不只看 Agent 声称完成。
- Trace 必须可读，失败时能判断是 Agent 错、工具错、评分器错还是任务规格错。
- 评测任务和评分器都应版本化。

### 2. AI First 评测平台

Harness Engineering 文章的核心模式：

1. 人只描述评测目标和验收标准。
2. AI 创建评测任务。
3. AI 生成标准用例和 Rubric 用例。
4. AI 执行用例，包括终端和 UI。
5. AI 提交评测报告。
6. Coding Agent 阅读报告并优化系统。
7. 再跑下一轮，形成多轮自动优化。

平台实体可抽象为：

- Workspace
- EvaluationTask
- EvaluationCase
- EvaluationRun
- EvaluationReport
- ScoreBreakdown
- ImprovementPlan
- RegressionBaseline

### 3. Trace / Span 语义模型

LoongSuite 文章可直接借鉴为可观测模型：

- `Entry Span`：一次用户任务入口。
- `Step Span`：Agent 的一个执行步骤。
- `LLM Span`：模型调用。
- `Tool Span`：工具调用。
- `Skill Span`：Skill 触发、读取和执行。
- `Memory Span`：记忆检索、写入、更新。
- `Token Metrics`：输入、输出、推理 token、TTFT、TPOT、per-token latency。

工程模式：

- 业务侧只填 Invocation 数据类。
- Handler 用 Context Manager 自动创建 span、挂属性、记录 metrics、处理异常。
- 语义规范升级只改工具层，不让每个插桩重复维护。

### 4. Skill 工程模式

Skill 的高质量标准：

- `name` 精准、短、可触发。
- `description` 写触发条件，而不是泛泛介绍。
- 正文写步骤、约束、输入输出、失败处理。
- 长示例和脚本放到引用文件或 `scripts/`。
- 低频长说明按需加载。
- Skill 要有测试用例，验证触发、执行、产物和边界条件。

Skill 迭代方式：

```text
RED：收集失败任务，建立基线
GREEN：写最小 Skill，让关键用例通过
REFACTOR：堵触发误差、压缩说明、沉淀脚本
EVAL：并行跑用例，读 trace，更新 description
```

### 5. 评测 Agent 模式

自动化评测 Agent 文章提供了“评测同学自动化”的模式：

- 学习标注文档，生成摘要和打分 prompt。
- 试标样本，人对错误给反馈。
- 错题进入评测任务记忆。
- 运行时检索文档、错题、问卷、常识知识。
- 多模态任务先用小 VLM 忠实描述，再由主模型推理评分。
- 输出概率或置信度，用于挑选人工复审样本。
- 评测结束自动生成单条 badcase 和整体分析报告。

可借鉴点：把“标准”作为可学习资产，把“错题”作为持续训练数据，把“人审”变成校准而不是全量劳动。

### 6. 缺陷修复 Agent 模式

ABACI 的内核缺陷智能体可抽象为：

```text
Crash / Fuzzing Finding
  -> workspace preparation
  -> defect reproduction
  -> cause bisect
  -> target function identification
  -> metadata extraction
  -> similar fix / pattern retrieval
  -> patch generation
  -> diff creation
  -> validation
  -> fix bisect / pruning
```

关键资产：

- 崩溃上下文。
- 内核工作区。
- Cause Bisect。
- 缺陷同一性判断。
- Fixes 匹配。
- 修复模式库。
- 验证脚本。

对 CodePulse 的启发：复杂修复任务不要只评最终 diff，应把复现、定位、模式检索、验证都纳入 trace 和评分。

### 7. 成本治理模式

Token 成本文章的核心模型：成本不是“问了多少字”，而是系统为了回答反复搬运了多少上下文。

五类成本：

- 输入 token：系统提示、历史、代码、检索结果、工具定义。
- 输出 token：最终回答。
- 推理 token：thinking budget。
- 工具往返：工具说明、参数、返回再次进入上下文。
- 重试成本：错误后整包上下文重复付费。

治理手段：

- 一个 session 一件事。
- 长会话及时压缩，不把聊天记录当数据库。
- 高频稳定 Skill 常驻，低频长 Skill 按需触发。
- MCP 控制数量，优先 CLI/Script。
- 引用文件给完整路径。
- 一次性给完整目标、背景、约束和验收条件。
- 模型路由：便宜模型做标准活，强模型做架构和复杂 bug。
- Prompt Cache：稳定内容前置，变化内容后置。
- 输出压缩：终端输出、测试日志、diff 做过滤。

### 8. 多模态评测的识图-推理解耦

自动化评测 Agent 文章的低成本技巧很重要：

- 不让大模型一边深度推理一边保留细粒度视觉事实。
- 先用小 VLM 做忠实描述或 OCR 级梗概。
- 再把图像梗概和原图交给主模型评分。
- 用图片策略分类模型选择描述策略。

这个模式可迁移到 UI 评测、截图评审、报告质量评估。

### 9. 安全与隔离模式

从 Claude Code、Java Harness、多 Agent 和环境演进文章中可提炼：

- 每个 Agent 任务有独立 workspace。
- 文件系统、网络、命令、浏览器操作需要权限策略。
- 高风险动作需要人工确认。
- 子 Agent 无状态或受控状态，避免上下文污染。
- 评测环境与生产环境相似，但必须隔离。
- 残留文件、缓存、历史 git 状态会污染分数。

## 对 CodePulse 的直接映射

### 产品架构映射

| CodePulse 层 | 可吸收的方法 |
|---|---|
| 环境层 | isolated workspace、Docker/沙箱、权限断言、可重放环境 |
| 数据层 | Task Suite、真实失败回灌、badcase、ground truth、错题集 |
| Agent 层 | 单 Agent + 工具优先，多 Agent 按阈值引入，Skill/CLI/Script 工具化 |
| 评测层 | 三类评分器、五大维度、能力/回归套件、pass@k/pass^k |
| 可观测性层 | Entry/Step/LLM/Tool/Skill/Memory Span，token/cost/latency metrics |
| 自进化层 | Report -> ImprovementPlan -> Skill/Prompt/Model 迭代 -> Baseline 回归 |
| 产出层 | Scorecard、趋势图、失败归因、成本画像、发布建议 |

### 最小 MVP 建议

1. 先做 Task/Case/Run/Report 四个核心实体。
2. Grader 先支持 deterministic、rubric、human-placeholder 三类接口。
3. Trace 先记录 step、tool_call、artifact、token/cost、error。
4. 每个用例必须能绑定 baseline。
5. UI 第一版只呈现：总分、五维度分、失败用例、成本、trace 链接、建议动作。
6. Skill 优化先不自动改代码，先产出可审查的 improvement plan。

### 评分模板建议

```yaml
id: code_agent_fix_bug_001
type: coding_agent
suite: regression
input:
  issue: "Fix auth bypass when password is empty"
environment:
  repo: sample-auth
  setup: "pytest fixtures/reset_db.py"
graders:
  - type: deterministic_tests
    required:
      - tests/test_empty_password_rejected.py
      - tests/test_null_password_rejected.py
  - type: static_analysis
    commands:
      - ruff check
      - mypy
      - bandit -r src
  - type: state_check
    expect:
      security_logs.event_type: auth_blocked
  - type: rubric
    rubric: rubrics/code_quality.md
metrics:
  - pass_at_k
  - pass_power_k
  - tool_calls
  - total_tokens
  - latency_ms
  - retry_count
  - cost_usd
baseline:
  version: 2026-06-28
  expected_score: 90
```

### 报告归因模板

```text
结果：改进 / 退化 / 持续失败 / 稳定成功
失败阶段：理解任务 / 检索上下文 / 工具调用 / 代码修改 / 验证 / 汇报
失败类型：规格不清 / 环境问题 / 工具错误 / 模型幻觉 / 权限越界 / 成本超限 / 评分器问题
证据：Trace step id、artifact、日志、diff、截图
建议动作：补 Spec / 补 Skill / 改 Grader / 加用例 / 调模型 / 调工具 / 修环境
是否进入回归套件：是 / 否
```

## 逐篇细读提炼

### Anthropic 万字长文：AI Agent 评估体系全解析

核心是 Agent eval 的基础语法。Task、Grader、Outcome、Evaluation Harness、Agent Harness、Evaluation Suite 必须分清。它特别强调 outcome 是环境最终状态，而不是 Agent 声称完成。最可借鉴的是三件事：能力评估与回归评估分离；确定性、模型、人工三类评分器组合；读 trace 校验评分器是否真的有效。

可落地到 CodePulse：作为评测层术语和数据模型的根规范。

### 自动化评测的九九归一——评测agent

核心是“评测同学 Agent 化”。评测 Agent 先学习业务标注文档，再通过样本试标、人审反馈、错题记忆、badcase 分析持续改进。工程上值得借鉴的是上下文增强、错题检索、多模态梗概模型、置信度筛选人工复审。

可落地到 CodePulse：把 Grader Agent 设计为可学习标准、可积累错题、可输出置信度和归因的组件。

### ABACI内核缺陷智能体

核心是把模糊测试后的缺陷处理自动化。它不是直接让模型写补丁，而是先做工作区准备、缺陷验证、目标函数识别、元数据提取、模式检索，再补丁生成和验证。Cause Bisect、Fix Bisect、缺陷同一性判断、修复模式库都值得吸收。

可落地到 CodePulse：用于复杂 bug 修复类 benchmark 的过程评分设计。

### 企业级 Agent 多智能体架构与选型指南

最重要的判断是不要默认多 Agent。先单 Agent + 工具，只有上下文、职责、权限、结构化流程超过阈值时再引入多 Agent。多 Agent 模式要按业务形态选型，而不是为了“看起来先进”。

可落地到 CodePulse：多 Agent benchmark 不应只测最终结果，还要测路由准确性、交接状态、上下文隔离和合并质量。

### 2026 年 AI 编码的“渐进式 Spec”实战指南

核心是把需求协作从聊天记录迁移到文件系统。Spec、任务拆分、项目规则、质量审查、变更摘要、变更日志形成稳定上下文。它解决的是长程 AI Coding 中最贵的隐性成本：心流中断和上下文漂移。

可落地到 CodePulse：所有评测任务都应有机器可读/人可读的 spec，而不是只有 prompt。

### 从聊天窗口到多 Agent 控制台

核心是交互范式变化。聊天窗口适合短任务，多 Agent 控制台适合长任务、多状态、多角色协作。关键价值不是“多个模型同时说话”，而是任务状态、职责边界、并行执行和可视化控制。

可落地到 CodePulse：Dashboard 可以从“评测结果页”演进为“评测运行控制台”。

### 深度解析 Claude Code 在 Prompt / Context / Harness 的设计与实践

核心是静态 Prompt、动态 Prompt、上下文注入、压缩和 Harness 的组合。MicroCompact、Session Memory Compact、Full LLM Compact 体现了分层压缩思路；权限引擎、沙箱、Hook、异步主循环体现了 Agent 运行时设计。

可落地到 CodePulse：把压缩、权限、沙箱、Hook 作为 Agent Harness 的可观测对象。

### Ontological Engineering

核心是用本体把业务对象、关系、指标和动作组织起来，让 Agent 在语义层而不是表结构层工作。它适合企业级 AI 转型，因为企业真正需要的是决策闭环，而不是单次问答。

可落地到 CodePulse：未来可为 benchmark、grader、skill、trace 建一层 ontology，支持跨项目归因和经验复用。

### Harness Engineering实践

核心是 AI First 评测平台。平台提供 workspace、任务、评测集、报告；AI 负责生成用例、运行评测、提交报告、再根据报告优化。它验证了评测平台本身可以成为 Agent 操作对象。

可落地到 CodePulse：把 CLI/API 设计成 Agent 友好，让 Agent 能自己创建评测、运行评测、读取报告。

### 一个文件让 AI Coding 效率翻倍：AGENTS.md 实践指南

核心是项目规则常驻文件化。AGENTS.md 应承载目录结构、命令、测试方式、编码规范、禁区、业务上下文。好处是减少重复说明和错误探索。

可落地到 CodePulse：评测时可以检查 Agent 是否读取并遵守 AGENTS.md。

### Agentic OS (ANOLISA) Token 账单

核心是成本观测产品化。Agent 的 token 开销需要按模型、会话、工具、事件、时间、任务归因，否则优化无从下手。

可落地到 CodePulse：成本不只是 tracked metric，应进入评分和回归门禁。

### LoongSuite GenAI 可观测语义规范

核心是统一语义。Agent、Skill、Tool、Memory、Token 推理都需要标准 span 和属性。尤其 Token 级观测可以定位慢 token、资源干扰、异常 token、采样参数问题。

可落地到 CodePulse：trace schema 应预留 span taxonomy 和 token-level metrics。

### Agent Skill规范、构建与设计模式

核心是 Skill 本身也要工程化。Skill 不是写一段说明，而是一个包含触发描述、正文、引用文件、脚本、测试、评审和迭代流程的可发布组件。description 太长或太宽都会导致误触发和上下文浪费。

可落地到 CodePulse：SkillOpt 应先优化 description 和测试，再优化正文和脚本。

### Agent从一问一答到自主执行面临哪些挑战？

核心是从回答者到执行者后，挑战从“答得好不好”变成“长程执行是否可靠”。关键问题包括任务规划、工具失败、自我校验、权限边界、状态管理。

可落地到 CodePulse：自主执行类任务必须测长程稳定性和异常恢复。

### Java Harness 方法论

核心是语言/技术栈的 AI Coding 体验取决于 Harness。Java 项目若缺本地环境、一键启动、配置查询、测试夹具、日志观测，AI 就会寸步难行。

可落地到 CodePulse：benchmark 应记录 harness maturity，否则模型分数会混入工程环境差异。

### Agent核心技术概念与范式演变

核心是六个模块的范式迁移：Prompt 从小作文到上下文工程；Planning 从 CoT 到长程任务拆解；Memory 从纯 RAG 到文件系统 + 向量混合；Tools 从 API/MCP 到 CLI/Script；Workflow 从刚性编排到 Skill + Script 混合；Environment 从无状态调用到隔离运行时。

可落地到 CodePulse：评测维度应覆盖这六个模块，而不是只测最终回答。

### AI Coding Agent Token 成本控制

核心是成本治理的方法论。最有价值的公式是：成本来自重复搬运上下文，而不是用户问题本身。Session 切分、上下文压缩、模型路由、CLI 优先、Skill 按需、Prompt Cache 都是工程手段。

可落地到 CodePulse：效率成本维度要细分输入、输出、推理、工具往返和重试。

### AI Agent & Skill 测评方案及落地实践

核心是最接近 CodePulse 的评测框架：三类评委、五大维度、用例设计、评分规则、用例基线、执行测评。它把“测评 = 输入 → 执行 → Trace + 产物 → 检查规则 → 可对比分数”讲得最完整。

可落地到 CodePulse：可直接作为 MVP 评测层和报告层的蓝本。

## 最值得优先吸收的 12 条

1. 能用确定性评分器判断的，绝不用 LLM 评分。
2. 能评最终状态的，不强制评固定路径。
3. 能从真实失败抽用例的，不凭空造 benchmark。
4. 能一条命令启动和验证的，才适合 AI Coding。
5. 能文件化的上下文，不留在聊天记录里。
6. 能按需加载的 Skill，不常驻进 prompt。
7. 能用 CLI/Script 解决的，不急着上 MCP。
8. 能单 Agent + 工具解决的，不急着多 Agent。
9. 能记录 Trace 的运行，才有资格谈优化。
10. 能量化成本的 Agent，才有资格规模化。
11. 能把 badcase 回灌为用例和错题的评测，才会越跑越强。
12. 能把评测报告转为下一轮改进计划的系统，才真正形成自进化闭环。
