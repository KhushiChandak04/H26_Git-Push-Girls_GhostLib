"""Migration Flight Simulator: baseline vs candidate test execution in disposable workspaces.

Workflow (state in ``experiments/<package>/experiment.json``):
  propose -> builds a reviewable candidate diff; nothing is executed
  approve -> blocked until a supported OS/container sandbox runner is configured
  reject  -> removes the candidate proposal workspace
"""
from __future__ import annotations

import difflib
import json
import re
import shutil
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from packaging.utils import canonicalize_name

from app.services import analysis, gemma
from app.services.metadata import get_package_metadata

DEFAULT_PYTHON = "3.12"
ALLOWED_PYTHONS = {"3.12", "3.13"}
SANDBOX_BLOCKER = ("Execution blocked: no supported OS/container sandbox runner is configured. A disposable copy "
                   "and virtualenv do not safely contain untrusted repository code.")
ISOLATION_NOTE = SANDBOX_BLOCKER


# --------------------------------------------------------------------------- helpers

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _inside(base: Path, target: Path) -> bool:
    base, target = base.resolve(), target.resolve()
    return target == base or base in target.parents


def run_command(argv: list[str], cwd: Path, log_dir: Path, label: str, timeout: int, boundary: Path) -> dict:
    """Refuse host-side execution; a copied project is not an execution sandbox."""
    if not _inside(boundary, cwd):
        raise ValueError(f"Refusing to run outside the experiment boundary: {cwd}")
    raise RuntimeError(SANDBOX_BLOCKER)


# --------------------------------------------------------------------------- test environment

def prepare_and_test(workspace: Path, venv: Path, log_dir: Path, boundary: Path, python: str,
                     extra_test_files: list[str] | None = None) -> dict:
    """Create venv, install declared requirements, run pytest. Returns an execution record."""
    commands = []
    uv = shutil.which("uv")
    if uv:
        commands.append(run_command([uv, "venv", "--python", python, str(venv)], workspace, log_dir,
                                    "01-create-venv", 300, boundary))
    else:
        commands.append(run_command([sys.executable, "-m", "venv", str(venv)], workspace, log_dir,
                                    "01-create-venv", 300, boundary))
    py = _venv_python(venv)
    record = {"python_requested": python, "commands": commands, "workspace": str(workspace), "venv": str(venv)}
    if commands[-1]["exit_code"] != 0 or not py.exists():
        record["status"] = "could_not_run"
        record["blocker"] = "Virtual environment creation failed."
        return record

    reqs = _requirement_files(workspace)
    install_args = sum((["-r", r] for r in reqs), []) if reqs else ["-e", "."]
    install = ([uv, "pip", "install", "--python", str(py)] if uv else [str(py), "-m", "pip", "install"]) + install_args
    commands.append(run_command(install, workspace, log_dir, "02-install", INSTALL_TIMEOUT, boundary))
    if commands[-1]["exit_code"] != 0:
        record["status"] = "could_not_run"
        record["blocker"] = "Dependency installation failed: " + _install_reason(commands[-1]) + \
            " (full output in 02-install.log). This is itself compatibility evidence."
        return record
    has_pytest = subprocess.run([str(py), "-c", "import pytest"], capture_output=True, timeout=60).returncode == 0
    if not has_pytest:
        pip = [uv, "pip", "install", "--python", str(py), "pytest"] if uv else [str(py), "-m", "pip", "install", "pytest"]
        commands.append(run_command(pip, workspace, log_dir, "02b-install-pytest", INSTALL_TIMEOUT, boundary))
    freeze = [uv, "pip", "freeze", "--python", str(py)] if uv else [str(py), "-m", "pip", "freeze"]
    commands.append(run_command(freeze, workspace, log_dir, "03-freeze", 120, boundary))
    record["installed"] = dict(line.split("==", 1) for line in commands[-1]["stdout_tail"].splitlines() if "==" in line)
    version = run_command([str(py), "-c", "import sys,platform;print(platform.python_version())"],
                          workspace, log_dir, "03b-python-version", 60, boundary)
    record["python_version"] = version["stdout_tail"].strip()

    # Pass A: the repository's own test suite (AI-added test files ignored) — like-for-like with baseline.
    pytest_base = [str(py), "-m", "pytest", "-q", "-rA", "-W", "default", "-p", "no:cacheprovider"]
    ignores = [f"--ignore={f}" for f in extra_test_files or []]
    junit = log_dir / "junit.xml"
    commands.append(run_command(pytest_base + ignores + [f"--junitxml={junit}"], workspace, log_dir,
                                "04-pytest", TEST_TIMEOUT, boundary))
    record.update(_pytest_result(commands[-1], junit, log_dir / "04-pytest.log"))

    # Pass B: AI-proposed regression tests, executed and reported separately so a broken AI test
    # cannot mask (or be confused with) the migration's effect on the existing suite.
    if extra_test_files:
        ai_junit = log_dir / "junit-ai-tests.xml"
        commands.append(run_command(pytest_base + list(extra_test_files) + [f"--junitxml={ai_junit}"], workspace,
                                    log_dir, "05-pytest-ai-tests", TEST_TIMEOUT, boundary))
        record["ai_tests"] = {"files": list(extra_test_files), "evidence_type": "EXECUTION-VERIFIED",
                              "note": "Tests written by Gemma; their results are reported separately from the "
                                      "repository's own suite.",
                              **_pytest_result(commands[-1], ai_junit, log_dir / "05-pytest-ai-tests.log")}
    return record


