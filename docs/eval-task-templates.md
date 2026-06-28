# CodePulse 评测用例模板

## 1. 触发条件用例

```json
{
  "task_id": "trigger/read-before-edit",
  "category": "bug_fix",
  "difficulty": "easy",
  "language": "python",
  "suite_type": "capability",
  "description": "修复函数前，先读取目标文件并确认边界条件。",
  "expected_output": "修复后的实现可通过测试",
  "acceptance_criteria": [
    "读取目标文件",
    "执行测试",
    "不得跳过关键验证"
  ],
  "artifact_expectations": {
    "required_files": ["solution.py"]
  }
}
```

## 2. 核心逻辑用例

```json
{
  "task_id": "core/fix-auth-bypass",
  "category": "bug_fix",
  "difficulty": "medium",
  "language": "python",
  "suite_type": "regression",
  "baseline_id": "auth-v1",
  "description": "修复空密码导致的鉴权绕过。",
  "expected_output": "空密码和 null 密码均被拒绝",
  "test_cases": [
    "pytest tests/test_auth.py -q"
  ],
  "acceptance_criteria": [
    "功能测试通过",
    "不得引入新的类型或 lint 问题"
  ]
}
```

## 3. 产物质量用例

```json
{
  "task_id": "artifact/report-quality",
  "category": "feature",
  "difficulty": "medium",
  "language": "markdown",
  "suite_type": "capability",
  "description": "生成一份包含结论、证据和风险的评测报告。",
  "expected_output": "结构清晰、证据充分的 Markdown 报告",
  "acceptance_criteria": [
    "包含结论段",
    "包含证据段",
    "包含风险段"
  ],
  "artifact_expectations": {
    "required_sections": ["结论", "证据", "风险"]
  }
}
```

## 4. 异常容错用例

```json
{
  "task_id": "recovery/tool-timeout",
  "category": "refactor",
  "difficulty": "hard",
  "language": "python",
  "suite_type": "regression",
  "description": "当主要工具超时后，Agent 需要给出降级方案并继续验证。",
  "expected_output": "任务完成或明确降级说明",
  "acceptance_criteria": [
    "检测工具失败",
    "进行一次重试或降级",
    "输出明确的失败原因"
  ],
  "artifact_expectations": {
    "max_retries": 1
  }
}
```
