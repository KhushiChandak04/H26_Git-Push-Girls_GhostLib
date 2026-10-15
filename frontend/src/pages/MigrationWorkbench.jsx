import { useEffect, useRef, useState } from "react";
import Panel from "../components/Panel.jsx";
import { Band, Evidence, Status } from "../components/Badge.jsx";
import { api } from "../services/api.js";

export default function MigrationWorkbench({ run, refresh, selected, setSelected, go, health }) {
  const pkgs = run?.packages || [];
  const pkg = pkgs.find(p => p.normalized_name === selected) || pkgs[0];
  const name = pkg?.normalized_name;
  const rec = run?.recommendations?.[name];
  const [exp, setExp] = useState(run?.experiments?.[name] || null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [choice, setChoice] = useState("");
  const [confirm, setConfirm] = useState(false);
  const [python, setPython] = useState("3.12");
  const poll = useRef(null);

  useEffect(() => { setExp(run?.experiments?.[name] || null); setChoice(""); setConfirm(false); setError(""); }, [name, run]);
  useEffect(() => {
    clearInterval(poll.current);
    if (exp?.state === "running") {
      poll.current = setInterval(async () => {
        try {
          const latest = await api.experiment(run.run_id, name);
          setExp(latest);
          if (latest.state !== "running") { clearInterval(poll.current); refresh(); }
        } catch (e) { setError(e.message); clearInterval(poll.current); }
      }, 2500);
    }
    return () => clearInterval(poll.current);
  }, [exp?.state, name, run?.run_id, refresh]);

  if (!pkg) return null;
  const aiOk = rec?.status === "ok";
  const options = [{ value: "upgrade::" + name, label: `Upgrade ${name} to latest PyPI release (deterministic, no AI)` }];
  if (aiOk) rec.recommendation.candidates.forEach(c => options.unshift({ value: `${c.kind}::${c.package}`, label: `${c.package} (${c.kind}) — AI candidate${c.package === rec.recommendation.recommended ? ", recommended" : ""}` }));
  if (pkg.usage.status === "not_observed_static") options.push({ value: "remove::" + name, label: `Remove ${name} (no static import observed)` });
  const current = choice || options[0].value;

  async function act(label, fn) {
    setBusy(label); setError("");
    try { await fn(); } catch (e) { setError(e.message); } finally { setBusy(""); }
  }
  const askGemma = () => act("ai", async () => { await api.recommend(run.run_id, name); await refresh(); });
  const propose = () => act("propose", async () => {
    const [kind, candidate] = current.split("::");
    setExp(await api.propose(run.run_id, name, { candidate, kind }));
    setConfirm(false);
  });
  const approve = () => act("approve", async () => setExp(await api.approve(run.run_id, name, { confirm: true, python, approved_by: "dashboard user" })));
  const reject = () => act("reject", async () => { setExp(await api.reject(run.run_id, name, "Rejected in dashboard")); refresh(); });

  return <div className="split">
    <div className="pkg-list">
      {pkgs.map(p => <button key={p.normalized_name} className={p.normalized_name === name ? "pkg active" : "pkg"} onClick={() => setSelected(p.normalized_name)}>
        <span>{p.normalized_name}</span>
        <span>{run.experiments?.[p.normalized_name]?.state === "completed" ? "✓ " : ""}<Band band={p.assessment.band} score={p.assessment.score} /></span></button>)}
    </div>
    <div>
      <Panel title={`Gemma 4 recommendation · ${name}`} eyebrow="AI-RECOMMENDED — NOT EVIDENCE">
        <div className="actions">
          <button className="primary" disabled={!!busy || !health?.ai?.configured} onClick={askGemma}
            title={health?.ai?.configured ? "" : "Set GEMINI_API_KEY in backend/.env and restart the backend"}>
            {busy === "ai" ? "Asking Gemma…" : aiOk ? "Ask Gemma again" : "Ask Gemma 4"}</button>
          <span className="muted-inline">Sends only collected evidence (declarations, PyPI facts, usage snippets) to {health?.ai?.model}.</span>
        </div>
        {!health?.ai?.configured && <div className="notice">Gemma 4 is not configured (no GEMINI_API_KEY). Status <code>AI_UNAVAILABLE</code>: no AI output is shown or invented. You can still run a deterministic upgrade experiment below.</div>}
        {rec && !aiOk && <div className="alert"><Status value={rec.status} /> {rec.reason}</div>}
        {aiOk && <div className="ai-box">
          <div className="ai-head"><Evidence type="AI-RECOMMENDED" /> <span>{rec.model_version || rec.model} · {rec.requested_at?.slice(0, 19)}</span></div>
          <p>{rec.recommendation.summary}</p>
          <p>Recommended: <strong>{rec.recommendation.recommended}</strong></p>
          <div className="cands">{rec.recommendation.candidates.map(c => {
            const v = (rec.candidate_validation || []).find(x => x.package === c.package);
            return <div key={c.package} className="cand"><strong>{c.package}</strong> <span className="tag">{c.kind}</span> {v && <Status value={v.status} />}
              <p>{c.rationale}</p>
              {c.pros.length > 0 && <p className="muted">+ {c.pros.join(" · ")}</p>}
              {c.cons.length > 0 && <p className="muted">− {c.cons.join(" · ")}</p>}
              {v && <ul className="plain small">{v.checks.map((ch, i) => <li key={i}><Evidence type={ch.evidence_type || "OBSERVED"} /> {ch.check}: {typeof ch.result === "object" ? JSON.stringify(ch.result) : ch.result}</li>)}</ul>}
            </div>;
          })}</div>
          <h3>Migration steps</h3><ol>{rec.recommendation.migration_steps.map((s, i) => <li key={i}>{s}</li>)}</ol>
          {rec.recommendation.breaking_changes.length > 0 && <><h3>Possible breaking changes</h3><ul>{rec.recommendation.breaking_changes.map((s, i) => <li key={i}>{s}</li>)}</ul></>}
          {rec.recommendation.suggested_tests.length > 0 && <><h3>Suggested tests</h3><ul>{rec.recommendation.suggested_tests.map((t, i) => <li key={i}><code>{t.name}</code> — {t.description}</li>)}</ul></>}
          {rec.recommendation.uncertainties.length > 0 && <><h3>Model-stated uncertainties</h3><ul>{rec.recommendation.uncertainties.map((s, i) => <li key={i}>{s}</li>)}</ul></>}
        </div>}
      </Panel>

      <Panel title="Migration Flight Simulator" eyebrow="PROPOSE → REVIEW → APPROVE → VERIFY">
        <label className="field-label">Candidate</label>
        <div className="input-row">
          <select value={current} onChange={e => setChoice(e.target.value)} disabled={!!busy || exp?.state === "running"}>
            {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}</select>
          <button className="primary" disabled={!!busy || exp?.state === "running"} onClick={propose}>{busy === "propose" ? "Building diff…" : "Propose change"}</button>
        </div>
        <p className="muted">Proposing executes nothing. Manifest edits are deterministic; code edits (for replacements) come from Gemma and are shown in the diff for review.</p>
        {error && <div className="alert">{error}</div>}

        {exp && <div className="experiment">
          <div className="exp-head"><Status value={exp.state} /> <strong>{exp.candidate}</strong> <span className="tag">{exp.kind}</span>
            {exp.manifest_requirement && <code>{exp.manifest_requirement}</code>}</div>
          {exp.notes?.map((n, i) => <p key={i} className="muted">{n}</p>)}
          {exp.code_proposal?.status && exp.code_proposal.status !== "not_requested" && <p className="muted"><Evidence type="AI-RECOMMENDED" /> Code changes: <Status value={exp.code_proposal.status} /> {exp.code_proposal.reason || ""}</p>}
          <h3>Proposed diff ({exp.changed_files?.length || 0} files)</h3>
          <Diff text={exp.diff} />
          {exp.state === "proposed" && <div className="approval">
            <label className="check"><input type="checkbox" checked={confirm} onChange={e => setConfirm(e.target.checked)} />
              I reviewed this diff. Apply it to a disposable copy and run baseline + candidate tests.</label>
            <div className="input-row">
              <select value={python} onChange={e => setPython(e.target.value)}><option value="3.12">Python 3.12</option><option value="3.13">Python 3.13</option></select>
              <button className="primary" disabled={!confirm || !!busy} onClick={approve}>{busy === "approve" ? "Starting…" : "Approve & run"}</button>
              <button className="danger" disabled={!!busy} onClick={reject}>Reject & discard</button>
            </div>
            <p className="muted">{exp.isolation}</p>
          </div>}
          {exp.state === "running" && <div className="notice">Running: creating venvs, installing, and executing pytest for baseline and candidate (≈1 minute)…</div>}
          {exp.state === "failed" && <div className="alert">Experiment failed: {exp.error}</div>}
          {exp.state === "rejected" && <div className="notice">{exp.discard_note}</div>}
          {exp.state === "completed" && <div className="done">
            <p><Status value={exp.comparison.verdict} /> fixed {exp.comparison.counts.fixed} · regressions {exp.comparison.counts.regression} · still failing {exp.comparison.counts.still_failing} · original repository unchanged: <strong>{String(exp.original_repository_check?.unchanged)}</strong></p>
            <div className="actions"><button className="secondary" onClick={() => go("Verification Center", name)}>Open verification →</button>
              <button className="danger" onClick={reject}>Discard candidate workspace</button></div>
          </div>}
        </div>}
      </Panel>
    </div>
  </div>;
}

export function Diff({ text }) {
  if (!text) return <p className="muted">No file changes.</p>;
  return <pre className="diff">{text.split("\n").map((l, i) => <div key={i} className={l.startsWith("+++") || l.startsWith("---") ? "d-file" : l.startsWith("+") ? "d-add" : l.startsWith("-") ? "d-del" : l.startsWith("@@") ? "d-hunk" : ""}>{l || " "}</div>)}</pre>;
}
