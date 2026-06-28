# observe — Layer 4: Observability Layer

## 职责边界

收集 Agent 执行轨迹、计算 pass@k/pass^k 指标、执行多 Agent 对比、检测 Agent 行为黑洞。**只管**事后分析与聚合，**不管**评测执行本身。

## 关键设计决策

### pass@k 与 pass^k 的区分

| 指标 | 含义 | 使用场景 |
|------|------|----------|
| pass@k | k 次至少成功 1 次 | 衡量 Agent 能力上限 |
| pass^k | k 次全成功 | 衡量 Agent 稳定性 |

这是 Codex 论文的标准指标，分别对应"能不能做对"和"能不能稳定做对"。

### 三大黑洞检测

`BlackholeDetector` 检测三种 Agent 退化模式：

1. **循环试错 (loop_trial)**：反复 write → test 循环，检测标准为 tool_call_count 过高
2. **上下文膨胀 (context_bloat)**：输入 token 持续增长无收敛
3. **过度谨慎 (over_caution)**：LLM 调用时间占比 > 80%（在思考而非执行）

检测阈值定义在类级常量，可配置但不写在外部配置文件（未来需改进）。

### Transcript 事件模型

`TraceEvent` 使用事件类型枚举（LLM_CALL、TOOL_CALL、TOOL_RESULT、REFLECTION、ERROR），而非自由文本。这使得后续分析可以按事件类型聚合和可视化，而非做 NLP 解析。

### Agent 对比独立于评测

`AgentComparator` 在自己的循环中调用 `EvaluationHarness`，不在 harness 内部做对比。职责分离：harness 负责单个 trial，comparator 负责多 trial 编排。

## 对外接口

- **被调用**: cli.py, api, evolve/gate
- **调用**: eval/harness, data/models, data/protocols

## 约定与模式

- Trace 以 JSONL 格式存储，一行一个 JSON 对象
- `Transcript.add_event()` 自动更新累计指标（tokens/duration/tool_calls）
- 比较报告使用 Markdown 表格输出

## 陷阱与已知问题

- Collector 不限制 Transcript 大小，长 session 可能导致内存膨胀
- 黑洞检测阈值是硬编码常量，未暴露为配置
- pass@k 计算依赖组合数公式，大 k 值可能有浮点精度问题

## 测试策略

- `test_metrics.py`：pass@k/pass^k 公式验证
- `test_blackhole.py`：黑洞检测模式验证
- `test_observability.py`：Transcript 事件追踪和指标计算
