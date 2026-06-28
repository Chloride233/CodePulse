<script setup lang="ts">
import { computed } from "vue";
import VChart from "vue-echarts";
import { use } from "echarts/core";
import { LineChart } from "echarts/charts";
import {
  GridComponent,
  TooltipComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";

use([LineChart, GridComponent, TooltipComponent, CanvasRenderer]);

const props = withDefaults(
  defineProps<{
    data: Array<{
      task_id: string;
      trial_id: string;
      total_score: number;
      success: boolean;
    }>;
  }>(),
  { data: () => [] }
);

const option = computed(() => {
  const labels = props.data.map((d) => d.trial_id);
  const values = props.data.map((d) => Math.round(d.total_score * 100) / 100);
  const colors = props.data.map((d) =>
    d.success ? "#34c759" : "#ff3b30"
  );

  return {
    tooltip: {
      trigger: "axis",
      formatter: (params: Array<{ name: string; value: number; dataIndex: number }>) => {
        const p = params[0];
        const item = props.data[p.dataIndex];
        const status = item.success ? "Pass" : "Fail";
        return `${item.task_id} / ${p.name}<br/>Score: <b>${p.value}</b><br/>Status: ${status}`;
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
        fontSize: 10,
        rotate: 30,
      },
    },
    yAxis: {
      type: "value",
      min: 0,
      max: 100,
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
        type: "line",
        data: values,
        smooth: true,
        symbol: "circle",
        symbolSize: 8,
        lineStyle: {
          color: "#0071e3",
          width: 2,
        },
        itemStyle: {
          color: (params: { dataIndex: number }) => colors[params.dataIndex],
          borderWidth: 2,
          borderColor: "#fff",
        },
        areaStyle: {
          color: {
            type: "linear",
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: "rgba(0,113,227,0.12)" },
              { offset: 1, color: "rgba(0,113,227,0)" },
            ],
          },
        },
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
