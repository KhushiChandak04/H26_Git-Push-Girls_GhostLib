"""Dependency Exit Capsule: a portable JSON + Markdown record of evidence and migration work.

Every statement is labelled with how it is known:
OBSERVED, SOURCED, EXECUTION-VERIFIED, AI-RECOMMENDED, or UNKNOWN / NOT TESTED.
"""
from __future__ import annotations

import json
import platform
import re
from datetime import datetime, timezone
from pathlib import Path

from app.services import gemma

CAPSULE_SCHEMA = "1.0"
TOOL_VERSION = "ghostlib 0.2.0"
LEGEND = {
    "OBSERVED": "Read directly from repository files (manifests, source AST) or git metadata.",
    "SOURCED": "Retrieved from an identifiable external source (PyPI JSON API); URL and time recorded.",
    "EXECUTION-VERIFIED": "Produced by a command GhostLib actually ran; argv, exit code and log recorded.",
    "AI-RECOMMENDED": "Suggested by Gemma 4; not independently established as true.",
    "UNKNOWN": "Could not be established, or not tested.",
}


def _compat_gaps(pkg: dict, exp: dict | None, requires_python: str | None = None) -> list[dict]:
    gaps = []
    usage = pkg.get("usage") or {}
    if usage.get("coverage_gap"):
        gaps.append({"type": "UNKNOWN", "gap": "Source files using this dependency are not reached by any test: "
                     + ", ".join(usage["source_files"])})
    for loc in usage.get("private_api_uses", []):
        gaps.append({"type": "OBSERVED", "gap": f"Private API {', '.join(loc['private_api'])} used at "
                     f"{loc['file']}:{loc['line']} — may change without notice in any release."})
    if not exp or exp.get("state") != "completed":
        gaps.append({"type": "UNKNOWN", "gap": "No candidate experiment executed; compatibility of any replacement is untested."})
        return gaps
    cmp_ = exp.get("comparison") or {}
    for row in cmp_.get("tests", []):
        if row["change"] in ("regression", "still_failing", "missing_in_candidate"):
            gaps.append({"type": "EXECUTION-VERIFIED",
                         "gap": f"{row['test']}: baseline={row['baseline']} candidate={row['candidate']} ({row['change']})"
                                + (f" — {row['candidate_message']}" if row.get("candidate_message") else "")})
    for w in cmp_.get("warnings_added", []):
        gaps.append({"type": "EXECUTION-VERIFIED", "gap": f"New warning in candidate: {w}"})
    cand = exp.get("candidate_run") or {}
    if cand.get("status") == "could_not_run":
        gaps.append({"type": "EXECUTION-VERIFIED", "gap": f"Candidate could not run: {cand.get('blocker')}"})
    if exp.get("kind") == "stdlib" and requires_python:
        gaps.append({"type": "UNKNOWN", "gap": f"Project declares requires-python '{requires_python}'. The stdlib "
                     f"module '{exp.get('candidate')}' was only verified on the Python versions tested here; it may "
                     "not exist on older interpreters the project still allows. Raise requires-python or keep a fallback."})
    ai = cand.get("ai_tests")
    if ai and ai.get("status") != "passed":
        gaps.append({"type": "EXECUTION-VERIFIED", "gap": f"AI-proposed regression tests ({', '.join(ai['files'])}) "
                     f"did not pass: {ai.get('status')} — {ai.get('summary_line')}; {'; '.join(ai.get('first_errors') or [])}. "
                     "The AI tests themselves may be wrong; review before adopting them."})
    tested = {cand.get("python_version")}
    for v in ("3.12", "3.13"):
        if not any((t or "").startswith(v) for t in tested):
            gaps.append({"type": "UNKNOWN", "gap": f"Candidate not executed on Python {v}."})
    return gaps


