# PRD：CodePulse —— Code Agent 评测与自进化框架

> 版本：v1.0 | 日期：2026-06-26 | 作者：杨宇轩

---

## 一、项目背景

### 1.1 为什么做

DeepSeek Code Agent 数据工程师岗位要求：
1. 将真实代码工程场景转化为可训练的 RL 环境，设计合理的奖励信号
2. 设计高质量评测任务，量化模型在复杂真实场景下的表现
3. 基于真实数据与反馈，定位模型能力缺陷，推动弱项持续进步

这三件事的共同基础是：**一个可量化、可复现、可自进化的评测体系**。

### 1.2 我的资格

- **深度使用 AI 编程工具构建完整项目**：以 Claude Code + Codex 为主力开发工具，结合市面各价位模型（DeepSeek、GPT、Qwen 等），独立交付两个企业级工程项目（Semantic Lighthouse + NeedRadar），累计消耗超 10 亿 token
- **理解不同模型的能力边界**：在实际项目中对比使用过不同价位模型，了解各模型在代码生成、推理、工具调用等任务上的差异
- **工程实践扎实**：累计 1200+ 自动化测试通过，项目均有完整的 CI/CD 和 Docker 部署
- **开源贡献**：阿里巴巴 UnifiedModel 4 个 PR 被合并

### 1.3 核心理念

> 评测即奖励信号，评测体系本身就是 RL 环境。

不需要传统 RL 框架（PPO/GRPO），而是用 Anthropic 评测方法论 + SkillOpt 训练循环构建一个"评测驱动的自进化框架"。

---

## 二、产品定义

### 2.1 一句话定位

CodePulse 是一个 **Code Agent 评测平台 + 轻量自进化引擎**。

它不是框架（别人不会在上面构建应用），而是一个工具——你用它给 AI 编程工具做"考试"，出成绩单。

### 2.2 它能完成什么

**能回答的问题：**

| 问题 | 怎么回答 |
|------|---------|
| Claude Code 和 Codex 谁写 Python bug fix 更强？ | 同一批任务分别跑，对比分数 |
| DeepSeek 在代码审查上比 GPT-5.5 差多少？ | 五维度评测 + pass@k/pass^k |
| 哪类任务所有 AI 都做不好？ | 失败模式分析 + 四类归因 |
| 我的 prompt 改进有没有效果？ | 改进前后跑同一评测集，对比分数 |
| 这个 AI 写的代码够不够稳定？ | 跑 5 次，看 pass^5 |

**产出物：**

| 产出 | 形式 | 用途 |
|------|------|------|
| 评测报告 | HTML | 五维度雷达图 + 详细分数 |
| 多模型对比 | HTML | 同一任务不同 Agent 对比表 |
| 失败模式分析 | Markdown | 哪类任务失败、失败原因分布 |
| 自进化报告 | Markdown | 改进前后分数变化 + 编辑统计 |
| 开源项目 | GitHub | 简历材料 + 代码品味证据 |

### 2.3 和 DeepSeek 岗位的对应

| DeepSeek 职责 | CodePulse 对应 |
|--------------|---------------|
| 构建 RL 环境 | 评测体系 = RL 环境（评测分数 = 奖励信号） |
| 评估 Agent 能力 | 五维度评测 + pass@k/pass^k + 跨 Agent 对比 |
| 补全能力短板 | SkillOpt 自进化 + 失败模式分析 + 四类归因 |

**面试叙事：**
> "我构建了 CodePulse，一个 Code Agent 评测平台。它能对 Claude Code、Codex、DeepSeek 等工具做五维度评测，产出量化报告。同时它有一个 SkillOpt 风格的自进化循环，能从评测失败中学习，自动改进 Agent 的 prompt。这个评测体系本质上就是一个 RL 环境——评测分数是奖励信号，Rejected-Edit Buffer 是负反馈。"

### 2.4 诚实评估

| 维度 | 现实 |
|------|------|
| 评测能力 | ✅ 可实现，有 Anthropic/腾讯方法论支撑 |
| 多模型对比 | ✅ 可实现，LiteLLM 支持多模型切换 |
| 自进化 | ⚠️ 实验性，SkillOpt 论文有理论支撑但工程实现需验证 |
| 生产可用 | ❌ 不是目标，这是展示能力的项目 |

