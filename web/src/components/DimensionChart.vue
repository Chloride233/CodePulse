<script setup lang="ts">
import { computed } from "vue";
import VChart from "vue-echarts";
import { use } from "echarts/core";
import { BarChart } from "echarts/charts";
import {
  GridComponent,
  TooltipComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import { DIMENSION_LABELS, DIMENSION_MAX } from "@/lib/utils";

use([BarChart, GridComponent, TooltipComponent, CanvasRenderer]);

const props = defineProps<{
  scores: Record<string, number>;
}>();

const option = computed(() => {
  const dims = Object.keys(props.scores);
  if (dims.length === 0) return {};

  const labels = dims.map((d) => DIMENSION_LABELS[d] ?? d);
  const maxes = dims.map((d) => DIMENSION_MAX[d] ?? 10);
  const values = dims.map((d, i) => {
    const max = maxes[i];
    return Math.round(props.scores[d] * max * 10) / 10;
  });
  // Dynamic y-axis max: ceil to nearest 5 above the highest value
  const dataMax = Math.max(...values, ...maxes);
  const yMax = Math.ceil(dataMax / 5) * 5;

  return {
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
      formatter: (params: unknown) => {
        const items = params as Array<{ name: string; value: number; dataIndex: number }>;
        if (!Array.isArray(items) || !items.length) return "";
        const p = items[0];
        const max = maxes[p.dataIndex] ?? 10;
        return `${p.name}<br/>Score: <b>${p.value}</b> / ${max}`;
      },
    },
    grid: {
      left: 16,
      right: 16,
      top: 8,
      bottom: 24,
      containLabel: true,
    },
    xAxis: {
      type: "category",
      data: labels,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: {
        color: "#86868b",
        fontSize: 11,
      },
    },
    yAxis: {
      type: "value",
      max: yMax,
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: {
        lineStyle: { color: "#d2d2d7", type: "dashed" },
      },
      axisLabel: {
        color: "#86868b",
        fontSize: 11,
      },
    },
    series: [
      {
        type: "bar",
        data: values.map((v) => ({
          value: v,
          itemStyle: {
            color: "#0071e3",
            borderRadius: [4, 4, 0, 0],
          },
        })),
        barWidth: "40%",
      },
    ],
  };
});
</script>

<template>
  <div class="chart-container">
    <v-chart :option="option" autoresize />
  </div>
</template>

<style scoped>
.chart-container {
  width: 100%;
  height: 240px;
}
</style>
