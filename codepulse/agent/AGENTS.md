# agent — Real Agent Implementation

## 职责边界

实现通过 LiteLLM 调用真实 LLM 的 Agent（RealAgent），以及三种零侵入 Adapter 模式（CLI/Protocol/Mock）。**只管**将 Task 转化为 LLM 交互循环，**不管**评测评分（那是 eval 的事）。

## 关键设计决策

### OpenAI function-calling 工具系统

`Tool` 基类统一工具接口：
- `name` / `description` / `parameters`：ClassVar，用于 LLM function-calling schema
- `execute()`：在 sandbox 中执行
- `to_schema()`：生成 OpenAI 格式的工具定义

`ToolRegistry` 管理工具注册和 schema 收集。默认注册表包含 ReadFile、WriteFile、Execute 三个工具，覆盖 Code Agent 的基本操作。

### 三种 Adapter 模式

| 模式 | `type` | 触发条件 | 用途 |
|------|--------|----------|------|
| CLI | `"cli"` | profile.type == "cli" | 零侵入：注入 task.json，执行用户命令，收集输出。不做任何 Agent 运行假设 |
| Protocol | `"protocol"` | profile.type == "protocol" | 标准路径：加载 Python Agent 实现，调用 `agent.run()` |
| Mock | `"mock"` | profile.type == "mock" | 测试和基准：返回固定 Transcript，不实际调用 LLM |

CLI 模式是"零侵入"设计的核心——用户可以提交任意可执行命令，CodePulse 只需注入 `task.json` 并收集输出文件。

### 工具输出截断策略

LLM 上下文有限，工具输出需截断：
- 普通工具输出：30,000 字符
- 文件读取：50,000 字符
- 命令执行输出：20,000 字符

截断阈值是经验值，基于 `deepseek-chat` 默认 64K 上下文窗口计算。

### 多 Provider token 提取

`RealAgent._extract_usage()` 兼容 DeepSeek 和 OpenAI 的 usage 对象格式差异。两者字段命名不完全一致（如 reasoning tokens 只在 DeepSeek 下出现）。

### config.calc_cost 无 Agent 耦合

成本计算在 `config.py` 中独立于 Agent 实现，`MODEL_PRICING` 字典按模型名精匹配+前缀匹配+零成本回退查找。新模型只需向字典添加一行。

## 对外接口

- **被调用**: benchmark, cli (via adapter)
- **调用**: env/sandbox, env/sandbox_utils, observe/trace, data/models, config

## 约定与模式

- `AgentProfile` 通过 YAML 文件定义，CLI 通过 `--agent` 参数传入路径
- `run_adapter_trials()` 是批处理入口，内部创建/销毁容器
- 异常在 `RealAgent.run()` 中捕获并记录为 ERROR 事件，不向上抛

## 陷阱与已知问题

- `RealAgent.run()` 的迭代循环没有时间硬上限，可能陷入长执行
- 工具输出截断可能导致 LLM 看不到完整报错信息
- CLI adapter 对用户命令的格式有隐式假设（接收 task.json 路径参数），文档中未充分说明

## 测试策略

- `test_real_agent.py`：Mock LLM 响应的单元测试
- `test_tools.py`：工具注册和 schema 生成测试
- adapter 测试依赖真实 agent profile 文件