**最大价值：证明你有能力设计和实现一个复杂的 AI 评测系统。**

---

## 三、技术架构

### 3.1 六层架构

```
┌─────────────────────────────────────────────────────────────┐
│                      Layer 6: 产出层                          │
│  HTML 报告 / 多模型对比 / 自进化报告 / 失败模式知识库           │
├─────────────────────────────────────────────────────────────┤
│                      Layer 5: 自进化层                         │
│  SkillOpt Forward→Backward→Validate→Buffer                   │
│  四类样本归因 / 学习率约束 / 经验三级进化                        │
├─────────────────────────────────────────────────────────────┤
│                      Layer 4: 可观测性层                       │
│  Agent Trace(session→turn→step→tool_call)                    │
│  Token 效率 / 黑洞模式检测 / 跨 Agent 对比 / pass@k/pass^k    │
├─────────────────────────────────────────────────────────────┤
│                      Layer 3: 评测层                          │
│  五维度评测体系                                                │
│  确定性 Grader + LLM-as-Judge + 人工校准                      │
│  100 分扣分制 / 三类 Grader 组合                              │
├─────────────────────────────────────────────────────────────┤
│                      Layer 2: 数据层                          │
│  SWE-bench Verified(500) + AACR-Bench(200) + 自定义(30+)     │
│  统一 Task/Trial/Grader schema / 数据集版本管理                │
├─────────────────────────────────────────────────────────────┤
│                      Layer 1: 环境层                          │
│  Docker 隔离执行 / 沙箱管理 / 资源监控 / 快照回滚              │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 技术栈

| 类别 | 技术 | 理由 |
|------|------|------|
| 语言 | Python 3.11+ | 主力语言、AI 生态原生 |
| 测试 | pytest | 848 条测试经验 |
| 代码质量 | ruff + mypy + bandit | 现代、快速、覆盖安全 |
| LLM | LiteLLM | 多模型切换经验，支持 DeepSeek/GPT/Claude/Qwen |
| 数据集 | SWE-bench + AACR-Bench | 社区公认基准 |
| 容器 | Docker + docker-py | 隔离执行 |
| 存储 | SQLite + JSONL + LanceDB | 轻量、可查询 |
| CI/CD | GitHub Actions | 有经验 |
| 报告 | Jinja2 + HTML | 可视化 |

---

## 四、功能规格

### 4.1 Layer 1：环境层

#### 功能

| 功能 | 优先级 | 说明 |
|------|--------|------|
| Docker 容器创建/销毁 | P0 | 每个评测任务独立容器 |
| 干净状态启动 | P0 | 每次评测从零开始 |
| 资源限制 | P1 | CPU/内存/时间限制 |
| 快照/回滚 | P2 | 支持重试 |
| 网络隔离 | P2 | 可选 |

#### 接口

```python
class SandboxManager:
    def create(self, image: str, resource_limits: dict) -> Container
    def execute(self, container: Container, command: str) -> ExecutionResult
    def snapshot(self, container: Container) -> Snapshot
    def restore(self, snapshot: Snapshot) -> Container
    def destroy(self, container: Container) -> None
```

---

### 4.2 Layer 2：数据层

#### 数据源

| 数据源 | 规模 | 场景 | 语言 |
|--------|------|------|------|
| SWE-bench Verified | 500 任务 | Bug 修复 | Python |
| AACR-Bench | 200 PR | 代码审查 | 10 种语言 |
| 自定义 | 30+ 任务 | 功能/重构/安全 | Python |

#### 统一 Schema

```python
@dataclass
class Task:
    task_id: str
    source: str                    # "swe-bench" | "aacr-bench" | "custom"
    category: str                  # "bug_fix" | "feature" | "refactor" | "code_review"
    difficulty: str                # "easy" | "medium" | "hard"
    language: str                  # "python" | "java" | "go" | ...
    input: dict                    # Issue 描述 + 代码库快照
    ground_truth: dict             # 参考 PR / 期望结果
    graders: list[GraderConfig]   # 评分器配置
    metadata: dict                 # 仓库、star 数、创建时间等

@dataclass
class Trial:
    trial_id: str
    task_id: str
    agent_config: AgentConfig      # Agent 配置
    transcript: Transcript         # 完整 Trace
    outcome: dict                  # 最终状态
    scores: dict[str, float]       # 各维度分数
    metrics: TrialMetrics          # token、时间、工具调用
