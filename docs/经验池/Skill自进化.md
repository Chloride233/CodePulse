# Skill 自进化

## 来源

- 阿里云开发者 "如何更科学、方向可控的实现 Skill 的'自进化'？"（2026-06-09）
- SkillOpt 论文：https://arxiv.org/pdf/2605.23904（微软 + 上交/同济/复旦）
- EvoSkill 论文：https://arxiv.org/pdf/2603.02766（Sentient Labs）
- Trace2Skill 论文：https://arxiv.org/pdf/2603.25158（阿里 Qwen 团队）

---

## 核心理念

> 验证即奖励函数。没有可量化信号告诉 Agent "什么是好的"，迭代就是盲目的。

Agent Skill 的优化可以借鉴 ML 训练范式：
- Forward Pass = 跑评测集收集轨迹
- Reward = 评测分数
- Backward Pass = 分析失败生成编辑
- Validation Gate = 新 Skill 必须严格优于旧版

---

## 三种自进化方法

### Trace2Skill（归纳聚合）

**哲学：** 从批量轨迹中提取经验，层级合并

**流程：**
1. 初始 Skill S0
2. 并行跑一批任务，产生轨迹
3. 分为成功集 T+ 和失败集 T-
4. 每条轨迹分配独立分析师子 Agent
   - 成功分析师：单次提取
   - 失败分析师：多轮 ReAct 推理找根因（质量门丢弃无明确根因的轨迹）
5. 所有分析师对冻结的初始 Skill S0 工作（无交叉污染）
6. 层级合并所有补丁提议：递归合并（每层最多 B_merge 个补丁）、去重、解冲突、硬约束检查
7. 输出：一份整合的、无冲突的 Skill 文档

**优势：** 快速、一次性、输出干净
**劣势：** 合并质量取决于合并模型；无自动验证

### EvoSkill（自然选择）

**哲学：** 验证集评分 + 自然选择

**流程：**
1. 从精英池 G（frontier set，固定容量 top-k）选父 Program p（轮询）
2. 在训练集上跑 p，收集低于阈值的失败样本
3. Proposer Agent 诊断失败，生成优化提议
4. Skill-Builder Agent 将提议物化为候选 Program p̃
5. 在独立验证集上评估 p̃，如果严格优于 G 中最弱成员则进入，否则丢弃
6. 无论结果如何，记录提议、分数和裁决到历史 H
7. 重复 T 次迭代，输出 G 中最高分 Program

**关键机制：**
- 失败记录到历史缓冲区作为负反馈
- Proposer Agent 从失败中学习什么不该再试

**优势：** 有机增长可解释的 Skill 库
**劣势：** 收敛慢（每轮一个变化）；运行间方差大

### SkillOpt（梯度下降类比）

**哲学：** 最像 ML 训练的方法

**流程：**

**Forward Pass（Rollout）：**
- 用当前 Skill 跑一批任务（默认 batch size 40）
- 记录完整轨迹（tool calls、observations、verifier feedback、harness metadata）

**Backward Pass（Minibatch Reflection）：**
- 分为成功/失败组，再分为 minibatch（size 8）
- 优化器模型生成结构化原子编辑操作（append/add/delete/replace）
- 失败组和成功组分别合并，全局合并时"失败优先"

**学习率约束：**
- 每步只允许 L_t 个编辑（有界文本更新）
- 支持 Cosine（默认）、Constant、Linear、Autonomous schedule
- 防止灾难性遗忘和过拟合

**Validation Gate：**
- 候选 Skill 在 held-out 验证集 D_sel 上运行
- 只有严格优于当前最优才被接受
- 平局拒绝
- 被拒编辑进入 Rejected-Edit Buffer

**Slow/Meta Update（Momentum）：**
- 每个 epoch 结束，重新跑前一个和当前 Skill 的样本
- 分为四类：Improvements / Regressions / Persistent Failures / Stable Successes
- 纵向原则写入 Skill 的"保护区"（step-level 编辑不可修改）
- 维护 Meta-Skill（仅优化器可见）：记录哪些编辑模式有效、哪些常被拒绝、哪些失败持续存在

**最终产出：** best_skill.md（300-2000 token，零依赖）

**优势：** 最可控、最稳定的收敛
**劣势：** 组件多；依赖稳定的验证集和评分函数

---

## 三种方法对比

| 维度 | Trace2Skill | EvoSkill | SkillOpt |
|------|------------|----------|----------|
| 哲学 | 归纳聚合 | 自然选择 | 梯度下降类比 |
| 更新粒度 | 一次性层级合并 | 每轮一个新 Skill 或编辑 | 每步多个有界原子编辑 |
| 验证 | 仅格式检查（无基准验证） | 验证集评分 vs 精英池 | 严格验证门 + 被拒编辑缓冲 |
| 学习率 | 无 | 无 | 有（L_t 编辑/步，cosine schedule） |
| Momentum | 无 | 无 | 有（epoch 级 meta 更新） |
| 元学习 | 无 | 累积反馈历史 H | Meta-Skill（优化器专属记忆） |

---

## 混合策略建议

1. **Trace2Skill**：快速从累积轨迹生成基线 Skill
2. **EvoSkill**：持续扩展 Skill 库，解决特定失败模式
3. **SkillOpt**：对关键瓶颈 Skill 做精细、稳定的优化

---

## Rejected-Edit Buffer

- 被拒绝的编辑记录为负反馈
- 记录 score delta（分数变化）
- 避免重复犯错
- 四类样本归因：
  - **Improvements**：新 Skill 比旧 Skill 好的样本
  - **Regressions**：新 Skill 比旧 Skill 差的样本
  - **Persistent Failures**：两个版本都失败的样本
  - **Stable Successes**：两个版本都成功的样本

---

## 评测即奖励信号

> 没有可量化信号告诉 Agent "什么是好的"，迭代就是盲目的。

- LLM 迭代快是因为改进越来越可测量（代码通过测试、基准有客观分数）
- Agent Skill 优化需要同样的自动验证基础设施
- 飞轮：Agent 产生轨迹 → 自动验证即时反馈 → 反馈调整 Skill → 新 Skill 进入验证循环

---

## 离线 vs 在线

- 真正的在线自进化（生产中实时更新 Skill）对企业太危险
- 推荐模式：离线优化 + 人工审核 + 回归测试 + 金丝雀部署
- 三篇论文旨在自动化更多离线循环，同时保持质量保证

---

## 关键洞察

1. **单对话轨迹的问题**：如果那一条轨迹是异常的、极端的、不具代表性的，Skill 更新就会"脱轨"
2. **验证反馈质量 > 计算预算**：arxiv 2605.29682，验证反馈质量（R²=0.94-0.99）比 token 消耗（R²=0.33-0.42）更能解释 Agent 成功
3. **Skill 工程正从"玄学调试"走向"科学工程"**
4. **验证/评测基础设施的成熟度是关键使能器**
