# data — Layer 2: Data Layer

## 职责边界

定义评测数据的统一模型、加载管道和类型契约。**只管** Task/Trial 结构定义、数据集解析与验证，**不管** Agent 执行逻辑、怎么评测、结果如何存储到文件。

## 关键设计决策

### Protocol 而非继承

Agent、Grader、DatasetLoader 使用 `typing.Protocol`（结构子类型），而非 ABC 继承。原因：
- 协议不强制导入依赖，调用方与被调用方零耦合
- 任何符合结构签名的对象即可通过 isinstance 检查
- 避免抽象基类的 diamond 继承问题

### frozen dataclass 数据模型

Task、AgentConfig、GraderConfig 均为 `frozen=True`。评测数据应不可变——一个 Task 被多次 Trial 引用时不应被修改。

### Loader 容错策略

所有 Loader（SweBench、AACR、Custom）对损坏行采用 skip + warning，不中断整个数据集加载。单行损坏不应阻止剩余任务进入评测。

### AACR 语言推断

通过评审文件的扩展名推断语言，而非显式字段。原因是 AACR-Bench 原始数据不包含 language 字段。映射表 `_EXT_LANG` 维护在 `aacr_bench.py` 顶部。

## 对外接口

- **被调用**: eval/harness, benchmark, api
- **调用**: 无内部依赖（models.py 零依赖）

## 约定与模式

- Task ID 服从 `{source}-{instance_id}` 格式
- GraderResult.score 始终在 [0,1] 区间
- ResultPath 在 `results/{task_id}/` 下组织，不与 datasets 混用

## 陷阱与已知问题

- Protocol 在 TYPE_CHECKING 下用于类型注解，运行时通过 `hasattr` 检查
- JSONL 中任意字段缺失都会触发校验失败，需确保数据集与 Loader 版本匹配

## 测试策略

- `test_loaders.py`：各 Loader 的解析和校验测试
- 测试数据来自 `datasets/` 下的示例文件
