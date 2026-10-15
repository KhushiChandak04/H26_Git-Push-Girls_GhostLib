// VITE_API_URL = backend origin (e.g. http://127.0.0.1:8000); VITE_API_BASE = full API base (overrides).
// When served by `ghostlib ui` the API is on the same origin; under `npm run dev` (port 5173) it is on :8000.
const DEFAULT_ORIGIN = typeof window !== "undefined" && window.location.port !== "5173" && window.location.protocol.startsWith("http")
  ? window.location.origin : "http://127.0.0.1:8000";
const ORIGIN = (import.meta.env.VITE_API_URL || DEFAULT_ORIGIN).replace(/\/$/, "");
export const API_BASE = import.meta.env.VITE_API_BASE || `${ORIGIN}/api`;

async function request(path, options = {}) {
  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...options,
      body: options.body ? JSON.stringify(options.body) : undefined,
    });
  } catch {
    throw new Error(`Cannot reach the GhostLib backend at ${API_BASE}. Start it with: uvicorn app.main:app --app-dir backend`);
  }
  const text = await response.text();
  let data;
  try { data = text ? JSON.parse(text) : null; } catch { data = text; }
  if (!response.ok) {
    const detail = data && data.detail;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail || data || response.statusText));
  }
  return data;
}

export const api = {
  health: () => request("/health"),
  aiStatus: () => request("/ai/status"),
  rubric: () => request("/rubric"),
  learning: () => request("/learning"),
  listRuns: () => request("/runs"),
  getRun: (id) => request(`/runs/${id}`),
  createRun: (repository, fetchMetadata = true, mode = null) =>
    request("/runs", { method: "POST", body: { repository, fetch_metadata: fetchMetadata, mode } }),
  source: (id, file, line, context = 4) =>
    request(`/runs/${id}/source?file=${encodeURIComponent(file)}&line=${line}&context=${context}`),
  recommend: (id, pkg) => request(`/runs/${id}/recommendations/${pkg}`, { method: "POST" }),
  propose: (id, pkg, body) => request(`/runs/${id}/experiments/${pkg}/propose`, { method: "POST", body }),
  approve: (id, pkg, body) => request(`/runs/${id}/experiments/${pkg}/approve`, { method: "POST", body }),
  reject: (id, pkg, reason) => request(`/runs/${id}/experiments/${pkg}/reject`, { method: "POST", body: { reason } }),
  experiment: (id, pkg) => request(`/runs/${id}/experiments/${pkg}`),
  openInEditor: (id, file, line = 1, scope = "repo") =>
    request(`/runs/${id}/open`, { method: "POST", body: { file, line, scope } }),
  capsule: (id) => request(`/runs/${id}/capsule`, { method: "POST" }),
  capsuleUrl: (id, fmt) => `${API_BASE}/runs/${id}/capsule.${fmt}`,
  logUrl: (id, pkg, name, side) => `${API_BASE}/runs/${id}/experiments/${pkg}/logs/${name}?side=${side}`,
};