def _pytest_result(cmd: dict, junit: Path, log: Path) -> dict:
    full_out = log.read_text(encoding="utf-8", errors="replace") if log.is_file() else ""
    errors = re.findall(r"^E\s+(\w+(?:Error|Exception)[^\n]*)", full_out, flags=re.MULTILINE)
    return {
        "tests": parse_junit(junit),
        "warnings": parse_warnings(full_out),
        "summary_line": next((l.strip("= ") for l in reversed(full_out.splitlines())
                              if re.search(r"\d+ (passed|failed|error)", l)), None),
        "first_errors": sorted(set(errors))[:5],
        "exit_code": cmd["exit_code"],
        "status": ("timed_out" if cmd["timed_out"] else "passed" if cmd["exit_code"] == 0 else
                   "tests_failed" if cmd["exit_code"] == 1 else
                   "collection_error" if cmd["exit_code"] == 2 else "could_not_run"),
    }


def _install_reason(cmd: dict) -> str:
    """The resolver's own explanation (uv prints 'cause:'/'hint:' lines), shortened for display."""
    text = (cmd.get("stderr_tail") or "") + "\n" + (cmd.get("stdout_tail") or "")
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    picked = [l for l in lines if l.lower().startswith(("cause:", "hint:", "error:", "because", "and because"))]
    return " ".join(picked or lines[-3:])[:600] or "no output"


def resolve_compatible(main_req: str, bundle_names: list[str], other_reqs: list[str], python: str, workdir: Path) -> dict:
    """Ask uv's resolver for versions of ``bundle_names`` compatible with ``main_req`` (no install).

    Pinning every coupled package to its newest release is often impossible (e.g. tensorflow 2.21 needs
    h5py<3.15). The resolver answers from real package metadata; the result is SOURCED and recorded."""
    uv = shutil.which("uv")
    if not uv:
        return {"status": "unavailable", "reason": "uv is not installed; bundled packages are pinned to latest instead."}
    workdir.mkdir(parents=True, exist_ok=True)
    infile = workdir / "resolve.in"
    infile.write_text("\n".join([main_req, *bundle_names, *other_reqs]) + "\n", encoding="utf-8")
    try:
        proc = subprocess.run([uv, "pip", "compile", str(infile), "--python-version", python, "--no-header",
                               "--no-annotate", "--quiet"], capture_output=True, text=True, timeout=300, env=_safe_env())
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"status": "failed", "reason": str(exc)}
    if proc.returncode != 0:
        return {"status": "failed", "reason": _install_reason({"stderr_tail": proc.stderr, "stdout_tail": proc.stdout})}
    pins = {}
    for line in proc.stdout.splitlines():
        if "==" in line and not line.strip().startswith("#"):
            name, ver = line.split("==", 1)
            pins[canonicalize_name(name.strip())] = ver.strip().split(" ")[0]
    return {"status": "resolved", "python": python, "pins": pins, "input": infile.read_text(encoding="utf-8")}


