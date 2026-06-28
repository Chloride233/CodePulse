<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { request } from "@/composables/useApi";
import { PhTrendUp as TrendUp, PhTrendDown as TrendDown, PhMinus as Minus } from "@phosphor-icons/vue";
import VChart from "vue-echarts";
import { use } from "echarts/core";
import { LineChart } from "echarts/charts";
import { GridComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";

use([LineChart, GridComponent, TooltipComponent, CanvasRenderer]);

interface EvolutionEpoch {
  epoch: number;
  baseline_score: number;
  candidate_score: number;
  improved: boolean;
  improvements: number;
  regressions: number;
  persistent_failures: number;
  stable_successes: number;
  edits_applied: number;
  edits_rejected: number;
}

const epochs = ref<EvolutionEpoch[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);

const chartOption = computed(() => {
  if (epochs.value.length === 0) return {};
  const labels = epochs.value.map((e) => `第 ${e.epoch} 轮`);
  const baseline = epochs.value.map((e) => Math.round(e.baseline_score * 100) / 100);
  const candidate = epochs.value.map((e) => Math.round(e.candidate_score * 100) / 100);

  return {
    tooltip: {
      trigger: "axis",
      formatter: (params: unknown) => {
        const p = params as Array<Array<{ dataIndex: number }>>;
        if (!p.length) return "";
        const idx = p[0][0]?.dataIndex ?? 0;
        const ep = epochs.value[idx];
        return [
          `<b>第 ${ep.epoch} 轮</b>`,
          `基线: ${ep.baseline_score.toFixed(2)}`,
          `候选: ${ep.candidate_score.toFixed(2)}`,
          `是否提升: ${ep.improved ? "是" : "否"}`,
          `编辑: ${ep.edits_applied} 采纳, ${ep.edits_rejected} 拒绝`,
        ].join("<br/>");
      },
    },
    legend: {
      data: ["基线", "候选"],
      bottom: 0,
      textStyle: { color: "#86868b", fontSize: 11 },
    },
    grid: { left: 16, right: 16, top: 16, bottom: 40, containLabel: true },
    xAxis: {
      type: "category",
      data: labels,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: "#86868b", fontSize: 11 },
    },
    yAxis: {
      type: "value",
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { lineStyle: { color: "#d2d2d7", type: "dashed" } },
      axisLabel: { color: "#86868b", fontSize: 11 },
    },
    series: [
      {
        name: "基线",
        type: "line",
        data: baseline,
        smooth: true,
        lineStyle: { color: "#86868b", width: 2, type: "dashed" },
        itemStyle: { color: "#86868b" },
        symbol: "circle",
        symbolSize: 6,
      },
      {
        name: "候选",
        type: "line",
        data: candidate,
        smooth: true,
        lineStyle: { color: "#0071e3", width: 2 },
        itemStyle: { color: "#0071e3" },
        symbol: "circle",
        symbolSize: 6,
        areaStyle: {
          color: {
            type: "linear",
            x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: "rgba(0,113,227,0.1)" },
              { offset: 1, color: "rgba(0,113,227,0)" },
            ],
          },
        },
      },
    ],
  };
});

const summaryStats = computed(() => {
  if (epochs.value.length === 0) return null;
  const totalImproved = epochs.value.filter((e) => e.improved).length;
  const totalEditsApplied = epochs.value.reduce((s, e) => s + e.edits_applied, 0);
  const totalEditsRejected = epochs.value.reduce((s, e) => s + e.edits_rejected, 0);
  const firstBaseline = epochs.value[0]?.baseline_score ?? 0;
  const lastCandidate = epochs.value[epochs.value.length - 1]?.candidate_score ?? 0;
  return {
    totalEpochs: epochs.value.length,
    totalImproved,
    totalEditsApplied,
    totalEditsRejected,
    netImprovement: lastCandidate - firstBaseline,
  };
});

async function fetchEvolution() {
  loading.value = true;
  error.value = null;
  try {
    const data = await request<{ epochs: EvolutionEpoch[] }>("/evolution");
    epochs.value = data.epochs;
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    loading.value = false;
  }
}

onMounted(fetchEvolution);
</script>

