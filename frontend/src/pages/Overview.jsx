import { useEffect, useState } from "react";
import Panel from "../components/Panel.jsx";
import Stat from "../components/Stat.jsx";
import { Band, Evidence } from "../components/Badge.jsx";
import { api } from "../services/api.js";

export default function Overview({ run, loadRun, go }) {
  const [repository, setRepository] = useState(() => localStorageGet("ghostlib.repo") || "");
  const [fetchMetadata, setFetchMetadata] = useState(true);
  const [runs, setRuns] = useState([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => { api.listRuns().then(setRuns).catch(() => {}); }, [run]);
  useEffect(() => { if (!repository && runs[0]) setRepository(runs[0].repository); }, [runs, repository]);

  async function runScan(event) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      localStorageSet("ghostlib.repo", repository);
      const created = await api.createRun(repository, fetchMetadata);
      await loadRun(created.run_id);
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }

  async function open(id) {
    setError("");
    try { await loadRun(id); } catch (e) { setError(e.message); }
  }

  const pkgs = run?.packages || [];
  const bands = (b) => pkgs.filter(p => p.assessment.band === b).length;

  return <>
    {!run && <div className="hero"><div><span className="eyebrow">DEPENDENCY RESILIENCE TOOLKIT</span>
      <h2>Know what breaks<br />before you migrate.</h2>
      <p>GhostLib scans a real repository, shows the evidence behind every dependency risk, asks Gemma 4 for a migration
        plan, and runs baseline-versus-candidate tests in a disposable workspace — then tells you what was proven and what was not.</p></div>
      <div className="hero-orbit"><div className="orbit-ring ring-one" /><div className="orbit-ring ring-two" /><div className="orbit-core">G</div><span className="orbit-node node-one" /><span className="orbit-node node-two" /><span className="orbit-node node-three" /></div></div>}

    <Panel title="Scan a repository" eyebrow="LOCAL WORKFLOW">
      <form className="scan-form" onSubmit={runScan}>
        <label htmlFor="repo">Absolute path to a local checkout (e.g. the LinkWatch clone)</label>
        <div className="input-row">
          <input id="repo" value={repository} onChange={e => setRepository(e.target.value)} placeholder="C:\path\to\LinkWatch" required />
          <button className="primary" disabled={busy}>{busy ? "Scanning…" : "Run scan"}</button>
        </div>
        <label className="check"><input type="checkbox" checked={fetchMetadata} onChange={e => setFetchMetadata(e.target.checked)} />
          Fetch PyPI metadata (network; ~15 s first time, then cached 24 h)</label>
        <p className="muted">The backend reads files at this path. It never executes repository code during a scan and never modifies the repository.</p>
      </form>
      {error && <div className="alert">{error}</div>}
      {runs.length > 0 && <div className="runs"><h3>Previous runs</h3>
        {runs.slice(0, 6).map(r => <button key={r.run_id} className={`run-row ${run?.run_id === r.run_id ? "active" : ""}`} onClick={() => open(r.run_id)}>
          <code>{r.run_id}</code><span>{r.repository}</span><span>{r.packages} packages</span></button>)}
      </div>}
    </Panel>

    {run && <>
      <div className="stats-grid four">
        <Stat label="PACKAGES" value={pkgs.length} detail={`${run.manifests.length} manifests · ${run.source_files_scanned} .py files`} />
        <Stat label="HIGH / MEDIUM RISK" value={`${bands("high")} / ${bands("medium")}`} detail="Rule-based triage score" />
        <Stat label="AI RECOMMENDATIONS" value={Object.values(run.recommendations || {}).filter(r => r.status === "ok").length} detail="Gemma 4, schema-validated" />
        <Stat label="EXPERIMENTS" value={Object.values(run.experiments || {}).filter(e => e.state === "completed").length} detail="Baseline vs candidate executed" />
      </div>

      <Panel title="Dependency risk ranking" eyebrow="EVIDENCE-BACKED INDICATORS">
        <p className="muted">Score = sum of rule points; each indicator links to its evidence. Not a probability, not a security assessment.
          Requires-python declared: <code>{run.python_requirement || "not declared"}</code> · commit <code>{(run.git?.commit || "").slice(0, 10)}</code> · {run.git?.remote_url}</p>
        <table className="table">
          <thead><tr><th>Package</th><th>Risk</th><th>Declared</th><th>Used in</th><th>Indicators</th></tr></thead>
          <tbody>{pkgs.map(p => <tr key={p.normalized_name} onClick={() => go("Dependency Explorer", p.normalized_name)} className="clickable">
            <td><strong>{p.normalized_name}</strong>{p.groups.includes("dev") && <span className="tag">dev</span>}</td>
            <td><Band band={p.assessment.band} score={p.assessment.score} /></td>
            <td><code>{[...new Set(p.declarations.map(d => d.specifier || "any"))].join(" vs ")}</code></td>
            <td>{p.usage.source_files.length ? p.usage.source_files.join(", ") : <span className="muted-inline">{p.usage.status === "observed" ? "tests only" : "no static import"}</span>}</td>
            <td className="indicators">{p.assessment.indicators.filter(i => i.points > 0).map(i => <span key={i.indicator + i.source} className="ind" title={i.evidence}>{i.indicator.replaceAll("_", " ")}</span>)}</td>
          </tr>)}</tbody>
        </table>
      </Panel>

      <Panel title="Repository findings" eyebrow="OBSERVED IN SOURCE AND MANIFESTS">
        <ul className="findings">
          {run.undeclared_imports.map(u => <li key={u.import_name}><Evidence type="OBSERVED" /> <code>{u.import_name}</code> is imported at {u.locations.map(l => `${l.file}:${l.line}`).join(", ")} but not declared in any manifest — it is only present transitively.</li>)}
          {run.declaration_conflicts.map(c => <li key={c.package}><Evidence type="OBSERVED" /> <code>{c.package}</code> declared inconsistently: {c.declarations.map(d => `${d.source}:${d.line} ${d.specifier}`).join(" vs ")}</li>)}
          {run.commented_out_requirements.map(c => <li key={c.raw}><Evidence type="OBSERVED" /> Commented-out requirement <code>{c.raw}</code> at {c.source}:{c.line}</li>)}
          {run.warnings.map(w => <li key={w}><Evidence type="UNKNOWN" /> {w}</li>)}
          {!run.undeclared_imports.length && !run.declaration_conflicts.length && !run.commented_out_requirements.length && <li className="muted">No repository-level findings.</li>}
        </ul>
      </Panel>
    </>}
  </>;
}

function localStorageGet(key) { try { return window.localStorage.getItem(key); } catch { return null; } }
function localStorageSet(key, value) { try { window.localStorage.setItem(key, value); } catch { /* ignore */ } }
