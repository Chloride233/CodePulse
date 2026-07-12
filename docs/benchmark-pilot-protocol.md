# Benchmark Pilot 实验协议

状态：**已锁定，尚未执行**  
协议版本：`pilot-v1`  
锁定日期：2026-07-12  
关联 Issue：[GitHub Issue #2](https://github.com/Chloride233/CodePulse/issues/2)

## 1. 目标与边界

本 pilot 用低成本真实运行验证 CodePulse 能否公平比较两个 Code Agent 的正确性、稳定性、Token、成本、耗时和失败类型。实验规模固定为：

| 项目 | 固定值 |
|---|---:|
| Benchmark | HumanEval |
| 任务数 | 20 |
| Agent 数 | 2 |
| 每个 Agent 每任务运行次数 | 3 (`k = 3`) |
| 计划 Trial 总数 | 120 |

本阶段不扩展到 200 个任务，不运行第三个 Agent，不做参数搜索、Prompt 优化或付费 LLM-as-Judge。pilot 结束并完成成本复盘前，不批准大规模实验。

## 2. 固定任务集

任务集固定为 HumanEval 官方数据集中的以下 ID，按此顺序运行：

```text
HumanEval/0, HumanEval/1, HumanEval/2, HumanEval/3, HumanEval/4,
HumanEval/5, HumanEval/6, HumanEval/7, HumanEval/8, HumanEval/9,
HumanEval/10, HumanEval/11, HumanEval/12, HumanEval/13, HumanEval/14,
HumanEval/15, HumanEval/16, HumanEval/17, HumanEval/18, HumanEval/19
```

数据源必须是 OpenAI HumanEval 官方发布版。下载后生成只含上述任务、顺序不变的 JSONL 清单，并在首次运行前记录源文件与清单的 SHA-256。任一哈希变化均视为任务集变化，必须中止而非继续混跑。

`pilot-v1` 已固定并提交以下数据文件：

| 文件 | SHA-256 |
|---|---|
| `datasets/humaneval/HumanEval.jsonl.gz` | `b796127e635a67f93fb35c04f4cb03cf06f38c8072ee7cee8833d7bee06979ef` |
| `datasets/humaneval/pilot-v1.jsonl` | `fd18c50d5e6aa3a7908cbc71b009fcb2bc00f1e1ba3cea104cada60f1979f294` |

清单可由官方源文件确定性重建：

```bash
python scripts/download_humaneval.py --no-download
```

## 3. Agent 与冻结项

两个 Agent 均使用 CodePulse 的标准 Agent profile 接入，并使用完全相同的任务文本、工具权限和资源限制。Agent 的具体选择在首次付费调用前写入实验运行清单；以下字段缺一不可，写入后整个 pilot 禁止修改：

| 冻结项 | 要求 |
|---|---|
| Agent | profile 名称、profile 文件 SHA-256、实现类型、实现版本或 Git commit |
| 模型 | Provider、不可变模型版本 ID、API 返回的模型版本（如有） |
| Prompt | system prompt、任务模板及二者 SHA-256 |
| 推理参数 | `temperature = 0.0`、`max_tokens = 4096`、随机种子（Provider 支持时固定；不支持时记为 `unsupported`） |
| 工具 | 工具名称、实现版本、权限列表 |
| CodePulse | Git commit SHA；工作区必须干净 |
| 数据 | HumanEval 源文件 SHA-256、20 任务清单 SHA-256 |
| 环境 | `python:3.11-slim@sha256:e031123e3d85762b141ad1cbc56452ba69c6e722ebf2f042cc0dc86c47c0d8b3`、2 CPU、2048 MB、无网络、每 Trial 300 秒 |
| 依赖 | Python、pytest 及评测依赖的精确版本和 lockfile SHA-256 |

不接受 `latest` 或无法验证底层版本的模型别名。仓库当前的 `deepseek/deepseek-chat` 只能作为候选；若 Provider 不能证明其在 120 次 Trial 内指向同一版本，则不得用于本 pilot。第二个真实 Agent profile 尚未入库，因此协议锁定不代表已经满足开跑条件。

每个 Trial 使用全新容器和干净工作区。Agent 运行顺序按“任务 → trial 序号 → Agent”交错，以降低时间段和服务负载偏差；Agent 先后顺序用固定种子 `20260712` 预先生成并随运行清单保存。失败 Trial 不重试，避免选择性重跑改变结果。

## 4. 成功判定与指标

单次 Trial 仅在隔离环境内全部官方测试通过时记为成功。超时、基础设施错误或 API 错误均记为失败并进入失败分类，不从分母剔除。所有指标分别按 Agent 汇总，原始 Trial 记录必须保留。

设任务数 `T = 20`，每任务运行次数 `n = k = 3`，任务 `i` 的成功次数为 `c_i`：

- **pass@1**：`(1/T) * sum(c_i / n)`。
- **pass@3**：`(1/T) * sum(1 - C(n-c_i, 3) / C(n, 3))`，即三次中至少成功一次的任务比例。
- **pass^3**：`(1/T) * sum(1[c_i = 3])`，即三次全部成功的任务比例。
- **Token**：每 Trial 的输入、输出、缓存和总 Token；报告总量、均值和 P95。
- **成本**：按实际 Provider 账单口径记录每 Trial USD，报告总成本和平均每 Trial/每任务成本。价格表版本和抓取日期写入运行清单。
- **耗时**：从任务提交到 Agent 结束的端到端 wall-clock 秒数，包含模型和工具时间；报告全部 Trial 的 P50/P95。
- **失败类型**：报告次数及占比，每个失败只能有一个主类型。

百分位使用 nearest-rank：排序后 P50 取第 `ceil(0.50N)` 个值，P95 取第 `ceil(0.95N)` 个值。Agent 间除汇总值外，还报告相同任务上的逐任务差异；pilot 样本较小，不宣称统计显著性。

失败主类型固定为：

| 类型 | 判定 |
|---|---|
| `wrong_answer` | 代码可执行，但官方测试失败 |
| `syntax_or_build_error` | 语法、导入或构建失败 |
| `timeout` | 超过 300 秒 |
| `agent_error` | Agent/工具协议、解析或进程异常 |
| `provider_error` | 限流、鉴权、模型服务或内容过滤错误 |
| `sandbox_error` | 容器、资源或环境准备失败 |
| `no_submission` | Agent 未产生可评测提交 |

若一个 Trial 同时满足多类，按根因优先序 `sandbox_error` → `provider_error` → `agent_error` → `no_submission` → `timeout` → `syntax_or_build_error` → `wrong_answer` 人工复核。原始错误信息另存，不新增临时类别；无法归类时使用 `agent_error` 并记录复核备注。

## 5. 预算上限与中止条件

预算是硬限制，不是目标：

| 限制 | 上限 |
|---|---:|
| pilot 总实际成本 | USD 20.00 |
| 单个 Agent 成本 | USD 10.00 |
| 单 Trial 成本 | USD 0.20 |
| 单 Trial wall-clock | 300 秒 |
| Trial 总数 | 120 |

先执行不计费的配置校验和每个 Agent 1 个任务的 smoke test；任何付费 smoke test 也计入 USD 20.00 总预算。满足以下任一条件立即停止提交新 Trial，保留已有结果并标记实验为 `aborted`：

1. 累计实际成本达到 USD 20.00，或任一 Agent 达到 USD 10.00。
2. 任一 Trial 达到 USD 0.20；先停止该 Agent，并复核计费与 Token 限制。
3. 按已完成 Trial 均价预测的总成本超过 USD 20.00，或成本数据无法采集。
4. 连续 3 次 `provider_error`、`agent_error` 或 `sandbox_error`。
5. 完成至少 10 个 Trial 后，非任务质量类故障（`provider_error`、`agent_error`、`sandbox_error`）超过 10%。
6. 发现模型、Prompt、任务、镜像、依赖、工具权限或 CodePulse commit 与运行清单不一致。
7. Provider 无法确认模型版本未漂移，或出现异常限流/服务降级，影响 Agent 间公平性。
8. 用户手动中止。

中止后不得只补跑失败项。修复原因后必须创建新实验 ID，并从 120 个 Trial 全量重跑；旧结果保留为无效/中止批次，不与新批次合并。

## 6. 开跑门禁与产出

首次正式运行前必须全部满足：

- [ ] 两个真实 Agent profile 已确定并提交，模型为可验证的固定版本。
- [ ] Prompt、profile、数据文件、任务清单和 lockfile 的 SHA-256 已写入运行清单。
- [x] Docker 基础镜像以 digest 固定，评测镜像已在无网络、2 CPU、2048 MB 限制下验证。
- [x] 成本采集字段和中止逻辑通过无付费 mock 测试。
- [ ] 预算获得人工确认。

运行清单使用 JSON，顶层必须包含 `protocol_version`、`benchmark`、`task_ids`、`n_trials`、`seed`、`agents`、`dataset`、`dependencies`、`codepulse_commit`、`environment` 和 `budget`。每个 Agent 必须记录 profile 路径及 SHA-256、Provider、不可变模型版本和 Provider 实际返回的模型版本；数据集、20 任务清单和 lockfile 必须同时记录路径与 SHA-256。

任何付费调用前先执行纯离线门禁：

```bash
codepulse benchmark preflight \
  --manifest experiments/pilot-v1/manifest.json \
  --repo-root .
```

命令必须输出 `Pilot preflight passed` 才能进入 smoke test。它会拒绝可漂移模型别名、错误任务范围、非 3 次运行、缺失或不匹配的文件哈希、非完整 Git SHA、未以 digest 固定的镜像，以及偏离协议的资源和预算配置。preflight 通过只证明配置冻结，不代表实验已经运行。

本地评测镜像 `codepulse-eval:pilot-v1` 构建 ID 为 `sha256:fcb59a48cd9017b030ebb32f2a7cddfba839b26c7137d3be16b60f986a919396`。离线容器实测版本为 Python 3.11.15、pytest 9.1.1、ruff 0.15.21、mypy 2.2.0 和 bandit 1.9.4；这些工具版本已固定在 `Dockerfile.eval`。该 ID 只作为当前机器构建证据，正式 manifest 仍须记录可由运行环境解析的镜像 digest。

正式产出包括运行清单、120 条原始 Trial JSONL、失败复核记录，以及包含 pass@1、pass@3、pass^3、Token、成本、P50/P95 耗时和失败分布的 Markdown/HTML 报告。本协议只锁定实验设计；不会在本次文档变更中启动任何实验。

## 7. pilot 后决策

只有 pilot 完整结束、成本数据可信且非任务质量类故障不超过 10% 时，才评估是否扩展。扩展到 200 任务 × 3 Agent × 3 次必须另建协议版本和预算审批，不由本协议自动授权。

## 8. 简历证据记录

当前可核验的证据仅限实验设计阶段：为 20 个 HumanEval 任务、2 个 Agent、每任务 3 次运行（计划 120 个 Trial）制定了可复现实验协议，统一定义 pass@1、pass@3、pass^3、Token、成本、P50/P95 耗时和 7 类失败归因，并设置 USD 20 总预算及模型、数据、Prompt、依赖和容器哈希门禁。

已实现可复现门禁命令 `codepulse benchmark preflight`，用确定性测试证明合法 manifest 可通过，并能拒绝可漂移模型版本与被篡改的 profile 哈希；该能力不产生模型调用费用。

在 120 条真实 Trial 和报告落盘前，不把该计划规模、对比结果或指标写成已完成实验成果。后续运行证据必须在此补充实验 ID、CodePulse commit、运行清单路径、实际规模、核心结果、报告路径和复现命令。
