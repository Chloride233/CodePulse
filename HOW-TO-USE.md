# CodePulse 使用指南

## 快速开始

### 1. 启动服务

```bash
# 终端 1 — 启动后端 API
cd F:\CodePulse
python -c "from codepulse.cli import cli; cli()" -- web --port 8000 --no-browser

# 终端 2 — 启动前端
cd F:\CodePulse\web
npm run dev
```

打开浏览器访问 **http://localhost:3000**

### 2. 查看示例数据

项目自带了 3 个评测任务的结果数据（在 `results/` 目录），启动后即可在界面上看到。

---

## 完整工作流程

### 第一步：编写评测任务

创建 JSONL 文件，每行一个任务。示例见 `datasets/example.jsonl`：

```json
{
  "task_id": "fix-parse-int",           // 任务唯一 ID
  "category": "bug_fix",                // 类别: bug_fix / feature / refactor / code_review
  "difficulty": "easy",                 // 难度: easy / medium / hard
  "language": "python",                 // 编程语言
  "description": "修复 parseInt 函数",  // 任务描述（给 Agent 看的）
  "input_code": "def parse_int(s): ...",// 初始代码（Agent 的输入）
  "expected_output": "def parse_int(s): ...", // 期望输出（用于评分）
  "test_cases": ["assert parse_int('42') == 42"]  // 测试用例
}
```

### 第二步：运行评测

```bash
# 评测单个任务（真实 LLM Agent）
python -m codepulse.cli evaluate \
  --task-file datasets/example.jsonl \
  --agent-name my-agent \
  --model deepseek-chat \
  --n-trials 5

# 使用 Mock Agent（不调用 LLM，测试管线用）
python -m codepulse.cli evaluate \
  --task-file datasets/example.jsonl \
  --mock

# 对比多个模型
python -m codepulse.cli compare \
  --task-file datasets/example.jsonl \
  --agents deepseek --agents gpt-4o \
  --models deepseek-chat --models gpt-4o \
  --n-trials 5
```

### 第三步：查看结果

评测结果会自动保存到 `results/` 目录。刷新前端页面即可看到新数据。

---

## 页面功能

### 总览（/overview）
- 6 个核心指标卡片：任务数、试运行数、通过率、平均分、花费、活跃 Agent
- 五维度柱状图：功能正确性(30分)、过程质量(25分)、效率成本(15分)、鲁棒安全(20分)、体验对齐(10分)
- 近期得分趋势图
- Agent 列表

### 任务（/tasks）
- 搜索和筛选（来源、类别、难度）
- 点击行进入详情页

### 任务详情（/tasks/:id）
- 维度得分条形图
- Token 黑洞警告（循环试错、上下文膨胀）
- 试运行表格（点击行查看详细信息）

### 对比（/compare）
- 多 Agent 通过率和自纠正率柱状图
- 详细指标表格

### 轨迹（/traces）
- 左侧会话列表，右侧事件时间线
- 事件类型：模型调用、工具调用、工具结果、反思、错误

### 进化（/evolution）
- SkillOpt 自进化轨迹
- 基线 vs 候选得分曲线
- 逐轮编辑数和归因分布

---

## 评测维度说明

| 维度 | 分值 | 评分方式 | 说明 |
|------|------|----------|------|
| 功能正确性 | 30分 | 确定性 | 测试是否通过 |
| 过程质量 | 25分 | LLM评判 | 代码质量、推理过程 |
| 效率成本 | 15分 | 确定性 | Token 消耗、耗时 |
| 鲁棒安全 | 20分 | 混合 | 错误处理、安全漏洞 |
| 体验对齐 | 10分 | LLM评判 | 输出格式、可读性 |

总分 100 分，80 分以上为通过。

---

## 目录结构

```
CodePulse/
├── codepulse/          # Python 后端
│   ├── agent/          # Agent 模块（RealAgent + 工具系统）
│   ├── api/            # FastAPI API
│   ├── config.py       # 集中配置（模型定价、Agent 参数）
│   ├── data/           # 数据加载器
│   ├── env/            # Docker 沙箱 + 沙箱工具
│   ├── eval/           # 评测引擎（五维度评分器）
│   ├── observe/        # 可观测性
│   ├── evolve/         # 自进化
│   └── output/         # 报告生成
├── web/                # Vue 前端
│   └── src/
│       ├── pages/      # 页面组件
│       ├── components/ # 通用组件
│       └── stores/     # 状态管理
├── datasets/           # 评测数据集
├── results/            # 评测结果
└── HOW-TO-USE.md       # 本文件
```

---

## 配置

### 环境变量

```bash
# LLM API Key（按模型提供商设置一个即可）
export DEEPSEEK_API_KEY=sk-xxx      # DeepSeek
export OPENAI_API_KEY=sk-xxx        # OpenAI
export ANTHROPIC_API_KEY=sk-xxx     # Anthropic
```

### 配置文件

创建 `codepulse.yaml` 自定义 Agent 和沙箱参数：

```yaml
agent:
  model: deepseek-chat           # 默认模型
  max_tokens: 4096               # 最大输出 token
  temperature: 0.0               # 温度（0 = 确定性）
  max_iterations: 20             # 最大工具调用轮次

sandbox:
  image: python:3.11-slim        # Docker 镜像
  cpu_count: 2                   # CPU 核数
  memory_mb: 2048                # 内存限制

results_dir: results             # 结果保存目录
```

---

## Agent 模式

### 真实 Agent（默认）

使用 LiteLLM 调用真实 LLM，Agent 在 Docker 沙箱中通过工具调用完成任务：

- **read_file**: 读取沙箱内的文件
- **write_file**: 写入文件到沙箱
- **execute**: 执行 shell 命令

Agent 自动：读取任务 → 写入解决方案 → 运行测试 → 修复错误 → 迭代直到通过

### Mock Agent（测试模式）

使用 `--mock` 参数，不调用 LLM，不使用 Docker，用于验证评测管线。
