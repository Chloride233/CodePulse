# Agent 可观测性

## 来源

- 阿里云开发者 "当 AI Coding Agent 成为基础设施：我们为什么要开源 LoongSuite Pilot"（2026-06-12）
- 阿里云开发者 "Agent 烧钱如流水？Agentic OS (ANOLISA) 帮你逐笔看清 Token 账单"（2026-05-11）
- 阿里云开发者 "阿里巴巴 & 蚂蚁 LoongSuite GenAI 可观测语义规范"（2026-05-11）
- 腾讯技术工程 "一篇搞懂 AI Coding Agent 的 Token 成本控制"（2026-06-15）

---

## 核心问题

> 组织花了大量预算在 AI 编程工具上，但对 Agent 的行为几乎零可见性。

---

## LoongSuite Pilot

### 是什么

端侧（本地机器）可观测性采集器。静默运行在开发者后台，自动检测已安装的 AI Coding Agent，采集完整行为数据，归一化为统一 schema，导出到多个后端。

### 核心能力

- 一键安装（`curl | bash`）
- 自动 Agent 检测和数据注入（不修改 Agent 本身）
- 内置本地 Dashboard
- 敏感数据自动掩码（AccessKey、API Key、数据库连接串、私钥）
- 多目标并行扇出：本地 JSONL + SLS + HTTP + OTLP Trace

### 支持的 Agent

| Agent | 覆盖范围 |
|-------|---------|
| Claude Code | 完整事件链：用户 prompt、tool call（前后）、任务完成、上下文压缩、子 Agent 生命周期 |
| Codex | 会话开始、用户 prompt、tool call（前后）、任务完成 |
| Cursor | 12 种事件类型 |
| Qoder | 多路径并行采集 |

### 统一数据归一化

所有原始 Agent 数据转为 `AgentActivityEntry` 格式，遵循 LoongSuite GenAI 语义规范（扩展 OpenTelemetry GenAI Semantic Conventions）。

标准化字段名：`gen_ai.usage.input_tokens`、`gen_ai.session.id`、`gen_ai.tool.call.id`

### 层级 Trace 结构

```
session → turn → step → response/tool_call
```

保留完整 ReAct 推理循环（思考、工具调用、反思）。

---

## 核心 ROI 指标

| 指标 | 定义 |
|------|------|
| 任务完成率 | 多少会话实际达成目标 |
| Token 效率比 | 每成功任务的平均 token 消耗 |
| 人机协作比 | Agent 自主完成 vs 人工介入 |
| 自修正率 | Agent 回滚重做的频率（适中=推理能力，过度=超出能力边界） |

---

## Token 成本分析

| 字段 | 含义 |
|------|------|
| `gen_ai.usage.input_tokens` | 输入 token |
| `gen_ai.usage.output_tokens` | 输出 token |
| `gen_ai.usage.total_tokens` | 总 token |
| `gen_ai.usage.cache_read.input_tokens` | 缓存读取 token |

---

## 三个 Token 黑洞模式

### 1. 循环试错

**表现：** Agent 尝试一个方案，测试失败，再试另一个，又失败
**Trace 特征：** Write + Bash(test) 反复出现，输出为错误
**根因：** 超出 Agent 能力边界

### 2. 上下文膨胀

**表现：** `input_tokens` 阶梯式增长
**Trace 特征：** 每个新 turn 携带完整之前输出，未裁剪无关信息
**根因：** 上下文管理策略不足

### 3. 过度谨慎

**表现：** Agent 在行动前花大量 token 做推理/确认
**Trace 特征：** LLM span 占 80%+ token，TOOL span 极少
**根因：** 过度思考，缺乏行动力

---

## 跨 Agent 行为对比

同一任务（"为一个模块添加单元测试"）在 Claude Code、Cursor、Qoder 上的表现：

| 维度 | Claude Code | Cursor | Qoder |
|------|------------|--------|-------|
| 总时间 | 最快 | 中等 | 最慢 |
| 单轮 LLM 速度 | 最快 | 中等 | 最慢 |
| LLM 调用次数 | 中等 | 最少 | 最多 |
| 每轮推理时间 | 中等 | 最长（高思考模式） | 最短 |
| 工具多样性 | 主要用 Bash | 最多样（Shell+Read+Grep+Write） | 最轻量（Glob, Read） |
| 输出 token | 中等 | 最多 | 最少 |
| Token 消耗 | 中等 | 中等 | 最低 |
| 风格 | 平衡思考/行动 | 深度思考、最彻底 | 小步快跑 |

---

## 自修正率的含义

- **适度自修正**：表明推理能力（Agent 能发现并回滚自己的错误）
- **过度自修正**：信号任务超出 Agent 能力边界
- Trace 特征：第 7 轮写代码，第 8 轮回滚

---

## 安全审计（六层）

1. 审计管理与运行时监控
2. 风险态势仪表板（全局风险事件统计 + 严重等级）
3. 风险主体识别（Top 3 风险实体，6 个维度）
4. 数据泄露链分析（攻击驱动外泄、模型上下文泄露、敏感数据类型分布）
5. 实体关联调查（可疑实体完整行为画像）
6. 会话级可追溯性（完整事件时间线回放）

---

## 关键洞察

1. **传统指标（代码行数、PR 数、提交频率）在 AI 时代无意义**
2. **自修正率是模型能力边界的信号**
3. **三个黑洞模式是模型缺陷的直接证据**，可作为 RL 训练的失败样本
4. **Agent 可观测性是训练的基础**——没有行为数据就无法训练
