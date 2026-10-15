import { Fragment, useCallback, useEffect, useRef, useState } from "react";
import { api } from "./services/api.js";

const na = (v) => (v === undefined || v === null || v === "" ? "Not available" : v);
const TABS = ["Overview", "Dependencies", "Migration", "Verification", "Capsule"];
const CHIP_CLASS = {
  OBSERVED: "observed", SOURCED: "sourced", "EXECUTION-VERIFIED": "verified",
  "AI-RECOMMENDED": "suggested", UNKNOWN: "unknown",
};
const storage = {
  get: (k) => { try { return window.localStorage.getItem(k); } catch { return null; } },
  set: (k, v) => { try { window.localStorage.setItem(k, v); } catch { /* private mode */ } },
};

const Chip = ({ claim }) => (
  <span className="chips">
    {(Array.isArray(claim) ? claim : [claim || "UNKNOWN"]).map((c) => (
      <span key={c} className={`chip chip-${CHIP_CLASS[c] || "unknown"}`} title={c}>{c}</span>
    ))}
  </span>
);

const State = ({ value }) => <span className={`state state-${value}`}>{na(value).replaceAll("_", " ")}</span>;

const vscode = (path, line) => `vscode://file/${encodeURI(path.replaceAll("\\", "/"))}:${line}`;

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

function Diff({ text }) {
  if (!text) return <p className="empty">No file changes.</p>;
  return <pre className="diff">{text.split("\n").map((l, i) => (
    <span key={i} className={l.startsWith("+++") || l.startsWith("---") ? "file" : l.startsWith("+") ? "add" : l.startsWith("-") ? "del" : l.startsWith("@@") ? "hunk" : ""}>{l + "\n"}</span>
  ))}</pre>;
}

/* ------------------------------------------------------------------ Overview */

