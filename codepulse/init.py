"""项目初始化 — codepulse init。

创建项目模板：示例任务、Agent 配置、配置文件。
"""

from __future__ import annotations

import json
from pathlib import Path

from rich.console import Console

console = Console()


def init_project(
    directory: str = ".",
    *,
    with_examples: bool = True,
    with_agent_config: bool = True,
) -> Path:
    """初始化 CodePulse 项目。

    创建以下结构：
        codepulse.yaml          # 项目配置
        datasets/
          example.jsonl         # 示例任务
        agents/
          deepseek-agent.yaml   # 示例 Agent 配置
          mock-agent.yaml       # Mock Agent（离线可用）
        results/                # 结果目录（空）

    Args:
        directory: 项目根目录。
        with_examples: 是否创建示例任务。
        with_agent_config: 是否创建示例 Agent 配置。

    Returns:
        项目根目录路径。
    """
    root = Path(directory).resolve()
    root.mkdir(parents=True, exist_ok=True)

    # 创建目录结构
    (root / "datasets").mkdir(exist_ok=True)
    (root / "agents").mkdir(exist_ok=True)
    (root / "results").mkdir(exist_ok=True)

    # 项目配置
    _write_config(root)

    if with_examples:
        _write_example_tasks(root)

    if with_agent_config:
        _write_example_agents(root)

    return root


def _write_config(root: Path) -> None:
    """写入项目配置文件。"""
    config = """\
# CodePulse 项目配置

agent:
model: deepseek/deepseek-v4-flash
  max_tokens: 4096
  temperature: 0.0
  max_iterations: 20

sandbox:
  image: python:3.11-slim
  cpu_count: 2
  memory_mb: 2048
  timeout_seconds: 300

results_dir: results
"""
    (root / "codepulse.yaml").write_text(config, encoding="utf-8")


def _write_example_tasks(root: Path) -> None:
    """写入示例评测任务。"""
    tasks = [
        {
            "task_id": "fix-parse-int",
            "category": "bug_fix",
            "difficulty": "easy",
            "language": "python",
            "description": "修复 parseInt 函数，使其正确解析整数字符串，处理空字符串和无效输入。",
            "input_code": "def parse_int(s):\n    return int(s)\n",
            "expected_output": "def parse_int(s):\n    if not s:\n        return 0\n    try:\n        return int(s)\n    except ValueError:\n        return 0\n",
            "test_cases": [
                "assert parse_int('42') == 42",
                "assert parse_int('') == 0",
                "assert parse_int('abc') == 0",
                "assert parse_int('-7') == -7",
            ],
        },
        {
            "task_id": "add-retry-decorator",
            "category": "feature",
            "difficulty": "medium",
            "language": "python",
            "description": "为函数添加重试装饰器，支持指定重试次数和间隔。",
            "input_code": "import time\nimport functools\n\ndef retry(func):\n    # TODO: 实现重试逻辑\n    pass\n",
            "expected_output": "def retry(max_retries=3, delay=1.0):\n    def decorator(func):\n        @functools.wraps(func)\n        def wrapper(*args, **kwargs):\n            for i in range(max_retries):\n                try:\n                    return func(*args, **kwargs)\n                except Exception:\n                    if i == max_retries - 1:\n                        raise\n                    time.sleep(delay)\n        return wrapper\n    return decorator\n",
            "test_cases": [
                "@retry(max_retries=3, delay=0.01)\ndef always_fail():\n    raise ValueError('fail')\ntry:\n    always_fail()\n    assert False\nexcept ValueError:\n    pass",
                "@retry(max_retries=3, delay=0.01)\ndef succeed_on_third():\n    succeed_on_third.count = getattr(succeed_on_third, 'count', 0) + 1\n    if succeed_on_third.count < 3:\n        raise ValueError('not yet')\n    return 'ok'\nassert succeed_on_third() == 'ok'",
            ],
        },
        {
            "task_id": "review-sql-injection",
            "category": "code_review",
            "difficulty": "hard",
            "language": "python",
            "description": "审查以下代码，找出 SQL 注入漏洞并提供修复方案。",
            "input_code": "def get_user(username):\n    query = f\"SELECT * FROM users WHERE name = '{username}'\"\n    return db.execute(query)\n",
            "expected_output": "def get_user(username):\n    query = \"SELECT * FROM users WHERE name = ?\"\n    return db.execute(query, (username,))\n",
            "test_cases": [
                "import inspect\nsource = inspect.getsource(get_user)\nassert \"'\" not in source or '?' in source",
            ],
        },
    ]

    path = root / "datasets" / "example.jsonl"
    with path.open("w", encoding="utf-8") as fh:
        for task in tasks:
            fh.write(json.dumps(task, ensure_ascii=False) + "\n")


