const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000/api";

export async function scanRepository(repository) {
  const response = await fetch(`${API_BASE}/scan`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ repository }),
  });
  if (!response.ok) throw new Error((await response.json()).detail || "Scan failed");
  return response.json();
}

export async function createCapsule(repository) {
  const response = await fetch(`${API_BASE}/capsule?repository=${encodeURIComponent(repository)}`, { method: "POST" });
  if (!response.ok) throw new Error((await response.json()).detail || "Capsule generation failed");
  return response.json();
}
