# web — Vue.js 评测仪表板前端

## 职责边界

提供评测结果的可视化仪表板。**只管**前端 UI 和数据展示，**不管**评测逻辑和数据存储（通过 API 读取）。

## 技术栈

| 技术 | 版本 | 用途 |
|------|------|------|
| Vue | 3.x | 响应式 UI 框架 |
| TypeScript | 5.x | 类型安全 |
| Vite | 5.x | 构建工具和 dev server |
| Tailwind CSS | 4.x | 原子化样式 |
| Pinia | 2.x | 状态管理 |
| Vue Router | 4.x | SPA 路由 |
| ECharts | 5.x | 数据图表（雷达图、柱状图）|

## 关键设计决策

### ECharts 而非 Chart.js

前端使用 ECharts（而非后端报告中的 Chart.js），因为：
- ECharts 支持更多图表类型（仪表盘、热力图）
- 中文本地化更好
- Vue 集成有官方 `vue-echarts` 包装

### Pinia 而非 Vuex

使用 Pinia 作为状态管理，因为 Vue 3 官方推荐，且 TypeScript 支持优于 Vuex。

### Tailwind CSS v4

使用最新 v4 版本，基于 CSS 变量配置主题，支持暗色模式。

## 约定与模式

- 开发时 API 代理到 `http://localhost:8000`（FastAPI 默认端口）
- 组件遵循 Vue SFC（Single File Component）模式
- 颜色主题与 CodePulse CLI 的 dark cyan/blue 风格一致

## 陷阱与已知问题

- 生产构建时需要配置 API 基础 URL（当前硬编码代理）
- ECharts 体积较大，未做按需加载
- 未做响应式设计——桌面端优先

## 目录结构

```
web/
├── src/
│   ├── assets/       # 静态资源
│   ├── components/   # Vue 组件
│   ├── stores/       # Pinia stores
│   ├── views/        # 路由页面
│   ├── App.vue       # 根组件
│   └── main.ts       # 入口
├── index.html
├── vite.config.ts
├── tsconfig.json
└── package.json
```

## 测试策略

- 当前无前端测试（需补充）
- 推荐方案：Playwright E2E + Vitest 单元测试