```

#### 自定义数据收集

从 3-5 个中等规模 Python 开源项目（star 1k-10k）收集：
- Issues + PR + CI 结果
- 按难度分类（easy/medium/hard）
- 人工标注 Ground Truth
- 目标：30+ 任务，覆盖 bug_fix、feature、refactor、code_review

---

### 4.3 Layer 3：评测层

#### 五维度评测体系

| 维度 | 优先级 | 权重 | Grader 类型 | 子维度 |
|------|--------|------|------------|--------|
| 功能正确性 | P0 | 30 分 | 确定性 | 测试通过率、编译成功率、任务完成率 |
| 过程质量 | P1 | 25 分 | LLM-as-Judge | 推理合理性、步骤最优性、信息完整性、自修正能力 |
| 效率成本 | P1 | 15 分 | 确定性 | Token 消耗、工具调用次数、延迟、每任务成本 |
| 鲁棒安全 | P0 | 20 分 | 确定性+LLM | 稳定性(pass^5)、故障恢复、幻觉率、安全合规 |
| 体验对齐 | P2 | 10 分 | LLM-as-Judge | 输出格式合规、清晰度、可解释性 |

#### 100 分扣分制

```
起始：100 分
通过阈值：80 分（可调）

功能正确性（30 分）：
  - 测试全部通过：+30
  - 测试部分通过：按比例
  - 测试全部失败：+0

过程质量（25 分）：
  - 推理合理性（LLM 1-5 分）：×2 = 10 分
  - 步骤最优性：5 分
  - 信息完整性：5 分
  - 自修正能力：5 分

效率成本（15 分）：
  - Token 消耗 vs 基线：5 分（超基线 10% 扣 1 分）
  - 工具调用次数：3 分
  - 延迟：4 分
  - 每任务成本：3 分

鲁棒安全（20 分）：
  - pass^5 稳定性：8 分（全通过 8 分，1 次失败 4 分，2+ 次失败 0 分）
  - 故障恢复：4 分
  - 幻觉率：4 分
  - 安全合规：4 分

体验对齐（10 分）：
  - 输出格式合规：4 分
  - 清晰度：3 分
  - 可解释性：3 分
```

#### 三类 Grader

**确定性 Grader（P0，必须）：**
- `pytest_grader`：在 Docker 容器中执行 pytest，统计通过率
- `ruff_grader`：代码规范检查
- `mypy_grader`：类型检查
- `bandit_grader`：安全检查
- `state_grader`：环境状态断言（文件存在、变量值等）
- `tool_call_grader`：工具调用序列验证（LCS 对齐）

**LLM-as-Judge（P1，重要）：**
- `rubric_grader`：Rubric 评分（1-5 分），有明确的评分标准
- `code_quality_grader`：代码质量（命名、结构、注释、可维护性）
- `reasoning_grader`：推理合理性（逻辑链是否完整）
- `calibrator`：按维度校准（功能维度使用确定性 oracle；定性维度使用完整证据人工双轮复核）

**人工 Grader（P2，校准用）：**
- 新评测集的 Ground Truth 标注（前 20-50 个参考解）
- 每周 Trace 抽样审计
- 异常诊断（0% 或 100% 通过率时）

#### LLM-as-Judge 设计

```python
class RubricGrader:
    def __init__(self, model: str = "deepseek-chat"):
        self.model = model
        self.rubric = """
        评分标准（1-5 分）：
        5 分：代码逻辑完全正确，边界条件处理完善，无冗余
        4 分：代码逻辑正确，少量边界遗漏，整体可维护
        3 分：代码基本能用，有明显改进空间
        2 分：代码有逻辑错误或严重质量问题
        1 分：代码完全不可用
        """

    def grade(self, task: Task, trial: Trial) -> float:
        prompt = f"""
        任务：{task.input['description']}
        参考答案：{task.ground_truth}
        Agent 输出：{trial.outcome}

        {self.rubric}

        请输出 JSON：{{"score": 1-5, "reasoning": "..."}}
        """
        result = self.llm.call(prompt, response_format="json")
        return result["score"]
