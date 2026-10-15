import { useCallback, useEffect, useState } from "react";
import Overview from "./pages/Overview.jsx";
import DependencyExplorer from "./pages/DependencyExplorer.jsx";
import MigrationWorkbench from "./pages/MigrationWorkbench.jsx";
import VerificationCenter from "./pages/VerificationCenter.jsx";
import ExitCapsule from "./pages/ExitCapsule.jsx";
import { api } from "./services/api.js";

const pages = {
  Overview, "Dependency Explorer": DependencyExplorer,
  "Migration Workbench": MigrationWorkbench,
  "Verification Center": VerificationCenter, "Exit Capsule": ExitCapsule,
};

export default function App() {
  const [active, setActive] = useState("Overview");
  const [run, setRun] = useState(null);
  const [selected, setSelected] = useState(null);
  const [health, setHealth] = useState(null);
  const [healthError, setHealthError] = useState("");

  useEffect(() => {
    api.health().then(setHealth).catch(e => setHealthError(e.message));
  }, []);

  const loadRun = useCallback(async (id) => {
    const data = await api.getRun(id);
    setRun(data);
    return data;
  }, []);

  const refresh = useCallback(() => run ? loadRun(run.run_id) : Promise.resolve(null), [run, loadRun]);

  const go = (page, pkg) => { if (pkg) setSelected(pkg); setActive(page); };
  const Page = pages[active];
  const ai = health?.ai;

  return <div className="shell">
    <aside className="sidebar">
      <div className="brand"><span className="brand-mark">G</span><div><strong>GhostLib</strong><small>DEPENDENCY RESILIENCE</small></div></div>
      <div className="nav-label">WORKSPACE</div>
      {Object.keys(pages).map((name, i) => <button key={name} className={active === name ? "nav-item active" : "nav-item"}
        disabled={i > 0 && !run} title={i > 0 && !run ? "Run or open a scan first" : ""}
        onClick={() => setActive(name)}><span className="nav-num">0{i + 1}</span>{name}</button>)}
      <div className="sidebar-bottom">
        {healthError ? <><span className="status-dot bad" /> Backend offline</> : <><span className="status-dot" /> Backend connected</>}
        <small>{ai ? `Gemma: ${ai.model} · ${ai.configured ? "key configured" : "no API key"}` : "…"}</small>
      </div>
    </aside>
    <main className="main">
      <header className="topbar">
        <div><span className="eyebrow">GHOSTLIB / {run ? run.project?.name?.toUpperCase() || "RUN" : "NO RUN"}</span><h1>{active}</h1></div>
        {run && <span className="pill" title={run.repository}>RUN {run.run_id} · {(run.git?.commit || "").slice(0, 7)}</span>}
      </header>
      {healthError && <div className="alert">{healthError} Start it with <code>uvicorn app.main:app --app-dir backend</code>.</div>}
      <Page run={run} loadRun={loadRun} refresh={refresh} selected={selected} setSelected={setSelected} go={go} health={health} />
    </main>
  </div>;
}