function Overview({ run, runs, openRun, scan, go }) {
  const [repo, setRepo] = useState(() => storage.get("ghostlib.repo") || "");
  const [fetchMeta, setFetchMeta] = useState(true);
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (!repo && runs[0]) setRepo(runs[0].repository); }, [runs, repo]);
  const pkgs = run?.packages || [];
  const flagged = pkgs.filter((p) => p.assessment.score > 0).length;
  const tested = Object.values(run?.experiments || {}).filter((e) => e.state === "completed").length;

  const submit = async (e) => {
    e.preventDefault(); setBusy(true); storage.set("ghostlib.repo", repo);
    try { await scan(repo, fetchMeta); } finally { setBusy(false); }
  };

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
          <button className="btn-bone" disabled={!run} onClick={() => go("Dependencies")}>Open findings</button>
        </div>
      </section>

      <section className="panel scan">
        <h2>Summon a scan</h2>
        <form onSubmit={submit}>
          <label className="field">Absolute path to a local checkout
            <input value={repo} onChange={(e) => setRepo(e.target.value)} placeholder="C:\path\to\LinkWatch" required />
          </label>
          <label className="check"><input type="checkbox" checked={fetchMeta} onChange={(e) => setFetchMeta(e.target.checked)} />
            Fetch PyPI metadata (network; cached 24 h)</label>
          <div className="actions">
            <button className="btn-bone" disabled={busy}>{busy ? "Scanning..." : "Run scan"}</button>
          </div>
          <p className="muted small">The backend only reads this folder. It never runs repository code during a scan and never modifies it.</p>
        </form>
        {runs.length > 0 && <>
          <h3>Previous runs</h3>
          {runs.slice(0, 6).map((r) => (
            <button key={r.run_id} className={`row runrow ${run?.run_id === r.run_id ? "on" : ""}`} onClick={() => openRun(r.run_id)}>
              <code>{r.run_id}</code><span className="muted ellipsis">{r.repository}</span>
              <span className="muted">{r.packages} packages</span><span className="muted">{(r.commit || "").slice(0, 7)}</span>
            </button>
          ))}
        </>}
      </section>

      {run && <>
        <section className="stats">
          <div><b>{pkgs.length}</b><span>dependencies scanned</span></div>
          <div><b>{flagged}</b><span>need review</span></div>
          <div><b>{tested}</b><span>migrations tested</span></div>
          <div><b>{na(run.project?.name)}</b><span>requires-python {na(run.python_requirement)} · {(run.git?.commit || "").slice(0, 7)}</span></div>
        </section>
        <section className="panel">
          <h2>Haunted packages</h2>
          <p className="muted small">Ranked by a transparent rule score. Each point links to its evidence; it is not a probability.</p>
          <div className="row head"><span>Package</span><span>Declared</span><span>Usages</span><span>Risk</span></div>
          {pkgs.map((p) => (
            <button key={p.normalized_name} className="row" onClick={() => go("Dependencies", p.normalized_name)}>
              <code>{p.normalized_name}{p.groups.includes("dev") ? " (dev)" : ""}</code>
              <span className="muted">{[...new Set(p.declarations.map((d) => d.specifier || "any"))].join(" vs ")}</span>
              <span className="muted">{p.locations.length} usages</span>
              <span><span className={`band band-${p.assessment.band}`}>{p.assessment.band} · {p.assessment.score}</span></span>
            </button>
          ))}
        </section>
        <section className="panel">
          <h2>Repository findings</h2>
          {run.undeclared_imports.map((u) => <div className="ev" key={u.import_name}><div><strong>Undeclared import <code>{u.import_name}</code></strong>
            <p>{u.locations.map((l) => `${l.file}:${l.line}`).join(", ")} imports it, but no manifest declares it. It is only present transitively.</p></div><Chip claim="OBSERVED" /></div>)}
          {run.declaration_conflicts.map((c) => <div className="ev" key={c.package}><div><strong>Conflicting declarations for <code>{c.package}</code></strong>
            <p>{c.declarations.map((d) => `${d.source}:${d.line} ${d.specifier}`).join(" vs ")}</p></div><Chip claim="OBSERVED" /></div>)}
          {run.commented_out_requirements.map((c) => <div className="ev" key={c.raw}><div><strong>Commented-out requirement</strong>
            <p><code>{c.raw}</code> at {c.source}:{c.line}</p></div><Chip claim="OBSERVED" /></div>)}
          {!run.undeclared_imports.length && !run.declaration_conflicts.length && !run.commented_out_requirements.length &&
            <p className="empty">No repository-level findings.</p>}
        </section>
      </>}
    </>
  );
}

/* ------------------------------------------------------------- Dependencies */

