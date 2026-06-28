<script setup lang="ts">
import { RouterView, useRoute } from "vue-router";
import { computed } from "vue";
import {
  PhChartLineUp as IconOverview,
  PhListChecks as IconTasks,
  PhScales as IconCompare,
  PhFlowArrow as IconTraces,
  PhDna as IconEvolution,
} from "@phosphor-icons/vue";

const route = useRoute();

const nav = [
  { path: "/overview", label: "总览", icon: IconOverview },
  { path: "/tasks", label: "任务", icon: IconTasks },
  { path: "/compare", label: "对比", icon: IconCompare },
  { path: "/traces", label: "轨迹", icon: IconTraces },
  { path: "/evolution", label: "进化", icon: IconEvolution },
];

const activeNav = computed(() => {
  const p = route.path;
  for (const item of nav) {
    if (p === item.path || p.startsWith(item.path + "/")) return item.path;
  }
  return p;
});
</script>

<template>
  <div class="app-layout">
    <aside class="sidebar">
      <div class="sidebar-brand">
        <div class="brand-mark">CP</div>
        <span class="brand-name">CodePulse</span>
      </div>
      <nav class="sidebar-nav">
        <router-link
          v-for="item in nav"
          :key="item.path"
          :to="item.path"
          class="nav-item"
          :class="{ active: activeNav === item.path }"
        >
          <component :is="item.icon" :size="18" class="nav-icon" />
          <span class="nav-label">{{ item.label }}</span>
        </router-link>
      </nav>
      <div class="sidebar-footer">
        <span class="version">v0.1.0</span>
      </div>
    </aside>
    <main class="main-content">
      <router-view v-slot="{ Component }">
        <transition name="fade" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </main>
  </div>
</template>

<style scoped>
.app-layout {
  display: flex;
  min-height: 100dvh;
  background: var(--apple-bg);
}

.sidebar {
  width: 220px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  padding: 20px 12px;
  border-right: 1px solid var(--apple-border);
  background: var(--apple-surface);
}

.sidebar-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 8px 20px;
  border-bottom: 1px solid var(--apple-border);
  margin-bottom: 16px;
}

.brand-mark {
  width: 32px;
  height: 32px;
  background: var(--apple-accent);
  color: #fff;
  border-radius: var(--apple-radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  font-family: var(--apple-font-mono);
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.02em;
  flex-shrink: 0;
}

.brand-name {
  font-size: 17px;
  font-weight: 600;
  color: var(--apple-text);
}

.sidebar-nav {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  border-radius: var(--apple-radius-sm);
  font-size: 14px;
  font-weight: 400;
  color: var(--apple-text-secondary);
  text-decoration: none;
  transition: all 0.15s ease;
}

.nav-item:hover {
  color: var(--apple-text);
  background: color-mix(in srgb, var(--apple-accent) 8%, transparent);
}

.nav-item.active {
  color: var(--apple-accent);
  background: color-mix(in srgb, var(--apple-accent) 10%, transparent);
  font-weight: 500;
}

.nav-icon {
  flex-shrink: 0;
}

.sidebar-footer {
  padding-top: 16px;
  border-top: 1px solid var(--apple-border);
}

.version {
  font-size: 12px;
  color: var(--apple-text-tertiary);
  font-family: var(--apple-font-mono);
}

.main-content {
  flex: 1;
  overflow-x: hidden;
  overflow-y: auto;
}

@media (max-width: 768px) {
  .sidebar {
    width: 56px;
    padding: 12px 6px;
  }
  .brand-name {
    display: none;
  }
  .sidebar-footer {
    display: none;
  }
  .nav-label {
    display: none;
  }
  .nav-item {
    justify-content: center;
    padding: 10px;
  }
  .brand-mark {
    margin: 0 auto;
  }
}
</style>
