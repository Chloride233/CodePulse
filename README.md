# CodePulse — Code Agent 可信评测与回归门禁

> 用冻结配置、可追溯证据和严格门禁验证 Code Agent 的改进声明。

## 项目简介

CodePulse 是一个面向 Code Agent 的可复现实验与可信评测平台。它统一记录
任务、Agent、模型、环境和成本配置，用确定性 Grader、经过人工校准的
LLM-as-Judge、稳定性指标和 Validation Gate 判断候选是否真的优于基线。

项目曾在 Phase 3 尝试基于失败轨迹改进 Agent，但真实 SWE-bench 对照没有证明
稳定收益，候选被门禁拒绝。该结果作为负面证据保留，不表述为“自进化成功”。
当前状态和证据边界见 [项目状态](docs/project-status.md)。

## 核心特性

- **可复现实验**：冻结任务、Agent、模型、依赖、容器、随机种子和预算
- **可信评分边界**：确定性 Grader 保持权威，LLM-as-Judge 仅用于完整证据的定性维度
- **稳定性比较**：报告 pass@k、pass^k、Token、成本、P50/P95 延迟和失败分类
- **回归门禁**：严格配对、完整覆盖、四类任务归因、零回归与资源约束
- **可审计报告**：保留 manifest、provenance、指标、典型案例和复现命令

## 核心链路

```
任务、Agent、模型、环境与预算冻结
                 │
                 ▼
        统一 Trial 与完整 Trace
                 │
                 ▼
确定性 Grader + 校准后的 LLM-as-Judge
                 │
                 ▼
严格配对 + pass@k/pass^k + 四类归因
                 │
                 ▼
       Validation Gate + 可审计报告
```

## 快速开始

### 安装

```bash
# 克隆仓库
git clone https://github.com/randy-labs/CodePulse.git
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
# 使用 Mock Agent 评测单个任务
codepulse evaluate --task-file datasets/example.jsonl --agent agents/mock-agent.yaml

# 对比多个 Agent 配置；--agents 是可重复参数
codepulse compare --task-file datasets/example.jsonl \
  --agents agents/mock-agent.yaml --agents agents/cli-agent.yaml

# 生成报告
codepulse report --results-dir ./results --format markdown
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
│   ├── evolve/        # Phase 3 研究实现 + 回归门禁
│   │   ├── skillopt.py   # Legacy SkillOpt 研究循环
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
