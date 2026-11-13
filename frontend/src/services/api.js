// VITE_API_URL = backend origin (e.g. http://127.0.0.1:8000); VITE_API_BASE = full API base (overrides).
// When served by `ghostlib ui` the API is on the same origin; under `npm run dev` (port 5173) it is on :8000.
const DEFAULT_ORIGIN = typeof window !== "undefined" && window.location.port !== "5173" && window.location.protocol.startsWith("http")
  ? window.location.origin : "http://127.0.0.1:8000";
const ORIGIN = (import.meta.env.VITE_API_URL || DEFAULT_ORIGIN).replace(/\/$/, "");
export const API_BASE = import.meta.env.VITE_API_BASE || `${ORIGIN}/api`;
const TOKEN_KEY = "ghostlib_api_token";

function getToken() {
  try { return window.sessionStorage.getItem(TOKEN_KEY); } catch { return null; }
}

function saveToken(token) {
  try { window.sessionStorage.setItem(TOKEN_KEY, token); } catch {
    throw new Error("This browser cannot store the GhostLib access token for this session.");
  }
}

function clearToken() {
  try { window.sessionStorage.removeItem(TOKEN_KEY); } catch { /* the next request can prompt again */ }
}

async function fetchResponse(path, options = {}, retryAuth = true) {
  let response;
  try {
    const token = getToken();
    response = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: options.body ? JSON.stringify(options.body) : undefined,
    });
  } catch {
    throw new Error(`Cannot reach the GhostLib backend at ${API_BASE}. Start it with: uvicorn app.main:app --app-dir backend`);
  }
  if (response.status === 401 && retryAuth && response.headers.get("WWW-Authenticate") === "Bearer") {
    const token = window.prompt("Enter the GhostLib access token provided by the site owner:")?.trim();
    if (!token) throw new Error("A GhostLib access token is required to use this hosted service.");
    saveToken(token);
    return fetchResponse(path, options, false);
  }
  if (response.status === 401) clearToken();
  return response;
}

async function request(path, options = {}) {
  const response = await fetchResponse(path, options);
  const text = await response.text();
  let data;
  try { data = text ? JSON.parse(text) : null; } catch { data = text; }
  if (!response.ok) {
    const detail = data && data.detail;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail || data || response.statusText));
  }
  return data;
}

async function responseText(path) {
  const response = await fetchResponse(path);
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new Error(data?.detail || response.statusText);
  }
  return response.text();
}

async function download(path, filename) {
  const response = await fetchResponse(path);
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new Error(data?.detail || response.statusText);
  }
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
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
  workspaceInfo: (id, pkg) => request(`/runs/${id}/experiments/${pkg}/workspace`),
  openWorkspace: (id, pkg) => request(`/runs/${id}/experiments/${pkg}/open-workspace`, { method: "POST" }),
  compareFile: (id, pkg, file) => request(`/runs/${id}/experiments/${pkg}/compare`, { method: "POST", body: { file } }),
  capsule: (id, force = false) => request(`/runs/${id}/capsule${force ? "?force=true" : ""}`, { method: "POST" }),
  capsuleMarkdown: (id) => responseText(`/runs/${id}/capsule.md`),
  downloadCapsule: (id, fmt) => download(`/runs/${id}/capsule.${fmt}`, `dependency-exit-capsule-${id}.${fmt}`),
  downloadLog: (id, pkg, name, side) =>
    download(`/runs/${id}/experiments/${pkg}/logs/${name}?side=${side}`, name),
  capsuleUrl: (id, fmt) => `${API_BASE}/runs/${id}/capsule.${fmt}`,
  logUrl: (id, pkg, name, side) => `${API_BASE}/runs/${id}/experiments/${pkg}/logs/${name}?side=${side}`,
};
