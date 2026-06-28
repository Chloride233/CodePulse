<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { useRouter } from "vue-router";
import { request } from "@/composables/useApi";
import { formatPercent, formatScore, scoreColor, difficultyColor } from "@/lib/utils";
import { PhMagnifyingGlass as MagnifyingGlass, PhFunnel as Funnel } from "@phosphor-icons/vue";

interface TaskItem {
  task_id: string;
  source: string;
  category: string;
  difficulty: string;
  language: string;
  n_trials: number;
  pass_rate: number;
  avg_score: number;
}

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

const router = useRouter();
const tasks = ref<TaskItem[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);

const filterSource = ref("");
const filterCategory = ref("");
const filterDifficulty = ref("");
const search = ref("");

const sources = computed(() => [...new Set(tasks.value.map((t) => t.source))]);
const categories = computed(() => [...new Set(tasks.value.map((t) => t.category))]);
const difficulties = computed(() => [...new Set(tasks.value.map((t) => t.difficulty))]);

const filtered = computed(() => {
  return tasks.value.filter((t) => {
    if (filterSource.value && t.source !== filterSource.value) return false;
    if (filterCategory.value && t.category !== filterCategory.value) return false;
    if (filterDifficulty.value && t.difficulty !== filterDifficulty.value) return false;
    if (search.value && !t.task_id.toLowerCase().includes(search.value.toLowerCase()))
      return false;
    return true;
  });
});

async function fetchTasks() {
  loading.value = true;
  error.value = null;
  try {
    tasks.value = await request<TaskItem[]>("/tasks");
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    loading.value = false;
  }
}

function goDetail(taskId: string) {
  router.push({ name: "task-detail", params: { id: taskId } });
}

onMounted(fetchTasks);
</script>

<template>
  <div class="page">
    <header class="page-header">
      <h1 class="page-title">任务</h1>
      <p class="page-subtitle">浏览和筛选已评测的任务。</p>
    </header>

    <div class="filters-bar">
      <div class="search-input">
        <MagnifyingGlass :size="16" class="search-icon" />
        <input
          v-model="search"
          type="text"
          placeholder="搜索任务 ID..."
          class="input"
        />
      </div>
      <div class="filter-group">
        <Funnel :size="14" class="filter-icon" />
        <select v-model="filterSource" class="select">
          <option value="">全部来源</option>
          <option v-for="s in sources" :key="s" :value="s">{{ s }}</option>
        </select>
        <select v-model="filterCategory" class="select">
          <option value="">全部类别</option>
          <option v-for="c in categories" :key="c" :value="c">{{ CATEGORY_LABELS[c] ?? c }}</option>
        </select>
        <select v-model="filterDifficulty" class="select">
          <option value="">全部难度</option>
          <option v-for="d in difficulties" :key="d" :value="d">{{ DIFFICULTY_LABELS[d] ?? d }}</option>
        </select>
      </div>
    </div>

    <div v-if="loading" class="loading-state">
      <div class="spinner"></div>
    </div>

    <div v-else-if="error" class="error-state">
      <p>{{ error }}</p>
      <button class="btn-primary" @click="fetchTasks">重试</button>
    </div>

    <div v-else class="card">
      <table class="data-table">
        <thead>
          <tr>
            <th>任务 ID</th>
            <th>来源</th>
            <th>类别</th>
            <th>难度</th>
            <th>试运行</th>
            <th>通过率</th>
            <th>平均分</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="task in filtered"
            :key="task.task_id"
            class="table-row"
            @click="goDetail(task.task_id)"
          >
            <td class="cell-mono">{{ task.task_id }}</td>
            <td class="cell-secondary">{{ task.source }}</td>
            <td>
              <span class="tag">{{ CATEGORY_LABELS[task.category] ?? task.category }}</span>
            </td>
            <td>
              <span class="difficulty-dot" :style="{ background: difficultyColor(task.difficulty) }"></span>
              {{ DIFFICULTY_LABELS[task.difficulty] ?? task.difficulty }}
            </td>
            <td class="cell-mono">{{ task.n_trials }}</td>
            <td>
              <span
                class="pass-badge"
                :class="task.pass_rate >= 0.8 ? 'pass' : task.pass_rate > 0 ? 'partial' : 'fail'"
              >
                {{ formatPercent(task.pass_rate) }}
              </span>
            </td>
            <td>
              <span class="score-value" :style="{ color: scoreColor(task.avg_score / 100) }">
                {{ formatScore(task.avg_score / 100) }}
              </span>
            </td>
          </tr>
          <tr v-if="filtered.length === 0">
            <td colspan="7" class="cell-empty">没有匹配的任务。</td>
          </tr>
        </tbody>
      </table>
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

.filters-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 24px;
  flex-wrap: wrap;
}

.search-input {
  position: relative;
  flex: 1;
  min-width: 200px;
  max-width: 320px;
}

.search-icon {
  position: absolute;
  left: 12px;
  top: 50%;
  transform: translateY(-50%);
  color: var(--apple-text-tertiary);
}

.input {
  width: 100%;
  height: 36px;
  padding: 0 12px 0 36px;
  border: 1px solid var(--apple-border);
  border-radius: var(--apple-radius-sm);
  font-size: 14px;
  font-family: var(--apple-font-body);
  color: var(--apple-text);
  background: var(--apple-bg);
  outline: none;
  transition: border-color 0.2s;
}

.input:focus {
  border-color: var(--apple-accent);
  box-shadow: 0 0 0 3px rgba(0, 113, 227, 0.12);
}

.filter-group {
  display: flex;
  align-items: center;
  gap: 8px;
}

.filter-icon {
  color: var(--apple-text-tertiary);
}

.select {
  height: 36px;
  padding: 0 28px 0 12px;
  border: 1px solid var(--apple-border);
  border-radius: var(--apple-radius-sm);
  font-size: 13px;
  font-family: var(--apple-font-body);
  color: var(--apple-text);
  background: var(--apple-bg);
  cursor: pointer;
  outline: none;
  appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg width='10' height='6' viewBox='0 0 10 6' fill='none' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M1 1L5 5L9 1' stroke='%2386868b' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 10px center;
}

.select:focus {
  border-color: var(--apple-accent);
}

.card {
  background: var(--apple-surface);
  border-radius: var(--apple-radius);
  overflow: hidden;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
}

.data-table th {
  text-align: left;
  padding: 12px 16px;
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

.table-row {
  cursor: pointer;
  transition: background 0.1s;
}

.table-row:hover {
  background: color-mix(in srgb, var(--apple-accent) 4%, transparent);
}

.table-row:last-child td {
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
  padding: 32px !important;
}

.tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 6px;
  font-size: 12px;
  background: color-mix(in srgb, var(--apple-accent) 10%, transparent);
  color: var(--apple-accent);
}

.difficulty-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-right: 6px;
  vertical-align: middle;
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

.score-value {
  font-family: var(--apple-font-mono);
  font-size: 13px;
  font-weight: 500;
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

@media (max-width: 768px) {
  .page {
    padding: 24px 16px;
  }
  .filters-bar {
    flex-direction: column;
    align-items: stretch;
  }
  .search-input {
    max-width: none;
  }
  .filter-group {
    flex-wrap: wrap;
  }
  .page-title {
    font-size: 32px;
  }
}
</style>
