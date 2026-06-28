# output — Layer 6: Output Layer

## 职责边界

生成评测报告（Markdown 和 HTML），将内存数据渲染为可交付的输出。**只管**格式化和渲染，**不管**数据来源、评测逻辑。

## 关键设计决策

### Markdown + HTML 双模输出

- **Markdown**：适合终端预览和 CI 输出，`generate_trial_report()`、`generate_comparison_report()`、`generate_evolution_report()`
- **HTML**：适合浏览器查看，`generate_html_report()` 自包含（inline CSS + Chart.js CDN）

选择 Chart.js（而非 ECharts）是因为单个 JS 文件即可绘制雷达图和柱状图，不需要额外依赖管理。

### 中英双语标签

维度名称同时展示中文和英文，例如 `功能正确性 (Functional)`。原因是目标用户以中文为主，但技术评审可能看英文。标签映射硬编码在 `ReportGenerator` 中，不依赖 i18n 框架（考虑到报告是离线静态文件）。

### 进化报告特殊处理

`generate_evolution_report()` 根据 `AttributionReport` 的 improvement_rate / regression_rate 输出判定（改进/退化/持平），使用 `AttributionType` 枚举来保证一致性。

## 对外接口

- **被调用**: cli.py, commands/evolve_cli
- **调用**: eval/scoring, data/models, evolve/attribution

## 约定与模式

- HTML 报告是单文件，所有样式和脚本内联或 CDN
- 雷达图维度顺序与 `ScoreDimension` 枚举保持一致
- 报告生成器是无状态类，每次 `generate_*()` 接收所需数据

## 陷阱与已知问题

- Chart.js 依赖 CDN，离线环境需手动加载
- HTML 报告不含响应式设计，移动端显示效果差
- Markdown 报告使用简单表格，无嵌套或复杂排版

## 测试策略

- `test_report.py`：Markdown 输出格式验证
- `test_html_report.py`：HTML 结构验证（检查关键元素是否存在）
