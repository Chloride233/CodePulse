import { ref, type Ref } from "vue";

declare const __API_BASE_URL__: string;

const BASE = __API_BASE_URL__ || "/api";

async function request<T>(path: string): Promise<T> {
  // Sanitize path: strip leading slashes and prevent traversal
  const cleanPath = path.replace(/^\/+/, "").replace(/\.\./g, "");
  const res = await fetch(`${BASE}/${cleanPath}`);
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`API ${res.status}: ${text}`);
  }
  return res.json();
}

export function useApi<T>(path: Ref<string> | string) {
  const data: Ref<T | null> = ref(null);
  const loading = ref(false);
  const error: Ref<string | null> = ref(null);

  async function fetch_() {
    loading.value = true;
    error.value = null;
    try {
      const p = typeof path === "string" ? path : path.value;
      data.value = await request<T>(p);
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : String(e);
    } finally {
      loading.value = false;
    }
  }

  return { data, loading, error, fetch: fetch_ };
}

export { request };