def parse_junit(path: Path) -> dict:
    if not path.is_file():
        return {"available": False, "cases": {}}
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        return {"available": False, "error": str(exc), "cases": {}}
    cases = {}
    for case in root.iter("testcase"):
        key = f"{case.get('classname')}::{case.get('name')}"
        outcome, message = "passed", None
        for tag in ("failure", "error", "skipped"):
            el = case.find(tag)
            if el is not None:
                outcome = {"failure": "failed", "error": "error", "skipped": "skipped"}[tag]
                message = (el.get("message") or "")[:500]
                break
        cases[key] = {"outcome": outcome, "message": message, "time": float(case.get("time") or 0)}
    counts = {k: sum(1 for c in cases.values() if c["outcome"] == k) for k in ("passed", "failed", "error", "skipped")}
    return {"available": True, "cases": cases, "counts": counts}


def parse_warnings(output: str) -> list[str]:
    found = re.findall(r"(\w+Warning): (.+)", output)
    return sorted({f"{cat}: {msg.strip()[:200]}" for cat, msg in found})


def compare(baseline: dict, candidate: dict) -> dict:
    b = (baseline.get("tests") or {}).get("cases", {})
    c = (candidate.get("tests") or {}).get("cases", {})
    rows = []
    for key in sorted(set(b) | set(c)):
        bo, co = (b.get(key) or {}).get("outcome"), (c.get(key) or {}).get("outcome")
        if bo is None:
            change = "new_in_candidate"
        elif co is None:
            change = "missing_in_candidate"
        elif bo == co:
            change = "unchanged_pass" if bo == "passed" else "still_failing" if bo in ("failed", "error") else "unchanged"
        elif co == "passed":
            change = "fixed"
        elif bo == "passed":
            change = "regression"
        else:
            change = "changed"
        rows.append({"test": key, "baseline": bo, "candidate": co, "change": change,
                     "candidate_message": (c.get(key) or {}).get("message")})
    bi, ci = baseline.get("installed", {}), candidate.get("installed", {})
    version_changes = {k: {"baseline": bi.get(k), "candidate": ci.get(k)}
                       for k in sorted(set(bi) | set(ci)) if bi.get(k) != ci.get(k)}
    bw, cw = set(baseline.get("warnings", [])), set(candidate.get("warnings", []))
    regressions = [r for r in rows if r["change"] in ("regression", "missing_in_candidate")]
    if baseline.get("status") == "could_not_run" and c:
        verdict = "baseline_could_not_run"
    elif not (b and c):
        verdict = "insufficient_evidence"
    elif regressions:
        verdict = "regressions_detected"
    elif any(r["change"] in ("still_failing",) for r in rows) or candidate.get("status") != "passed":
        verdict = "no_regressions_but_failures_remain"
    else:
        verdict = "no_regressions_observed"
    return {
        "verdict": verdict,
        "baseline_status": baseline.get("status"), "baseline_blocker": baseline.get("blocker"),
        "candidate_status": candidate.get("status"),
        "tests": rows,
        "counts": {k: sum(1 for r in rows if r["change"] == k) for k in
                   ("fixed", "regression", "still_failing", "unchanged_pass", "new_in_candidate", "missing_in_candidate")},
        "installed_version_changes": version_changes,
        "warnings_removed": sorted(bw - cw),
        "warnings_added": sorted(cw - bw),
        "caveat": "Test outcomes are evidence, not proof of behavioural equivalence. Only behaviour exercised by "
                  "these tests was compared.",
    }


# --------------------------------------------------------------------------- baseline

def ensure_baseline(run_id: str, python: str = DEFAULT_PYTHON) -> dict:
    if python not in ALLOWED_PYTHONS:
        raise ValueError(f"Python {python} is not a supported target ({sorted(ALLOWED_PYTHONS)}).")
    return {"kind": "baseline", "python_requested": python, "status": "blocked",
            "evidence_type": "UNKNOWN", "blocker": SANDBOX_BLOCKER,
            "commands": [], "tests": {"available": False, "cases": {}}, "isolation": ISOLATION_NOTE}


