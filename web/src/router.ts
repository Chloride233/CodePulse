import { createRouter, createWebHistory } from "vue-router";

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: "/",
      redirect: "/overview",
    },
    {
      path: "/overview",
      name: "overview",
      component: () => import("@/pages/Overview.vue"),
    },
    {
      path: "/tasks",
      name: "tasks",
      component: () => import("@/pages/Tasks.vue"),
    },
    {
      path: "/tasks/:id",
      name: "task-detail",
      component: () => import("@/pages/TaskDetail.vue"),
    },
    {
      path: "/compare",
      name: "compare",
      component: () => import("@/pages/Compare.vue"),
    },
    {
      path: "/traces",
      name: "traces",
      component: () => import("@/pages/Traces.vue"),
    },
    {
      path: "/evolution",
      name: "evolution",
      component: () => import("@/pages/Evolution.vue"),
    },
    {
      path: "/:pathMatch(.*)*",
      name: "not-found",
      redirect: "/overview",
    },
  ],
});

export default router;
