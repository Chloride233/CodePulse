# CodePulse — Code Agent 评测与自进化框架

## 项目定位

CodePulse 是一个 Code Agent 评测与自进化框架。核心理念：评测即奖励信号，评测体系本身就是 RL 环境。

六层架构：环境层 → 数据层 → 评测层 → 可观测性层 → 自进化层 → 产出层。

## 技术栈

- Python 3.11+、pytest、ruff、mypy、bandit
- LiteLLM（多模型：DeepSeek / GPT / Claude / Qwen）
- Docker（隔离执行）、SQLite + JSONL（存储）、LanceDB（向量）
- GitHub Actions（CI/CD）、Jinja2（报告）

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
│   ├── eval/         # Layer 3: 评测层（五维度 + 三类 Grader）
│   ├── observe/      # Layer 4: 可观测性层（Trace + 指标）
│   ├── evolve/       # Layer 5: 自进化层（SkillOpt）
│   └── output/       # Layer 6: 产出层（报告）
├── tests/            # 测试
├── datasets/         # 数据集
├── docs/             # 文档
├── scripts/          # 工具脚本
├── Dockerfile        # Docker 镜像
├── docker-compose.yml
├── pyproject.toml    # 项目配置
└── CLAUDE.md         # 本文件
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
- **SkillOpt 循环**：Forward → Backward → Validate → Buffer

## 代码图谱工具（codebase-memory-mcp）

本项目使用 codebase-memory-mcp 作为代码发现和架构分析工具。

**工具使用顺序：** `list_projects` → `get_architecture` → `search_graph` → `trace_path` → `get_code_snippet` → `query_graph` → `search_code`

**何时使用：**
- 架构分析、符号查找、调用链追踪、影响分析
- 路由、模块依赖、接口关系查询

**何时不用：**
- 纯文本搜索、日志、配置文件、精确字符串 → 用 Grep/Glob
- 项目未索引时 → 先运行 `index_repository`

**MCP 配置：** `.claude/.mcp.json`，缓存目录 `.tmp/codebase-memory-cache`

## 参考资料

经验池位于 `F:\Resume\06-岗位研究\DeepSeek-Code-Agent数据工程师\经验池\`，包含：
- Agent 评测方法论（Anthropic + 腾讯）
- Harness 工程（Claude Code 架构解析）
- Skill 自进化（Trace2Skill / EvoSkill / SkillOpt）
- Agent 可观测性（LoongSuite Pilot）
- Agent Skill 规范与设计模式
- 代码审查评测（Open Code Review + AACR-Bench）

PRD 位于 `F:\Resume\06-岗位研究\DeepSeek-Code-Agent数据工程师\PRD-CodePulse.md`

## 开发节奏

- 先 MVP（Phase 1-3，6 周），再扩展（Phase 4-6）
- 每个 Phase 结束有明确里程碑
- 早部署常交付，每个 PR 都可运行
- 为故障设计，每个模块有错误处理和重试逻辑
