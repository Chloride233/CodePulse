#!/usr/bin/env python3
"""
示例 CLI Agent — 零侵入模式。

这个脚本不需要 import 任何 CodePulse 代码。
它只需要：
1. 读取 /workspace/task.json 获取任务
2. 在 /workspace/ 下写入解决方案
3. 返回 exit code 0（成功）或非 0（失败）

运行方式：
    codepulse evaluate --task-file datasets/example.jsonl --agent agents/cli-agent.yaml
"""

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
    """根据任务描述生成解决方案。

    这里应该调用你的 LLM Agent。
    示例中用简单规则代替。
    """
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
    """运行测试用例。"""
    # 写入测试文件
    test_code = "\n".join(test_cases)
    test_file = "/workspace/test_solution.py"

    # 导入解决方案
    import_line = f"import sys; sys.path.insert(0, '/workspace'); from solution import *"

    with open(test_file, "w") as f:
        f.write(f"{import_line}\n\n")
        for i, case in enumerate(test_cases):
            f.write(f"def test_{i+1}():\n")
            for line in case.split("\n"):
                f.write(f"    {line}\n")
            f.write("\n")

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
