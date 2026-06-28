<script setup lang="ts">
import { ref, onMounted } from "vue";
import { request } from "@/composables/useApi";
import { formatNumber, formatDuration } from "@/lib/utils";
import {
  PhMagnifyingGlass as MagnifyingGlass,
  PhLightning as Lightning,
  PhWrench as Wrench,
  PhChatCircle as ChatCircle,
  PhBug as Bug,
  PhArrowSquareOut as ArrowSquareOut,
} from "@phosphor-icons/vue";

interface TraceSummary {
  session_id: string;
  n_events: number;
  total_tokens: number;
  total_duration: number;
  tool_call_count: number;
}

interface TraceEvent {
  timestamp: number;
  event_type: string;
  content: Record<string, unknown>;
  token_usage: Record<string, number>;
  duration: number;
}

const EVENT_TYPE_LABELS: Record<string, string> = {
  llm_call: "模型调用",
  tool_call: "工具调用",
  tool_result: "工具结果",
  reflection: "反思",
  error: "错误",
};

const traces = ref<TraceSummary[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);
const selectedSession = ref<string | null>(null);
const sessionEvents = ref<TraceEvent[]>([]);
const sessionLoading = ref(false);

const eventIcons: Record<string, typeof Lightning> = {
  llm_call: Lightning,
  tool_call: Wrench,
  tool_result: ChatCircle,
  reflection: ChatCircle,
  error: Bug,
};

const eventColors: Record<string, string> = {
  llm_call: "var(--apple-accent)",
  tool_call: "var(--apple-success)",
  tool_result: "var(--apple-text-secondary)",
  reflection: "var(--apple-warning)",
  error: "var(--apple-error)",
};

async function fetchTraces() {
  loading.value = true;
  error.value = null;
  try {
    traces.value = await request<TraceSummary[]>("/traces");
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    loading.value = false;
  }
}

async function loadSession(sessionId: string) {
  selectedSession.value = sessionId;
  sessionLoading.value = true;
  try {
    const data = await request<{ events: TraceEvent[] }>(`/traces/${sessionId}`);
    sessionEvents.value = data.events;
  } catch {
    sessionEvents.value = [];
  } finally {
    sessionLoading.value = false;
  }
}

function eventLabel(type: string): string {
  return EVENT_TYPE_LABELS[type] ?? type;
}

function safeStringify(obj: unknown, maxLen = 150): string {
  try {
    return JSON.stringify(obj).slice(0, maxLen);
  } catch {
    return "[无法序列化]";
  }
}

function eventContent(event: TraceEvent): string {
  const c = event.content;
  if (event.event_type === "llm_call") {
    return (c.response as string) ?? (c.prompt as string) ?? "";
  }
  if (event.event_type === "tool_call") {
    return `${c.tool_name ?? ""} ${c.args ? safeStringify(c.args, 120) : ""}`;
  }
  if (event.event_type === "tool_result") {
    return String(c.result ?? "").slice(0, 150);
  }
  return safeStringify(c);
}

onMounted(fetchTraces);
</script>

<template>
  <div class="page">
    <header class="page-header">
      <h1 class="page-title">轨迹</h1>
      <p class="page-subtitle">查看 Agent 执行轨迹和事件时间线。</p>
    </header>

    <div v-if="loading" class="loading-state">
      <div class="spinner"></div>
    </div>

    <div v-else-if="error" class="error-state">
      <p>{{ error }}</p>
      <button class="btn-primary" @click="fetchTraces">重试</button>
    </div>

    <template v-else>
      <div class="traces-layout">
        <aside class="session-list">
          <div class="session-list-header">
            <h2 class="list-title">会话列表</h2>
            <span class="session-count">{{ traces.length }}</span>
          </div>
          <div
            v-for="trace in traces"
            :key="trace.session_id"
            class="session-item"
            :class="{ active: selectedSession === trace.session_id }"
            @click="loadSession(trace.session_id)"
          >
            <span class="session-id">{{ trace.session_id }}</span>
            <span class="session-meta">
              {{ trace.n_events }} 个事件
              <span class="meta-dot"></span>
              {{ formatNumber(trace.total_tokens) }} token
            </span>
          </div>
          <div v-if="traces.length === 0" class="empty-list">
            暂无轨迹数据。
          </div>
        </aside>

        <section class="event-panel">
          <template v-if="selectedSession">
            <div class="panel-header">
              <h2 class="panel-title">会话 {{ selectedSession }}</h2>
              <span v-if="!sessionLoading" class="panel-meta">
                {{ sessionEvents.length }} 个事件
              </span>
            </div>

            <div v-if="sessionLoading" class="loading-state">
              <div class="spinner"></div>
            </div>

            <div v-else class="timeline">
              <div
                v-for="(event, i) in sessionEvents"
                :key="i"
                class="timeline-item"
              >
                <div class="timeline-marker">
                  <component
                    :is="eventIcons[event.event_type] ?? ArrowSquareOut"
                    :size="14"
                    :style="{ color: eventColors[event.event_type] ?? 'var(--apple-text-tertiary)' }"
                  />
                </div>
                <div class="timeline-content">
                  <div class="event-header">
                    <span
                      class="event-type-badge"
                      :style="{ background: eventColors[event.event_type] ?? 'var(--apple-text-tertiary)' }"
                    >
                      {{ eventLabel(event.event_type) }}
                    </span>
                    <span class="event-duration" v-if="event.duration > 0">
                      {{ formatDuration(event.duration) }}
                    </span>
                    <span
                      class="event-tokens"
                      v-if="event.token_usage && Object.keys(event.token_usage).length > 0"
                    >
                      {{ Object.values(event.token_usage).reduce((a, b) => a + b, 0) }} token
                    </span>
                  </div>
                  <pre class="event-body">{{ eventContent(event) }}</pre>
                </div>
              </div>
            </div>
          </template>

          <div v-else class="empty-panel">
            <MagnifyingGlass :size="32" class="empty-icon" />
            <p>选择一个会话查看执行轨迹。</p>
          </div>
        </section>
      </div>
    </template>
  </div>