<template>
  <div class="page">
    <header class="page-header">
      <h1 class="page-title">进化</h1>
      <p class="page-subtitle">SkillOpt 自进化轨迹和逐轮结果。</p>
    </header>

    <div v-if="loading" class="loading-state">
      <div class="spinner"></div>
    </div>

    <div v-else-if="error" class="error-state">
      <p>{{ error }}</p>
      <button class="btn-primary" @click="fetchEvolution">重试</button>
    </div>

    <template v-else-if="summaryStats">
      <div class="summary-grid">
        <div class="summary-card">
          <span class="summary-label">总轮次</span>
          <span class="summary-value">{{ summaryStats.totalEpochs }}</span>
        </div>
        <div class="summary-card">
          <span class="summary-label">提升轮次</span>
          <span class="summary-value text-success">{{ summaryStats.totalImproved }}</span>
        </div>
        <div class="summary-card">
          <span class="summary-label">采纳编辑</span>
          <span class="summary-value">{{ summaryStats.totalEditsApplied }}</span>
        </div>
        <div class="summary-card">
          <span class="summary-label">拒绝编辑</span>
          <span class="summary-value text-warning">{{ summaryStats.totalEditsRejected }}</span>
        </div>
        <div class="summary-card">
          <span class="summary-label">净提升</span>
          <span class="summary-value" :class="summaryStats.netImprovement >= 0 ? 'text-success' : 'text-error'">
            {{ summaryStats.netImprovement >= 0 ? "+" : "" }}{{ (summaryStats.netImprovement * 100).toFixed(1) }}%
          </span>
        </div>
      </div>

      <section class="card">
        <h2 class="section-title">得分轨迹</h2>
        <p class="section-desc">基线 vs 候选得分的进化曲线。</p>
        <div class="chart-container">
          <v-chart :option="chartOption" autoresize />
        </div>
      </section>

      <section class="card">
        <h2 class="section-title">逐轮详情</h2>
        <p class="section-desc">每轮的编辑数和归因分布。</p>
        <div class="table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th>轮次</th>
                <th>状态</th>
                <th>基线</th>
                <th>候选</th>
                <th>变化</th>
                <th>采纳</th>
                <th>拒绝</th>
                <th>归因</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="ep in epochs" :key="ep.epoch">
                <td class="cell-mono">{{ ep.epoch }}</td>
                <td>
                  <component
                    :is="ep.improved ? TrendUp : TrendDown"
                    :size="16"
                    :class="ep.improved ? 'icon-success' : 'icon-error'"
                  />
                </td>
                <td class="cell-mono">{{ (ep.baseline_score * 100).toFixed(1) }}</td>
                <td class="cell-mono">{{ (ep.candidate_score * 100).toFixed(1) }}</td>
                <td>
                  <span
                    class="delta-value"
                    :class="ep.candidate_score >= ep.baseline_score ? 'text-success' : 'text-error'"
                  >
                    {{ ep.candidate_score >= ep.baseline_score ? "+" : "" }}{{ ((ep.candidate_score - ep.baseline_score) * 100).toFixed(1) }}
                  </span>
                </td>
                <td class="cell-mono">{{ ep.edits_applied }}</td>
                <td class="cell-mono">{{ ep.edits_rejected }}</td>
                <td>
                  <div class="attribution-bar">
                    <span class="attr-segment attr-improve" :style="{ flex: ep.improvements }" :title="`改进: ${ep.improvements}`"></span>
                    <span class="attr-segment attr-regress" :style="{ flex: ep.regressions }" :title="`退化: ${ep.regressions}`"></span>
                    <span class="attr-segment attr-persist" :style="{ flex: ep.persistent_failures }" :title="`持续失败: ${ep.persistent_failures}`"></span>
                    <span class="attr-segment attr-stable" :style="{ flex: ep.stable_successes }" :title="`稳定成功: ${ep.stable_successes}`"></span>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="legend-row">
          <span class="legend-item"><span class="legend-dot attr-improve"></span> 改进</span>
          <span class="legend-item"><span class="legend-dot attr-regress"></span> 退化</span>
          <span class="legend-item"><span class="legend-dot attr-persist"></span> 持续失败</span>
          <span class="legend-item"><span class="legend-dot attr-stable"></span> 稳定成功</span>
        </div>
      </section>
    </template>

    <div v-else class="empty-state">
      <p>暂无进化数据。运行 SkillOpt 进化后结果将显示在此处。</p>
    </div>
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

.summary-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 12px;
  margin-bottom: 24px;
}

.summary-card {
  background: var(--apple-surface);
  border-radius: var(--apple-radius);
  padding: 16px 20px;
  text-align: center;
}

.summary-label {
  display: block;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--apple-text-secondary);
  margin-bottom: 6px;
}

.summary-value {
  font-family: var(--apple-font-display);
  font-size: 24px;
  font-weight: 700;
}

.text-success { color: var(--apple-success); }
.text-warning { color: var(--apple-warning); }
.text-error { color: var(--apple-error); }

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

.icon-success { color: var(--apple-success); }
.icon-error { color: var(--apple-error); }

.delta-value {
  font-family: var(--apple-font-mono);
  font-size: 13px;
  font-weight: 500;
}

.attribution-bar {
  display: flex;
  height: 8px;
  border-radius: 4px;
  overflow: hidden;
  min-width: 80px;
}

.attr-segment {
  min-width: 0;
}

.attr-improve { background: var(--apple-success); }
.attr-regress { background: var(--apple-error); }
.attr-persist { background: var(--apple-warning); }
.attr-stable { background: var(--apple-accent); }

.legend-row {
  display: flex;
  gap: 16px;
  margin-top: 16px;
  flex-wrap: wrap;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--apple-text-secondary);
}

.legend-dot {
  width: 8px;
  height: 8px;
  border-radius: 2px;
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

.empty-state {
  text-align: center;
  padding: 80px 0;
  color: var(--apple-text-tertiary);
  font-size: 15px;
}

@media (max-width: 1024px) {
  .summary-grid {
    grid-template-columns: repeat(3, 1fr);
  }
}

@media (max-width: 640px) {
  .page { padding: 24px 16px; }
  .summary-grid {
    grid-template-columns: repeat(2, 1fr);
  }
  .page-title { font-size: 32px; }
}
</style>