# --------------------------------------------------------------------------- proposals

def _edit_manifests(repo: Path, pkg: dict, new_requirement: str | None,
                    base: dict[str, str] | None = None) -> dict[str, str]:
    """Return {relative_path: new_content} replacing (or removing) every declaration of pkg.

    ``base`` holds edits already made (so several packages can be changed in one candidate)."""
    edits: dict[str, str] = dict(base or {})
    by_file: dict[str, list[dict]] = {}
    for decl in pkg.get("declarations", []):
        by_file.setdefault(decl["source"], []).append(decl)
    for rel, decls in by_file.items():
        path = repo / rel
        text = edits.get(rel) or path.read_text(encoding="utf-8")
        lines = text.splitlines(keepends=True)
        for decl in decls:
            idx = (decl.get("line") or 0) - 1
            if not (0 <= idx < len(lines)) or decl["raw"] not in lines[idx]:
                idx = next((i for i, l in enumerate(lines) if decl["raw"] in l), -1)
            if idx < 0:
                continue
            line = lines[idx]
            if rel.endswith(".toml"):
                if new_requirement:
                    lines[idx] = line.replace(decl["raw"], new_requirement, 1)
                else:
                    lines[idx] = ""
            else:
                ending = "\n" if line.endswith("\n") else ""
                lines[idx] = (new_requirement + ending) if new_requirement else ""
        edits[rel] = "".join(lines)
    return edits


def _diff(repo: Path, edits: dict[str, str]) -> str:
    chunks = []
    for rel, new in sorted(edits.items()):
        path = repo / rel
        old = path.read_text(encoding="utf-8") if path.is_file() else ""
        chunks += difflib.unified_diff(old.splitlines(keepends=True), new.splitlines(keepends=True),
                                       fromfile=f"a/{rel}", tofile=f"b/{rel}")
    return "".join(c if c.endswith("\n") else c + "\n" for c in chunks)


