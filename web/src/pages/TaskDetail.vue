<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import { request } from "@/composables/useApi";
import {
  formatPercent,
  formatScore,
  formatNumber,
  formatDuration,
  formatCost,
  scoreColor,
  difficultyColor,
  DIMENSION_LABELS,
  DIMENSION_MAX,
} from "@/lib/utils";
import { PhArrowLeft as ArrowLeft, PhCheckCircle as CheckCircle, PhXCircle as XCircle, PhWarning as Warning } from "@phosphor-icons/vue";

const CATEGORY_LABELS: Record<string, string> = {
  bug_fix: "缺陷修复",
  feature: "功能开发",
  refactor: "重构",
  code_review: "代码审查",
};

const DIFFICULTY_LABELS: Record<string, string> = {
  easy: "简单",
  medium: "中等",
  hard: "困难",
};

interface TrialData {
  trial_id: string;
  task_id: string;
  agent_config: { name: string; model: string; temperature: number; max_tokens: number };
  outcome: Record<string, unknown>;
  scores: Record<string, number>;
  metrics: {
    total_tokens: number;
    input_tokens: number;
    output_tokens: number;
    cache_tokens: number;
    total_duration: number;
    tool_call_count: number;
    self_correction_count: number;
    cost_usd: number;
  };
  success: boolean;
  total_score: number;
}

interface TaskDetailData {
  task_id: string;
  source: string;
  category: string;
  difficulty: string;
  language: string;
  n_trials: number;
  pass_rate: number;
  avg_score: number;
  trials: TrialData[];
}

interface Blackhole {
  blackhole_type: string;
  details: Record<string, unknown>;
}

const BH_LABELS: Record<string, string> = {
  loop_trial: "循环试错",
  context_bloat: "上下文膨胀",
};

const route = useRoute();
const router = useRouter();
const task = ref<TaskDetailData | null>(null);
const blackholes = ref<Blackhole[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);
const selectedTrial = ref<string | null>(null);

const selectedTrialData = computed(() => {
  if (!task.value || !selectedTrial.value) return null;
  return task.value.trials.find((t) => t.trial_id === selectedTrial.value) ?? null;
});

const dimAverages = computed(() => {
  const result: Record<string, number> = {};
  if (!task.value || task.value.trials.length === 0) return result;
  for (const dim of Object.keys(DIMENSION_LABELS)) {
    const sum = task.value.trials.reduce((acc, t) => acc + (t.scores[dim] ?? 0), 0);
    result[dim] = sum / task.value.trials.length;
  }
  return result;
});

function dimBarWidth(dim: string | number): string {
  const avg = dimAverages.value[String(dim)] ?? 0;
  return `${avg * 100}%`;
}

function dimScoreDisplay(dim: string | number): string {
  const key = String(dim);
  const avg = dimAverages.value[key] ?? 0;
  const max = DIMENSION_MAX[key] ?? 10;
  return `${(avg * max).toFixed(1)}/${max}`;
}

async function fetchData() {
  const id = route.params.id as string;
  loading.value = true;
  error.value = null;
  try {
    const [taskResult, bhResult] = await Promise.allSettled([
      request<TaskDetailData>(`/tasks/${id}`),
      request<Blackhole[]>(`/tasks/${id}/blackholes`),
    ]);
    if (taskResult.status === "rejected") {
      throw taskResult.reason;
    }
    task.value = taskResult.value;
    blackholes.value = bhResult.status === "fulfilled" ? bhResult.value : [];
    if (task.value.trials.length > 0) {
      selectedTrial.value = task.value.trials[0].trial_id;
    }
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    loading.value = false;
  }
}

onMounted(fetchData);
</script>

