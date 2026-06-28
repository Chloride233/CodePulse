import { defineStore } from "pinia";
import { ref } from "vue";
import { request } from "@/composables/useApi";

export interface OverviewData {
  total_tasks: number;
  total_trials: number;
  overall_pass_rate: number;
  avg_score: number;
  total_cost_usd: number;
  dimension_scores: Record<string, number>;
  recent_scores: Array<{
    task_id: string;
    trial_id: string;
    total_score: number;
    success: boolean;
  }>;
  active_agents: Array<{
    name: string;
    model: string;
    pass_rate: number;
    avg_tokens: number;
  }>;
  weakest_dimension: string | null;
  costliest_task: {
    task_id?: string;
    cost_usd?: number;
  };
  regression_risks: Array<{
    task_id: string;
    trial_id: string;
    stage: string;
    failure_type: string;
  }>;
}

export const useDashboardStore = defineStore("dashboard", () => {
  const overview = ref<OverviewData | null>(null);
  const loading = ref(false);
  const error = ref<string | null>(null);

  async function fetchOverview() {
    loading.value = true;
    error.value = null;
    try {
      overview.value = await request<OverviewData>("/overview");
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : String(e);
    } finally {
      loading.value = false;
    }
  }

  return { overview, loading, error, fetchOverview };
});
