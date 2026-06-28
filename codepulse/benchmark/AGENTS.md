# benchmark — 业界 Benchmark 注册与运行

## 职责边界

管理已知评测基准的元数据注册表、数据集下载和批量评测运行。**只管**流水线编排（下载→加载→运行→保存），**不管**评测逻辑本身（委托给 eval/harness）。

## 关键设计决策

### 三级分离架构

| 模块 | 职责 |
|------|------|
| `registry.py` | 基准的元数据（名称、描述、任务数、URL、baseline、期望路径）|
| `downloader.py` | 数据集文件的 HTTP 下载和缓存管理 |
| `cli.py` | Click CLI 命令（list/info/status/run）|

注册表不碰文件系统，下载器不关心基准定义，CLI 仅做编排。任何一方可独立替换。

### 内置基准

| 基准 | 任务数 | 语言 | Loader |
|------|--------|------|--------|
| swe-bench-lite | 300 | Python | SweBenchLoader |
| swe-bench-verified | ~500 | Python | SweBenchLoader |
| humaneval | 164 | Python | CustomDatasetLoader |
| mbpp | ~974 | Python | CustomDatasetLoader |
| aacr-bench | ~1000 | 多语言 | AacrBenchLoader |

### 自动下载策略

`run` 命令在数据集缺失且 URL 已知时自动触发下载。下载到 `datasets/cache/` 下，按基准名称命名。force 参数可强制重新下载。

### 结果存储约定

`_save_benchmark_summary()` 输出到 `results/benchmarks/{name}/summary.json`，与其他模块的 `results/{task_id}/` 结构形成统一约定。

## 对外接口

- **被调用**: cli.py (plugin 模式)
- **调用**: data/loaders, eval/harness, eval/scoring, agent/adapter

## 约定与模式

- CLI 使用 Click multi-command group
- `benchmark run` 的 `--agent` 参数接收 YAML profile 文件路径
- `_register()` 函数注册内置基准，非类方法，避免循环导入

## 陷阱与已知问题

- SWE-bench 数据集体积大（数 GB），下载时间可能很长
- AACR 的多语言支持依赖于 `aacr_bench.py` 中维护的扩展名-语言映射
- `run` 命令是同步的——大批量任务需要较长时间，未做并行处理

## 测试策略

- `test_benchmark.py`：注册表查询和下载器缓存测试
- 下载测试可跳过（需要网络）
