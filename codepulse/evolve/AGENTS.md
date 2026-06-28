# evolve — Layer 5: Self-Evolution Layer

## 职责边界

通过 SkillOpt 循环驱动 Agent 能力自我进化。**只管**进化算法、经验抽象、建议生成，**不管**评测执行（调用 eval/harness）、报告输出（调用 output/report）。

## 关键设计决策

### SkillOpt 四步循环

```
Forward → Backward → Validate → Buffer
```

1. **Forward**：用候选 prompt 执行评测
2. **Backward**：对比新旧分数，归因分类
3. **Validate**：ValidationGate 验证候选优于基线
4. **Buffer**：EditBuffer 记录被拒绝的编辑供后续学习

每一步都是独立模块，循环调度在 `skillopt.py` 中编排。

### 三级经验进化（Lesson → Pattern → Instinct）

| 级别 | 条件 | 含义 |
|------|------|------|
| Lesson | 单次观察 | 特定上下文的一次事件 |
| Pattern | 重复 ≥ 3 次 + 验证 | 跨任务的通用规律 |
| Instinct | confidence ≥ 0.8 + 验证 ≥ 3 次 | 自动应用的规则 |

建模人类学习过程：单次错误 → 多次重复形成模式 → 自动化的本能反应。Instinct 不经过 Gate 直接应用。

### 四类归因分类

`SampleAttribution` 用分数变化对样本分类：

| 类型 | 条件 | 含义 |
|------|------|------|
| IMPROVEMENT | new > old | Prompt 改动有效 |
| REGRESSION | new < old | Prompt 改动有害 |
| PERSISTENT_FAILURE | 都 < 阈值 | 该任务一直做不对 |
| STABLE_SUCCESS | 都 ≥ 阈值 | 该任务一直能做对 |

### Scheduler 调度策略

三层学习率调度器：
- `CosineDecayScheduler`：标准余弦退火 + 线性预热
- `AdaptiveScheduler`：根据 improvement/regression 率动态调整
- `CombinedScheduler`：上述两者的加权混合

### 中文建议引擎

`SuggestionEngine` 输出中文化、面向用户的改进建议。规则是硬编码的（维度 score < 阈值 → 对应 action），不需要 LLM 调用。这保证了建议的确定性和低成本。

## 对外接口

- **被调用**: cli.py, commands/evolve_cli, api/routers/evolution
- **调用**: eval/harness, eval/scoring, data/models

## 约定与模式

- ValidationGate 的 pass 条件：improvement_rate > regression_rate
- EditBuffer 是内存中的环形缓冲区，不持久化（未来需要）
- PromptEdit 必须携带 reasoning 和 confidence 字段

## 陷阱与已知问题

- ExperienceEvolution 的 promote 阈值是硬编码验证次数阈值，未暴露为配置
- Buffer 纯内存存储，重启丢失
- ForwardPass 对每个候选运行完整评测（代价高），未做增量评估

## 测试策略

- `test_skillopt.py`：完整循环集成测试
- `test_experience.py`：三级进化升级逻辑
- `test_scheduler.py`：调度器衰减曲线
- `test_suggest.py`：建议规则引擎覆盖
- `test_attribution.py`：归因分类正确性
- `test_prompt_edit.py`：编辑结构和 batch 逻辑
