# commands — CLI 子命令组

## 职责边界

提供 `codepulse evolve` 和 `codepulse baseline` 两个 CLI 子命令组。**只管** CLI 参数解析和结果打印，**不管**核心逻辑（委托给 evolve/suggest 和文件操作）。

## 关键设计决策

### baseline 快照机制

`baseline save` 将当前 `results/` 下的所有 `summary.json` 文件**复制**到 `results/baselines/{name}/`，并生成 `baseline.json` manifest。选择复制而非移动，因为原始结果仍需被 API 访问。

`baseline compare` 对比当前结果与快照的净分数差。这提供了简单的 A/B 实验能力，无需额外基础设施。

### evolve suggest 的规则引擎集成

`evolve suggest` 加载所有 summary，计算平均维度分，调用 `SuggestionEngine` 生成 Markdown 格式建议。建议可输出到终端或文件。

### Click 集成模式

两个命令组通过 `add_command()` 注册到主 CLI，与 `cli.py` 保持松耦合。命令组定义各自独立的 Click group，主入口仅做 import + add_command。

## 对外接口

- **被调用**: cli.py (注册为子命令组)
- **调用**: evolve/suggest, file system

## 约定与模式

- 所有命令使用 Click decorator 模式
- 输出默认使用终端（`click.echo`），可选 `--output` 重定向到文件
- baseline 目录是自包含的——复制后不依赖原始 results

## 陷阱与已知问题

- baseline compare 只比较 summary.json 层级的聚合分数，不对比单 trial 细节
- 大量结果的 baseline save 可能 I/O 较重
- baseline delete 无回收站机制，`--yes` 跳过确认

## 测试策略

- `test_baseline.py`：save/list/compare/delete 的集成测试
- 使用临时目录模拟 results 结构
