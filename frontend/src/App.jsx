import { useEffect, useState } from "react";
import sample from "./sample-capsule.json";

const API = import.meta.env.VITE_API_URL;
const na = (v) => (v === undefined || v === null || v === "" ? "Not available" : v);
const dependencyInfo = (item) => item?.dependency || {};
const dependencyName = (item) => na(dependencyInfo(item).name);
const TABS = ["Overview", "Dependencies", "Migration", "Verification", "Capsule"];

function useCapsule() {
  const [state, setState] = useState({ data: sample, origin: "sample", warn: null, loading: !!API });
  useEffect(() => {
    if (!API) return;
    fetch(`${API}/api/capsule/latest`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`Backend returned ${r.status}`))))
      .then((data) => setState({ data, origin: "api", warn: null, loading: false }))
      .catch((e) => setState({ data: sample, origin: "sample", loading: false,
        warn: `Could not reach the backend (${e.message}). Showing sample data.` }));
  }, []);
  return [state, setState];
}

const Chip = ({ claim }) => (
  <span className="chips">
    {(Array.isArray(claim) ? claim : [claim || "UNKNOWN"]).map((c) => (
      <span key={c} className={`chip chip-${c.toLowerCase()}`}>{c}</span>
    ))}
  </span>
);

const vscode = (path, line) => `vscode://file/${encodeURI(path)}:${line}`;

function Ghost({ className }) {
  return (
    <svg className={className} viewBox="0 0 200 260" aria-hidden="true">
      <ellipse cx="150" cy="248" rx="120" ry="9" fill="#140b10" opacity=".55" transform="skewX(-40) translate(95 0)" />
      <path d="M30 120C30 56 66 18 100 18s70 38 70 102v120l-23-18-24 18-23-18-23 18-24-18-23 18z" fill="#140b10" />
      <ellipse cx="78" cy="104" rx="11" ry="15" fill="#f2e7d0" />
      <ellipse cx="122" cy="104" rx="11" ry="15" fill="#f2e7d0" />
      <ellipse cx="100" cy="150" rx="9" ry="13" fill="#f2e7d0" />
    </svg>
  );
}

function Burst() {
  const pts = Array.from({ length: 24 }, (_, i) => {
    const a = (i / 24) * Math.PI * 2, r = i % 2 ? 34 : 98;
    return `${100 + r * Math.cos(a)},${100 + r * Math.sin(a)}`;
  }).join(" ");
  return (
    <svg className="burst" viewBox="0 0 200 200" aria-hidden="true">
      <polygon points={pts} fill="#140b10" />
      <circle cx="100" cy="100" r="17" fill="#d9381e" />
      <circle cx="100" cy="100" r="7" fill="#140b10" />
    </svg>
  );
}

function Overview({ data, go }) {
  const deps = data.dependencies || [];
  const flagged = deps.filter((d) => (d.risk_indicators || []).length).length;
  const ran = deps.filter((d) => d.test_results?.candidate?.status && d.test_results.candidate.status !== "not_run").length;
  return (
    <>
      <section className="hero">
        <div className="hero-copy-l">
          <p>Dependencies that<br />haunt your repo.<br />Evidence for every<br />claim we make.</p>
        </div>
        <Burst />
        <h1 className="warp"><span>The</span><span>Ghost</span><span>Lib</span></h1>
        <Ghost className="hero-ghost" />
        <div className="hero-copy-r">
          <p>Scan a Python project, map where each package lives, test a replacement in a sandbox, and keep the receipts.</p>
          <button className="btn-bone" onClick={() => go("Dependencies")}>Open findings</button>
        </div>
      </section>
      <section className="stats">
        <div><b>{na(data.repository?.dependencies_scanned ?? deps.length)}</b><span>dependencies scanned</span></div>
        <div><b>{flagged}</b><span>need review</span></div>
        <div><b>{ran}</b><span>migrations tested</span></div>
        <div><b>{na(data.repository?.name)}</b><span>{na(data.environment?.python && "Python " + data.environment.python)}</span></div>
      </section>
      <section className="panel">
        <h2>Haunted packages</h2>
        {deps.length === 0 && <p className="empty">No dependencies found. Run <code>ghostwatch scan ./LinkWatch</code> and reload.</p>}
        {deps.map((d, i) => (
          <button key={i} className="row" onClick={() => go("Dependencies", i)}>
            <code>{dependencyName(d)}</code>
            <span className="muted">{na(dependencyInfo(d).declared_version)}</span>
            <span className="muted">{(d.usage_locations || []).length} usages</span>
            <span className="muted">{(d.risk_indicators || []).length} signals</span>
          </button>
        ))}
      </section>
    </>
  );
}

