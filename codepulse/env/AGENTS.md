# env — Layer 1: Docker Sandbox

## 职责边界

为评测提供隔离执行环境。本层**只管**容器生命周期（创建/执行/快照/恢复/销毁），**不管** Agent 如何被调用、Task 如何被加载、分数如何计算。

## 关键设计决策

### tar 文件写入替代 inline script

`SandboxUtils.write_file()` 通过 `tar + put_archive` 写入文件，而非 `echo >> file` 内联脚本。后者在特殊字符（引号、换行、Unicode）面前极易损坏，且难以调试。tar 归档是确定性的，不依赖转义。

### active_container 绑定模式

`SandboxManager.set_active_container()` / `get_active_container()` 将当前容器绑定到模块级状态，供工具系统访问。这避免了对 Agent 做 monkey-patch，也没有走全局单例——容器切换显式可控。

### frozen dataclasses

所有容器句柄（Container、Snapshot、ResourceLimits、ExecutionResult、PytestResult）都是 `frozen=True`，防止下游代码意外修改，确保执行记录不变。

## 对外接口

- **被调用**: eval/harness, agent/adapter, benchmark/cli
- **调用**: 仅 `docker` SDK，不依赖任何其他 codepulse 模块

## 约定与模式

- 每个 trial 创建独立容器，`finally` 块保证销毁
- `run_pytest()` 要求容器内有 pytest，解析标准 JSON report
- 超时控制通过 Kubernetes/docker `timeout` 参数，不依赖 Python 信号

## 陷阱与已知问题

- Windows 下的 Docker Desktop 需要切换到 Linux 容器模式
- 镜像拉取超时在弱网环境下可能失败，未做重试（需改进）
- `MockAgent` 仅用于集成测试，不下场执行

## 测试策略

- `test_sandbox.py`：容器创建/执行/销毁的集成测试（Docker 不可用时自动跳过）
- MockAgent 用于评估管线测试，不依赖真实 LLM 调用
