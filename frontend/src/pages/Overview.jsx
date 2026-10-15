import { useState } from "react";
import Panel from "../components/Panel.jsx";
import Stat from "../components/Stat.jsx";
import { scanRepository } from "../services/api.js";

export default function Overview() {
  const [repository, setRepository] = useState("");
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function runScan(event) {
    event.preventDefault(); setBusy(true); setError(""); setResult(null);
    try { setResult(await scanRepository(repository)); } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }
  return <>
    <div className="hero"><div><span className="eyebrow">DEPENDENCY RESILIENCE TOOLKIT</span><h2>Know what breaks<br/>before you migrate.</h2><p>Inspect dependency manifests, map Python import usage, and generate an evidence-labelled Dependency Exit Capsule.</p></div><div className="hero-orbit"><div className="orbit-ring ring-one"/><div className="orbit-ring ring-two"/><div className="orbit-core">G</div><span className="orbit-node node-one"/><span className="orbit-node node-two"/><span className="orbit-node node-three"/></div></div>
    <div className="stats-grid"><Stat label="SCAN ENGINE" value="Ready*" detail="Manifest + static import scan"/><Stat label="MIGRATION RUNNER" value="Guarded" detail="No candidate commands executed"/><Stat label="EXIT CAPSULE" value="JSON + MD" detail="Explicit evidence limitations"/></div>
    <Panel title="Start a repository scan" eyebrow="LOCAL WORKFLOW">
      <form className="scan-form" onSubmit={runScan}><label htmlFor="repo">Absolute path to a local repository</label><div className="input-row"><input id="repo" value={repository} onChange={e=>setRepository(e.target.value)} placeholder="C:\path\to\LinkWatch or /path/to/LinkWatch" required/><button className="primary" disabled={busy}>{busy ? "Scanning…" : "Run scan"}</button></div><p className="muted">The backend reads files at the path you provide. Use a trusted local checkout.</p></form>
      {error && <div className="alert">{error}</div>}
      {result && <div className="scan-result"><div className="result-heading"><strong>Scan complete</strong><span>{result.dependencies.length} manifest entries</span></div><p className="muted">{result.repository}</p><div className="result-tags">{result.manifests.map((m,i)=><span key={i}>{typeof m === "string" ? m : m.path}</span>)}</div><h3>Dependencies</h3>{result.dependencies.length ? <div className="dep-list">{result.dependencies.map((d,i)=><div className="dep-row" key={i}><strong>{d.name}</strong><code>{d.specifier || "unconstrained"}</code><span>{d.source}</span></div>)}</div> : <p className="muted">No dependencies found in the supported manifest files.</p>}<p className="muted">Static usage is best-effort. Read the limitations before interpreting absence of an import as proof of non-use.</p></div>}
    </Panel>
    <div className="two-col"><Panel title="Evidence-first analysis"><p>Separate observed repository facts from AI-generated recommendations. Each finding should be traceable to a manifest, source file, metadata record or test execution.</p></Panel><Panel title="Safe migration workflow"><p>Candidate changes belong in disposable workspaces. The original repository should remain untouched; run only reviewed commands in isolated environments.</p></Panel></div>
    <p className="footnote">* “Ready” refers to the starter scanner only. Gemma 4, metadata enrichment, migration execution and behavioral comparison are not configured yet.</p>
  </>;
}