function Dependencies({ data, idx, setIdx }) {
  const deps = data.dependencies || [];
  const d = deps[idx];
  if (!d) return <p className="empty">Nothing to inspect yet.</p>;
  return (
    <div className="split">
      <aside className="list">
        {deps.map((x, i) => (
          <button key={i} className={i === idx ? "item on" : "item"} onClick={() => setIdx(i)}>
            <code>{dependencyName(x)}</code><small>{na(dependencyInfo(x).declared_version)}</small>
          </button>
        ))}
      </aside>
      <div className="detail">
        <h2>{dependencyName(d)} <small className="muted">{na(dependencyInfo(d).manifest)}</small></h2>
        <h3>Why it was flagged</h3>
        {(d.risk_indicators || []).map((r, i) => (
          <div className="ev" key={i}>
            <div><strong>{r.label}</strong><p>{na(r.detail)}</p><small className="muted">Source: {na(r.source)}</small></div>
            <Chip claim={r.claim} />
          </div>
        ))}
        <h3>Where it is used</h3>
        {(d.usage_locations || []).length === 0 && <p className="empty">No usages detected. Static analysis cannot rule out dynamic imports.</p>}
        {(d.usage_locations || []).map((u, i) => (
          <div className="usage" key={i}>
            <div className="usage-h">
              <code>{u.file}:{u.line}</code><Chip claim={u.claim} />
              <a href={vscode(u.file, u.line)}>Open in VS Code</a>
            </div>
            <pre>{na(u.snippet)}</pre>
          </div>
        ))}
        <h3>Limits of this analysis</h3>
        <ul>{(d.limitations || ["Not available"]).map((l, i) => <li key={i}>{l}</li>)}</ul>
      </div>
    </div>
  );
}

function Migration({ data, idx, setIdx, act }) {
  const deps = data.dependencies || [];
  const d = deps[idx];
  if (!d) return <p className="empty">Nothing to migrate yet.</p>;
  const m = d.migration || {};
  const cands = d.replacement_candidates || [];
  return (
    <>
      <div className="toolbar">
        <label>Dependency
          <select value={idx} onChange={(e) => setIdx(+e.target.value)}>
            {deps.map((x, i) => <option key={i} value={i}>{dependencyName(x)}</option>)}
          </select>
        </label>
        <span className={`state state-${m.status}`}>{na(m.status).replaceAll("_", " ")}</span>
      </div>
      <h3>Replacement tournament</h3>
      {cands.length === 0 && <p className="empty">No candidates yet. Ask the backend for Gemma suggestions.</p>}
      <div className="cands">
        {cands.map((c) => (
          <article key={c.name} className={m.selected === c.name ? "cand picked" : "cand"}>
            <header><code>{c.name}</code><Chip claim={c.claim} /></header>
            <dl>
              <dt>Exists on PyPI</dt><dd>{na(c.exists_on_pypi?.value)} <Chip claim={c.exists_on_pypi?.claim} /></dd>
              <dt>Python 3.12 / 3.13</dt><dd>{na(c.python_support?.value)} <Chip claim={c.python_support?.claim} /></dd>
              <dt>Migration effort</dt><dd>{na(c.effort)}</dd>
            </dl>
            <p className="pro">{(c.pros || []).join("; ") || "Not available"}</p>
            <p className="con">{(c.cons || []).join("; ") || "Not available"}</p>
            <button className="btn-line" onClick={() => act("select", d, c.name)}>Test this one</button>
          </article>
        ))}
      </div>
      <h3>Proposed diff <Chip claim={m.claim || "UNKNOWN"} /></h3>
      {m.diff ? <pre className="diff">{m.diff.split("\n").map((l, i) => (
        <span key={i} className={l.startsWith("+") ? "add" : l.startsWith("-") ? "del" : ""}>{l + "\n"}</span>
      ))}</pre> : <p className="empty">No diff generated.</p>}
      <div className="actions">
        <button className="btn-bone" disabled={m.status !== "awaiting_approval"} onClick={() => act("approve", d)}>Approve in sandbox</button>
        <button className="btn-line" disabled={m.status !== "awaiting_approval"} onClick={() => act("reject", d)}>Reject</button>
        <button className="btn-line" disabled={!m.selected} onClick={() => act("discard", d)}>Discard candidate</button>
      </div>
      <p className="muted">Approved changes touch the sandbox copy only. Your repository is never modified.</p>
    </>
  );
}

function Run({ title, r = {} }) {
  return (
    <div className="run">
      <h3>{title}</h3>
      <span className={`state state-${r.status}`}>{na(r.status).replaceAll("_", " ")}</span>
      <p><span className="muted">Command</span><br /><code>{na(r.command)}</code></p>
      <p><span className="muted">Exit code</span><br /><code>{na(r.exit_code)}</code></p>
    </div>
  );
}

function Verification({ data, idx }) {
  const d = (data.dependencies || [])[idx];
  if (!d) return <p className="empty">Nothing verified yet.</p>;
  const t = d.test_results || {}, b = d.behavioral_comparison || {};
  return (
    <>
      <h2>{dependencyName(d)}</h2>
      <div className="runs"><Run title="Original baseline" r={t.baseline} /><Run title="Candidate" r={t.candidate} /></div>
      <h3>Behavioural comparison</h3>
      <p className="note">Passing tests do not prove the two packages behave the same.</p>
      <div className="runs">
        <div className="run"><h3>Checked</h3>{(b.checked || []).length ? <ul>{b.checked.map((c, i) => <li key={i}>{typeof c === "string" ? c : JSON.stringify(c)}</li>)}</ul> : <p className="empty">Nothing compared yet.</p>}</div>
        <div className="run"><h3>Not tested</h3>{(b.untested || []).length ? <ul>{b.untested.map((c, i) => <li key={i}>{c}</li>)}</ul> : <p className="empty">Not available</p>}</div>
      </div>
    </>
  );
}

