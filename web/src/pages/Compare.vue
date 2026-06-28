<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { request } from "@/composables/useApi";
import { formatNumber, formatDuration, formatCost, formatPercent } from "@/lib/utils";
import VChart from "vue-echarts";
import { use } from "echarts/core";
import { BarChart } from "echarts/charts";
import { GridComponent, TooltipComponent, LegendComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";

use([BarChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer]);

interface AgentComparison {
  agent_name: string;
  n_success: number;
  n_total: number;
  pass_at_1: number;
  pass_at_k: number;
  pass_hat_k: number;
  avg_tokens: number;
  avg_duration: number;
  avg_cost: number;
  self_correction_rate: number;
}

const agents = ref<AgentComparison[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);

const chartOption = computed(() => {
  if (agents.value.length === 0) return {};
  const names = agents.value.map((a) => a.agent_name);
  const passRates = agents.value.map((a) => Math.round(a.pass_at_1 * 1000) / 10);
  const scRates = agents.value.map((a) => Math.round(a.self_correction_rate * 1000) / 10);

  return {
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
      formatter: (params: unknown) => {
        const items = params as Array<{ seriesName: string; value: number; marker: string; dataIndex: number }>;
        if (!Array.isArray(items) || !items.length) return "";
        const idx = items[0].dataIndex;
        let html = `<b>${names[idx] ?? ""}</b><br/>`;
        for (const item of items) {
          html += `${item.marker} ${item.seriesName}: <b>${item.value}%</b><br/>`;
        }
        return html;
      },
    },
    legend: {
      data: ["通过率", "自纠正率"],
      bottom: 0,
      textStyle: { color: "#86868b", fontSize: 11 },
    },
    grid: { left: 16, right: 16, top: 16, bottom: 40, containLabel: true },
    xAxis: {
      type: "category",
      data: names,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: "#86868b", fontSize: 11 },
    },
    yAxis: {
      type: "value",
      max: 100,
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { lineStyle: { color: "#d2d2d7", type: "dashed" } },
      axisLabel: { color: "#86868b", fontSize: 11, formatter: "{value}%" },
    },
    series: [
      {
        name: "通过率",
        type: "bar",
        data: passRates,
        itemStyle: { color: "#0071e3", borderRadius: [4, 4, 0, 0] },
        barWidth: "30%",
      },
      {
        name: "自纠正率",
        type: "bar",
        data: scRates,
        itemStyle: { color: "#ff9500", borderRadius: [4, 4, 0, 0] },
        barWidth: "30%",
      },
    ],
  };
});

async function fetchCompare() {
  loading.value = true;
  error.value = null;
  try {
    const data = await request<{ agents: AgentComparison[] }>("/compare");
    agents.value = data.agents;
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    loading.value = false;
  }
}

onMounted(fetchCompare);
</script>

<template>
  <div class="page">
    <header class="page-header">
      <h1 class="page-title">对比</h1>
      <p class="page-subtitle">多 Agent 性能横向对比。</p>
    </header>

    <div v-if="loading" class="loading-state">
      <div class="spinner"></div>
    </div>

    <div v-else-if="error" class="error-state">
      <p>{{ error }}</p>
      <button class="btn-primary" @click="fetchCompare">重试</button>
    </div>

    <template v-else>
      <section v-if="agents.length > 0" class="card">
        <h2 class="section-title">性能概览</h2>
        <div class="chart-container">
          <v-chart :option="chartOption" autoresize />
        </div>
      </section>

      <section class="card">
        <h2 class="section-title">Agent 指标</h2>
        <p class="section-desc">各 Agent 在所有任务上的详细指标。</p>
        <div class="table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th>Agent</th>
                <th>Pass @1</th>
                <th>Pass ^k</th>
                <th>平均 Token</th>
                <th>平均耗时</th>
                <th>平均花费</th>
                <th>自纠正率</th>
                <th>试运行</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="agent in agents" :key="agent.agent_name">
                <td class="cell-mono">{{ agent.agent_name }}</td>
                <td>
                  <span
                    class="pass-badge"
                    :class="agent.pass_at_1 >= 0.8 ? 'pass' : agent.pass_at_1 > 0 ? 'partial' : 'fail'"
                  >
                    {{ formatPercent(agent.pass_at_1) }}
                  </span>
                </td>
                <td class="cell-mono">{{ formatPercent(agent.pass_hat_k) }}</td>
                <td class="cell-mono">{{ formatNumber(agent.avg_tokens) }}</td>
                <td>{{ formatDuration(agent.avg_duration) }}</td>
                <td class="cell-mono">{{ formatCost(agent.avg_cost) }}</td>
                <td class="cell-mono">{{ agent.self_correction_rate.toFixed(2) }}</td>
                <td class="cell-mono">{{ agent.n_success }}/{{ agent.n_total }}</td>
              </tr>
              <tr v-if="agents.length === 0">
                <td colspan="8" class="cell-empty">暂无对比数据。</td>
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
  margin-bottom: 32px;
}

.page-title {
  font-family: var(--apple-font-display);
  font-size: 40px;
  font-weight: 700;
  line-height: 1.08;
  letter-spacing: -0.02em;
}

.page-subtitle {
  margin-top: 8px;
  font-size: 17px;
  color: var(--apple-text-secondary);
}

.card {
  background: var(--apple-surface);
  border-radius: var(--apple-radius);
  padding: 28px;
  margin-bottom: 24px;
}

.section-title {
  font-size: 20px;
  font-weight: 600;
  margin-bottom: 4px;
}

.section-desc {
  font-size: 14px;
  color: var(--apple-text-secondary);
  margin-bottom: 20px;
}

.chart-container {
  width: 100%;
  height: 280px;
}

.table-wrap {
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
}

.data-table tr:last-child td {
  border-bottom: none;
}

.cell-mono {
  font-family: var(--apple-font-mono);
  font-size: 13px;
}

.cell-empty {
  text-align: center;
  color: var(--apple-text-tertiary);
  padding: 32px !important;
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

.pass-badge.partial {
  background: color-mix(in srgb, var(--apple-warning) 15%, transparent);
  color: var(--apple-warning);
}

.pass-badge.fail {
  background: color-mix(in srgb, var(--apple-error) 15%, transparent);
  color: var(--apple-error);
}

.btn-primary {
  display: inline-flex;
  align-items: center;
  height: 36px;
  padding: 0 20px;
  background: var(--apple-accent);
  color: #fff;
  font-size: 14px;
  font-weight: 500;
  border-radius: var(--apple-radius-sm);
  border: none;
  cursor: pointer;
  margin-top: 12px;
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
  to { transform: rotate(360deg); }
}

.error-state {
  text-align: center;
  padding: 80px 0;
  color: var(--apple-error);
}

@media (max-width: 768px) {
  .page { padding: 24px 16px; }
  .page-title { font-size: 32px; }
}
</style>
