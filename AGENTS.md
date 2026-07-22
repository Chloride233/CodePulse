# CodePulse — Code Agent 可信评测与回归门禁

## 项目定位

CodePulse 是一个面向 Code Agent 的可复现实验、可信评测与回归门禁平台。
核心价值是验证改进声明，而不是自研通用 Agent、沙箱或优化器。

当前权威状态见 `docs/project-status.md`。历史 PRD 和日期化实验规格不得覆盖
该状态页中的阶段结论与证据边界。

## 技术栈

- Python 3.11+、pytest、ruff、mypy、bandit
- LiteLLM（多模型：DeepSeek / GPT / Codex / Qwen）
- Docker（隔离执行）、JSONL（证据与结果存储）
- GitHub Actions（CI/CD）、Markdown + HTML（报告）

## 开发原则

代码是负债。每行新代码都是维护成本。删掉一行比写一行更骄傲。
追问真需求。用户给的是方案不是问题，追问为什么找到本质。
简单即美。好方案 = 满足需求的最简方案。
不过度设计。只解决当下确实存在的问题，扩展性留在接口层。
为故障设计。限流、熔断、降级，为故障准备对策而非幻想消灭故障。
追查根因。不治表面症状，多问几层为什么。
命名即文档。好命名胜过注释，精确一致词达意。
注释写为什么。不写显而易见的，只揭示代码无法表达的意图。
DRY。一切重复都是膨胀的种子。
测试改善设计。不好测 = 结构不好，单测倒逼更好的架构。
先怀疑自己。出 bug 先查自己代码，框架几乎不会错。
接口服务使用者。好用比好实现重要，复杂性封装内部。
善用 AI 但别依赖 AI。把 AI 当加速器，审查输出比写 prompt 更重要。
像负责一辈子那样写代码。如果每行代码都会公开到朋友圈，你一定写得更好。

## Build or Buy

新增 Agent controller、sandbox backend、optimizer 或 benchmark harness 前，先审查
维护活跃度、许可证和适配成本。成熟开源方案能够覆盖职责时，优先写小型 Adapter，
不扩展同职责的 legacy 实现。CodePulse 的自研代码只服务于实验冻结、证据、评测、
归因、门禁和报告。

## 工程规范

### 测试

- 每个模块必须有测试，覆盖率 ≥ 80%
- pytest 为唯一测试框架
- 测试命名：`test_<模块>_<场景>_<预期>`
- 确定性测试优先于 LLM 测试

### 代码质量

- ruff check 零报错才能提交
- mypy 零报错才能提交
- bandit 无高危才能提交
- 函数签名必须有类型注解

### Git

- commit message 格式：`<type>(<scope>): <description>`
- type：feat / fix / refactor / test / docs / chore
- 每个 PR 必须通过 CI

### 文档

- README：项目介绍 + 快速开始 + 架构说明
- 每个模块有 docstring
- 接口变更必须更新文档

## 目录结构

```
CodePulse/
├── codepulse/
│   ├── env/          # Layer 1: 环境层（Docker 沙箱）
│   ├── data/         # Layer 2: 数据层（数据集加载）
│   ├── agent/        # Layer 2b: Agent 实现层（RealAgent + 适配器）
│   ├── shared/       # Layer 1: 共享类型（trace_types / constants）
│   ├── eval/         # Layer 3: 评测层（五维度 + 三类 Grader）
│   ├── observe/      # Layer 4: 可观测性层（Trace + 指标）
│   ├── evolve/       # Phase 3 研究实现 + 回归门禁
│   ├── output/       # Layer 6: 产出层（报告）
│   ├── api/          # REST API（FastAPI + Dashboard 后端）
│   ├── benchmark/    # 业界基准注册 + 下载 + 运行
│   ├── commands/     # CLI 子命令组（baseline / evolve suggest）
│   ├── cli.py        # 主 CLI 入口
│   ├── config.py     # 配置管理
│   └── inspect.py    # 结果检查工具
├── tests/            # 测试
├── web/              # Vue 3 前端仪表板（独立构建）
├── datasets/         # 数据集
├── docs/             # 文档
├── .github/workflows/ # CI/CD 流水线
├── Dockerfile        # Docker 多阶段构建
├── docker-compose.yml
├── pyproject.toml    # 项目配置
└── AGENTS.md         # 本文件
```

## 五维度评测体系

| 维度 | 优先级 | 权重 | Grader 类型 |
|------|--------|------|------------|
| 功能正确性 | P0 | 30 分 | 确定性 |
| 过程质量 | P1 | 25 分 | LLM-as-Judge |
| 效率成本 | P1 | 15 分 | 确定性 |
| 鲁棒安全 | P0 | 20 分 | 确定性+LLM |
| 体验对齐 | P2 | 10 分 | LLM-as-Judge |

100 分扣分制，通过阈值 80 分。

## 关键概念

- **pass@k**：k 次至少成功 1 次（能力上限）
- **pass^k**：k 次全成功（稳定性）
- **三个黑洞**：循环试错、上下文膨胀、过度谨慎
- **四类归因**：改进 / 退化 / 持续失败 / 稳定成功
- **Phase 3 legacy SkillOpt**：研究实现，不作为已验证能力或后续默认扩展点

## 代码图谱工具（codebase-memory-mcp）

本项目使用 codebase-memory-mcp 作为代码发现和架构分析工具。

**工具使用顺序：** `list_projects` → `get_architecture` → `search_graph` → `trace_path` → `get_code_snippet` → `query_graph` → `search_code`

**何时使用：**
- 架构分析、符号查找、调用链追踪、影响分析
- 路由、模块依赖、接口关系查询

**何时不用：**
- 纯文本搜索、日志、配置文件、精确字符串 → 用 Grep/Glob
- 项目未索引时 → 先运行 `index_repository`

如果当前 Agent 运行器未配置该 MCP，使用 `rg` 和项目内测试完成发现与验证，
不要假设仓库内存在本地 MCP 配置文件。

## 参考资料

经验池位于 `docs/经验池/`，包含：
- Agent 评测方法论（Anthropic + 腾讯）
- Harness 工程（Codex 架构解析）
- Skill 自进化（Trace2Skill / EvoSkill / SkillOpt）
- Agent 可观测性（LoongSuite Pilot）
- Agent Skill 规范与设计模式
- 代码审查评测（Open Code Review + AACR-Bench）

PRD 位于 `docs/PRD.md`。

## 开发节奏

- 先 MVP（Phase 1-3，6 周），再扩展（Phase 4-6）
- 每个 Phase 结束有明确里程碑
- 早部署常交付，每个 PR 都可运行
- 为故障设计，每个模块有错误处理和重试逻辑

## 当前证据路线

按以下证据状态推进阶段：

1. Phase 1：[可复现多 Agent Benchmark 基线](https://github.com/randy-labs/CodePulse/issues/2)
2. Phase 2：[LLM-as-Judge 人工校准](https://github.com/randy-labs/CodePulse/issues/1)
3. Phase 3：[自进化收益与回归门禁](https://github.com/randy-labs/CodePulse/issues/3) — 已以负面证据关闭，收益验收未通过
4. Phase 4：[一键演示与作品级交付](https://github.com/randy-labs/CodePulse/issues/4) — Draft PR #8 待合并

失败阶段可以在完整记录结论和停止条件后解除后续门禁，但不得标记为验收通过。
新功能必须服务于当前 Phase 的验收项。每个阶段结束时必须保留可复现命令、
测试或实验报告以及量化结果。设计、计划和未运行的能力不得写成已实现结果。
