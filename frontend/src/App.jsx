import { useState } from "react";
import Overview from "./pages/Overview.jsx";
import DependencyExplorer from "./pages/DependencyExplorer.jsx";
import MigrationWorkbench from "./pages/MigrationWorkbench.jsx";
import VerificationCenter from "./pages/VerificationCenter.jsx";
import ExitCapsule from "./pages/ExitCapsule.jsx";

const pages = {
  Overview, "Dependency Explorer": DependencyExplorer,
  "Migration Workbench": MigrationWorkbench,
  "Verification Center": VerificationCenter, "Exit Capsule": ExitCapsule,
};

export default function App() {
  const [active, setActive] = useState("Overview");
  const Page = pages[active];
  return <div className="shell">
    <aside className="sidebar">
      <div className="brand"><span className="brand-mark">G</span><div><strong>GhostLib</strong><small>DEPENDENCY RESILIENCE</small></div></div>
      <div className="nav-label">WORKSPACE</div>
      {Object.keys(pages).map(name => <button key={name} className={active === name ? "nav-item active" : "nav-item"} onClick={() => setActive(name)}>{name}</button>)}
      <div className="sidebar-bottom"><span className="status-dot" /> Local-first workspace <small>Starter scaffold · v0.1</small></div>
    </aside>
    <main className="main">
      <header className="topbar"><div><span className="eyebrow">GHOSTLIB / WORKSPACE</span><h1>{active}</h1></div><span className="pill">PROTOTYPE SCAFFOLD</span></header>
      <Page />
    </main>
  </div>;
}