<template>
  <div class="page">
    <button class="back-btn" @click="router.push('/tasks')">
      <ArrowLeft :size="16" />
      返回任务列表
    </button>

    <div v-if="loading" class="loading-state">
      <div class="spinner"></div>
    </div>

    <div v-else-if="error" class="error-state">
      <p>{{ error }}</p>
      <button class="btn-primary" @click="fetchData">重试</button>
    </div>

    <template v-else-if="task">
      <header class="task-header">
        <div class="task-header-left">
          <h1 class="task-id">{{ task.task_id }}</h1>
          <div class="task-meta">
            <span class="tag">{{ task.source }}</span>
            <span class="tag">{{ CATEGORY_LABELS[task.category] ?? task.category }}</span>
            <span class="difficulty-tag" :style="{ color: difficultyColor(task.difficulty) }">
              {{ DIFFICULTY_LABELS[task.difficulty] ?? task.difficulty }}
            </span>
            <span class="lang-tag">{{ task.language }}</span>
          </div>
        </div>
        <div class="task-header-right">
          <div class="stat-block">
            <span class="stat-label">通过率</span>
            <span class="stat-value" :class="task.pass_rate >= 0.8 ? 'text-success' : 'text-error'">
              {{ formatPercent(task.pass_rate) }}
            </span>
          </div>
          <div class="stat-block">
            <span class="stat-label">平均分</span>
            <span class="stat-value">{{ formatScore(task.avg_score / 100) }}</span>
          </div>
          <div class="stat-block">
            <span class="stat-label">试运行</span>
            <span class="stat-value">{{ task.n_trials }}</span>
          </div>
        </div>
      </header>

      <div v-if="blackholes.length > 0" class="alert-card">
        <div class="alert-header">
          <Warning :size="18" class="alert-icon" />
          <span class="alert-title">检测到 Token 黑洞</span>
        </div>
        <div v-for="(bh, i) in blackholes" :key="i" class="alert-item">
          <span class="alert-type">{{ BH_LABELS[bh.blackhole_type] ?? bh.blackhole_type }}</span>
          <span class="alert-detail">{{ JSON.stringify(bh.details) }}</span>
        </div>
      </div>

      <section class="card">
        <h2 class="section-title">维度得分</h2>
        <p class="section-desc">五个评测维度的平均得分。</p>
        <div class="dimension-bars">
          <div v-for="(label, dim) in DIMENSION_LABELS" :key="dim" class="dim-row">
            <span class="dim-label">{{ label }}</span>
            <div class="dim-bar-track">
              <div
                class="dim-bar-fill"
                :style="{
                  width: dimBarWidth(dim),
                  background: scoreColor(dimAverages[dim] ?? 0),
                }"
              ></div>
            </div>
            <span class="dim-value" :style="{ color: scoreColor(dimAverages[dim] ?? 0) }">
              {{ dimScoreDisplay(dim) }}
            </span>
          </div>
        </div>
      </section>

      <section class="card">
        <h2 class="section-title">试运行记录</h2>
        <p class="section-desc">点击行查看详情。</p>
        <table class="data-table">
          <thead>
            <tr>
              <th>试运行</th>
              <th>状态</th>
              <th>得分</th>
              <th>Token</th>
              <th>耗时</th>
              <th>花费</th>
              <th>自纠正</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="trial in task.trials"
              :key="trial.trial_id"
              class="table-row"
              :class="{ selected: selectedTrial === trial.trial_id }"
              @click="selectedTrial = trial.trial_id"
            >
              <td class="cell-mono">{{ trial.trial_id }}</td>
              <td>
                <component
                  :is="trial.success ? CheckCircle : XCircle"
                  :size="16"
                  :class="trial.success ? 'icon-success' : 'icon-error'"
                />
              </td>
              <td>
                <span class="score-value" :style="{ color: scoreColor(trial.total_score / 100) }">
                  {{ trial.total_score.toFixed(1) }}
                </span>
              </td>
              <td class="cell-mono">{{ formatNumber(trial.metrics.total_tokens) }}</td>
              <td>{{ formatDuration(trial.metrics.total_duration) }}</td>
              <td class="cell-mono">{{ formatCost(trial.metrics.cost_usd) }}</td>
              <td class="cell-mono">{{ trial.metrics.self_correction_count }}</td>
            </tr>
          </tbody>
        </table>
      </section>

      <section v-if="selectedTrialData" class="card">
        <h2 class="section-title">试运行 {{ selectedTrialData.trial_id }}</h2>
        <div class="trial-detail-grid">
          <div class="detail-block">
            <span class="detail-label">Agent</span>
            <span class="detail-value">{{ selectedTrialData.agent_config.name }}</span>
          </div>
          <div class="detail-block">
            <span class="detail-label">模型</span>
            <span class="detail-value cell-mono">{{ selectedTrialData.agent_config.model }}</span>
          </div>
          <div class="detail-block">
            <span class="detail-label">温度</span>
            <span class="detail-value">{{ selectedTrialData.agent_config.temperature }}</span>
          </div>
          <div class="detail-block">
            <span class="detail-label">输入 Token</span>
            <span class="detail-value cell-mono">{{ formatNumber(selectedTrialData.metrics.input_tokens) }}</span>
          </div>
          <div class="detail-block">
            <span class="detail-label">输出 Token</span>
            <span class="detail-value cell-mono">{{ formatNumber(selectedTrialData.metrics.output_tokens) }}</span>
          </div>
          <div class="detail-block">
            <span class="detail-label">工具调用</span>
            <span class="detail-value">{{ selectedTrialData.metrics.tool_call_count }}</span>
          </div>
        </div>
        <div class="outcome-block">
          <span class="detail-label">执行结果</span>
          <pre class="outcome-pre">{{ JSON.stringify(selectedTrialData.outcome, null, 2) }}</pre>
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

