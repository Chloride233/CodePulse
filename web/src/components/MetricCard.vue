<script setup lang="ts">
import { computed, type Component } from "vue";

const props = withDefaults(
  defineProps<{
    label: string;
    value: number;
    format?: "number" | "percent" | "score" | "cost";
    icon?: Component;
    accent?: "default" | "success" | "warning" | "error";
  }>(),
  {
    format: "number",
    accent: "default",
  }
);

const displayValue = computed(() => {
  switch (props.format) {
    case "percent":
      return `${(props.value * 100).toFixed(1)}%`;
    case "score":
      return props.value.toFixed(1);
    case "cost":
      return props.value < 0.01
        ? `$${props.value.toFixed(4)}`
        : `$${props.value.toFixed(2)}`;
    default:
      return props.value.toLocaleString();
  }
});

const accentColor = computed(() => {
  switch (props.accent) {
    case "success":
      return "var(--apple-success)";
    case "warning":
      return "var(--apple-warning)";
    case "error":
      return "var(--apple-error)";
    default:
      return "var(--apple-accent)";
  }
});
</script>

<template>
  <div class="metric-card">
    <div class="metric-header">
      <span class="metric-label">{{ label }}</span>
      <component :is="icon" v-if="icon" :size="18" class="metric-icon" />
    </div>
    <div class="metric-value" :style="{ color: accentColor }">
      {{ displayValue }}
    </div>
  </div>
</template>

<style scoped>
.metric-card {
  background: var(--apple-surface);
  border-radius: var(--apple-radius);
  padding: 20px 24px;
  transition: transform 0.15s ease;
}

.metric-card:hover {
  transform: translateY(-1px);
}

.metric-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.metric-label {
  font-size: 12px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--apple-text-secondary);
}

.metric-icon {
  color: var(--apple-text-tertiary);
}

.metric-value {
  font-family: var(--apple-font-display);
  font-size: 32px;
  font-weight: 700;
  line-height: 1;
  letter-spacing: -0.02em;
}
</style>
