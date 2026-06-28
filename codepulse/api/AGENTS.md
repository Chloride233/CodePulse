# api — REST API + Dashboard 后端

## 职责边界

为 Web 前端提供 REST API，从 results 目录读取评测结果并返回 JSON。**只管** HTTP 路由和数据读取，**不管**评测执行、结果写入的数据结构（读取方遵循 data 层定义）。

## 关键设计决策

### results_dir 三级解析优先级

```
query param > app.state.results_dir > 默认路径
```

1. 请求级：`GET /api/overview?results_dir=/custom/path`（调试用）
2. 应用级：`create_app(results_dir=...)` 或环境变量 `CODEPULSE_RESULTS_DIR`
3. 默认：`results/`（相对于工作目录）

这种设计允许同一 API 实例在不同上下文中查看不同评测结果，无需重启。

### FastAPI 路由模块化

5 个独立 router 文件：
- `overview.py`：仪表板总览（任务数/通过率/平均分/维度分/活跃 Agent）
- `evaluations.py`：任务列表和详细 trial 数据
- `compare.py`：多 Agent 对比数据
- `traces.py`：单 trial 的 Trace 事件流
- `evolution.py`：进化周期数据

每个 router 独立于其他，可单独禁用或替换。

### CORS 配置

`create_app()` 默认允许 Vue dev server（`http://localhost:5173`），生产部署时需要调整为实际域名。

### Pydantic v2 响应模型

所有 API 响应使用 Pydantic v2 BaseModel，冻结不可变。Schema 定义在 `schemas.py` 中，与数据层的 dataclass 模型有映射但不共用——API schema 可以添加计算字段。

## 对外接口

- **被调用**: web/ (Vue 前端), 外部 HTTP 客户端
- **调用**: 无内部模块依赖（纯文件读取），读取 `results/` 目录

## 约定与模式

- 启动命令：`uvicorn codepulse.api.main:app --reload`
- `deps.py` 使用 FastAPI 依赖注入模式
- 数据读取函数（`load_all_summaries`, `load_task_trials`）无状态，每次请求重新读取

## 陷阱与已知问题

- 未做分页——大量 trial 数据时单次请求载荷大
- 无认证机制（开发阶段）
- 对 results 目录结构有约定（`results/{task_id}/summary.json`, `trial-*.jsonl`），结构不符时返回空而非报错
- 文件读取在每个请求中重新执行，无内存缓存

## 测试策略

- `test_api.py`：FastAPI TestClient 集成测试
- 测试使用临时 results 目录，不依赖真实评测输出