def propose(run_id: str, package: str, candidate: str | None = None, kind: str | None = None,
            use_ai_code_changes: bool = True, also: list[str] | None = None) -> dict:
    """Build a reviewable candidate change. Executes nothing."""
    rdir = analysis.run_dir(run_id)
    scan = json.loads((rdir / "scan.json").read_text(encoding="utf-8"))
    pkg = analysis._package(scan, package)
    repo = Path(scan["repository"])
    rec_file = rdir / "recommendations" / f"{package}.json"
    rec = json.loads(rec_file.read_text(encoding="utf-8")) if rec_file.is_file() else None
    ai = (rec or {}).get("recommendation") if (rec or {}).get("status") == "ok" else None

    if candidate is None and ai:
        rec_name = ai["recommended"]
        # The model sometimes names the action ("remove") instead of a package; match on either.
        chosen = (next((c for c in ai["candidates"] if c["package"] == rec_name), None)
                  or next((c for c in ai["candidates"] if c["kind"] == rec_name), None)
                  or ai["candidates"][0])
        candidate, kind = chosen["package"], chosen["kind"]
    if candidate is None:
        candidate, kind = package, "upgrade"  # deterministic default: latest release of the same package
    kind = kind or ("upgrade" if candidate == package else "pypi")
    if kind not in ("upgrade", "pypi", "stdlib", "remove"):
        raise ValueError("Unsupported candidate kind.")

    notes, new_req = [], None
    if kind in ("upgrade", "pypi"):
        meta = get_package_metadata(candidate)
        if meta.get("status") != "fetched":
            raise ValueError(f"Candidate {candidate} could not be validated on PyPI ({meta.get('status')}).")
        new_req = f"{meta['package']}=={meta['latest_version']}"
        notes.append(f"SOURCED: {meta['package']} latest version {meta['latest_version']} from {meta['source']}.")
    elif kind == "stdlib":
        notes.append(f"Candidate is the standard-library module '{candidate}'; the declaration is removed.")
    else:
        notes.append("Candidate removes the dependency declaration.")
    edits = _edit_manifests(repo, pkg, new_req)

    # Stack migration: upgrade tightly coupled packages (e.g. tensorflow + keras + numpy) in the same candidate.
    bundle, bundle_pkgs, resolution = [], [], None
    others = list(dict.fromkeys(a for a in (also or []) if a and a != package))
    if others:
        bundle_set = {package, *others}
        other_reqs = sorted({d["raw"] for p in scan["packages"] if p["normalized_name"] not in bundle_set
                             for d in p["declarations"] if (d.get("group") or "runtime") == "runtime" and d.get("raw")})
        resolution = resolve_compatible(new_req or package, others, other_reqs, DEFAULT_PYTHON, rdir / "experiments" / package)
        if resolution["status"] == "resolved":
            notes.append(f"SOURCED: uv resolved a compatible set for Python {DEFAULT_PYTHON} "
                         f"(pinning every package to its newest release is often impossible).")
        else:
            notes.append(f"Resolver could not find a compatible set ({resolution.get('reason')}); "
                         "bundled packages are pinned to their latest release instead.")
    for other in others:
        opkg = analysis._package(scan, other)
        ometa = get_package_metadata(other)
        if ometa.get("status") != "fetched":
            raise ValueError(f"Bundled package {other} could not be validated on PyPI ({ometa.get('status')}).")
        version = ((resolution or {}).get("pins") or {}).get(canonicalize_name(other)) or ometa["latest_version"]
        oreq = f"{ometa['package']}=={version}"
        edits = _edit_manifests(repo, opkg, oreq, base=edits)
        bundle.append({"package": other, "requirement": oreq, "latest": ometa["latest_version"], "source": ometa["source"]})
        bundle_pkgs.append(opkg)
        why = "" if version == ometa["latest_version"] else f" (latest is {ometa['latest_version']}, not compatible)"
        notes.append(f"Also upgrading {ometa['package']} to {version}{why} (stack migration).")

    code_proposal = {"status": "not_requested"}
    if kind != "upgrade" or use_ai_code_changes:
        source_files = sorted({f for p in [pkg, *bundle_pkgs] for f in (p.get("usage") or {}).get("source_files", [])})
        if not source_files:
            code_proposal = {"status": "not_needed",
                             "reason": f"No source file imports {package}; only manifests change."}
        elif kind in ("pypi", "stdlib") or (kind == "upgrade" and use_ai_code_changes and ai):
            target = new_req or candidate
            if bundle:
                target += " together with " + ", ".join(b["requirement"] for b in bundle)
            code_proposal = gemma.propose_code_changes(
                package=package if not bundle else ", ".join([package] + [b["package"] for b in bundle]),
                candidate=target, kind=kind,
                files={f: (repo / f).read_text(encoding="utf-8", errors="replace") for f in source_files},
                recommendation=ai)
            for change in code_proposal.get("files", []):
                rel = change["path"]
                allowed = rel in source_files or re.match(r"^tests/test_ghostlib_[a-z0-9_]+\.py$", rel)
                if not allowed or not _inside(repo, repo / rel):
                    change["rejected"] = "Path not in the allowed set (affected source files or tests/test_ghostlib_*.py)."
                    continue
                edits[rel] = change["new_content"]
            if kind in ("pypi", "stdlib") and code_proposal.get("status") != "ok":
                notes.append("Code changes could not be generated (AI unavailable or invalid); the candidate only "
                             "changes manifests, so tests are expected to show where the code still depends on "
                             f"{package}.")

    edir = rdir / "experiments" / package
    edir.mkdir(parents=True, exist_ok=True)
    if code_proposal.get("call_id"):
        analysis.log_ai_call(run_id, "code change proposal", package, code_proposal,
                             f"experiments/{package}/proposal.diff")
    diff = _diff(repo, edits)
    (edir / "proposal.diff").write_text(diff, encoding="utf-8")
    record = {
        "package": package, "candidate": candidate, "kind": kind, "state": "proposed", "proposed_at": _now(),
        "manifest_requirement": new_req, "bundle": bundle, "resolution": resolution, "notes": notes, "diff": diff,
        "diff_file": str(edir / "proposal.diff"),
        "changed_files": sorted(edits), "code_proposal": {k: v for k, v in code_proposal.items() if k != "prompt"},
        "ai_recommendation_used": bool(ai), "approval": None, "isolation": ISOLATION_NOTE,
    }
    (edir / "edits.json").write_text(json.dumps(edits, indent=2), encoding="utf-8")
    _save(edir, record)
    return record