def _experiment_summary(exp: dict) -> dict:
    out = {k: exp.get(k) for k in ("package", "candidate", "kind", "state", "manifest_requirement", "notes",
                                    "changed_files", "diff", "approval", "isolation", "error",
                                    "original_repository_check", "rejection_reason", "discard_note")}
    for side in ("baseline", "candidate"):
        rec = exp.get(f"{side}_run")
        if rec:
            out[f"{side}_run"] = {k: rec.get(k) for k in ("evidence_type", "status", "python_version", "summary_line", "exit_code",
                                                 "blocker", "warnings", "installed", "workspace", "first_errors")}
            if rec.get("ai_tests"):
                ai = rec["ai_tests"]
                out[f"{side}_run"]["ai_tests"] = {k: ai.get(k) for k in ("files", "status", "summary_line",
                                                                       "first_errors", "note", "evidence_type")}
                out[f"{side}_run"]["ai_tests"]["cases"] = {k: v["outcome"] for k, v in (ai.get("tests") or {}).get("cases", {}).items()}
            out[f"{side}_run"]["test_counts"] = (rec.get("tests") or {}).get("counts")
            out[f"{side}_run"]["commands"] = [{k: c[k] for k in ("argv", "cwd", "exit_code", "timed_out", "duration_seconds", "log")}
                                     for c in rec.get("commands", [])]
    out["comparison"] = exp.get("comparison")
    cp = exp.get("code_proposal") or {}
    out["ai_code_changes"] = {"evidence_type": "AI-RECOMMENDED", "status": cp.get("status"), "reason": cp.get("reason"),
                              "model": cp.get("model"), "files": [{"path": f.get("path"), "explanation": f.get("explanation"),
                                                                    "rejected": f.get("rejected")} for f in cp.get("files", [])],
                              "notes": cp.get("notes", [])}
    return out


def build_capsule(run: dict) -> dict:
    recs = run.get("recommendations", {})
    exps = run.get("experiments", {})
    deps = []
    for pkg in run.get("packages", []):
        name = pkg["normalized_name"]
        rec, exp = recs.get(name), exps.get(name)
        assessment = pkg.get("assessment") or {}
        entry = {
            "package": name,
            "declarations": {"evidence_type": "OBSERVED", "items": pkg.get("declarations"), "groups": pkg.get("groups")},
            "metadata": {"evidence_type": "SOURCED" if (pkg.get("metadata") or {}).get("status") == "fetched" else "UNKNOWN",
                         **(pkg.get("metadata") or {})},
            "risk": {"score": assessment.get("score"), "band": assessment.get("band"), "rubric": assessment.get("rubric"),
                     "indicators": assessment.get("indicators", []), "disclaimer": assessment.get("disclaimer")},
            "usage": {"evidence_type": "OBSERVED", "import_names": pkg.get("import_names"),
                      "mapping_confidence": pkg.get("mapping_confidence"), **(pkg.get("usage") or {}),
                      "locations": pkg.get("locations", [])},
            "recommendation": _recommendation_view(rec),
            "experiment": _experiment_summary(exp) if exp else {"state": "not_run"},
            "compatibility_gaps": _compat_gaps(pkg, exp, run.get("python_requirement")),
        }
        deps.append(entry)

    experiments_done = [e for e in exps.values() if e.get("state") == "completed"]
    git = run.get("git") or {}
    capsule = {
        "schema_version": CAPSULE_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generated_by": TOOL_VERSION,
        "run_id": run.get("run_id"),
        "evidence_legend": LEGEND,
        "project": {"name": (run.get("project") or {}).get("name"), "repository_path": run.get("repository"),
                    "remote_url": git.get("remote_url"), "commit": git.get("commit"), "branch": git.get("branch"),
                    "working_tree_dirty": git.get("dirty"), "declared_requires_python": run.get("python_requirement"),
                    "target_pythons": ["3.12", "3.13"]},
        "environment": {"ghostlib_python": platform.python_version(), "platform": platform.platform(),
                        "experiment_pythons": sorted({(e.get("candidate_run") or {}).get("python_version") or "?" for e in experiments_done})},
        "ai": {**gemma.model_info(), "used_for": ["replacement recommendations", "code change proposals"],
               "recommendations": {k: v.get("status") for k, v in recs.items()}},
        "summary": {
            "manifests": [m["path"] for m in run.get("manifests", [])],
            "packages": len(deps),
            "by_band": {b: [d["package"] for d in deps if d["risk"]["band"] == b] for b in ("high", "medium", "low", "none")},
            "ai_recommendations_ok": sum(1 for r in recs.values() if r.get("status") == "ok"),
            "experiments_completed": len(experiments_done),
        },
        "repository_findings": {
            "evidence_type": "OBSERVED",
            "undeclared_imports": run.get("undeclared_imports", []),
            "declaration_conflicts": run.get("declaration_conflicts", []),
            "commented_out_requirements": run.get("commented_out_requirements", []),
            "source_parse_errors": run.get("source_parse_errors", []),
            "test_files": run.get("test_files", []),
        },
        "dependencies": deps,
        "open_concerns": _open_concerns(run, deps),
        "limitations": run.get("limitations", []) + [
            "Risk scores are rule-based triage aids, not probabilities; see each indicator's evidence.",
            "AI-RECOMMENDED content was schema-validated and its package names checked, but not proven correct.",
            "Passing tests show no regressions in exercised behaviour only; untested paths remain unverified.",
        ],
        "reproduction": [
            "pip install -e .  # in the GhostLib repo, Python 3.12 or 3.13",
            f"ghostlib scan {run.get('repository')}",
            "ghostlib recommend <run-id> --all        # requires GEMINI_API_KEY",
            "ghostlib experiment <run-id> <package> --approve",
            "ghostlib capsule <run-id>",
        ],
        "rollback": [
            "Nothing is merged automatically; the original repository is never modified.",
            "To discard a candidate: `ghostlib experiment <run-id> <package> --reject` (deletes its workspace and venv).",
            "To adopt a candidate: review experiments/<package>/proposal.diff and apply it yourself (e.g. `git apply`).",
        ],
        "warnings": run.get("warnings", []),
    }
    return capsule


