import { useEffect, useState } from "react";
import Panel from "../components/Panel.jsx";
import { Band, Evidence } from "../components/Badge.jsx";
import { api } from "../services/api.js";

export default function DependencyExplorer({ run, selected, setSelected, go }) {
  const pkgs = run?.packages || [];
  const pkg = pkgs.find(p => p.normalized_name === selected) || pkgs[0];
  const [source, setSource] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => { setSource(null); setError(""); }, [pkg?.normalized_name]);
  if (!pkg) return <Panel title="No packages" eyebrow="STATIC ANALYSIS"><p className="muted">This run found no dependency declarations.</p></Panel>;

  async function openSource(loc) {
    setError("");
    try { setSource(await api.source(run.run_id, loc.file, loc.line)); } catch (e) { setError(e.message); }
  }
  const meta = pkg.metadata || {};
  const pin = meta.pinned;

  return <div className="split">
    <div className="pkg-list">
      {pkgs.map(p => <button key={p.normalized_name} className={p.normalized_name === pkg.normalized_name ? "pkg active" : "pkg"}
        onClick={() => setSelected(p.normalized_name)}><span>{p.normalized_name}</span><Band band={p.assessment.band} score={p.assessment.score} /></button>)}
    </div>
    <div>
      <Panel title={pkg.normalized_name} eyebrow="IMPACT DNA">
        <div className="actions"><button className="secondary" onClick={() => go("Migration Workbench", pkg.normalized_name)}>Plan a migration →</button></div>
        <h3><Evidence type="OBSERVED" /> Declarations</h3>
        <ul className="plain">{pkg.declarations.map((d, i) => <li key={i}><code>{d.raw}</code> — {d.source}{d.line ? `:${d.line}` : ""} <span className="tag">{d.group}</span></li>)}</ul>

        <h3><Evidence type={meta.status === "fetched" ? "SOURCED" : "UNKNOWN"} /> PyPI metadata</h3>
        {meta.status === "fetched" ? <div className="kv">
          <span>Latest</span><b>{meta.latest_version}</b>
          <span>Most recent upload</span><b>{(meta.most_recent_upload || "?").slice(0, 10)}</b>
          <span>Requires-Python</span><b>{meta.requires_python || "not declared"}</b>
          <span>Python classifiers</span><b>{(meta.python_classifiers || []).join(", ") || "none"}</b>
          {pin && <><span>Pinned version</span><b>{pin.version} · released {(pin.release_date || "?").slice(0, 10)}{pin.yanked ? " · YANKED" : ""}</b></>}
          <span>Source</span><b><a href={meta.source} target="_blank" rel="noreferrer">{meta.source}</a> · {meta.retrieved_at?.slice(0, 19)}</b>
        </div> : <p className="muted">{meta.status}: {meta.reason || "metadata not available"}</p>}

        <h3>Risk indicators <Band band={pkg.assessment.band} score={pkg.assessment.score} /></h3>
        {pkg.assessment.indicators.length ? <ul className="plain">{pkg.assessment.indicators.map((i, k) => <li key={k}>
          <Evidence type={i.evidence_type} /> <strong>{i.indicator.replaceAll("_", " ")}</strong> <span className="tag">+{i.points}</span><br />
          <span className="evidence-text">{i.evidence}</span>{i.source && <span className="muted-inline"> — {i.source}</span>}</li>)}</ul>
          : <p className="muted">No indicators fired.</p>}
        <p className="muted">{pkg.assessment.disclaimer}</p>

        <h3><Evidence type="OBSERVED" /> Usage locations <span className="tag">mapping: {pkg.mapping_confidence}</span></h3>
        {pkg.locations.length ? <table className="table compact"><thead><tr><th>Location</th><th>Statement</th><th>Symbols used</th></tr></thead>
          <tbody>{pkg.locations.map((l, i) => <tr key={i} className="clickable" onClick={() => openSource(l)}>
            <td><code>{l.file}:{l.line}</code>{l.is_test && <span className="tag">test</span>}{l.private_api.length > 0 && <span className="tag warn">private API</span>}</td>
            <td><code>{l.statement}</code></td><td>{l.symbols_used.join(", ") || "—"}</td></tr>)}</tbody></table>
          : <p className="muted">No static imports of {pkg.import_names.join(", ")} found. It may be unused, or used dynamically/indirectly.</p>}
        {error && <div className="alert">{error}</div>}
        {source && <div className="source"><div className="source-head">{source.file} <Evidence type="OBSERVED" /></div>
          <pre>{source.lines.map(l => <div key={l.n} className={l.n === source.line ? "hl" : ""}><span className="ln">{l.n}</span>{l.text}</div>)}</pre></div>}

        <h3><Evidence type="OBSERVED" /> Relevant tests</h3>
        <p>{pkg.usage.relevant_tests.length ? pkg.usage.relevant_tests.map(t => <code key={t} className="chip">{t}</code>) : "None found"}
          {pkg.usage.coverage_gap && <span className="tag warn">coverage gap: no test reaches {pkg.usage.source_files.join(", ")}</span>}</p>
        <p className="muted">Tests are related through static (including transitive and function-level) imports; this does not measure line coverage.</p>
      </Panel>
    </div>
  </div>;
}