</template>

<style scoped>
.page {
  padding: 40px 48px;
  max-width: 1400px;
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

.traces-layout {
  display: grid;
  grid-template-columns: 280px 1fr;
  gap: 16px;
  min-height: 600px;
}

.session-list {
  background: var(--apple-surface);
  border-radius: var(--apple-radius);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.session-list-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 16px 12px;
  border-bottom: 1px solid var(--apple-border);
}

.list-title {
  font-size: 14px;
  font-weight: 600;
}

.session-count {
  font-size: 12px;
  font-family: var(--apple-font-mono);
  color: var(--apple-text-tertiary);
  background: var(--apple-border);
  padding: 1px 6px;
  border-radius: 10px;
}

.session-item {
  padding: 12px 16px;
  cursor: pointer;
  border-bottom: 1px solid var(--apple-border);
  transition: background 0.1s;
}

.session-item:hover {
  background: color-mix(in srgb, var(--apple-accent) 4%, transparent);
}

.session-item.active {
  background: color-mix(in srgb, var(--apple-accent) 10%, transparent);
  border-left: 3px solid var(--apple-accent);
}

.session-id {
  display: block;
  font-family: var(--apple-font-mono);
  font-size: 13px;
  font-weight: 500;
  color: var(--apple-text);
  margin-bottom: 4px;
}

.session-meta {
  font-size: 12px;
  color: var(--apple-text-tertiary);
}

.meta-dot {
  display: inline-block;
  width: 3px;
  height: 3px;
  border-radius: 50%;
  background: var(--apple-text-tertiary);
  vertical-align: middle;
  margin: 0 6px;
}

.empty-list {
  padding: 24px 16px;
  text-align: center;
  font-size: 13px;
  color: var(--apple-text-tertiary);
}

.event-panel {
  background: var(--apple-surface);
  border-radius: var(--apple-radius);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--apple-border);
}

.panel-title {
  font-size: 14px;
  font-weight: 600;
  font-family: var(--apple-font-mono);
}

.panel-meta {
  font-size: 12px;
  color: var(--apple-text-tertiary);
}

.timeline {
  flex: 1;
  overflow-y: auto;
  padding: 16px 20px;
}

.timeline-item {
  display: flex;
  gap: 12px;
  padding-bottom: 16px;
  margin-bottom: 16px;
  border-bottom: 1px solid var(--apple-border);
}

.timeline-item:last-child {
  border-bottom: none;
  margin-bottom: 0;
  padding-bottom: 0;
}

.timeline-marker {
  flex-shrink: 0;
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--apple-bg);
  border-radius: 50%;
  border: 1px solid var(--apple-border);
}

.timeline-content {
  flex: 1;
  min-width: 0;
}

.event-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
  flex-wrap: wrap;
}

.event-type-badge {
  display: inline-block;
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 10px;
  font-weight: 600;
  color: #fff;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.event-duration {
  font-size: 11px;
  font-family: var(--apple-font-mono);
  color: var(--apple-text-secondary);
}

.event-tokens {
  font-size: 11px;
  font-family: var(--apple-font-mono);
  color: var(--apple-text-tertiary);
}

.event-body {
  font-size: 13px;
  font-family: var(--apple-font-mono);
  color: var(--apple-text-secondary);
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.5;
  margin: 0;
}

.empty-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: var(--apple-text-tertiary);
  font-size: 14px;
}

.empty-icon {
  opacity: 0.4;
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
  .traces-layout {
    grid-template-columns: 1fr;
    min-height: auto;
  }
  .session-list {
    max-height: 240px;
  }
  .page-title { font-size: 32px; }
}
</style>
