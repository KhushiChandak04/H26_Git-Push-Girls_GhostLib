export const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000/api";

async function request(path, options = {}) {
  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...options,
      body: options.body ? JSON.stringify(options.body) : undefined,
    });
  } catch {
    throw new Error(`Cannot reach the GhostLib backend at ${API_BASE}. Is uvicorn running?`);
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
  listRuns: () => request("/runs"),
  getRun: (id) => request(`/runs/${id}`),
  createRun: (repository, fetchMetadata = true) =>
    request("/runs", { method: "POST", body: { repository, fetch_metadata: fetchMetadata } }),
  source: (id, file, line) => request(`/runs/${id}/source?file=${encodeURIComponent(file)}&line=${line}`),
  recommend: (id, pkg) => request(`/runs/${id}/recommendations/${pkg}`, { method: "POST" }),
  propose: (id, pkg, body) => request(`/runs/${id}/experiments/${pkg}/propose`, { method: "POST", body }),
  approve: (id, pkg, body) => request(`/runs/${id}/experiments/${pkg}/approve`, { method: "POST", body }),
  reject: (id, pkg, reason) => request(`/runs/${id}/experiments/${pkg}/reject`, { method: "POST", body: { reason } }),
  experiment: (id, pkg) => request(`/runs/${id}/experiments/${pkg}`),
  capsule: (id) => request(`/runs/${id}/capsule`, { method: "POST" }),
  capsuleUrl: (id, fmt) => `${API_BASE}/runs/${id}/capsule.${fmt}`,
  logUrl: (id, pkg, name, side) => `${API_BASE}/runs/${id}/experiments/${pkg}/logs/${name}?side=${side}`,
};