```

#### 评测编排器

```python
class EvaluationHarness:
    def run_task(self, task: Task, agent: Agent, n_trials: int = 5) -> list[Trial]:
        """运行一个任务的多次试运行"""
        trials = []
        for i in range(n_trials):
            # 1. 创建干净环境
            container = self.sandbox.create(task.image)
            # 2. 运行 Agent
            transcript = agent.run(task, container)
            # 3. 收集结果
            outcome = self._collect_outcome(container, transcript)
            # 4. 多维度评分
            scores = self._grade(task, transcript, outcome)
            # 5. 收集指标
            metrics = self._collect_metrics(transcript)
            # 6. 记录 Trial
            trials.append(Trial(...))
            # 7. 销毁环境
            self.sandbox.destroy(container)
        return trials

    def _grade(self, task, transcript, outcome) -> dict:
        """三类 Grader 并行执行"""
        scores = {}
        # 确定性 Grader
        scores["functional"] = self.pytest_grader.grade(task, outcome)
        scores["code_quality"] = self.ruff_grader.grade(task, outcome)
        # LLM-as-Judge
        scores["reasoning"] = self.rubric_grader.grade(task, transcript)
        scores["robustness"] = self.stability_grader.grade(task, trials)
        # 聚合
        return self._aggregate(scores)
```

---

### 4.4 Layer 4：可观测性层

#### Agent Trace 采集

```python
@dataclass
class TraceEvent:
    timestamp: float
    event_type: str        # "llm_call" | "tool_call" | "tool_result" | "reflection"
    content: dict          # 事件内容
    token_usage: dict      # input/output/cache tokens
    duration: float        # 耗时

@dataclass
class Transcript:
    session_id: str
    agent_config: AgentConfig
    events: list[TraceEvent]
    total_tokens: int
    total_duration: float
    tool_call_count: int
```

#### 核心指标

| 指标 | 计算方式 | 意义 |
|------|---------|------|
| pass@k | k 次至少成功 1 次的概率 | 能力上限 |
| pass^k | k 次全部成功的概率 | 稳定性 |
| Token 效率比 | 总 token / 成功任务数 | 成本效率 |
| 自修正率 | 回滚次数 / 总步骤数 | 能力边界信号 |
| 工具调用效率 | 有效调用 / 总调用 | 工具使用合理性 |

#### 三个黑洞模式检测

```python
class BlackholeDetector:
    def detect_loop_trial(self, trace: Transcript) -> dict | None:
        """检测循环试错：Write+Bash(test) 反复出现"""
        write_bash_pairs = self._find_write_bash_pairs(trace)
        if len(write_bash_pairs) >= 3:
            return {"type": "loop_trial", "count": len(write_bash_pairs)}
        return None

    def detect_context_bloat(self, trace: Transcript) -> dict | None:
        """检测上下文膨胀：input_tokens 阶梯式增长"""
        input_tokens = [e.token_usage["input"] for e in trace.events if e.event_type == "llm_call"]
        if len(input_tokens) >= 5:
            growth_rate = (input_tokens[-1] - input_tokens[0]) / input_tokens[0]
            if growth_rate > 2.0:  # 增长超过 200%
                return {"type": "context_bloat", "growth_rate": growth_rate}
        return None

    def detect_over_caution(self, trace: Transcript) -> dict | None:
        """检测过度谨慎：LLM span 占比 > 80%"""
        llm_time = sum(e.duration for e in trace.events if e.event_type == "llm_call")
        total_time = trace.total_duration
        if total_time > 0 and llm_time / total_time > 0.8:
            return {"type": "over_caution", "llm_ratio": llm_time / total_time}
        return None
```

#### 跨 Agent 对比

```python
class AgentComparator:
    def compare(self, task: Task, agents: list[Agent], n_trials: int = 5) -> dict:
        """同一任务在不同 Agent 上的表现对比"""
        results = {}
        for agent in agents:
            trials = self.harness.run_task(task, agent, n_trials)
            results[agent.name] = {
                "pass_at_1": self._calc_pass_at_k(trials, 1),
                "pass_at_5": self._calc_pass_at_k(trials, 5),
                "pass_hat_5": self._calc_pass_hat_k(trials, 5),
                "avg_tokens": np.mean([t.metrics.total_tokens for t in trials]),
                "avg_duration": np.mean([t.metrics.total_duration for t in trials]),
                "self_correction_rate": np.mean([t.metrics.self_correction_rate for t in trials]),
            }
        return results