function toMarkdown(c) {
  const out = [`# Dependency Exit Capsule`, `Repository: ${na(c.repository?.name)}`, `Generated: ${na(c.generated_at)}`, ""];
  (c.dependencies || []).forEach((d) => {
    out.push(`## ${dependencyName(d)} ${na(dependencyInfo(d).declared_version)}`);
    (d.risk_indicators || []).forEach((r) => out.push(`- [${[].concat(r.claim).join("+")}] ${r.label}: ${na(r.detail)}`));
    (d.limitations || []).forEach((l) => out.push(`- Limitation: ${l}`));
    out.push("");
  });
  return out.join("\n");
}
function download(name, text, type) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([text], { type }));
  a.download = name; a.click(); URL.revokeObjectURL(a.href);
}

function Capsule({ data, setState }) {
  const load = (e) => {
    const f = e.target.files?.[0]; if (!f) return;
    f.text().then((t) => { try { setState({ data: JSON.parse(t), origin: "file", warn: null, loading: false }); }
      catch { setState((s) => ({ ...s, warn: "That file is not valid JSON." })); } });
  };
  return (
    <>
      <h2>Exit Capsule</h2>
      <dl className="kv">
        <dt>Repository</dt><dd>{na(data.repository?.name)}</dd>
        <dt>Commit</dt><dd><code>{na(data.repository?.commit)}</code></dd>
        <dt>Python</dt><dd>{na(data.environment?.python)}</dd>
        <dt>AI model</dt><dd>{na(data.environment?.model)}</dd>
        <dt>Generated</dt><dd>{na(data.generated_at)}</dd>
      </dl>
      <div className="actions">
        <button className="btn-bone" onClick={() => download("capsule.json", JSON.stringify(data, null, 2), "application/json")}>Export capsule.json</button>
        <button className="btn-line" onClick={() => download("capsule.md", toMarkdown(data), "text/markdown")}>Export capsule.md</button>
        <label className="btn-line file">Load a capsule.json<input type="file" accept=".json" onChange={load} hidden /></label>
      </div>
      <h3>Reproduce</h3>
      <pre>{`ghostwatch scan ./LinkWatch\n# then reload this dashboard`}</pre>
    </>
  );
}

export default function App() {
  const [{ data, origin, warn, loading }, setState] = useCapsule();
  const [tab, setTab] = useState("Overview");
  const [idx, setIdx] = useState(0);
  const go = (nextTab, nextIndex) => {
    setTab(nextTab);
    if (nextIndex !== undefined) setIdx(nextIndex);
  };
  const act = (kind, dependency, candidate) => {
    if (!API) return alert("Connect the backend (VITE_API_URL) to run this action.");
    fetch(`${API}/api/migration/${kind}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ dependency: dependencyName(dependency), candidate })
    })
      .then((response) => (response.ok ? response.json() : Promise.reject(new Error(response.status))))
      .then(() => fetch(`${API}/api/capsule/latest`))
      .then((response) => (response.ok ? response.json() : Promise.reject(new Error(response.status))))
      .then((nextData) => setState({ data: nextData, origin: "api", warn: null, loading: false }))
      .catch((error) => setState((state) => ({ ...state, warn: `Action failed: ${error.message}` })));
  };
  return (
    <>
      <svg width="0" height="0" style={{ position: "absolute" }} aria-hidden="true">
        <filter id="melt">
          <feTurbulence type="fractalNoise" baseFrequency="0.010 0.018" numOctaves="2" seed="7" result="n" />
          <feDisplacementMap in="SourceGraphic" in2="n" scale="34" xChannelSelector="R" yChannelSelector="G" />
        </filter>
      </svg>
      <header className="nav">
        <strong className="mark">GhostLib</strong>
        <nav>{TABS.map((name) => <button key={name} className={name === tab ? "on" : ""} onClick={() => go(name)}>{name}</button>)}</nav>
        <span className="muted">{origin === "sample" ? "sample data" : origin === "file" ? "loaded file" : "live"}</span>
      </header>
      {warn && <div className="banner warn">{warn}</div>}
      <main>
        {loading ? <p className="empty">Summoning the capsule...</p> : (
          <>
            {tab === "Overview" && <Overview data={data} go={go} />}
            {tab === "Dependencies" && <Dependencies data={data} idx={idx} setIdx={setIdx} />}
            {tab === "Migration" && <Migration data={data} idx={idx} setIdx={setIdx} act={act} />}
            {tab === "Verification" && <Verification data={data} idx={idx} />}
            {tab === "Capsule" && <Capsule data={data} setState={setState} />}
          </>
        )}
      </main>
    </>
  );
}