def _save(edir: Path, record: dict) -> None:
    (edir / "experiment.json").write_text(json.dumps(record, indent=2, default=str), encoding="utf-8")


def get_experiment(run_id: str, package: str) -> dict:
    if not analysis.PKG_RE.fullmatch(package or ""):
        raise ValueError("Invalid package name.")
    edir = analysis.run_dir(run_id) / "experiments" / package
    if not (edir / "experiment.json").is_file():
        raise FileNotFoundError("No experiment for this package.")
    return json.loads((edir / "experiment.json").read_text(encoding="utf-8"))


def reject(run_id: str, package: str, reason: str = "") -> dict:
    if not analysis.PKG_RE.fullmatch(package or ""):
        raise ValueError("Invalid package name.")
    edir = analysis.run_dir(run_id) / "experiments" / package
    record = get_experiment(run_id, package)
    if record["state"] == "running":
        raise ValueError("Experiment is running; wait for it to finish.")
    shutil.rmtree(edir / "workspace", ignore_errors=True)
    shutil.rmtree(edir / "venv", ignore_errors=True)
    record.update(state="rejected", rejected_at=_now(), rejection_reason=reason,
                  discard_note="Candidate workspace and venv deleted. The original repository was never modified.")
    _save(edir, record)
    return record


def approve_and_run(run_id: str, package: str, approved_by: str = "local user", python: str = DEFAULT_PYTHON) -> dict:
    """Keep approval auditable while refusing to execute outside a security sandbox."""
    if python not in ALLOWED_PYTHONS:
        raise ValueError("Unsupported Python version.")
    rdir = analysis.run_dir(run_id)
    edir = rdir / "experiments" / package
    record = get_experiment(run_id, package)
    if record["state"] == "running":
        return record
    scan = json.loads((rdir / "scan.json").read_text(encoding="utf-8"))
    repo = Path(scan["repository"])
    edits = json.loads((edir / "edits.json").read_text(encoding="utf-8"))
    if _diff(repo, edits) != record["diff"]:
        raise ValueError("Original repository changed since the proposal was reviewed; propose again.")
    record.update(state="running", approval={"approved_by": approved_by, "approved_at": _now(),
                                             "diff_sha256": hashlib.sha256(record["diff"].encode()).hexdigest()},
                  python_requested=python)
    _save(edir, record)
    try:
        before = _original_state(repo, scan["manifests"])
        # Baseline (cached per run) and candidate are independent: run them concurrently.
        from concurrent.futures import ThreadPoolExecutor
        pool = ThreadPoolExecutor(max_workers=1)
        baseline_future = pool.submit(ensure_baseline, run_id, python)
        workspace = edir / "workspace"
        shutil.rmtree(workspace, ignore_errors=True)
        shutil.rmtree(edir / "venv", ignore_errors=True)
        shutil.copytree(repo, workspace, ignore=COPY_IGNORE)
        for rel, content in edits.items():
            target = workspace / rel
            if not _inside(workspace, target):
                raise ValueError(f"Edit escapes workspace: {rel}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        ai_tests = sorted(r for r in edits if re.match(r"^tests/test_ghostlib_[a-z0-9_]+\.py$", r))
        candidate = prepare_and_test(workspace, edir / "venv", edir / "logs", rdir, python, ai_tests)
        candidate.update(kind="candidate", evidence_type="EXECUTION-VERIFIED", completed_at=_now())
        baseline = baseline_future.result()
        pool.shutdown()
        after = _original_state(repo, scan["manifests"])
        record.update(
            state="completed", baseline_run=baseline, candidate_run=candidate, comparison=compare(baseline, candidate),
            original_repository_check={"before": before, "after": after, "unchanged": before == after},
            completed_at=_now(),
        )
    except Exception as exc:  # record honestly; never pretend success
        record.update(state="failed", error=f"{type(exc).__name__}: {exc}", completed_at=_now())
    _save(edir, record)
    return record


def approve_in_background(run_id: str, package: str, approved_by: str, python: str) -> dict:
    return approve_and_run(run_id, package, approved_by, python)
