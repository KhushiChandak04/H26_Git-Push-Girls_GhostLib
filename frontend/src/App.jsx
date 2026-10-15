import { Fragment, useCallback, useEffect, useRef, useState } from "react";
import { api } from "./services/api.js";

const na = (v) => (v === undefined || v === null || v === "" ? "Not available" : v);
const TABS = ["Overview", "Dependencies", "Migration", "Verification", "Capsule"];
// Display names/colours only; the meaning of each label is served by the backend (/api/health).
const EVIDENCE = {
  OBSERVED: ["observed", "Observed"], SOURCED: ["sourced", "Sourced"], "EXECUTION-VERIFIED": ["verified", "Verified"],
  "AI-RECOMMENDED": ["ai", "AI"], UNKNOWN: ["unknown", "Unknown"],
};
let LEGEND = {};
const storage = {
  get: (k) => { try { return window.localStorage.getItem(k); } catch { return null; } },
  set: (k, v) => { try { window.localStorage.setItem(k, v); } catch { /* private mode */ } },
};

const Chip = ({ claim }) => (
  <span className="chips">
    {(Array.isArray(claim) ? claim : [claim || "UNKNOWN"]).map((c) => {
      const [cls, label] = EVIDENCE[c] || EVIDENCE.UNKNOWN;
      return <span key={c} className={`chip chip-${cls}`} title={`${c}: ${LEGEND[c] || ""}`}>{label}</span>;
    })}
  </span>
);

const State = ({ value }) => <span className={`state state-${value}`}>{na(value).replaceAll("_", " ")}</span>;