def _write_example_agents(root: Path) -> None:
    """写入示例 Agent 配置。"""
    # DeepSeek Agent（Protocol 模式）
    deepseek_config = """\
# DeepSeek Coding Agent
# 使用 DeepSeek 模型，通过工具调用完成编程任务

name: deepseek-agent
type: protocol
model: deepseek-chat
description: "DeepSeek 编程 Agent，支持工具调用"

# Protocol 模式配置
agent_class: codepulse.agent.real_agent.RealAgent
system_prompt: |
  你是一个 Python 编程专家。请根据任务描述修复或编写代码。
  使用 read_file 读取容器中的文件。
  使用 write_file 将你的解决方案写入 /workspace/solution.py。
  使用 execute 运行测试验证正确性。测试文件在 /workspace/test_solution.py。
  如果测试失败，分析错误并修复。写入修复方案到 /workspace/solution.py。

tools:
  - read_file
  - write_file
  - execute

max_iterations: 15
temperature: 0.0
max_tokens: 4096

version: "1.0"
"""

    # Mock Agent（离线可用）
    mock_config = """\
# Mock Agent
# 不调用 LLM，不使用 Docker，用于测试评测管线

name: mock-agent
type: mock
model: mock
description: "Mock Agent，离线可用，用于测试管线"

version: "1.0"
"""

    # CLI Agent 示例（零侵入）
    cli_config = """\
# CLI Agent 示例
# 零侵入模式：Agent 不需要 import 任何 CodePulse 代码
#
# 使用方法：
#   1. 编写你的 Agent 脚本（见下方注释）
#   2. 运行: codepulse evaluate --task-file datasets/example.jsonl --agent agents/cli-agent.yaml
#
# 你的 Agent 脚本只需要：
#   1. 读取 {task_file} 获取任务描述
#   2. 在 /workspace/ 下写入解决方案
#   3. 返回 exit code（0 = 成功）

name: cli-agent
type: cli
description: "零侵入 CLI Agent，不依赖 CodePulse SDK"

# Agent 启动命令
# {task_file} 会被替换为任务文件路径
command: "python agent.py"

# 工作目录
workdir: /workspace

# 超时时间（秒）
timeout: 300

version: "1.0"
"""

    (root / "agents" / "deepseek-agent.yaml").write_text(deepseek_config, encoding="utf-8")
    (root / "agents" / "mock-agent.yaml").write_text(mock_config, encoding="utf-8")
    (root / "agents" / "cli-agent.yaml").write_text(cli_config, encoding="utf-8")

    # 写一个示例 CLI Agent 脚本
    example_agent_py = """\
#!/usr/bin/env python3
\"\"\"
示例 CLI Agent — 零侵入模式。

这个脚本不需要 import 任何 CodePulse 代码。
它只需要：
1. 读取 /workspace/task.json 获取任务
2. 在 /workspace/ 下写入解决方案
3. 返回 exit code 0（成功）或非 0（失败）

运行方式：
    codepulse evaluate --task-file datasets/example.jsonl --agent agents/cli-agent.yaml
\"\"\"

import json
import os
import subprocess
import sys


def main():
    # 1. 读取任务
    task_file = os.environ.get("TASK_FILE", "/workspace/task.json")
    with open(task_file) as f:
        task = json.load(f)

    description = task.get("description", "")
    input_code = task.get("input_code", "")
    test_cases = task.get("test_cases", [])
    language = task.get("language", "python")

    # 2. 根据任务描述生成解决方案
    # 这里用简单的规则代替 LLM 调用
    # 实际使用时，你应该在这里调用你的 LLM
    solution = generate_solution(description, input_code, language)

    # 3. 写入解决方案
    solution_file = f"/workspace/solution.{get_extension(language)}"
    with open(solution_file, "w") as f:
        f.write(solution)

    # 4. 运行测试（可选）
    if test_cases:
        exit_code = run_tests(solution_file, test_cases, language)
        sys.exit(exit_code)

    sys.exit(0)


def generate_solution(description, input_code, language):
    \"\"\"根据任务描述生成解决方案。

    这里应该调用你的 LLM Agent。
    示例中用简单规则代替。
    \"\"\"
    if "修复" in description or "fix" in description.lower():
        # 简单的 bug 修复：用正确的实现替换
        if "parse_int" in input_code:
            return '''def parse_int(s):
    if not s:
        return 0
    try:
        return int(s)
    except ValueError:
        return 0
'''
    # 默认返回输入代码（不做修改）
    return input_code


def run_tests(solution_file, test_cases, language):
    \"\"\"运行测试用例。\"\"\"
    # 写入测试文件
    test_code = "\\n".join(test_cases)
    test_file = "/workspace/test_solution.py"

    # 导入解决方案
    import_line = f"import sys; sys.path.insert(0, '/workspace'); from solution import *"

    with open(test_file, "w") as f:
        f.write(f"{import_line}\\n\\n")
        for i, case in enumerate(test_cases):
            f.write(f"def test_{i+1}():\\n")
            for line in case.split("\\n"):
                f.write(f"    {line}\\n")
            f.write("\\n")

    # 运行 pytest
    result = subprocess.run(
        ["python", "-m", "pytest", test_file, "-v", "--tb=short"],
        capture_output=True, text=True,
    )
    return result.returncode


def get_extension(language):
    ext_map = {"python": "py", "javascript": "js", "typescript": "ts", "go": "go", "rust": "rs"}
    return ext_map.get(language, "txt")


if __name__ == "__main__":
    main()
"""

    (root / "agents" / "example_cli_agent.py").write_text(example_agent_py, encoding="utf-8")