.back-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  color: var(--apple-accent);
  background: none;
  border: none;
  cursor: pointer;
  margin-bottom: 24px;
  font-family: var(--apple-font-body);
}

.back-btn:hover {
  text-decoration: underline;
}

.task-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 32px;
  gap: 24px;
  flex-wrap: wrap;
}

.task-id {
  font-family: var(--apple-font-display);
  font-size: 32px;
  font-weight: 700;
  letter-spacing: -0.02em;
  margin-bottom: 8px;
}

.task-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 6px;
  font-size: 12px;
  background: color-mix(in srgb, var(--apple-accent) 10%, transparent);
  color: var(--apple-accent);
}

.difficulty-tag {
  font-size: 12px;
  font-weight: 500;
}

.lang-tag {
  font-size: 12px;
  font-family: var(--apple-font-mono);
  color: var(--apple-text-secondary);
}

.task-header-right {
  display: flex;
  gap: 24px;
}

.stat-block {
  text-align: center;
}

.stat-label {
  display: block;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--apple-text-secondary);
  margin-bottom: 4px;
}

.stat-value {
  font-family: var(--apple-font-display);
  font-size: 24px;
  font-weight: 700;
}

.text-success { color: var(--apple-success); }
.text-error { color: var(--apple-error); }

.alert-card {
  background: color-mix(in srgb, var(--apple-warning) 8%, var(--apple-surface));
  border: 1px solid color-mix(in srgb, var(--apple-warning) 30%, var(--apple-border));
  border-radius: var(--apple-radius);
  padding: 16px 20px;
  margin-bottom: 24px;
}

.alert-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.alert-icon { color: var(--apple-warning); }

.alert-title {
  font-size: 14px;
  font-weight: 600;
}

.alert-item {
  font-size: 13px;
  color: var(--apple-text-secondary);
  margin-bottom: 4px;
}

.alert-type {
  font-family: var(--apple-font-mono);
  font-weight: 500;
  color: var(--apple-warning);
  margin-right: 8px;
}

.alert-detail {
  font-family: var(--apple-font-mono);
  font-size: 12px;
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

.dimension-bars {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.dim-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.dim-label {
  width: 100px;
  font-size: 13px;
  font-weight: 500;
  flex-shrink: 0;
}

.dim-bar-track {
  flex: 1;
  height: 8px;
  background: var(--apple-border);
  border-radius: 4px;
  overflow: hidden;
}

.dim-bar-fill {
  height: 100%;
  border-radius: 4px;
  transition: width 0.5s cubic-bezier(0.25, 0.46, 0.45, 0.94);
}

.dim-value {
  width: 70px;
  text-align: right;
  font-family: var(--apple-font-mono);
  font-size: 13px;
  font-weight: 500;
  flex-shrink: 0;
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

.table-row {
  cursor: pointer;
  transition: background 0.1s;
}

.table-row:hover {
  background: color-mix(in srgb, var(--apple-accent) 4%, transparent);
}

.table-row.selected {
  background: color-mix(in srgb, var(--apple-accent) 8%, transparent);
}

.table-row:last-child td {
  border-bottom: none;
}

.cell-mono {
  font-family: var(--apple-font-mono);
  font-size: 13px;
}

.icon-success { color: var(--apple-success); }
.icon-error { color: var(--apple-error); }

.score-value {
  font-family: var(--apple-font-mono);
  font-weight: 500;
}

.trial-detail-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  margin-bottom: 16px;
}

.detail-block {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.detail-label {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--apple-text-secondary);
}

.detail-value {
  font-size: 15px;
  font-weight: 500;
}

.outcome-block {
  margin-top: 16px;
}

.outcome-pre {
  margin-top: 8px;
  padding: 12px 16px;
  background: var(--apple-bg);
  border-radius: var(--apple-radius-sm);
  font-family: var(--apple-font-mono);
  font-size: 13px;
  overflow-x: auto;
  border: 1px solid var(--apple-border);
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

@media (max-width: 768px) {
  .page { padding: 24px 16px; }
  .task-header { flex-direction: column; }
  .trial-detail-grid { grid-template-columns: repeat(2, 1fr); }
  .task-id { font-size: 24px; }
}
</style>
