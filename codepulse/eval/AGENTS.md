# eval — Layer 3: Evaluation Layer

## 职责边界

执行评测管线：容器创建 → Agent 执行 → 维度打分 → 总分判定。**只管**单个 trial 的完整评测生命周期，**不管**多 Agent 对比（那是 observe/comparator 的事）、进化循环调度（那是 evolve 的事）。

## 关键设计决策

### 五维度 + 三类 Grader 体系

| 维度 | 权重 | Grader 类型 |
|------|------|-----------|
| 功能正确性 (FUNCTIONAL) | 30 | 确定性（PytestGrader）|
| 过程质量 (PROCESS) | 25 | LLM-as-Judge（Rubric + Reasoning）|
| 效率成本 (EFFICIENCY) | 15 | 确定性（EfficiencyGrader）|
| 鲁棒安全 (ROBUSTNESS) | 20 | 确定性+LLM |
| 体验对齐 (ALIGNMENT) | 10 | LLM-as-Judge |

100 分扣分制，pass 阈值 80 分。

### LLM Judge 降级策略

当 LiteLLM 调用失败时，RubricGrader / ReasoningGrader **不抛异常**，而是返回 `GraderResult(score=0, details={"error": ...})`。原因：单维度打分失败不应中断整个 trial，且 score=0 保证了保守估计。

### Calibrator 的 Cohen's Kappa

`Calibrator` 不是简单的 bias 加减——它计算 Cohen's Kappa（消除随机一致性后的人类-LLM 一致性），然后按 bias 偏移量修正 LLM judge 分数。这是 Reviewer-Calibration 的标准做法，来源于 AACR-Bench 的校准方法论。

## 对外接口

- **被调用**: cli.py, observe/comparator, evolve/gate, benchmark
- **调用**: data/models, data/protocols, env/sandbox, env/sandbox_utils

## 约定与模式

- 所有 Grader 的 `grade()` 返回 `GraderResult`（score ∈ [0,1]）
- `EvaluationHarness.run_task()` 在 finally 块保证容器销毁，即使中途异常
- `aggregate_scores()` 为纯函数，便于测试

## 陷阱与已知问题

- LiteLLM 依赖外部 API——评测结果在 API 不稳定时有波动
- 当前未对 LLM Judge 做重试，网络瞬断会直接记为 0 分
- CodeQualityGrader 依赖 lint 工具（ruff/mypy/bandit）存在于容器镜像中

## 测试策略

- `test_graders.py`：各 Grader 的单元测试
- `test_harness.py`：端到端评测流程（MockAgent + CustomDataset）
- `test_scoring.py`：聚合分数和 pass 判定的纯函数测试
- `test_calibrator.py`：校准流程和 Kappa 计算
