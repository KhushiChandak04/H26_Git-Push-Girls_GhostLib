import Panel from "../components/Panel.jsx";
import { Evidence, Status } from "../components/Badge.jsx";
import { api } from "../services/api.js";
import { Diff } from "./MigrationWorkbench.jsx";

export default function VerificationCenter({ run, selected, setSelected, go }) {
  const exps = Object.values(run?.experiments || {});
  if (!exps.length) return <Panel title="No experiments yet" eyebrow="BASELINE VS CANDIDATE">
    <div className="empty-state"><span className="empty-icon">✓</span><h3>Run an experiment in the Migration Workbench</h3>
      <p>Results appear here only after GhostLib has actually executed the baseline and candidate test suites.</p>
      <button className="secondary" onClick={() => go("Migration Workbench")}>Open Migration Workbench →</button></div></Panel>;
  const exp = exps.find(e => e.package === selected) || exps.find(e => e.state === "completed") || exps[0];

  return <>
    <div className="tabs">{exps.map(e => <button key={e.package} className={e.package === exp.package ? "tab active" : "tab"} onClick={() => setSelected(e.package)}>
      {e.package} → {e.manifest_requirement || e.candidate} <Status value={e.state} /></button>)}</div>
    {exp.state !== "completed" ? <Panel title={`${exp.package}: ${exp.state}`} eyebrow="NOT EXECUTED"><p className="muted">{exp.error || exp.discard_note || "This experiment has not completed; no execution results exist."}</p></Panel> : <>
      <div className="verdict"><Evidence type="EXECUTION-VERIFIED" /> <Status value={exp.comparison.verdict} />
        <span>fixed <b>{exp.comparison.counts.fixed}</b></span><span>regressions <b>{exp.comparison.counts.regression}</b></span>
        <span>still failing <b>{exp.comparison.counts.still_failing}</b></span><span>unchanged pass <b>{exp.comparison.counts.unchanged_pass}</b></span>
        <span>original repo unchanged <b>{String(exp.original_repository_check?.unchanged)}</b></span></div>
      <div className="two-col">
        {[["Baseline", exp.baseline_run, "baseline"], ["Candidate", exp.candidate_run, "candidate"]].map(([title, r, side]) =>
          <Panel key={side} title={`${title} · Python ${r.python_version || r.python_requested}`} eyebrow={side === "baseline" ? "ORIGINAL DEPENDENCIES" : `${exp.candidate} (${exp.kind})`}>
            <p><Status value={r.status} /> {r.summary_line || r.blocker}</p>
            <table className="table compact"><thead><tr><th>Command</th><th>Exit</th><th>Time</th><th>Log</th></tr></thead>
              <tbody>{r.commands.map(c => <tr key={c.label}><td><code>{c.label}</code></td><td>{c.timed_out ? "timeout" : String(c.exit_code)}</td><td>{c.duration_seconds}s</td>
                <td><a href={api.logUrl(run.run_id, exp.package, `${c.label}.log`, side)} target="_blank" rel="noreferrer">view</a></td></tr>)}</tbody></table>
            {r.warnings?.length > 0 && <><h3>Warnings emitted</h3><ul className="plain small">{r.warnings.map(w => <li key={w}>{w}</li>)}</ul></>}
          </Panel>)}
      </div>
      <Panel title="Per-test comparison" eyebrow="WHAT THE TESTS ACTUALLY SHOWED">
        <table className="table compact"><thead><tr><th>Test</th><th>Baseline</th><th>Candidate</th><th>Change</th></tr></thead>
          <tbody>{exp.comparison.tests.map(t => <tr key={t.test} className={`row-${t.change}`}><td><code>{t.test}</code>{t.candidate_message && <div className="muted small">{t.candidate_message}</div>}</td>
            <td><Status value={t.baseline} /></td><td><Status value={t.candidate} /></td><td><Status value={t.change} /></td></tr>)}</tbody></table>
        {Object.keys(exp.comparison.installed_version_changes).length > 0 && <><h3>Installed versions that differ</h3>
          <ul className="plain">{Object.entries(exp.comparison.installed_version_changes).map(([k, v]) => <li key={k}><code>{k}</code> {v.baseline || "—"} → {v.candidate || "—"}</li>)}</ul></>}
        {exp.comparison.warnings_removed.length > 0 && <p>Warnings no longer emitted: {exp.comparison.warnings_removed.join("; ")}</p>}
        {exp.comparison.warnings_added.length > 0 && <p>New warnings: {exp.comparison.warnings_added.join("; ")}</p>}
        <div className="notice">{exp.comparison.caveat}</div>
      </Panel>
      <Panel title="Applied diff (approved)" eyebrow={`APPROVED BY ${exp.approval?.approved_by?.toUpperCase()} · ${exp.approval?.approved_at?.slice(0, 19)} · SHA-256 ${exp.approval?.diff_sha256?.slice(0, 12)}`}>
        <Diff text={exp.diff} />
        <p className="muted">{exp.isolation}</p>
      </Panel>
    </>}
  </>;
}
