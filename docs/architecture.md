# CodePulse 架构文档

## 六层架构

### Layer 1: 环境层 (`codepulse/env/`)

Docker 沙箱隔离执行环境。提供容器生命周期管理（创建、执行、快照、回滚、销毁）、资源限制、沙箱工具集。

关键类：`SandboxManager`、`SandboxUtils`、`MockAgent`

### Layer 2: 数据层 (`codepulse/data/`)

数据集加载与统一数据模型。支持 SWE-bench Verified (500)、AACR-Bench (200)、自定义数据集 (30+)。统一 Task/Trial/Grader Schema。

关键类：`Task`、`Trial`、`SweBenchLoader`、`AacrBenchLoader`、`CustomDatasetLoader`

### Layer 3: 评测层 (`codepulse/eval/`)

五维度评测体系（功能正确性 P0-30分、过程质量 P1-25分、效率成本 P1-15分、鲁棒安全 P0-20分、体验对齐 P2-10分）。三类 Grader：确定性（pytest/ruff/mypy/bandit）、LLM-as-Judge（Rubric/Reasoning/CodeQuality）、人工校准。

关键类：`EvaluationHarness`、`PytestGrader`、`RubricGrader`、`ReasoningGrader`、`Calibrator`

### Layer 4: 可观测性层 (`codepulse/observe/`)

Agent Trace 采集（session→turn→step→tool_call）、Token 效率统计、三个黑洞模式检测（循环试错/上下文膨胀/过度谨慎）、pass@k/pass^k 统计、跨 Agent 行为对比。

关键类：`TraceCollector`、`BlackholeDetector`、`AgentComparator`、`PassMetrics`

### Layer 5: 自进化层 (`codepulse/evolve/`)

SkillOpt 训练循环：Forward Pass 收集轨迹 → Backward Pass 分析失败生成原子编辑 → Validation Gate 严格验证 → Rejected-Edit Buffer 负反馈学习。四类样本归因（改进/退化/持续失败/稳定成功）。三级经验进化（Lesson→Pattern→Instinct）。学习率调度器控制编辑激进程度。

关键类：`SkillOpt`、`ForwardPass`、`ValidationGate`、`EditBuffer`、`SampleAttribution`、`ExperienceEvolution`

### Layer 6: 产出层 (`codepulse/output/`)

HTML/Markdown 评测报告生成、多模型对比报告、雷达图可视化。支持 Chart.js 交互式图表。`ReportGenerator` 可输出单次评测报告、多模型对比报告、自进化报告、失败模式报告。

关键类：`ReportGenerator`

## 跨层模块

### Agent 模块 (`codepulse/agent/`)

LiteLLM 驱动的多模型 Agent 适配器。支持 DeepSeek / GPT / Codex / Qwen 等模型。工具系统（ReadFile/WriteFile/ExecuteTool）。RealAgent 通过 ToolRegistry 与沙箱交互。

### API 模块 (`codepulse/api/`)

FastAPI 后端，提供 5 个路由器：Overview、Evaluations、Compare、Traces、Evolution。Pydantic v2 请求/响应 Schema。

### CLI 模块 (`codepulse/cli.py`)

Click CLI 入口：评测运行、结果检视、基线对比、自进化触发、Web 服务启动。

### Web 前端 (`web/`)

Vue.js 3 + TypeScript + Vite。路由页面：Overview、Tasks、TaskDetail、Compare、Evolution、Traces。Pinia 状态管理。Chart.js 图表组件。

## 评分系统

100 分扣分制，通过阈值 80 分：

| 维度 | 优先级 | 满分 | Grader 类型 |
|------|--------|------|-------------|
| 功能正确性 | P0 | 30 | 确定性 |
| 过程质量 | P1 | 25 | LLM-as-Judge |
| 效率成本 | P1 | 15 | 确定性 |
| 鲁棒安全 | P0 | 20 | 确定性+LLM |
| 体验对齐 | P2 | 10 | LLM-as-Judge |

## SkillOpt 循环

```
Forward Pass → Backward Pass → Validation Gate → Edit Buffer
     ↓               ↓                ↓               ↓
  收集轨迹       分析失败         候选vs基线      存储负反馈
```

## 经验三级进化

```
Lesson（单次观察）→ Pattern（≥2次泛化）→ Instinct（高置信度自动注入）
```

## 技术栈

| 类别 | 技术 |
|------|------|
| 语言 | Python 3.11+ |
| 评测 | pytest、ruff、mypy、bandit |
| 模型 | LiteLLM（DeepSeek/GPT/Codex/Qwen） |
| 环境 | Docker 隔离执行 |
| 存储 | SQLite + JSONL |
| 向量 | LanceDB |
| 报告 | Jinja2 + Chart.js |
| CI/CD | GitHub Actions |
| 前端 | Vue.js 3 + TypeScript + Vite + Pinia |
| 后端 | FastAPI + Pydantic v2 |
