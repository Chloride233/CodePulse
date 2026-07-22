# tests — 测试规范

## 职责边界

所有测试集中于此目录，通过 pytest 统一运行。**只管**测试代码，**不管**测试数据（放在 `datasets/`）和测试结果（放在 `results/`）。

## 关键设计决策

### pytest 为唯一测试框架

不使用 unittest.TestCase，不使用 nose。`conftest.py` 提供共享 fixtures。

### 测试命名规范

```
test_<模块>_<场景>_<预期>.py
```

示例：`test_sandbox_create_container_returns_id.py`

### Docker 可用性自动检测

`conftest.py` 中有 Docker 可用性检测 fixture。依赖 Docker 的测试（如 sandbox、harness 集成测试）在 Docker 不可用时自动 skip，不标记为失败。

### 覆盖率目标

`pyproject.toml` 配置 `--cov-fail-under=80`，与根目录 `AGENTS.md` 一致。

## 约定与模式

- `__init__.py` 存在以使 tests 成为 Python 包（支持相对导入和 fixtures）
- `conftest.py` 中的 fixtures 按 scope 组织（function/session）
- 测试使用 MockAgent 替代真实 LLM 调用，保证确定性
- 异步测试使用 `pytest-asyncio`

## 陷阱与已知问题

- Docker 依赖的测试在 Windows 上可能因 Docker Desktop 模式问题 skip
- 当前 sparse checkout 可能省略少量已跟踪的 Phase 2 fixture；完整 CI checkout 才是
  全量仓库测试的权威环境

## 当前测试覆盖

| 层 | 测试文件 | 覆盖范围 |
|----|---------|---------|
| env | test_sandbox.py | 容器生命周期 |
| data | test_loaders.py | 数据集加载和校验 |
| eval | test_graders.py, test_harness.py, test_scoring.py, test_calibrator.py | 评分、评测管线、校准 |
| observe | test_metrics.py, test_observability.py, test_blackhole.py | 指标、Trace、黑洞 |
| evolve | test_skillopt.py, test_evolution.py, test_experience.py, test_scheduler.py, test_suggest.py, test_attribution.py, test_prompt_edit.py | SkillOpt 循环、经验进化、调度器、建议 |
| output | test_report.py, test_html_report.py | 报告生成 |
| agent | test_real_agent.py, test_tools.py | Agent 实现和工具 |
| api | test_api.py | REST API |
| config | test_config.py, test_schemas.py | 配置和 schema |
| cli | test_cli_integration.py, test_baseline.py, test_benchmark.py | CLI 集成 |
| 其他 | test_inspect.py | 项目检查工具 |
