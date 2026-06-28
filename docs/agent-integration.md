# Agent 接入指南

CodePulse 支持三种接入 Agent 的模式，覆盖从零侵入到深度集成的各种需求。

## 快速选择

| 你的场景 | 推荐模式 | 需要 Docker |
|----------|---------|------------|
| "我有一个 Python 脚本，输入任务输出结果" | CLI | ✅ |
| "我用 LangChain/LiteLLM 写了一个 Agent" | Protocol | ✅ |
| "我只是想测试评测管线" | Mock | ❌ |
| "我想要完整的评测功能" | Protocol + CLI 混合 | ✅ |

---

## CLI 模式（零侵入）

你的 Agent 不需要 import 任何 CodePulse 代码——只需一个可执行命令。

### 工作流程

1. CodePulse 将任务注入到容器的 `/workspace/task.json`
2. CodePulse 执行你配置的命令
3. 你的命令读取 `task.json`，生成解决方案
4. CodePulse 收集输出文件并运行验证

### 配置文件

```yaml
# agents/my-agent.yaml
name: my-cli-agent
type: cli
description: "我的自定义 CLI Agent"

# 启动命令（{task_file} 会被替换为任务文件路径）
command: "python /workspace/agent.py --task {task_file}"

# 工作目录
workdir: /workspace

# 超时（秒）
timeout: 300
```

### task.json 格式

```json
{
  "task_id": "fix-parse-int",
  "description": "修复 parseInt 函数...",
  "input_code": "def parse_int(s):\n    return int(s)\n",
  "expected_output": "def parse_int(s):\n    if not s:\n        return 0\n    ...",
  "test_cases": ["assert parse_int('42') == 42", "..."],
  "language": "python"
}
```

### 运行

```bash
codepulse evaluate --task-file datasets/example.jsonl --agent agents/my-agent.yaml
```

---

## Protocol 模式（深度集成）

通过实现 CodePulse 的 `Agent` Protocol 获取完整控制（工具调用、轨迹追踪）。

### 实现 Agent Protocol

```python
from codepulse.data.protocols import Agent
from codepulse.observe.trace import Transcript, TraceEvent, EventType
from codepulse.env.sandbox import SandboxManager, Container


class MyAgent:
    """自定义 Agent — 实现 Agent Protocol 即可被 CodePulse 使用。"""

    def __init__(self, name: str = "my-agent", model: str = "deepseek-chat"):
        self.name = name
        self.model = model

    async def run(
        self,
        task: Task,
        sandbox: SandboxManager | None = None,
    ) -> Transcript:
        transcript = Transcript(
            session_id=f"{task.task_id}-{self.name}",
            agent_config={"name": self.name, "model": self.model},
        )

        # 你的 Agent 逻辑
        # 使用 LiteLLM / OpenAI SDK / 任意框架

        transcript.add_event(TraceEvent(
            event_type=EventType.LLM_CALL,
            content="...",
        ))

        return transcript
```

### 配置文件

```yaml
name: my-agent
type: protocol
model: deepseek-chat
description: "自定义 Protocol Agent"

# Protocol 模式：指向你的 Agent 类
agent_class: my_agent.MyAgent

# 工具配置
tools:
  - read_file
  - write_file
  - execute

max_iterations: 20
temperature: 0.0
max_tokens: 4096
```

### 运行

```bash
export DEEPSEEK_API_KEY="sk-..."
codepulse evaluate --task-file datasets/example.jsonl --agent agents/my-agent.yaml
```

---

## Mock 模式（离线测试）

无需 LLM、无需 Docker，仅用固定返回结果验证评测管线。

```yaml
name: mock-agent
type: mock
model: mock
description: "离线 Mock Agent"
```

```bash
codepulse evaluate --task-file datasets/example.jsonl --agent agents/mock-agent.yaml
```

---

## 环境变量

| 变量 | 用途 | 默认值 |
|------|------|--------|
| `DEEPSEEK_API_KEY` | DeepSeek API 密钥 | — |
| `OPENAI_API_KEY` | OpenAI API 密钥 | — |
| `ANTHROPIC_API_KEY` | Anthropic API 密钥 | — |
| `CODEPULSE_RESULTS_DIR` | 结果输出目录 | `results` |
| `CODEPULSE_CONFIG` | 配置文件路径 | `codepulse.yaml` |

---

## 完整示例

### 带工具调用的 Protocol Agent

```python
# agents/calculator_agent.py - 一个简单的计算 Agent
import json
from codepulse.observe.trace import Transcript, TraceEvent, EventType
from codepulse.env.sandbox import SandboxManager


class CalculatorAgent:
    name = "calculator"
    model = "deepseek-chat"

    async def run(self, task, sandbox=None):
        transcript = Transcript(
            session_id=task.task_id,
            agent_config={"name": self.name, "model": self.model},
        )

        # 解析任务
        expression = task.input.get("input_code", "")

        try:
            result = str(eval(expression))  # noqa: PGH001
            transcript.add_event(TraceEvent(
                event_type=EventType.TOOL_CALL,
                content=json.dumps({"tool": "execute", "input": expression, "output": result}),
            ))
        except Exception as e:
            result = f"Error: {e}"

        return transcript
```

```yaml
# agents/calculator.yaml
name: calculator-agent
type: protocol
model: deepseek-chat
agent_class: agents.calculator_agent.CalculatorAgent
max_iterations: 1
temperature: 0.0
max_tokens: 256
```

### CLI 模式（Shell 脚本）

```bash
#!/bin/bash
# agents/solve.sh — 一个简单的 bash Agent
TASK_FILE="${1:-/workspace/task.json}"
INPUT=$(python3 -c "import json; print(json.load(open('$TASK_FILE'))['input_code'])")
python3 <<EOF
$INPUT
EOF
```

```yaml
name: bash-solver
type: cli
command: "bash /workspace/solve.sh {task_file}"
workdir: /workspace
timeout: 30
```

---

## 多 Agent 对比

```bash
codepulse compare \
  --task-file datasets/example.jsonl \
  --agents agents/deepseek-agent.yaml \
  --agents agents/mock-agent.yaml \
  --agents agents/my-agent.yaml \
  --n-trials 3
```

---

## 迁移指南：从 Mock 到生产

```
Mock Agent (验证管线) → CLI Agent (快速集成现有脚本) → Protocol (深度优化)
```