function Dependencies({ run, selected, select }) {
  const pkgs = run.packages;
  const p = pkgs.find((x) => x.normalized_name === selected) || pkgs[0];
  const [snippets, setSnippets] = useState({});
  useEffect(() => {
    if (!p) return;
    let alive = true;
    Promise.all(p.locations.slice(0, 12).map((l) =>
      api.source(run.run_id, l.file, l.line, 3).then((s) => [`${l.file}:${l.line}`, s]).catch(() => null)))
      .then((pairs) => alive && setSnippets(Object.fromEntries(pairs.filter(Boolean))));
    return () => { alive = false; };
  }, [run.run_id, p?.normalized_name]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!p) return <p className="empty">This run found no dependency declarations.</p>;
  const m = p.metadata || {};
  const pin = m.pinned;
  return (
    <div className="split">
      <aside className="list">
        {pkgs.map((x) => (
          <button key={x.normalized_name} className={x === p ? "item on" : "item"} onClick={() => select(x.normalized_name)}>
            <code>{x.normalized_name}</code><small>{x.assessment.band} · {x.assessment.score} · {[...new Set(x.declarations.map((d) => d.specifier || "any"))].join(" vs ")}</small>
          </button>
        ))}
      </aside>
      <div className="detail">
        <h2>{p.normalized_name} <small className="muted">{p.declarations.map((d) => `${d.source}${d.line ? ":" + d.line : ""}`).join(", ")}</small></h2>

        <h3>Declared as <Chip claim="OBSERVED" /></h3>
        <ul>{p.declarations.map((d, i) => <li key={i}><code>{d.raw}</code> in {d.source}{d.line ? `:${d.line}` : ""} ({d.group})</li>)}</ul>

        <h3>PyPI facts <Chip claim={m.status === "fetched" ? "SOURCED" : "UNKNOWN"} /></h3>
        {m.status === "fetched" ? <dl className="kv">
          <dt>Latest</dt><dd>{m.latest_version}</dd>
          <dt>Last upload</dt><dd>{(m.most_recent_upload || "").slice(0, 10)}</dd>
          <dt>Requires-Python</dt><dd>{na(m.requires_python)}</dd>
          <dt>Classifiers</dt><dd>{(m.python_classifiers || []).join(", ") || "none"}</dd>
          {pin && <><dt>Pinned</dt><dd>{pin.version} · released {(pin.release_date || "?").slice(0, 10)}{pin.yanked ? " · YANKED" : ""}</dd></>}
          <dt>Source</dt><dd><a href={m.source} target="_blank" rel="noreferrer">{m.source}</a> <span className="muted">· {(m.retrieved_at || "").slice(0, 19)}</span></dd>
        </dl> : <p className="empty">{m.status}: {m.reason || "metadata not available"}</p>}

        <h3>Why it was flagged <span className={`band band-${p.assessment.band}`}>{p.assessment.band} · {p.assessment.score}</span></h3>
        {p.assessment.indicators.length === 0 && <p className="empty">No indicators fired.</p>}
        {p.assessment.indicators.map((r, i) => (
          <div className="ev" key={i}>
            <div><strong>{r.indicator.replaceAll("_", " ")} <span className="muted">+{r.points}</span></strong><p>{r.evidence}</p>
              {r.source && <small className="muted">Source: {r.source}</small>}</div>
            <Chip claim={r.evidence_type} />
          </div>
        ))}
        <p className="muted small">{p.assessment.disclaimer}</p>

        <h3>Where it is used <Chip claim="OBSERVED" /> <small className="muted">import mapping: {p.mapping_confidence}</small></h3>
        {p.locations.length === 0 && <p className="empty">No static import of {p.import_names.join(", ")} found. It may be unused, or used dynamically.</p>}
        {p.locations.map((u, i) => {
          const s = snippets[`${u.file}:${u.line}`];
          return (
            <div className="usage" key={i}>
              <div className="usage-h">
                <code>{u.file}:{u.line}</code>
                {u.is_test && <span className="state">test</span>}
                {u.private_api.length > 0 && <span className="state state-warn">private API: {u.private_api.join(", ")}</span>}
                <span className="muted small">{u.symbols_used.join(", ")}</span>
                <a href={vscode(`${run.repository}/${u.file}`, u.line)}>Open in VS Code</a>
              </div>
              <pre>{s ? s.lines.map((l) => <span key={l.n} className={l.n === u.line ? "hl" : ""}>{String(l.n).padStart(4)}  {l.text}{"\n"}</span>) : u.statement}</pre>
            </div>
          );
        })}

        <h3>Relevant tests <Chip claim="OBSERVED" /></h3>
        {p.usage.relevant_tests.length ? <ul>{p.usage.relevant_tests.map((t) => <li key={t}><code>{t}</code></li>)}</ul>
          : <p className="empty">No test reaches this code.</p>}
        {p.usage.coverage_gap && <p className="note">Coverage gap: no test imports {p.usage.source_files.join(", ")}.</p>}

        <h3>Limits of this analysis</h3>
        <ul>{run.limitations.map((l, i) => <li key={i} className="muted">{l}</li>)}</ul>
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- Migration */

function Migration({ run, health, selected, select, refresh, go, setWarn }) {
  const pkgs = run.packages;
  const p = pkgs.find((x) => x.normalized_name === selected) || pkgs[0];
  const name = p.normalized_name;
  const rec = run.recommendations?.[name];
  const [exp, setExp] = useState(run.experiments?.[name] || null);
  const [busy, setBusy] = useState("");
  const [confirm, setConfirm] = useState(false);
  const [python, setPython] = useState("3.12");
  const poll = useRef(null);
  const aiReady = !!health?.ai?.configured;
  const ok = rec?.status === "ok";

  useEffect(() => { setExp(run.experiments?.[name] || null); setConfirm(false); }, [name, run]);
  useEffect(() => {
    clearInterval(poll.current);
    if (exp?.state !== "running") return undefined;
    poll.current = setInterval(async () => {
      try {
        const latest = await api.experiment(run.run_id, name);
        setExp(latest);
        if (latest.state !== "running") { clearInterval(poll.current); refresh(); }
      } catch (e) { setWarn(e.message); clearInterval(poll.current); }
    }, 2500);
    return () => clearInterval(poll.current);
  }, [exp?.state, name, run.run_id, refresh, setWarn]);

  const act = async (label, fn) => {
    setBusy(label); setWarn(null);
    try { await fn(); } catch (e) { setWarn(e.message); } finally { setBusy(""); }
  };
  const askGemma = () => act("ai", async () => { await api.recommend(run.run_id, name); await refresh(); });
  const propose = (candidate, kind) => act("propose", async () => {
    setExp(await api.propose(run.run_id, name, { candidate, kind })); setConfirm(false);
  });
  const approve = () => act("approve", async () => setExp(await api.approve(run.run_id, name, { confirm: true, python, approved_by: "dashboard user" })));
  const reject = () => act("reject", async () => { setExp(await api.reject(run.run_id, name, "Rejected in dashboard")); await refresh(); });

  const validation = (pkgName) => (rec?.candidate_validation || []).find((v) => v.package === pkgName);
  const check = (v, key) => v?.checks.find((c) => c.check === key);
  const cards = ok ? rec.recommendation.candidates.map((c) => ({ ...c, v: validation(c.package), ai: true })) : [];
  if (!cards.some((c) => c.kind === "upgrade" && c.package === name))
    cards.push({ package: name, kind: "upgrade", rationale: `Pin ${name} to its latest PyPI release (deterministic, no AI).`, pros: [], cons: [], ai: false });
  if (p.usage.status === "not_observed_static" && !cards.some((c) => c.kind === "remove"))
    cards.push({ package: name, kind: "remove", rationale: "No static import was observed; remove the declaration.", pros: [], cons: [], ai: false });
  const picked = exp && exp.state !== "rejected" ? exp.candidate : null;

  return (
    <>
      <div className="toolbar">
        <label>Dependency
          <select value={name} onChange={(e) => select(e.target.value)} disabled={exp?.state === "running"}>
            {pkgs.map((x) => <option key={x.normalized_name} value={x.normalized_name}>{x.normalized_name} ({x.assessment.band} · {x.assessment.score})</option>)}
          </select>
        </label>
        <State value={exp ? exp.state : "no_experiment"} />
      </div>

      <h3>Ask Gemma 4 <Chip claim="AI-RECOMMENDED" /></h3>
      <div className="actions">
        <button className="btn-bone" disabled={!aiReady || !!busy} onClick={askGemma}
          title={aiReady ? "" : "Set GEMINI_API_KEY in backend/.env and restart the backend"}>
          {busy === "ai" ? "Asking Gemma..." : ok ? "Ask again" : "Get recommendation"}</button>
        <span className="muted small">{health?.ai?.model} sees only collected evidence: declarations, PyPI facts, usage snippets.</span>
      </div>
      {!aiReady && <p className="note">Gemma 4 is not configured (AI_UNAVAILABLE). No AI output is shown or invented. Deterministic experiments still work.</p>}
      {rec && !ok && <p className="note">Gemma status <code>{rec.status}</code>: {rec.reason}</p>}
      {ok && <div className="ai">
        <p>{rec.recommendation.summary}</p>
        <p className="muted small">{rec.model_version || rec.model} · {(rec.requested_at || "").slice(0, 19)} · recommended <strong>{rec.recommendation.recommended}</strong></p>
        <div className="runs">
          <div><h4>Migration steps</h4><ol>{rec.recommendation.migration_steps.map((s, i) => <li key={i}>{s}</li>)}</ol></div>
          <div>
            {rec.recommendation.breaking_changes.length > 0 && <><h4>Possible breaking changes</h4><ul>{rec.recommendation.breaking_changes.map((s, i) => <li key={i}>{s}</li>)}</ul></>}
            {rec.recommendation.suggested_tests.length > 0 && <><h4>Suggested tests</h4><ul>{rec.recommendation.suggested_tests.map((t, i) => <li key={i}><code>{t.name}</code>: {t.description}</li>)}</ul></>}
            {rec.recommendation.uncertainties.length > 0 && <><h4>Model's own uncertainties</h4><ul>{rec.recommendation.uncertainties.map((s, i) => <li key={i}>{s}</li>)}</ul></>}
          </div>
        </div>
      </div>}

      <h3>Replacement tournament</h3>
      <div className="cands">
        {cards.map((c, i) => {
          const exists = check(c.v, "exists_on_pypi") || check(c.v, "is_stdlib_module") || check(c.v, "no_static_import_observed");
          const support = check(c.v, "declared_python_support");
          return (
            <article key={`${i}-${c.kind}-${c.package}`} className={picked === c.package && exp?.kind === c.kind ? "cand picked" : "cand"}>
              <header><code>{c.package}</code><span className="chips"><span className="state">{c.kind}</span>{c.ai ? <Chip claim="AI-RECOMMENDED" /> : <span className="state">deterministic</span>}</span></header>
              <p>{c.rationale}</p>
              {c.ai && <dl>
                <dt>{c.kind === "stdlib" ? "In stdlib" : c.kind === "remove" ? "Unused in scan" : "Exists on PyPI"}</dt>
                <dd>{na(exists?.result)} {exists && <Chip claim={exists.evidence_type} />}</dd>
                <dt>Python 3.12 / 3.13</dt>
                <dd>{support ? Object.values(support.result).join(" / ").replaceAll("_", " ") : c.kind === "stdlib" ? "verified on running Python only" : "Not available"} {support && <Chip claim="SOURCED" />}</dd>
              </dl>}
              {c.pros.length > 0 && <p className="pro">{c.pros.join("; ")}</p>}
              {c.cons.length > 0 && <p className="con">{c.cons.join("; ")}</p>}
              <button className="btn-line" disabled={!!busy || exp?.state === "running"} onClick={() => propose(c.package, c.kind)}>
                {busy === "propose" ? "Building diff..." : "Test this one"}</button>
            </article>
          );
        })}
      </div>

      {exp && <>
        <h3>Proposed diff {exp.code_proposal?.status === "ok" ? <Chip claim="AI-RECOMMENDED" /> : <span className="state">deterministic manifest edit</span>}</h3>
        {(exp.notes || []).map((n, i) => <p key={i} className="muted small">{n}</p>)}
        {exp.code_proposal?.status && !["ok", "not_requested"].includes(exp.code_proposal.status) &&
          <p className="note">Gemma code changes: {exp.code_proposal.status} {exp.code_proposal.reason || ""}</p>}
        <Diff text={exp.diff} />
        {exp.state === "proposed" && <>
          <label className="check"><input type="checkbox" checked={confirm} onChange={(e) => setConfirm(e.target.checked)} />
            I reviewed this diff. Apply it to a disposable copy and run baseline and candidate tests.</label>
          <div className="actions">
            <select value={python} onChange={(e) => setPython(e.target.value)}><option value="3.12">Python 3.12</option><option value="3.13">Python 3.13</option></select>
            <button className="btn-bone" disabled={!confirm || !!busy} onClick={approve}>Approve in sandbox</button>
            <button className="btn-line" disabled={!!busy} onClick={reject}>Reject</button>
          </div>
        </>}
        {exp.state === "running" && <p className="note">Running: creating virtualenvs, installing, and executing pytest for baseline and candidate (about a minute)...</p>}
        {exp.state === "failed" && <p className="note">Experiment failed: {exp.error}</p>}
        {exp.state === "rejected" && <p className="note">{exp.discard_note}</p>}
        {exp.state === "completed" && <div className="actions">
          <State value={exp.comparison.verdict} />
          <button className="btn-bone" onClick={() => go("Verification", name)}>See verification</button>
          <button className="btn-line" onClick={reject}>Discard candidate</button>
        </div>}
        <p className="muted small">{exp.isolation}</p>
      </>}
      {!exp && <p className="muted">Approved changes touch the sandbox copy only. Your repository is never modified.</p>}
    </>
  );
}

/* ------------------------------------------------------------- Verification */

function Run({ title, r, runId, pkg, side }) {
  if (!r) return <div className="run"><h3>{title}</h3><p className="empty">Not run.</p></div>;
  return (
    <div className="run">
      <h3>{title} <Chip claim="EXECUTION-VERIFIED" /></h3>
      <State value={r.status} />
      <p><span className="muted">Python</span><br /><code>{na(r.python_version)}</code></p>
      <p><span className="muted">Result</span><br />{na(r.summary_line || r.blocker)}</p>
      <dl>{r.commands.map((c) => <Fragment key={c.label}><dt><code>{c.label}</code></dt>
        <dd>exit <code>{c.timed_out ? "timeout" : String(c.exit_code)}</code> · {c.duration_seconds}s · <a href={api.logUrl(runId, pkg, `${c.label}.log`, side)} target="_blank" rel="noreferrer">log</a></dd></Fragment>)}</dl>
      {r.ai_tests && <div className="ai small-pad">
        <p><Chip claim={["AI-RECOMMENDED", "EXECUTION-VERIFIED"]} /></p>
        <p>Gemma-written tests <code>{r.ai_tests.files.join(", ")}</code>: <State value={r.ai_tests.status} /> {r.ai_tests.summary_line}</p>
        {(r.ai_tests.first_errors || []).length > 0 && <p className="muted small">{r.ai_tests.first_errors.join("; ")}</p>}
        <p className="muted small">{r.ai_tests.note}</p>
      </div>}
      {(r.warnings || []).length > 0 && <><h4>Warnings emitted</h4><ul>{r.warnings.map((w) => <li key={w} className="muted small">{w}</li>)}</ul></>}
    </div>
  );
}

function Verification({ run, capsule, selected, select, go }) {
  const exps = Object.values(run.experiments || {});
  if (!exps.length) return <>
    <h2>Verification</h2>
    <p className="empty">Nothing has been executed yet. Results appear only after GhostLib actually runs baseline and candidate tests.</p>
    <div className="actions"><button className="btn-bone" onClick={() => go("Migration")}>Open Migration</button></div>
  </>;
  const e = exps.find((x) => x.package === selected) || exps.find((x) => x.state === "completed") || exps[0];
  const gaps = (capsule?.dependencies || []).find((d) => d.package === e.package)?.compatibility_gaps || [];
  const c = e.comparison;
  return (
    <>
      <div className="toolbar">
        <label>Experiment
          <select value={e.package} onChange={(ev) => select(ev.target.value)}>
            {exps.map((x) => <option key={x.package} value={x.package}>{x.package} → {x.manifest_requirement || x.candidate} ({x.state})</option>)}
          </select>
        </label>
        {c && <State value={c.verdict} />}
      </div>
      <h2>{e.package} → {e.manifest_requirement || e.candidate}</h2>
      {e.state !== "completed" ? <p className="empty">{e.error || e.discard_note || `State: ${e.state}. No execution results exist.`}</p> : <>
        <section className="stats">
          <div><b>{c.counts.fixed}</b><span>fixed</span></div>
          <div><b>{c.counts.regression}</b><span>regressions</span></div>
          <div><b>{c.counts.still_failing}</b><span>still failing</span></div>
          <div><b>{String(e.original_repository_check?.unchanged)}</b><span>original repo unchanged</span></div>
        </section>
        <div className="runs">
          <Run title="Original baseline" r={e.baseline_run} runId={run.run_id} pkg={e.package} side="baseline" />
          <Run title="Candidate" r={e.candidate_run} runId={run.run_id} pkg={e.package} side="candidate" />
        </div>
        <h3>Behavioural comparison</h3>
        <p className="note">{c.caveat}</p>
        <div className="runs">
          <div className="run"><h3>Checked <Chip claim="EXECUTION-VERIFIED" /></h3>
            <ul>{c.tests.map((t) => <li key={t.test}><code>{t.test}</code>: {na(t.baseline)} → {na(t.candidate)} <State value={t.change} /></li>)}</ul>
            {Object.entries(c.installed_version_changes).map(([k, v]) => <p key={k} className="muted small">Installed <code>{k}</code>: {na(v.baseline)} → {na(v.candidate)}</p>)}
            {c.warnings_removed.length > 0 && <p className="muted small">Warnings gone: {c.warnings_removed.join("; ")}</p>}
            {c.warnings_added.length > 0 && <p className="muted small">New warnings: {c.warnings_added.join("; ")}</p>}
          </div>
          <div className="run"><h3>Gaps and not tested</h3>
            {gaps.length ? <ul>{gaps.map((g, i) => <li key={i}><Chip claim={g.type} /> {g.gap}</li>)}</ul> : <p className="empty">None recorded.</p>}
          </div>
        </div>
        <h3>Approved diff</h3>
        <p className="muted small">Approved by {e.approval?.approved_by} at {(e.approval?.approved_at || "").slice(0, 19)} · SHA-256 {(e.approval?.diff_sha256 || "").slice(0, 12)}</p>
        <Diff text={e.diff} />
        <p className="muted small">{e.isolation}</p>
      </>}
    </>
  );
}

/* ------------------------------------------------------------------ Capsule */

function Capsule({ run, capsule, regenerate }) {
  const [md, setMd] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let alive = true;
    fetch(api.capsuleUrl(run.run_id, "md")).then((r) => (r.ok ? r.text() : "")).then((t) => alive && setMd(t)).catch(() => {});
    return () => { alive = false; };
  }, [run.run_id, capsule?.generated_at]);
  if (!capsule) return <p className="empty">Generating the capsule...</p>;
  const redo = async () => { setBusy(true); try { await regenerate(); } finally { setBusy(false); } };
  return (
    <>
      <h2>Exit Capsule</h2>
      <dl className="kv">
        <dt>Repository</dt><dd>{na(capsule.project.remote_url || capsule.project.repository_path)}</dd>
        <dt>Commit</dt><dd><code>{na(capsule.project.commit)}</code></dd>
        <dt>Python</dt><dd>requires {na(capsule.project.declared_requires_python)} · experiments on {capsule.environment.experiment_pythons.join(", ") || "none"}</dd>
        <dt>AI model</dt><dd>{capsule.ai.model} via {capsule.ai.inference_method} · <a href={capsule.ai.terms} target="_blank" rel="noreferrer">terms</a></dd>
        <dt>Generated</dt><dd>{capsule.generated_at.slice(0, 19)} · run <code>{capsule.run_id}</code></dd>
      </dl>
      <div className="actions">
        <a className="btn-bone" href={api.capsuleUrl(run.run_id, "json")} download>Export capsule.json</a>
        <a className="btn-line" href={api.capsuleUrl(run.run_id, "md")} download>Export capsule.md</a>
        <button className="btn-line" disabled={busy} onClick={redo}>{busy ? "Regenerating..." : "Regenerate"}</button>
      </div>
      <h3>Evidence legend</h3>
      {Object.entries(capsule.evidence_legend).map(([k, v]) => <div className="ev" key={k}><p>{v}</p><Chip claim={k} /></div>)}
      <h3>Open concerns</h3>
      <ul>{capsule.open_concerns.map((c, i) => <li key={i}>{c}</li>)}</ul>
      <h3>Limitations</h3>
      <ul>{capsule.limitations.map((c, i) => <li key={i} className="muted">{c}</li>)}</ul>
      <h3>Reproduce</h3>
      <pre>{capsule.reproduction.join("\n")}</pre>
      <h3>Rollback</h3>
      <ul>{capsule.rollback.map((c, i) => <li key={i}>{c}</li>)}</ul>
      {md && <><h3>capsule.md</h3><pre className="md">{md}</pre></>}
    </>
  );
}

/* ---------------------------------------------------------------------- App */

export default function App() {
  const [tab, setTab] = useState("Overview");
  const [runs, setRuns] = useState([]);
  const [run, setRun] = useState(null);
  const [capsule, setCapsule] = useState(null);
  const [selected, setSelected] = useState(null);
  const [health, setHealth] = useState(null);
  const [warn, setWarn] = useState(null);
  const [loading, setLoading] = useState(false);

  const loadCapsule = useCallback(async (id) => {
    try { setCapsule((await api.capsule(id)).capsule); } catch (e) { setWarn(e.message); }
  }, []);
  const openRun = useCallback(async (id) => {
    setLoading(true); setWarn(null);
    try {
      const data = await api.getRun(id);
      setRun(data); setCapsule(null); storage.set("ghostlib.run", id);
      loadCapsule(id);
    } catch (e) { setWarn(e.message); } finally { setLoading(false); }
  }, [loadCapsule]);
  const refresh = useCallback(async () => {
    if (!run) return;
    const data = await api.getRun(run.run_id);
    setRun(data); loadCapsule(run.run_id);
  }, [run, loadCapsule]);

  useEffect(() => {
    api.health().then(setHealth).catch((e) => setWarn(e.message));
    api.listRuns().then((list) => {
      setRuns(list);
      const last = storage.get("ghostlib.run");
      const pick = list.find((r) => r.run_id === last) || list[0];
      if (pick) openRun(pick.run_id);
    }).catch(() => {});
  }, [openRun]);

  const scan = async (repository, fetchMeta) => {
    setWarn(null);
    try {
      const created = await api.createRun(repository, fetchMeta);
      setRuns(await api.listRuns());
      await openRun(created.run_id);
    } catch (e) { setWarn(e.message); }
  };
  const go = (next, pkg) => { if (pkg) setSelected(pkg); setTab(next); window.scrollTo(0, 0); };
  const status = warn && !health ? "backend offline" : run ? `live · ${run.project?.name || "run"} @ ${(run.git?.commit || "").slice(0, 7)}` : "no run yet";

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
        <nav>{TABS.map((name, i) => (
          <button key={name} className={name === tab ? "on" : ""} disabled={i > 0 && !run}
            title={i > 0 && !run ? "Run or open a scan first" : ""} onClick={() => go(name)}>{name}</button>
        ))}</nav>
        <span className="muted">{status}{health?.ai ? ` · Gemma ${health.ai.configured ? "ready" : "not configured"}` : ""}</span>
      </header>
      {warn && <div className="banner warn">{warn} <button className="link" onClick={() => setWarn(null)}>dismiss</button></div>}
      <main>
        {loading && <p className="empty">Summoning the run...</p>}
        {tab === "Overview" && <Overview run={run} runs={runs} openRun={openRun} scan={scan} go={go} />}
        {run && tab === "Dependencies" && <Dependencies run={run} selected={selected} select={setSelected} />}
        {run && tab === "Migration" && <Migration run={run} health={health} selected={selected} select={setSelected} refresh={refresh} go={go} setWarn={setWarn} />}
        {run && tab === "Verification" && <Verification run={run} capsule={capsule} selected={selected} select={setSelected} go={go} />}
        {run && tab === "Capsule" && <Capsule run={run} capsule={capsule} regenerate={() => loadCapsule(run.run_id)} />}
      </main>
    </>
  );
}