def _recommendation_view(rec: dict | None) -> dict:
    if not rec:
        return {"evidence_type": "AI-RECOMMENDED", "status": "not_requested"}
    view = {"evidence_type": "AI-RECOMMENDED", "status": rec.get("status"), "reason": rec.get("reason"),
            "model": rec.get("model"), "model_version": rec.get("model_version"),
            "inference_method": rec.get("inference_method"), "requested_at": rec.get("requested_at"),
            "prompt_sha256": rec.get("prompt_sha256")}
    if rec.get("status") == "ok":
        view["recommendation"] = rec["recommendation"]
        view["candidate_validation"] = rec.get("candidate_validation", [])
    return view


def _open_concerns(run: dict, deps: list[dict]) -> list[str]:
    concerns = []
    for c in run.get("declaration_conflicts", []):
        concerns.append(f"[OBSERVED] {c['package']} is declared inconsistently: " +
                        "; ".join(f"{d['source']} {d['specifier']}" for d in c["declarations"]) +
                        ". Which one is installed depends on how the project is installed.")
    for u in run.get("undeclared_imports", []):
        concerns.append(f"[OBSERVED] '{u['import_name']}' is imported "
                        f"({', '.join(l['file'] + ':' + str(l['line']) for l in u['locations'])}) but not declared; "
                        "it is only available transitively.")
    for d in deps:
        if d["recommendation"].get("status") in ("AI_UNAVAILABLE", "AI_ERROR", "AI_INVALID_OUTPUT"):
            concerns.append(f"[UNKNOWN] No valid AI recommendation for {d['package']} ({d['recommendation']['status']}).")
        exp = d["experiment"]
        if exp.get("state") == "completed" and (exp.get("comparison") or {}).get("verdict") != "no_regressions_observed":
            concerns.append(f"[EXECUTION-VERIFIED] {d['package']} -> {exp.get('candidate')}: "
                            f"{exp['comparison']['verdict']}.")
    return concerns


# --------------------------------------------------------------------------- markdown

def _short_cmd(argv: list[str]) -> str:
    """Readable command: tool basename, and run-directory paths abbreviated as $RUN."""
    parts = []
    for i, arg in enumerate(argv):
        arg = arg.replace(chr(92), "/")
        arg = re.sub(r"^(--[a-z]+=)?.*/runs/[^/]+", lambda m: (m.group(1) or "") + "$RUN", arg)
        if i == 0:
            arg = arg.rsplit("/", 1)[-1]
        parts.append(arg)
    return " ".join(parts)


def _fmt_loc(loc: dict) -> str:
    syms = f" — uses {', '.join(loc['symbols_used'])}" if loc.get("symbols_used") else ""
    return f"`{loc['file']}:{loc['line']}` `{loc['statement']}`{syms}"


