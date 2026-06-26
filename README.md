# CodePulse — Code Agent 评测与自进化框架

> 评测即奖励信号，评测体系本身就是 RL 环境。

## 项目简介

CodePulse 是一个 Code Agent 评测与自进化框架，从真实 GitHub 场景收集评测数据，用确定性工程 + LLM-as-Judge 构建五维度评测体系，通过 SkillOpt 风格的训练循环推动 Agent 能力自进化。

## 核心特性

- **五维度评测体系**：功能正确性、过程质量、效率成本、鲁棒安全、体验对齐
- **三类 Grader**：确定性评分 + LLM-as-Judge + 人工校准
- **100 分扣分制**：通过阈值 80 分，可配置
- **Agent 可观测性**：完整 Trace 采集、Token 黑洞模式检测、pass@k/pass^k 统计
- **自进化框架**：SkillOpt 训练循环，四类样本归因，经验三级进化

## 六层架构

```
┌─────────────────────────────────────────────────────────────┐
│                      Layer 6: 产出层                          │
│  HTML 报告 / 多模型对比 / 自进化报告 / 失败模式知识库           │
├─────────────────────────────────────────────────────────────┤
│                      Layer 5: 自进化层                         │
│  SkillOpt Forward→Backward→Validate→Buffer                   │
├─────────────────────────────────────────────────────────────┤
│                      Layer 4: 可观测性层                       │
│  Agent Trace / Token 统计 / 黑洞模式检测 / pass@k/pass^k     │
├─────────────────────────────────────────────────────────────┤
│                      Layer 3: 评测层                          │
│  五维度评测体系 / 确定性 Grader + LLM-as-Judge               │
├─────────────────────────────────────────────────────────────┤
│                      Layer 2: 数据层                          │
│  SWE-bench + AACR-Bench + 自定义数据集                       │
├─────────────────────────────────────────────────────────────┤
│                      Layer 1: 环境层                          │
│  Docker 沙箱管理 / 容器生命周期                               │
└─────────────────────────────────────────────────────────────┘
```

## 快速开始

### 安装

```bash
# 克隆仓库
git clone https://github.com/Chloride233/CodePulse.git
cd CodePulse

# 安装依赖
pip install -e ".[dev]"
```

### 使用示例

#### 1. 定义评测任务

```python
from codepulse.data.models import Task, TaskSource, TaskCategory, Difficulty

task = Task(
    task_id="fix-add-function",
    source=TaskSource.CUSTOM,
    category=TaskCategory.BUG_FIX,
    difficulty=Difficulty.EASY,
    language="python",
    input={"description": "Fix the add function to handle edge cases"},
    ground_truth={"expected": "def add(a, b): return a + b"},
)
```

#### 2. 创建 Agent

```python
from codepulse.data.protocols import Agent

class MyAgent:
    name = "my-agent"
    model = "deepseek-chat"

    def run(self, task, sandbox):
        # 实现 Agent 逻辑
        ...
```

#### 3. 运行评测

```python
from codepulse.env.sandbox import SandboxManager
from codepulse.eval.harness import EvaluationHarness
from codepulse.eval.pytest_grader import PytestGrader

# 创建评测环境
sandbox = SandboxManager()
harness = EvaluationHarness(sandbox=sandbox, graders=[PytestGrader()])

# 运行评测
agent = MyAgent()
trials = harness.run_task(task, agent, n_trials=5)

# 查看结果
for trial in trials:
    print(f"Trial {trial.trial_id}: score={trial.scores}, success={trial.success}")
```

#### 4. 使用 CLI

```bash
# 评测单个任务
codepulse evaluate --task-file task.jsonl --agent-name my-agent --model deepseek-chat

# 对比多个 Agent
codepulse compare --task-file task.jsonl --agents agent1 agent2 agent3

# 生成报告
codepulse report --results-dir ./results --format markdown
```

#### 5. 自进化循环

```python
from codepulse.evolve.skillopt import SkillOpt

# 创建 SkillOpt
opt = SkillOpt(harness=harness, dataset=[task])

# 运行进化
baseline = MockAgent(name="baseline", model="v1")
candidate = MockAgent(name="candidate", model="v2")
results = opt.evolve(baseline, candidate, n_epochs=3)

# 查看结果
for result in results:
    print(f"Epoch {result.epoch}: {result.baseline_score} -> {result.candidate_score}")
```

### 运行测试

```bash
# 运行所有测试
pytest

# 运行特定测试
pytest tests/test_scoring.py

# 查看覆盖率
pytest --cov-report=html
```

### 代码质量检查

```bash
# ruff 检查
ruff check .

# mypy 类型检查
mypy codepulse

# bandit 安全检查
bandit -r codepulse
```

## 技术栈

| 类别 | 技术 |
|------|------|
| 语言 | Python 3.11+ |
| 测试 | pytest |
| 代码质量 | ruff + mypy + bandit |
| LLM | LiteLLM |
| 容器 | Docker |
| 存储 | SQLite + JSONL |
| 报告 | Jinja2 |

## 目录结构

```
CodePulse/
├── codepulse/          # 主包
│   ├── env/           # Layer 1: 环境层
│   │   ├── sandbox.py    # Docker 沙箱管理
│   │   └── mock_agent.py # Mock Agent
│   ├── data/          # Layer 2: 数据层
│   │   ├── models.py     # 数据模型
│   │   ├── protocols.py  # Protocol 定义
│   │   └── *_loader.py   # 数据加载器
│   ├── eval/          # Layer 3: 评测层
│   │   ├── harness.py    # 评测编排器
│   │   ├── scoring.py    # 评分系统
│   │   └── *_grader.py   # 各类 Grader
│   ├── observe/       # Layer 4: 可观测性层
│   │   ├── trace.py      # Trace 定义
│   │   ├── collector.py  # Trace 采集
│   │   ├── blackhole.py  # 黑洞检测
│   │   └── metrics.py    # pass@k/pass^k
│   ├── evolve/        # Layer 5: 自进化层
│   │   ├── skillopt.py   # SkillOpt 主循环
│   │   ├── forward.py    # Forward Pass
│   │   ├── gate.py       # Validation Gate
│   │   ├── buffer.py     # Edit Buffer
│   │   └── attribution.py# 样本归因
│   └── output/        # Layer 6: 产出层
│       ├── report.py     # 报告生成
│       └── cli.py        # 命令行接口
├── tests/             # 测试 (350+)
├── datasets/          # 数据集
├── docs/              # 文档
├── pyproject.toml     # 项目配置
└── CLAUDE.md          # 开发指南
```

## 开发指南

详见 [CLAUDE.md](./CLAUDE.md)。

## 许可证

MIT License