// Asks the local backend to run `code -g file:line`. A browser cannot launch apps itself;
// the vscode:// link is only offered as a fallback when the backend cannot find VS Code.
function OpenInVSCode({ runId, file, line, scope = "repo", label = "Open in VS Code", big = false }) {
  const [state, setState] = useState(null);
  const open = async () => {
    setState({ busy: true });
    try { setState(await api.openInEditor(runId, file, line, scope)); }
    catch (e) { setState({ opened: false, reason: e.message }); }
  };
  return (
    <span className="opener">
      <button type="button" className={big ? "btn-bone" : "link"} disabled={state?.busy} onClick={open}>{state?.busy ? "Opening..." : label}</button>
      {state?.opened && <span className="muted small"> ✓ opened in VS Code</span>}
      {state && state.opened === false && <span className="muted small"> {state.reason} {state.uri && <a href={state.uri}>try vscode:// link</a>}</span>}
    </span>
  );
}

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

const isUrl = (v) => /^(https?:\/\/|git@|ssh:\/\/|git:\/\/|file:\/\/|github\.com\/)/i.test((v || "").trim());
const GH_RE = /^https:\/\/(www\.)?github\.com\/[A-Za-z0-9][\w.-]*\/[A-Za-z0-9][\w.-]*?(\.git)?\/?$/;
const MODES = {
  local: { label: "Local repository path", placeholder: "D:\\GitHub\\LinkWatch", busy: "Scanning...",
           help: "A folder on this machine. GhostLib reads it and never modifies it." },
  github: { label: "GitHub repository URL", placeholder: "https://github.com/rishrek/LinkWatch", busy: "Cloning and scanning...",
            help: "A public github.com repository. The backend makes a fresh shallow clone for this run under artifacts/checkouts/." },
};
function inputProblem(mode, v) {
  const t = (v || "").trim();
  if (!t) return "";
  if (mode === "local" && isUrl(t)) return "This looks like a URL. Switch to \u201cGitHub repository URL\u201d, or enter a folder path.";
  if (mode === "github" && !isUrl(t)) return "This looks like a folder path. Switch to \u201cLocal repository path\u201d.";
  if (mode === "github" && /@/.test(t.split("/")[2] || "")) return "URLs with credentials are not allowed.";
  if (mode === "github" && !GH_RE.test(t)) return "Use the form https://github.com/<owner>/<repo> (public github.com repositories only).";
  return "";
}

function Overview({ run, runs, openRun, scan, go }) {
  const [repo, setRepo] = useState(() => storage.get("ghostlib.repo") || "");
  const [mode, setMode] = useState(() => (isUrl(storage.get("ghostlib.repo") || "") ? "github" : "local"));
  const [fetchMeta, setFetchMeta] = useState(true);
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (!repo && runs[0]) setRepo(runs[0].repository); }, [runs, repo]);
  const pkgs = run?.packages || [];
  const flagged = pkgs.filter((p) => p.assessment.score > 0).length;
  const tested = Object.values(run?.experiments || {}).filter((e) => e.state === "completed").length;

  const problem = inputProblem(mode, repo);
  const submit = async (e) => {
    e.preventDefault();
    if (problem) return;
    setBusy(true); storage.set("ghostlib.repo", repo);
    try { await scan(repo, fetchMeta, mode); } finally { setBusy(false); }
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
          <p>Scan a Python project, map where each package lives, test a replacement on a disposable copy, and keep the receipts.</p>
          <button className="btn-bone" disabled={!run} onClick={() => go("Dependencies")}>Open findings</button>
        </div>
      </section>

      <section className="panel scan">
        <h2>Summon a scan</h2>
        <form onSubmit={submit}>
          <div className="modes" role="radiogroup" aria-label="Repository input type">
            {Object.entries(MODES).map(([key, m]) => (
              <button type="button" key={key} role="radio" aria-checked={mode === key} className={mode === key ? "mode on" : "mode"}
                onClick={() => setMode(key)}>{m.label}</button>))}
          </div>
          <label className="field">{MODES[mode].label}
            <input value={repo} onChange={(e) => setRepo(e.target.value)} placeholder={MODES[mode].placeholder} required aria-invalid={!!problem} />
          </label>
          <p className="muted small">{MODES[mode].help}</p>
          {problem && <p className="note">{problem}</p>}
          <label className="check"><input type="checkbox" checked={fetchMeta} onChange={(e) => setFetchMeta(e.target.checked)} />
            Fetch PyPI metadata (network; cached 24 h)</label>
          <div className="actions">
            <button className="btn-bone" disabled={busy || !!problem}>{busy ? MODES[mode].busy : "Run scan"}</button>
          </div>
          <p className="muted small">The backend only reads this folder. It never runs repository code during a scan and never modifies it.</p>
        </form>
        {runs.length > 0 && <>
          <h3>Previous runs</h3>
          <p className="muted small">Newest first. Runs with experiments hold the full evidence (tests actually executed).</p>
          <div className="runlist">{runs.map((r) => (
            <button key={r.run_id} className={`row runrow ${run?.run_id === r.run_id ? "on" : ""}`} onClick={() => openRun(r.run_id)}>
              <code>{r.run_id}</code><span className="muted ellipsis">{r.repository}</span>
              <span className="muted">{r.recommendations} AI · {r.experiments_completed}/{r.at_risk} tested{r.input === "github" ? " · GitHub" : ""}</span><span className="muted">{(r.commit || "").slice(0, 7)}</span>
            </button>
          ))}</div>
        </>}
      </section>

      {run && <>
        <section className="stats">
          <div><b>{pkgs.length}</b><span>dependencies scanned</span></div>
          <div><b>{flagged}</b><span>need review</span></div>
          <div><b>{tested}</b><span>migrations tested{run.run_status ? ` · run ${run.run_status.status.replace("_", " ")}` : ""}</span></div>
          <div><b>{na(run.project?.name)}</b><span>requires-python {na(run.python_requirement)} · {(run.git?.commit || "").slice(0, 7)}</span></div>
        </section>
        {run.run_status && run.run_status.status !== "complete" && <p className="note">
          This run is <b>{run.run_status.status.replace("_", " ")}</b>: {run.run_status.recommendations_ok} AI recommendations,
          {" "}{run.run_status.experiments_completed}/{run.run_status.at_risk} at-risk packages tested
          {run.run_status.untested_at_risk.length ? ` (not yet tested: ${run.run_status.untested_at_risk.join(", ")})` : ""}.
          Untested packages have no verified results.</p>}
        <section className="panel">
          <h2>Haunted packages</h2>
          <p className="muted small">Ranked by a transparent rule score. Each point links to its evidence; it is not a probability.</p>
          <div className="row head"><span>Package</span><span>Declared</span><span>Usages · known vulns</span><span>Risk (rules) · learned priority</span></div>
          {pkgs.map((p) => (
            <button key={p.normalized_name} className="row" onClick={() => go("Dependencies", p.normalized_name)}>
              <code>{p.normalized_name}{p.groups.includes("dev") ? " (dev)" : ""}</code>
              <span className="muted">{[...new Set(p.declarations.map((d) => d.specifier || "any"))].join(" vs ")}</span>
              <span className="muted">{p.locations.length} usages{p.advisories?.status === "checked" && p.advisories.count ? ` · ${p.advisories.unique_issues} vuln` : ""}</span>
              <span><span className={`band band-${p.assessment.band}`}>{p.assessment.band} · {p.assessment.score}</span>
                {p.learned && <span className="muted small" title={p.learned.priority.basis}> · {p.learned.priority.value}</span>}</span>
            </button>
          ))}
        </section>
        <ScoreSources />
        <Learning />
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

function ScoreSources() {
  const [rubric, setRubric] = useState(null);
  useEffect(() => { api.rubric().then(setRubric).catch(() => {}); }, []);
  if (!rubric) return null;
  return (
    <section className="panel">
      <details className="more" open>
        <summary><h2 className="inline">Where do these risk scores come from?</h2></summary>
        <p><strong>Not from AI.</strong> {rubric.computed_by} Each package's score is the sum of the rules below that fired for it.
          Bands: high ≥ {rubric.bands.high}, medium ≥ {rubric.bands.medium}, low ≥ {rubric.bands.low}. Gemma 4 is only used later, to suggest replacements.</p>
        <table className="cmp">
          <thead><tr><th>Rule</th><th>Points</th><th>Data from</th><th>Meaning</th></tr></thead>
          <tbody>{rubric.rules.map((r) => <tr key={r.indicator}><td><code>{r.indicator.replaceAll("_", " ")}</code></td><td>+{r.points}</td>
            <td><Chip claim={r.evidence_type} /> {r.source}</td><td>{r.description}</td></tr>)}</tbody>
        </table>
      </details>
    </section>
  );
}

function Learning() {
  const [m, setM] = useState(null);
  useEffect(() => { api.learning().then(setM).catch(() => {}); }, []);
  if (!m) return null;
  return (
    <section className="panel">
      <h2>What GhostLib has learned</h2>
      <p>From <b>{m.experiments_learned_from}</b> verified experiments across <b>{m.repositories_experimented}</b> repositor{m.repositories_experimented === 1 ? "y" : "ies"}
        {" "}({m.repositories_scanned} scanned). Every test run GhostLib executes becomes experience: the more repositories it tests, the better it
        ranks risky packages and picks replacements. <Chip claim="EXECUTION-VERIFIED" /></p>
      <p className="muted small">Reward per experiment: 1.0 = fixed failing tests with no regressions, 0.5 = nothing broke, 0 = something broke. {m.policy}</p>
      {m.arms.length > 0 ? <table className="cmp">
        <thead><tr><th>Replacement tried</th><th>Times</th><th>Avg. reward</th><th>Repos</th></tr></thead>
        <tbody>{m.arms.map((a) => <tr key={a.package + a.kind + a.candidate}><td><code>{a.package}</code> → {a.requirements[0] || a.candidate} <span className="muted">({a.kind})</span></td>
          <td>{a.tries}</td><td>{a.value}</td><td>{a.repositories.length}</td></tr>)}</tbody>
      </table> : <p className="empty">Nothing learned yet. Run an experiment in the Migration tab.</p>}
      {m.indicators.length > 0 && <details className="more"><summary>Which risk rules have been most predictive</summary>
        <table className="cmp"><thead><tr><th>Rule</th><th>Flagged packages worth migrating</th><th>Learned weight</th></tr></thead>
          <tbody>{m.indicators.map((i) => <tr key={i.indicator}><td><code>{i.indicator.replaceAll("_", " ")}</code></td>
            <td>{i.worth_migrating} / {i.experiments}</td><td>{(2 * i.precision).toFixed(2)}×</td></tr>)}</tbody></table>
        <ul>{m.limitations.map((l, i) => <li key={i} className="muted small">{l}</li>)}</ul>
      </details>}
    </section>
  );
}

function Advisories({ adv }) {
  const a = adv || { status: "not_checked", reason: "This run predates advisory checks." };
  return (
    <>
      <h3>Known vulnerabilities <Chip claim={a.status === "checked" ? "SOURCED" : "UNKNOWN"} /> <small className="muted">OSV.dev · not part of the risk score</small></h3>
      {a.status !== "checked" ? <p className="empty">{a.reason}</p>
        : a.count === 0 ? <p className="empty">No known advisories for version {a.version} (checked {(a.retrieved_at || "").slice(0, 10)}).</p>
        : <>
          <p>{a.unique_issues} unique issue{a.unique_issues === 1 ? "" : "s"} ({a.count} advisory IDs) affect the pinned version <code>{a.version}</code>.</p>
          <ul>{a.vulnerabilities.map((v) => <li key={v.id}><a href={v.url} target="_blank" rel="noreferrer">{v.id}</a>
            {v.aliases?.length ? <span className="muted"> ({v.aliases.join(", ")})</span> : null} — {v.summary || "no summary"}
            {v.fixed_in?.length ? <span className="muted"> · fixed in {v.fixed_in.join(", ")}</span> : null}</li>)}</ul>
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

        <Advisories adv={p.advisories} />

        <h3>Why it was flagged <span className={`band band-${p.assessment.band}`}>{p.assessment.band} · {p.assessment.score}</span></h3>
        {p.assessment.indicators.length === 0 && <p className="empty">No indicators fired.</p>}
        {p.assessment.indicators.map((r, i) => (
          <div className="ev" key={i}>
            <div><strong>{r.indicator.replaceAll("_", " ")} <span className="muted">+{r.points}</span></strong><p>{r.evidence}</p>
              {r.source && <small className="muted">Source: {r.source}</small>}</div>
            <Chip claim={r.evidence_type} />
          </div>
        ))}
        <p className="muted small">Scored by fixed rules (see Overview → "Where do these risk scores come from?"), not by AI. {p.assessment.disclaimer}</p>

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
                <OpenInVSCode runId={run.run_id} file={u.file} line={u.line} />
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

const STEPS = ["Choose", "Review", "Test", "Adopt"];

function Steps({ current }) {
  return (
    <ol className="steps">
      {STEPS.map((s, i) => (
        <li key={s} className={i < current ? "done" : i === current ? "now" : ""}><b>{i + 1}</b>{s}</li>
      ))}
    </ol>
  );
}

function Migration({ run, health, selected, select, refresh, go, setWarn }) {
  const pkgs = run.packages;
  const p = pkgs.find((x) => x.normalized_name === selected) || pkgs[0];
  const name = p.normalized_name;
  const rec = run.recommendations?.[name];
  const [exp, setExp] = useState(run.experiments?.[name] || null);
  const [busy, setBusy] = useState("");
  const [confirm, setConfirm] = useState(false);
  const [adoptOpen, setAdoptOpen] = useState(false);
  const [python, setPython] = useState(health?.default_python || "");
  useEffect(() => { if (!python && health?.default_python) setPython(health.default_python); }, [health, python]);
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
  const runTests = () => act("approve", async () => setExp(await api.approve(run.run_id, name, { confirm: true, python, approved_by: "dashboard user" })));
  const drop = (reason) => act("reject", async () => { setExp(await api.reject(run.run_id, name, reason)); await refresh(); });

  const validation = (pkgName) => (rec?.candidate_validation || []).find((v) => v.package === pkgName);
  const cards = ok ? rec.recommendation.candidates.map((c) => ({ ...c, v: validation(c.package), ai: true })) : [];
  if (!cards.some((c) => c.kind === "upgrade" && c.package === name))
    cards.push({ package: name, kind: "upgrade", rationale: `Keep ${name}, but move to its newest release.`, pros: [], cons: [], ai: false });
  if (p.usage.status === "not_observed_static" && !cards.some((c) => c.kind === "remove"))
    cards.push({ package: name, kind: "remove", rationale: "Nothing imports it, so try deleting it.", pros: [], cons: [], ai: false });

  const live = exp && exp.state !== "rejected" ? exp : null;
  const step = !live ? 0 : live.state === "proposed" ? 1 : live.state === "running" ? 2 : 3;
  const KIND = { upgrade: "Upgrade", pypi: "Switch package", stdlib: "Use Python built-in", remove: "Remove" };
  const checkText = (v) => {
    if (!v) return null;
    const c = v.checks[0];
    if (!c) return null;
    const label = { exists_on_pypi: "Exists on PyPI", is_stdlib_module: "Built into Python", no_static_import_observed: "Unused in code" }[c.check] || c.check;
    return <span className="okline">{c.result === "pass" ? "✓" : "✗"} {label}</span>;
  };

  return (
    <>
      <div className="toolbar">
        <label>Dependency
          <select value={name} onChange={(e) => select(e.target.value)} disabled={exp?.state === "running"}>
            {pkgs.map((x) => <option key={x.normalized_name} value={x.normalized_name}>{x.normalized_name} (risk {x.assessment.score})</option>)}
          </select>
        </label>
      </div>
      <h2>Replace {name}</h2>
      <Steps current={step} />

      {/* Step 1 — choose */}
      <section className={`stepbox ${step === 0 ? "active" : ""}`}>
        <h3>1. Choose a replacement</h3>
        {ok ? <p>{rec.recommendation.summary} <Chip claim="AI-RECOMMENDED" /></p>
          : <p className="muted">Ask Gemma 4 for ideas, or test the simple upgrade below. {!aiReady && "(Gemma is not configured, so no AI ideas are shown.)"}</p>}
        <div className="actions">
          <button className="btn-line" disabled={!aiReady || !!busy} onClick={askGemma}>{busy === "ai" ? "Asking Gemma..." : ok ? "Ask Gemma again" : "Ask Gemma 4 for ideas"}</button>
        </div>
        {rec && !ok && <p className="note">Gemma could not answer ({rec.status}). Nothing was invented.</p>}
        <div className="cands">
          {cards.map((c, i) => (
            <article key={`${i}-${c.kind}-${c.package}`} className={live && live.candidate === c.package && live.kind === c.kind ? "cand picked" : "cand"}>
              <header><code>{c.package}</code><span className="state">{KIND[c.kind] || c.kind}</span></header>
              <p>{c.rationale}</p>
              <p className="small">{c.ai ? <Chip claim="AI-RECOMMENDED" /> : <span className="muted">Suggested by GhostLib (no AI)</span>} {checkText(c.v)}</p>
              {(() => {
                const arm = (p.learned?.arms || []).find((a) => a.kind === c.kind && a.candidate === c.package);
                const best = p.learned?.best_bet;
                return <>
                  {arm && <p className="small">Past results: tried {arm.tries}× in {arm.repositories.length} repo{arm.repositories.length === 1 ? "" : "s"}, avg. reward {arm.value} <Chip claim="EXECUTION-VERIFIED" /></p>}
                  {best && best.kind === c.kind && best.candidate === c.package && <p className="small"><span className="state state-completed">best bet from experience</span></p>}
                </>;
              })()}
              <button className="btn-bone" disabled={!!busy || exp?.state === "running"} onClick={() => propose(c.package, c.kind)}>
                {busy === "propose" ? "Preparing..." : "Use this"}</button>
            </article>
          ))}
        </div>
        {ok && <details className="more"><summary>Gemma's full plan (steps, risks, suggested tests)</summary>
          <h4>Steps</h4><ol>{rec.recommendation.migration_steps.map((s, i) => <li key={i}>{s}</li>)}</ol>
          {rec.recommendation.breaking_changes.length > 0 && <><h4>Could break</h4><ul>{rec.recommendation.breaking_changes.map((s, i) => <li key={i}>{s}</li>)}</ul></>}
          {rec.recommendation.suggested_tests.length > 0 && <><h4>Tests to add</h4><ul>{rec.recommendation.suggested_tests.map((t, i) => <li key={i}><code>{t.name}</code>: {t.description}</li>)}</ul></>}
          {rec.recommendation.uncertainties.length > 0 && <><h4>Gemma is unsure about</h4><ul>{rec.recommendation.uncertainties.map((s, i) => <li key={i}>{s}</li>)}</ul></>}
          <p className="muted small">{rec.model_version || rec.model} · {(rec.requested_at || "").slice(0, 19)}</p>
        </details>}
        {rec && rec.status !== "AI_UNAVAILABLE" && <GemmaProof r={rec} />}
      </section>

      {/* Step 2 — review */}
      {live && <section className={`stepbox ${step === 1 ? "active" : ""}`}>
        <h3>2. Review the change</h3>
        <p>To try <strong>{live.manifest_requirement || live.candidate}</strong>, GhostLib would edit {live.changed_files.length} file{live.changed_files.length === 1 ? "" : "s"}: {live.changed_files.map((f) => <code key={f} className="fname">{f}</code>)}.
          {live.code_proposal?.status === "ok" ? <> The code edits were written by Gemma <Chip claim="AI-RECOMMENDED" />, so read them carefully.</> : " These are simple version edits made by GhostLib."}</p>
        {live.code_proposal?.status && !["ok", "not_requested"].includes(live.code_proposal.status) &&
          <p className="note">Gemma could not write the code changes ({live.code_proposal.status}), so only the dependency files change. Tests will show what still breaks.</p>}
        <Diff text={live.diff} />
        <p className="muted small">Nothing has run yet. Your project has not been changed.</p>
      </section>}

      {/* Step 3 — test */}
      {live && <section className={`stepbox ${step === 2 || step === 1 ? "active" : ""}`}>
        <h3>3. Test it on a copy</h3>
        <p>GhostLib copies your project to a temporary folder, installs the <em>current</em> dependencies in one copy and the <em>new</em> ones in another,
          and runs your test suite in both. Your real project is never touched.</p>
        {live.state === "proposed" && <>
          <label className="check"><input type="checkbox" checked={confirm} onChange={(e) => setConfirm(e.target.checked)} />
            I have read the change above. Run the tests.</label>
          <div className="actions">
            <select value={python} onChange={(e) => setPython(e.target.value)}>
              {(health?.supported_pythons || []).map((v) => <option key={v} value={v}>Python {v}</option>)}</select>
            <button className="btn-bone" disabled={!confirm || !!busy} onClick={runTests}>Run tests on a copy</button>
            <button className="btn-line" disabled={!!busy} onClick={() => drop("Not chosen in review")}>Not this one</button>
          </div>
        </>}
        {live.state === "running" && <p className="note">Running tests on both copies... this takes about a minute.</p>}
        {live.state === "failed" && <p className="note">The test run itself failed: {live.error}</p>}
        {live.state === "completed" && <p><Verdict c={live.comparison} /></p>}
      </section>}

      {/* Step 4 — adopt */}
      {live?.state === "completed" && <section className="stepbox active">
        <h3>4. Adopt it (your decision, in your editor)</h3>
        {p.advisories?.status === "checked" && p.advisories.count > 0 && <p>Security side effect <Chip claim="SOURCED" />: the current pin has {p.advisories.unique_issues} known
          issue(s) on OSV.dev; see the Capsule for which ones this candidate's version is past the fix for.</p>}
        <p>GhostLib never changes your repository. If you are happy with the result, apply the patch yourself:</p>
        <div className="actions">
          <button className="btn-bone" onClick={() => setAdoptOpen(true)}>Open migrated project in VS Code</button>
          <OpenInVSCode runId={run.run_id} file={live.diff_file} line={1} scope="run" label="Open the patch file" />
          <button className="btn-line" onClick={() => go("Verification", name)}>See full test comparison</button>
        </div>
        <pre>{`cd "${run.repository}"\ngit apply "${live.diff_file}"`}</pre>
        <p className="muted small">Done with it? <button className="link" disabled={!!busy} onClick={() => drop("Test copy deleted after review")}>Delete the test copy</button>
          {" "}removes the temporary folder and its virtualenv to free disk space. The results stay in the report.</p>
      </section>}
      {exp?.state === "rejected" && <p className="note">{exp.discard_note}</p>}
      {adoptOpen && live?.state === "completed" && <AdoptModal runId={run.run_id} pkg={name} onClose={() => setAdoptOpen(false)} />}
    </>
  );
}

function GemmaProof({ r }) {
  const u = r.usage || {};
  return (
    <details className="more"><summary>Proof this came from Gemma 4</summary>
      <dl className="kv">
        <dt>Call ID</dt><dd><code>{na(r.call_id)}</code></dd>
        <dt>Model requested</dt><dd><code>{r.model}</code> via {r.inference_method}</dd>
        <dt>Model that answered</dt><dd><code>{na(r.model_version)}</code> <span className="muted small">(the API's own <code>modelVersion</code> field)</span></dd>
        <dt>Requested at</dt><dd>{(r.requested_at || "").slice(0, 19)} · {na(r.latency_seconds)} s</dd>
        <dt>Tokens</dt><dd>{na(u.promptTokenCount)} in · {na(u.candidatesTokenCount)} out{u.thoughtsTokenCount ? ` · ${u.thoughtsTokenCount} thinking` : ""}</dd>
        <dt>Prompt SHA-256</dt><dd><code>{na(r.prompt_sha256)}</code></dd>
        <dt>Status</dt><dd><State value={r.status} /> {r.reason || ""}</dd>
      </dl>
      {r.raw_text && <><h4>Raw response from the API</h4><pre className="md">{r.raw_text}</pre></>}
      {r.evidence_sent && <><h4>Evidence GhostLib sent to Gemma</h4><pre className="md">{JSON.stringify(r.evidence_sent, null, 2)}</pre></>}
    </details>
  );
}

function AdoptModal({ runId, pkg, onClose }) {
  const [info, setInfo] = useState(null);
  const [error, setError] = useState("");
  const [opened, setOpened] = useState(null);
  const [compared, setCompared] = useState({});
  useEffect(() => {
    api.workspaceInfo(runId, pkg).then(setInfo).catch((e) => setError(e.message));
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [runId, pkg, onClose]);
  const open = async () => {
    setOpened({ busy: true });
    try { setOpened(await api.openWorkspace(runId, pkg)); } catch (e) { setOpened({ opened: false, reason: e.message }); }
  };
  const compare = async (file) => {
    try { const r = await api.compareFile(runId, pkg, file); setCompared((c) => ({ ...c, [file]: r.opened ? "opened" : r.reason })); }
    catch (e) { setCompared((c) => ({ ...c, [file]: e.message })); }
  };
  const ok = info?.tests?.status === "passed";
  return (
    <div className="modal-backdrop" role="presentation" onClick={onClose}>
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="adopt-title" onClick={(e) => e.stopPropagation()}>
        <h2 id="adopt-title">Open the migrated project</h2>
        {error && <p className="note">{error}</p>}
        {!info && !error && <p className="muted">Preparing the migrated copy...</p>}
        {info && <>
          <p>This opens a <b>new VS Code window</b> on the tested copy of your project, with the new libraries already applied.
            Your original repository is not changed.</p>
          <p><State value={info.tests.status} /> Tests in this copy: {na(info.tests.summary)}
            {!ok && <span className="muted small"> (failures listed in the Verification tab; some may predate the migration)</span>}</p>
          <ul className="plain">
            <li>✓ <b>Source Control</b> (Ctrl+Shift+G) lists every change against the original ({info.git_changes.length} file{info.git_changes.length === 1 ? "" : "s"}).</li>
            <li>✓ The Python interpreter is set to the environment where these tests ran{info.interpreter ? "" : " (not available: the test environment was deleted)"}, so imports of the new libraries resolve.</li>
            <li>✓ Testing is configured for pytest, so you can re-run the tests from VS Code.</li>
          </ul>
          <h4>Changed files</h4>
          <ul className="plain">{info.changed_files.map((f) => <li key={f}><code>{f}</code>{" "}
            <button type="button" className="link" onClick={() => compare(f)}>compare with original</button>
            {compared[f] && <span className="muted small"> {compared[f] === "opened" ? "✓ opened side by side" : compared[f]}</span>}</li>)}</ul>
          <p className="muted small">Folder: <code>{info.workspace}</code></p>
        </>}
        <div className="actions">
          <button className="btn-bone" disabled={!info || opened?.busy} onClick={open}>{opened?.busy ? "Opening..." : "Open in VS Code"}</button>
          <button className="btn-line" onClick={onClose}>Close</button>
          {opened?.opened && <span className="muted small">✓ Opened. Look for the new VS Code window.</span>}
          {opened && opened.opened === false && <span className="muted small">{opened.reason}</span>}
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------- Verification */

function Verdict({ c }) {
  if (!c) return null;
  const n = c.counts;
  const s = (k, one, many) => `${n[k]} ${n[k] === 1 ? one : many}`;
  if (c.verdict === "regressions_detected")
    return <strong className="v-bad">Breaks something: {s("regression", "test that passed before now fails", "tests that passed before now fail")}.</strong>;
  if (c.verdict === "baseline_could_not_run")
    return <strong className="v-good">The current dependencies cannot even be installed on this Python version; with the change, {n.new_in_candidate} test{n.new_in_candidate === 1 ? "" : "s"} ran
      {c.candidate_status === "passed" ? " and all passed." : " (see results below)."}</strong>;
  if (c.verdict === "insufficient_evidence")
    return <strong className="v-warn">Not enough evidence: the tests could not run on one of the copies.</strong>;
  const fixed = n.fixed ? ` It also fixes ${s("fixed", "test that was failing", "tests that were failing")}.` : "";
  const still = n.still_failing ? ` ${s("still_failing", "test was", "tests were")} already failing before the change and still fail${n.still_failing === 1 ? "s" : ""}.` : "";
  return <strong className={c.verdict === "no_regressions_observed" ? "v-good" : "v-warn"}>Nothing new broke: every test that passed before still passes.{fixed}{still}</strong>;
}

const CHANGE_WORDS = {
  fixed: ["✓", "Now passes (was failing)", "good"], regression: ["✗", "Newly broken", "bad"],
  still_failing: ["!", "Already failing before", "warn"], unchanged_pass: ["✓", "Still passes", "same"],
  new_in_candidate: ["+", "New test (only in the new version)", "warn"], missing_in_candidate: ["?", "Did not run in the new version", "bad"],
};
const RANK = { regression: 0, missing_in_candidate: 1, fixed: 2, still_failing: 3, new_in_candidate: 4, unchanged_pass: 5 };
const OUTCOME = { passed: "✓ pass", failed: "✗ fail", error: "✗ error", skipped: "– skip" };

function Run({ title, r, runId, pkg, side }) {
  if (!r) return <div className="run"><h3>{title}</h3><p className="empty">Not run.</p></div>;
  return (
    <div className="run">
      <h3>{title}</h3>
      <p><State value={r.status} /> {na(r.summary_line || r.blocker)} · Python {na(r.python_version)}</p>
      <dl>{r.commands.map((c) => <Fragment key={c.label}><dt><code>{c.label}</code></dt>
        <dd>exit <code>{c.timed_out ? "timeout" : String(c.exit_code)}</code> · {c.duration_seconds}s · <a href={api.logUrl(runId, pkg, `${c.label}.log`, side)} target="_blank" rel="noreferrer">log</a></dd></Fragment>)}</dl>
      {(r.warnings || []).length > 0 && <><h4>Warnings</h4><ul>{r.warnings.map((w) => <li key={w} className="muted small">{w}</li>)}</ul></>}
    </div>
  );
}

function Verification({ run, capsule, selected, select, go }) {
  const exps = Object.values(run.experiments || {});
  if (!exps.length) return <>
    <h2>Test comparison</h2>
    <p className="empty">Nothing has been tested yet. Results appear here only after GhostLib actually runs your tests.</p>
    <div className="actions"><button className="btn-bone" onClick={() => go("Migration")}>Go to Migration</button></div>
  </>;
  const e = exps.find((x) => x.package === selected) || exps.find((x) => x.state === "completed") || exps[0];
  const gaps = (capsule?.dependencies || []).find((d) => d.package === e.package)?.compatibility_gaps || [];
  const c = e.comparison;
  const ai = e.candidate_run?.ai_tests;
  return (
    <>
      <div className="toolbar">
        <label>Experiment
          <select value={e.package} onChange={(ev) => select(ev.target.value)}>
            {exps.map((x) => <option key={x.package} value={x.package}>{x.package} → {x.manifest_requirement || x.candidate} ({x.state})</option>)}
          </select>
        </label>
      </div>
      <h2>{e.package} → {e.manifest_requirement || e.candidate}</h2>
      {e.state !== "completed" ? <p className="empty">{e.error || e.discard_note || `State: ${e.state}. No test results exist.`}</p> : <>
        <p className="verdict"><Verdict c={c} /> <Chip claim="EXECUTION-VERIFIED" /></p>
        <p className="muted">Same tests, run twice on Python {e.candidate_run?.python_version}: once with the <b>current</b> dependencies, once with the <b>new</b> one.
          Your original project was {e.original_repository_check?.unchanged ? "verified unchanged" : "NOT verified unchanged"}.</p>
        <table className="cmp">
          <thead><tr><th>Test</th><th>Before (current)</th><th>After (new)</th><th>What it means</th></tr></thead>
          <tbody>{[...c.tests].sort((a, b) => RANK[a.change] - RANK[b.change]).map((t) => {
            const [icon, words, tone] = CHANGE_WORDS[t.change] || ["", t.change, "same"];
            return <tr key={t.test} className={`tone-${tone}`}><td><code>{t.test.replace(/^tests\./, "")}</code></td>
              <td>{OUTCOME[t.baseline] || "—"}</td><td>{OUTCOME[t.candidate] || "—"}</td><td><b>{icon}</b> {words}</td></tr>;
          })}</tbody>
        </table>
        {Object.keys(c.installed_version_changes).length > 0 && <p className="muted">Installed versions that differ: {Object.entries(c.installed_version_changes).map(([k, v]) => `${k} ${v.baseline || "none"} → ${v.candidate || "none"}`).join(", ")}</p>}
        {ai && <div className="ai">
          <p><Chip claim="AI-RECOMMENDED" /> Gemma also wrote new tests (<code>{ai.files.join(", ")}</code>). They were run separately, so a broken AI test cannot hide the real result:
            {" "}<State value={ai.status} /> {ai.summary_line}</p>
          {(ai.first_errors || []).length > 0 && <p className="muted small">{ai.first_errors.join("; ")}</p>}
        </div>}
        <h3>What is still not proven</h3>
        <p className="note">Passing tests only cover the code paths those tests exercise. They do not prove the two versions behave identically.</p>
        {gaps.length ? <ul>{gaps.map((g, i) => <li key={i}><Chip claim={g.type} /> {g.gap}</li>)}</ul> : <p className="empty">No gaps recorded.</p>}
        <details className="more"><summary>Technical details: commands, exit codes, logs, the applied diff</summary>
          <div className="runs">
            <Run title="Before (current dependencies)" r={e.baseline_run} runId={run.run_id} pkg={e.package} side="baseline" />
            <Run title="After (new dependency)" r={e.candidate_run} runId={run.run_id} pkg={e.package} side="candidate" />
          </div>
          <p className="muted small">Approved by {e.approval?.approved_by} at {(e.approval?.approved_at || "").slice(0, 19)} · patch SHA-256 {(e.approval?.diff_sha256 || "").slice(0, 12)}</p>
          <Diff text={e.diff} />
          <p className="muted small">{e.isolation}</p>
        </details>
      </>}
    </>
  );
}

/* ------------------------------------------------------------------ Capsule */

function Capsule({ run, capsule, regenerate }) {
  const [md, setMd] = useState("");
  const [live, setLive] = useState(null);
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
      <h3>Gemma 4 calls in this run <Chip claim="AI-RECOMMENDED" /></h3>
      <p className="muted small">Source: {capsule.ai.call_log_source}. Each row is a real API request. "Model that answered" is the <code>modelVersion</code> field returned by Google's API.</p>
      <div className="actions"><button className="btn-line" onClick={() => api.aiStatus().then(setLive).catch((e) => setLive({ status: "AI_ERROR", reason: e.message }))}>Check model live now</button>
        {live && <span><State value={live.status} /> <code>{na(live.model_resource)}</code> {live.display_name || ""} {live.version ? `v${live.version}` : ""} {live.reason || ""}</span>}</div>
      {(capsule.ai.calls || []).length ? <table className="cmp">
        <thead><tr><th>When</th><th>Call ID</th><th>Purpose</th><th>Package</th><th>Model that answered</th><th>Tokens in/out</th><th>Status</th></tr></thead>
        <tbody>{capsule.ai.calls.map((c, i) => <tr key={i}><td>{(c.requested_at || "").slice(11, 19)}</td><td><code>{(c.call_id || "—").slice(0, 8)}</code></td><td>{c.purpose}</td><td><code>{c.package}</code></td>
          <td><code>{na(c.model_version_returned)}</code></td><td>{na(c.prompt_tokens)} / {na(c.output_tokens)}</td><td><State value={c.status} /> {c.error ? <span className="muted small">{c.error.slice(0, 80)}</span> : null}</td></tr>)}</tbody>
      </table> : <p className="empty">No Gemma calls were made in this run.</p>}
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

  const loadCapsule = useCallback(async (id, force = false) => {
    try { setCapsule((await api.capsule(id, force)).capsule); } catch (e) { setWarn(e.message); }
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
    api.health().then((h) => { LEGEND = h.evidence_legend || {}; setHealth(h); }).catch((e) => setWarn(e.message));
    api.listRuns().then((list) => {
      setRuns(list);
      const last = storage.get("ghostlib.run");
      const pick = list.find((r) => r.run_id === last) || list[0];
      if (pick) openRun(pick.run_id);
    }).catch(() => {});
  }, [openRun]);

  const scan = async (repository, fetchMeta, mode) => {
    setWarn(null);
    try {
      const created = await api.createRun(repository, fetchMeta, mode);
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
        {run && tab === "Capsule" && <Capsule run={run} capsule={capsule} regenerate={() => loadCapsule(run.run_id, true)} />}
      </main>
    </>
  );
}