def capsule_markdown(c: dict) -> str:
    p = c["project"]
    L = [f"# Dependency Exit Capsule — {p.get('name') or 'repository'}", "",
         f"- Generated: {c['generated_at']} by {c['generated_by']} (run `{c['run_id']}`)",
         f"- Repository: {p.get('remote_url') or p.get('repository_path')} @ `{p.get('commit')}`",
         f"- Declared requires-python: `{p.get('declared_requires_python')}`; targets: Python 3.12 / 3.13",
         f"- AI: {c['ai']['model']} via {c['ai']['inference_method']} (configured: {c['ai']['configured']}; terms: {c['ai']['terms']})",
         "", "## Evidence legend", ""]
    L += [f"- **{k}** — {v}" for k, v in c["evidence_legend"].items()]
    s = c["summary"]
    L += ["", "## Summary", "", f"- Manifests: {', '.join(f'`{m}`' for m in s['manifests'])}",
          f"- Packages: {s['packages']} — high: {', '.join(s['by_band']['high']) or '—'}; "
          f"medium: {', '.join(s['by_band']['medium']) or '—'}; low: {', '.join(s['by_band']['low']) or '—'}",
          f"- AI recommendations: {s['ai_recommendations_ok']} valid; experiments completed: {s['experiments_completed']}", ""]
    rf = c["repository_findings"]
    L += ["## Repository findings [OBSERVED]", ""]
    for u in rf["undeclared_imports"]:
        L.append(f"- Undeclared import `{u['import_name']}`: " + "; ".join(_fmt_loc(l) for l in u["locations"]))
    for x in rf["declaration_conflicts"]:
        L.append(f"- Conflicting declarations for `{x['package']}`: " +
                 "; ".join(f"`{d['source']}:{d['line']}` {d['specifier']}" for d in x["declarations"]))
    for x in rf["commented_out_requirements"]:
        L.append(f"- Commented-out requirement `{x['raw']}` at `{x['source']}:{x['line']}`")
    L.append("")

    for d in c["dependencies"]:
        r = d["risk"]
        L += [f"## {d['package']} — risk {r['score']} ({r['band']})", ""]
        L.append("**Declarations [OBSERVED]:** " + "; ".join(
            f"`{x['raw']}` (`{x['source']}:{x.get('line') or '?'}`)" for x in d["declarations"]["items"]))
        m = d["metadata"]
        if m.get("status") == "fetched":
            pin = m.get("pinned") or {}
            L.append(f"**PyPI [SOURCED]:** latest {m.get('latest_version')}, last upload {(m.get('most_recent_upload') or '?')[:10]}, "
                     f"requires-python `{m.get('requires_python')}`" +
                     (f"; pinned {pin.get('version')} released {(pin.get('release_date') or '?')[:10]}" if pin else "") +
                     f" — <{m.get('source')}> (retrieved {(m.get('retrieved_at') or '')[:19]})")
        else:
            L.append(f"**PyPI [UNKNOWN]:** {m.get('status')} {m.get('reason') or ''}")
        L += ["", "**Risk indicators:**"]
        L += [f"- [{i['evidence_type']}] `{i['indicator']}` (+{i['points']}): {i['evidence']}" for i in r["indicators"]] or ["- none"]
        u = d["usage"]
        L += ["", f"**Usage [OBSERVED]** ({u.get('status')}, import mapping: {u.get('mapping_confidence')}):"]
        L += [f"- {_fmt_loc(loc)}" for loc in u.get("locations", [])] or ["- No static imports observed."]
        L.append(f"- Relevant tests: {', '.join(f'`{t}`' for t in u.get('relevant_tests', [])) or 'none found'}")
        rec = d["recommendation"]
        L += ["", f"**Recommendation [AI-RECOMMENDED]** — status `{rec.get('status')}`" +
              (f", model `{rec.get('model_version') or rec.get('model')}`" if rec.get("status") == "ok" else "")]
        if rec.get("status") == "ok":
            body = rec["recommendation"]
            L.append(f"> {body['summary']}")
            L.append(f"- Recommended: **{body['recommended']}**")
            for cand in body["candidates"]:
                L.append(f"- Candidate `{cand['package']}` ({cand['kind']}): {cand['rationale']}")
            L += ["- Migration steps:"] + [f"  {i + 1}. {step}" for i, step in enumerate(body["migration_steps"])]
            if body.get("breaking_changes"):
                L += ["- Possible breaking changes:"] + [f"  - {b}" for b in body["breaking_changes"]]
            if body.get("suggested_tests"):
                L += ["- Suggested tests:"] + [f"  - `{t['name']}`: {t['description']}" for t in body["suggested_tests"]]
            if body.get("uncertainties"):
                L += ["- Model-stated uncertainties:"] + [f"  - {x}" for x in body["uncertainties"]]
            for v in rec.get("candidate_validation", []):
                checks = "; ".join(f"{ch['check']}={ch['result']}" for ch in v["checks"])
                L.append(f"- Validation of `{v['package']}` [{'SOURCED/EXECUTION-VERIFIED'}]: {v['status']} ({checks})")
        elif rec.get("reason"):
            L.append(f"- {rec['reason']}")
        e = d["experiment"]
        L += ["", f"**Experiment** — state `{e.get('state')}`"]
        if e.get("state") not in (None, "not_run"):
            L.append(f"- Candidate: `{e.get('candidate')}` ({e.get('kind')}); approval: {json.dumps(e.get('approval'))}")
            for note in e.get("notes") or []:
                L.append(f"- {note}")
            if e.get("diff"):
                L += ["", "```diff", e["diff"].rstrip(), "```"]
            for side in ("baseline", "candidate"):
                rec_ = e.get(f"{side}_run")
                if rec_:
                    L.append(f"- {side.title()} [EXECUTION-VERIFIED]: `{rec_.get('status')}` on Python {rec_.get('python_version')} — "
                             f"{rec_.get('summary_line') or rec_.get('blocker')}")
                    if rec_.get("ai_tests"):
                        ai = rec_["ai_tests"]
                        L.append(f"  - AI-proposed tests [AI-RECOMMENDED tests, EXECUTION-VERIFIED results] "
                                 f"{', '.join(ai['files'])}: `{ai['status']}` — {ai.get('summary_line')}"
                                 + (f" ({'; '.join(ai['first_errors'])})" if ai.get("first_errors") else ""))
                    for cmd in rec_.get("commands", []):
                        L.append(f"  - `{_short_cmd(cmd['argv'])}` → exit {cmd['exit_code']}"
                                 f"{' (timed out)' if cmd['timed_out'] else ''}, {cmd['duration_seconds']}s")
            cmp_ = e.get("comparison")
            if cmp_:
                L.append(f"- Comparison verdict: **{cmp_['verdict']}** — {json.dumps(cmp_['counts'])}")
                for row in cmp_["tests"]:
                    if row["change"] != "unchanged_pass":
                        L.append(f"  - `{row['test']}`: {row['baseline']} → {row['candidate']} ({row['change']})")
                if cmp_.get("installed_version_changes"):
                    L.append("- Installed versions changed: " + ", ".join(
                        f"{k} {v['baseline']} → {v['candidate']}" for k, v in cmp_["installed_version_changes"].items()))
                L.append(f"- _{cmp_['caveat']}_")
            orc = e.get("original_repository_check")
            if orc:
                L.append(f"- Original repository unchanged after experiment: **{orc['unchanged']}**")
            if e.get("isolation"):
                L.append(f"- Isolation: {e['isolation']}")
            if e.get("error"):
                L.append(f"- Error: {e['error']}")
        L += ["", "**Compatibility gaps:**"]
        L += [f"- [{g['type']}] {g['gap']}" for g in d["compatibility_gaps"]] or ["- none recorded"]
        L.append("")
    L += ["## Open concerns", ""] + [f"- {x}" for x in c["open_concerns"]]
    L += ["", "## Limitations", ""] + [f"- {x}" for x in c["limitations"]]
    L += ["", "## Reproduce", "", "```bash"] + c["reproduction"] + ["```"]
    L += ["", "## Rollback / discard", ""] + [f"- {x}" for x in c["rollback"]]
    return "\n".join(L).rstrip() + "\n"


def write_capsule(capsule: dict, output_dir: Path | str) -> list[str]:
    out = Path(output_dir).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    json_path, md_path = out / "capsule.json", out / "capsule.md"
    json_path.write_text(json.dumps(capsule, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    md_path.write_text(capsule_markdown(capsule), encoding="utf-8")
    return [str(json_path), str(md_path)]


def generate_for_run(run_id: str) -> dict:
    from app.services import analysis
    run = analysis.get_run(run_id)
    capsule = build_capsule(run)
    files = write_capsule(capsule, analysis.run_dir(run_id) / "capsule")
    return {"capsule": capsule, "files": files}