```

---

### 4.5 Layer 5：自进化层

#### SkillOpt 训练循环

```python
class SkillOpt:
    def __init__(self, harness: EvaluationHarness, dataset: Dataset):
        self.harness = harness
        self.dataset = dataset
        self.buffer = RejectedEditBuffer()
        self.attribution = SampleAttribution()

    def evolve(self, initial_skill: Skill, n_epochs: int = 3) -> Skill:
        """SkillOpt 主循环"""
        current_skill = initial_skill
        best_skill = initial_skill
        best_score = self._evaluate(current_skill)

        for epoch in range(n_epochs):
            # Forward Pass：收集轨迹
            trajectories = self._forward_pass(current_skill)

            # 分析：四类样本归因
            old_scores = {t.task_id: t.scores for t in self._forward_pass(best_skill)}
            attributions = self.attribution.classify_all(old_scores, trajectories)

            # Backward Pass：生成编辑
            edits = self._backward_pass(trajectories, attributions)

            # 学习率约束：每步最多 L_t 个编辑
            edits = edits[:self.L_t]

            # 应用编辑
            candidate_skill = self._apply_edits(current_skill, edits)

            # Validation Gate：严格验证
            candidate_score = self._evaluate(candidate_skill)
            if candidate_score > best_score:
                best_skill = candidate_skill
                best_score = candidate_score
                current_skill = candidate_skill
            else:
                # 进入 Rejected-Edit Buffer
                self.buffer.add_rejected(edits, candidate_score - best_score)
                # 不更新 current_skill，保持上一轮

        return best_skill

    def _forward_pass(self, skill: Skill) -> list[Trajectory]:
        """跑评测集，收集轨迹"""
        trajectories = []
        for task in self.dataset.tasks:
            trials = self.harness.run_task(task, skill, n_trials=5)
            trajectories.append(Trajectory(
                task=task,
                trials=trials,
                success=all(t.scores["functional"] >= 80 for t in trials),
                avg_scores=self._avg_scores(trials),
            ))
        return trajectories

    def _backward_pass(self, trajectories: list[Trajectory], attributions: dict) -> list[Edit]:
        """分析失败，生成编辑"""
        edits = []
        for traj in trajectories:
            if not traj.success:
                # LLM 分析失败根因
                analysis = self.llm.analyze_failure(traj)
                if analysis.confidence >= 0.7:  # 质量门
                    edits.extend(self._generate_edits(analysis))
        return edits
```

#### Rejected-Edit Buffer

```python
class RejectedEditBuffer:
    def __init__(self):
        self.entries: list[RejectedEntry] = []

    def add_rejected(self, edits: list[Edit], score_delta: float):
        for edit in edits:
            self.entries.append(RejectedEntry(
                edit=edit,
                score_delta=score_delta,
                timestamp=time.time(),
                reason=self._classify_rejection(edit, score_delta),
            ))

    def get_negative_signals(self) -> list[Edit]:
        """获取负反馈信号"""
        return [e.edit for e in self.entries if e.score_delta < -0.05]

    def get_patterns(self) -> dict:
        """分析被拒编辑的模式"""
        patterns = {}
        for entry in self.entries:
            key = entry.edit.type  # "append" | "add" | "delete" | "replace"
            patterns.setdefault(key, []).append(entry)
        return patterns
```

#### 四类样本归因

```python
class SampleAttribution:
    def classify(self, old_score: float, new_score: float) -> str:
        old_pass = old_score >= 80
        new_pass = new_score >= 80
        if not old_pass and new_pass:
            return "improvement"
        elif old_pass and not new_pass:
            return "regression"
        elif not old_pass and not new_pass:
            return "persistent_failure"
        else:
            return "stable_success"

    def classify_all(self, old_scores: dict, trajectories: list[Trajectory]) -> dict:
        attributions = {}
        for traj in trajectories:
            old = old_scores.get(traj.task_id, 0)
            new = traj.avg_scores["functional"]
            attributions[traj.task_id] = self.classify(old, new)
        return attributions

    def report(self, attributions: dict) -> AttributionReport:
        counts = Counter(attributions.values())
        return AttributionReport(
            improvements=counts["improvement"],
            regressions=counts["regression"],
            persistent_failures=counts["persistent_failure"],
            stable_successes=counts["stable_success"],
            improvement_rate=counts["improvement"] / len(attributions),
            regression_rate=counts["regression"] / len(attributions),
        )
