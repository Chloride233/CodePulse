<script setup lang="ts">
import { onMounted } from "vue";
import { useDashboardStore } from "@/stores/dashboard";
import MetricCard from "@/components/MetricCard.vue";
import DimensionChart from "@/components/DimensionChart.vue";
import TrendChart from "@/components/TrendChart.vue";
import {
  PhChartLineUp as ChartLineUp,
  PhCheckCircle as CheckCircle,
  PhClock as Clock,
  PhCoins as Coins,
  PhListChecks as ListChecks,
  PhRocket as Rocket,
} from "@phosphor-icons/vue";

const store = useDashboardStore();

onMounted(() => {
  store.fetchOverview();
});
</script>

<template>
  <div class="page">
    <header class="page-header">
      <h1 class="page-title">总览</h1>
      <p class="page-subtitle">所有任务和 Agent 的评测指标概览。</p>
    </header>

    <div v-if="store.loading" class="loading-state">
      <div class="spinner"></div>
    </div>

    <div v-else-if="store.error" class="error-state">
      <p>{{ store.error }}</p>
      <button class="btn-primary" @click="store.fetchOverview">重试</button>
    </div>

    <template v-else-if="store.overview">
      <div class="metrics-grid">
        <MetricCard
          label="任务总数"
          :value="store.overview.total_tasks"
          :icon="ListChecks"
        />
        <MetricCard
          label="试运行次数"
          :value="store.overview.total_trials"
          :icon="Rocket"
        />
        <MetricCard
          label="通过率"
          :value="store.overview.overall_pass_rate"
          format="percent"
          :icon="CheckCircle"
          :accent="
            store.overview.overall_pass_rate >= 0.8
              ? 'success'
              : store.overview.overall_pass_rate >= 0.5
                ? 'warning'
                : 'error'
          "
        />
        <MetricCard
          label="平均得分"
          :value="store.overview.avg_score"
          format="score"
          :icon="ChartLineUp"
        />
        <MetricCard
          label="总花费"
          :value="store.overview.total_cost_usd"
          format="cost"
          :icon="Coins"
        />
        <MetricCard
          label="活跃 Agent"
          :value="store.overview.active_agents.length"
          :icon="Clock"
        />
      </div>

      <div class="charts-row">
        <section class="chart-card">
          <h2 class="section-title">维度得分</h2>
          <p class="section-desc">五个评测维度的平均得分。</p>
          <DimensionChart :scores="store.overview.dimension_scores" />
        </section>
        <section class="chart-card">
          <h2 class="section-title">近期得分</h2>
          <p class="section-desc">最近 10 次试运行结果。</p>
          <TrendChart :data="store.overview.recent_scores" />
        </section>
      </div>

      <section class="card">
        <h2 class="section-title">活跃 Agent</h2>
        <p class="section-desc">当前结果目录中跟踪的 Agent。</p>
        <div class="agent-table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th>Agent</th>
                <th>模型</th>
                <th>通过率</th>
                <th>平均 Token</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="agent in store.overview.active_agents" :key="agent.name">
                <td class="cell-mono">{{ agent.name }}</td>
                <td class="cell-secondary">{{ agent.model }}</td>
                <td>
                  <span class="pass-badge" :class="agent.pass_rate >= 0.8 ? 'pass' : 'fail'">
                    {{ (agent.pass_rate * 100).toFixed(1) }}%
                  </span>
                </td>
                <td class="cell-mono">{{ agent.avg_tokens.toLocaleString() }}</td>
              </tr>
              <tr v-if="store.overview.active_agents.length === 0">
                <td colspan="4" class="cell-empty">暂无 Agent 数据。</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </template>
  </div>
</template>

<style scoped>
.page {
  padding: 40px 48px;
  max-width: 1200px;
}

.page-header {
  margin-bottom: 40px;
}

.page-title {
  font-family: var(--apple-font-display);
  font-size: 40px;
  font-weight: 700;
  line-height: 1.08;
  letter-spacing: -0.02em;
  color: var(--apple-text);
}

.page-subtitle {
  margin-top: 8px;
  font-size: 17px;
  color: var(--apple-text-secondary);
  max-width: 65ch;
}

.metrics-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  margin-bottom: 32px;
}

.charts-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin-bottom: 32px;
}

.chart-card {
  background: var(--apple-surface);
  border-radius: var(--apple-radius);
  padding: 28px;
}

.card {
  background: var(--apple-surface);
  border-radius: var(--apple-radius);
  padding: 28px;
  margin-bottom: 32px;
}

.section-title {
  font-size: 20px;
  font-weight: 600;
  color: var(--apple-text);
  margin-bottom: 4px;
}

.section-desc {
  font-size: 14px;
  color: var(--apple-text-secondary);
  margin-bottom: 20px;
}

.agent-table-wrap {
  overflow-x: auto;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
}

.data-table th {
  text-align: left;
  padding: 10px 16px;
  font-weight: 500;
  color: var(--apple-text-secondary);
  border-bottom: 1px solid var(--apple-border);
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.data-table td {
  padding: 12px 16px;
  border-bottom: 1px solid var(--apple-border);
  color: var(--apple-text);
}

.data-table tr:last-child td {
  border-bottom: none;
}

.cell-mono {
  font-family: var(--apple-font-mono);
  font-size: 13px;
}

.cell-secondary {
  color: var(--apple-text-secondary);
}

.cell-empty {
  text-align: center;
  color: var(--apple-text-tertiary);
  padding: 24px !important;
}

.pass-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 500;
  font-family: var(--apple-font-mono);
}

.pass-badge.pass {
  background: color-mix(in srgb, var(--apple-success) 15%, transparent);
  color: var(--apple-success);
}

.pass-badge.fail {
  background: color-mix(in srgb, var(--apple-error) 15%, transparent);
  color: var(--apple-error);
}

.loading-state {
  display: flex;
  justify-content: center;
  padding: 80px 0;
}

.spinner {
  width: 32px;
  height: 32px;
  border: 3px solid var(--apple-border);
  border-top-color: var(--apple-accent);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.error-state {
  text-align: center;
  padding: 80px 0;
  color: var(--apple-error);
}

.error-state .btn-primary {
  margin-top: 16px;
}

.btn-primary {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 36px;
  padding: 0 20px;
  background: var(--apple-accent);
  color: #fff;
  font-family: var(--apple-font-body);
  font-size: 14px;
  font-weight: 500;
  border-radius: var(--apple-radius-sm);
  border: none;
  cursor: pointer;
  transition: background 0.15s ease;
}

.btn-primary:hover {
  background: var(--apple-accent-hover);
}

@media (max-width: 1024px) {
  .metrics-grid {
    grid-template-columns: repeat(2, 1fr);
  }
  .charts-row {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 640px) {
  .page {
    padding: 24px 16px;
  }
  .metrics-grid {
    grid-template-columns: 1fr;
  }
  .page-title {
    font-size: 32px;
  }
}
</style>
