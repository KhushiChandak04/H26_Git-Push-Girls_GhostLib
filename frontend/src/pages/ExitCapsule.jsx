import { useEffect, useState } from "react";
import Panel from "../components/Panel.jsx";
import { Evidence } from "../components/Badge.jsx";
import { api } from "../services/api.js";

export default function ExitCapsule({ run }) {
  const [markdown, setMarkdown] = useState("");
  const [capsule, setCapsule] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function regenerate() {
    setBusy(true); setError("");
    try {
      const result = await api.capsule(run.run_id);
      setCapsule(result.capsule);
      const response = await fetch(api.capsuleUrl(run.run_id, "md"));
      setMarkdown(await response.text());
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  useEffect(() => { if (run) regenerate(); }, [run?.run_id]); // eslint-disable-line react-hooks/exhaustive-deps

  return <>
    <Panel title="Dependency Exit Capsule" eyebrow="PORTABLE, EVIDENCE-LABELLED MIGRATION RECORD">
      <div className="actions">
        <button className="secondary" onClick={regenerate} disabled={busy}>{busy ? "Generating…" : "Regenerate"}</button>
        <a className="primary link-btn" href={api.capsuleUrl(run.run_id, "json")} download>Download capsule.json</a>
        <a className="primary link-btn" href={api.capsuleUrl(run.run_id, "md")} download>Download capsule.md</a>
      </div>
      {error && <div className="alert">{error}</div>}
      {capsule && <div className="legend">{Object.entries(capsule.evidence_legend).map(([k, v]) => <div key={k}><Evidence type={k} /> <span>{v}</span></div>)}</div>}
      {capsule && <div className="stats-grid four">
        <div className="stat"><span>PACKAGES</span><strong>{capsule.summary.packages}</strong><small>{capsule.summary.manifests.join(", ")}</small></div>
        <div className="stat"><span>HIGH RISK</span><strong>{capsule.summary.by_band.high.length}</strong><small>{capsule.summary.by_band.high.join(", ") || "none"}</small></div>
        <div className="stat"><span>AI RECOMMENDATIONS</span><strong>{capsule.summary.ai_recommendations_ok}</strong><small>{capsule.ai.model} · {capsule.ai.configured ? "configured" : "not configured"}</small></div>
        <div className="stat"><span>EXPERIMENTS</span><strong>{capsule.summary.experiments_completed}</strong><small>executed baseline vs candidate</small></div>
      </div>}
    </Panel>
    {capsule && <Panel title="Open concerns & limitations" eyebrow="WHAT IS NOT PROVEN">
      <ul className="plain">{capsule.open_concerns.map((c, i) => <li key={i}>{c}</li>)}</ul>
      <ul className="plain muted">{capsule.limitations.map((c, i) => <li key={i}>{c}</li>)}</ul>
    </Panel>}
    {markdown && <Panel title="capsule.md" eyebrow="RENDERED REPORT"><pre className="markdown">{markdown}</pre></Panel>}
  </>;
}