```

#### 经验三级进化

```python
class ExperienceEvolution:
    def record_lesson(self, observation: str, context: dict):
        """Lesson：单次记录"""
        self.lessons.append(Lesson(
            observation=observation,
            context=context,
            timestamp=time.time(),
        ))

    def try_promote_to_pattern(self) -> list[Pattern]:
        """Pattern：跨项目泛化"""
        patterns = []
        for obs, group in groupby(self.lessons, key=lambda l: l.observation):
            if len(list(group)) >= 2:  # 至少两次
                pattern = self._generalize(obs, list(group))
                patterns.append(pattern)
        return patterns

    def try_promote_to_instinct(self, pattern: Pattern) -> bool:
        """Instinct：自动注入（需人工确认）"""
        if pattern.confidence >= 0.8 and pattern.verification_count >= 3:
            # 提交给人类确认
            return self._request_human_approval(pattern)
        return False
```

---

### 4.6 Layer 6：产出层

#### 评测报告

| 报告类型 | 内容 | 格式 |
|---------|------|------|
| 单次评测报告 | 五维度分数 + 详细分析 | HTML |
| 多模型对比报告 | 雷达图 + pass@k/pass^k + 效率对比 | HTML |
| 自进化报告 | 分数变化 + 编辑统计 + 归因分析 | HTML |
| 失败模式报告 | 根因分布 + 改进建议 | Markdown |

#### 多模型对比

支持对比的 Agent/模型：
- Claude Code（Claude-4.6-Opus / Claude-4.8-Opus）
- Codex（GPT-5.5）
- DeepSeek（DeepSeek-V4-Pro）
- Qwen（Qwen3.7-Max）
- 其他（通过 LiteLLM 接入）

---

## 五、项目计划

### 5.1 Phase 1：环境与数据基础（2.5 周）

| 任务 | 周期 | 产出 |
|------|------|------|
| Docker 沙箱管理器 | 1 周 | sandbox.py + 测试 |
| SWE-bench 数据加载器 | 0.5 周 | swe_bench.py + 测试 |
| AACR-Bench 数据加载器 | 0.5 周 | aacr_bench.py + 测试 |
| 自定义数据收集 | 0.5 周 | 30+ 任务 + 标注 |

**里程碑：** 能加载 SWE-bench + AACR-Bench，在 Docker 中跑通一个评测任务

### 5.2 Phase 2：确定性评测引擎（2 周）

| 任务 | 周期 | 产出 |
|------|------|------|
| pytest Grader | 0.5 周 | pytest_grader.py + 测试 |
| ruff/mypy/bandit Grader | 0.5 周 | 代码质量评分器 |
| 100 分扣分制 | 0.5 周 | scoring.py + 测试 |
| 评测编排器 | 0.5 周 | harness.py + 测试 |

**里程碑：** 能对一个任务跑 5 次评测，输出 100 分制分数

### 5.3 Phase 3：LLM-as-Judge（2 周）

| 任务 | 周期 | 产出 |
|------|------|------|
| Rubric Grader | 0.5 周 | rubric_grader.py + 测试 |
| 代码质量 Grader | 0.5 周 | code_quality_grader.py |
| 推理合理性 Grader | 0.5 周 | reasoning_grader.py |
| 人工校准工具 | 0.5 周 | calibrator.py + 校准数据集 |

**里程碑：** 五维度评测完整运行，输出结构化评分

### 5.4 Phase 4：可观测性（2 周）

| 任务 | 周期 | 产出 |
|------|------|------|
| Trace 采集器 | 0.5 周 | trace_collector.py |
| Token 统计 | 0.5 周 | token_collector.py |
| 黑洞模式检测 | 0.5 周 | blackhole.py + 测试 |
| pass@k/pass^k | 0.5 周 | pass_k.py + 测试 |

**里程碑：** 能采集完整 Trace，检测黑洞模式，输出 pass@k/pass^k

### 5.5 Phase 5：自进化框架（3.5 周）

| 任务 | 周期 | 产出 |
|------|------|------|
| Forward Pass | 0.5 周 | rollout.py + trajectory.py |
| Backward Pass | 1 周 | analyzer.py + editor.py + merger.py |
| Validation Gate | 0.5 周 | gate.py |
| Rejected-Edit Buffer | 0.5 周 | buffer.py + 测试 |
| 四类样本归因 | 0.5 周 | classifier.py + reporter.py |
| 学习率约束 | 0.5 周 | scheduler.py |

**里程碑：** 能跑完一轮 SkillOpt 循环，输出分数变化和归因报告

### 5.6 Phase 6：实验与开源（2.5 周）

| 任务 | 周期 | 产出 |
|------|------|------|
| 多模型对比实验 | 1 周 | 对比报告（5 个模型） |
| 自进化实验 | 0.5 周 | 3 轮进化 + 分数变化 |
| 失败模式分析 | 0.5 周 | 根因分布报告 |
| GitHub 开源 | 0.5 周 | README + 文档 + CI/CD |

**里程碑：** 完整实验报告 + GitHub 开源项目

---

## 六、验收标准

### 6.1 功能验收

- [ ] 能加载 SWE-bench + AACR-Bench + 自定义数据集
- [ ] 能在 Docker 隔离环境中运行评测
- [ ] 五维度评测完整运行，输出 100 分制分数
- [ ] pass@k / pass^k 统计正确
- [ ] 三个黑洞模式检测功能正常
- [ ] SkillOpt 自进化循环跑通，输出分数变化
- [ ] 四类样本归因报告正确

### 6.2 质量验收

- [ ] 测试覆盖率 ≥ 80%
- [ ] 所有测试通过（pytest）
- [ ] 代码规范（ruff check 无报错）
- [ ] 类型检查（mypy 无报错）
- [ ] 安全检查（bandit 无高危）

### 6.3 文档验收

- [ ] README（项目介绍、快速开始、架构说明）
- [ ] 架构文档（六层架构详细说明）
- [ ] 使用指南（如何添加新数据集、新评分器、新维度）
- [ ] 贡献指南

### 6.4 开源验收

- [ ] GitHub 仓库公开
- [ ] CI/CD 流水线通过
- [ ] Docker 镜像可用
- [ ] 示例数据集和评测报告

---

## 七、风险与对策

| 风险 | 概率 | 影响 | 对策 |
|------|------|------|------|
| SWE-bench 任务太难 | 中 | 低 | 选 Verified 版本；同时用 AACR-Bench 平衡 |
| LLM-as-Judge 不稳定 | 中 | 中 | 多次运行取平均；仅对完整证据定性维度做人工双轮校准 |
| SkillOpt 实现复杂度超预期 | 中 | 高 | 先实现 Forward + Validation Gate，再加 Backward |
| 自进化效果不明显 | 低 | 高 | 选简单任务先验证；分析失败原因作为产出 |
| 项目太大做不完 | 中 | 高 | Phase 1-3 是 MVP，Phase 4-6 是加分项 |

---

## 八、简历 bullet 预览

1. 构建 Code Agent 评测框架 CodePulse，基于 Anthropic 评测方法论设计五维度评测体系（功能正确性/过程质量/效率成本/鲁棒安全/体验对齐），三类 Grader（确定性 + LLM-as-Judge + 人工校准），100 分扣分制，覆盖 SWE-bench + AACR-Bench + 自定义数据集共 730+ 评测任务。

2. 实现 Agent 可观测性系统，采集完整 Trace（session→turn→step→tool_call），检测三个 Token 黑洞模式（循环试错/上下文膨胀/过度谨慎），支持 pass@k/pass^k 统计和跨 Agent 行为对比分析。

3. 设计 SkillOpt 风格的自进化框架：Forward Pass 收集轨迹 → Backward Pass 分析失败生成原子编辑 → Validation Gate 严格验证 → Rejected-Edit Buffer 负反馈学习，四类样本归因（改进/退化/持续失败/稳定成功），评测分数从 X 提升到 Y。

4. 以 Claude Code + Codex 为主力开发工具，结合市面各价位模型（DeepSeek/GPT/Qwen）构建 CodePulse 框架（累计消耗超 10 亿 token），交付 ~4000 行代码 + ~600 条测试 + 6 份文档，项目完整 CI/CD + Docker 部署。
