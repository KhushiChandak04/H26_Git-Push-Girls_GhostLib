"""Migration Flight Simulator: baseline vs candidate test execution in disposable workspaces.

Workflow (state in ``experiments/<package>/experiment.json``):
  propose  -> builds a candidate diff (manifest edits + optional Gemma code edits); nothing executed
  approve  -> human approval; applies the diff to a fresh copy and runs candidate tests
  reject   -> deletes the candidate workspace; the original repository was never touched

Isolation actually provided (documented in every record):
  * the original repository is copied (without .git); it is never written to — verified by
    comparing ``git status --porcelain`` and manifest hashes before/after;
  * baseline and candidate each get their own virtual environment (uv);
  * commands are fixed argument lists (no shell), run with timeouts and an allow-listed
    environment (API keys and git credentials are not passed through).
  It is NOT a security sandbox: test code runs as the current user on this machine.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import threading
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from app.services import analysis, gemma
from app.services.metadata import get_package_metadata

COPY_IGNORE = shutil.ignore_patterns(".git", ".venv", "venv", "env", "node_modules", "__pycache__", "dist",
                                     "build", ".pytest_cache", ".mypy_cache", ".ruff_cache", "*.egg-info")
ENV_ALLOW = {"PATH", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "TEMP", "TMP", "COMSPEC", "PATHEXT", "LOCALAPPDATA",
             "APPDATA", "USERPROFILE", "HOME", "HOMEDRIVE", "HOMEPATH", "NUMBER_OF_PROCESSORS",
             "PROCESSOR_ARCHITECTURE", "UV_CACHE_DIR", "UV_PYTHON_INSTALL_DIR", "LANG", "LC_ALL", "TZ"}
INSTALL_TIMEOUT = 600
TEST_TIMEOUT = 600
DEFAULT_PYTHON = "3.12"
ALLOWED_PYTHONS = {"3.12", "3.13"}
ISOLATION_NOTE = ("Disposable copy + separate uv virtualenv; fixed argv commands (no shell) with timeouts and an "
                  "allow-listed environment. Not a security sandbox: tests execute as the current OS user with "
                  "network access.")
_LOCKS: dict[str, threading.Lock] = {}


# --------------------------------------------------------------------------- helpers

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def _safe_env(extra: dict | None = None) -> dict:
    env = {k: v for k, v in os.environ.items() if k.upper() in ENV_ALLOW}
    env.update({"PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1", "GIT_TERMINAL_PROMPT": "0",
                "PIP_DISABLE_PIP_VERSION_CHECK": "1", "PYTHONIOENCODING": "utf-8"})
    env.update(extra or {})
    return env


def _inside(base: Path, target: Path) -> bool:
    base, target = base.resolve(), target.resolve()
    return target == base or base in target.parents


def run_command(argv: list[str], cwd: Path, log_dir: Path, label: str, timeout: int, boundary: Path) -> dict:
    """Run a fixed argv (no shell) inside ``boundary``; persist full output to a log file."""
    if not _inside(boundary, cwd):
        raise ValueError(f"Refusing to run outside the experiment boundary: {cwd}")
    log_dir.mkdir(parents=True, exist_ok=True)
    started, t0 = _now(), time.monotonic()
    timed_out = False
    try:
        proc = subprocess.run(argv, cwd=str(cwd), env=_safe_env(), capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout, shell=False)
        code, out, err = proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out, code = True, None
        out = exc.stdout if isinstance(exc.stdout, str) else (exc.stdout or b"").decode("utf-8", "replace")
        err = exc.stderr if isinstance(exc.stderr, str) else (exc.stderr or b"").decode("utf-8", "replace")
    except OSError as exc:
        code, out, err = None, "", f"Could not start command: {exc}"
    log_path = log_dir / f"{label}.log"
    log_path.write_text(f"$ {' '.join(argv)}\n# cwd: {cwd}\n# exit: {code} timed_out: {timed_out}\n\n"
                        f"--- stdout ---\n{out}\n--- stderr ---\n{err}\n", encoding="utf-8")
    return {"label": label, "argv": argv, "cwd": str(cwd), "exit_code": code, "timed_out": timed_out,
            "started_at": started, "duration_seconds": round(time.monotonic() - t0, 2),
            "log": str(log_path), "stdout_tail": out[-4000:], "stderr_tail": err[-2000:]}


def _venv_python(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _original_state(repo: Path, manifests: list[dict]) -> dict:
    status = None
    try:
        proc = subprocess.run(["git", "-C", str(repo), "status", "--porcelain"], capture_output=True, text=True, timeout=20)
        status = proc.stdout if proc.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        pass
    return {"git_status_porcelain": status,
            "manifest_sha256": {m["path"]: _sha(repo / m["path"]) for m in manifests if m.get("sha256")}}


# --------------------------------------------------------------------------- test environment

def _requirement_files(workspace: Path) -> list[str]:
    return sorted(p.name for p in workspace.glob("requirements*.txt"))


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
        record["blocker"] = "Dependency installation failed (see 02-install.log). This is itself compatibility evidence."
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
    rdir = analysis.run_dir(run_id)
    bdir = rdir / f"baseline-py{python}"
    record_file = bdir / "baseline.json"
    lock = _LOCKS.setdefault(str(bdir), threading.Lock())
    with lock:
        if record_file.is_file():
            return json.loads(record_file.read_text(encoding="utf-8"))
        scan = json.loads((rdir / "scan.json").read_text(encoding="utf-8"))
        repo = Path(scan["repository"])
        workspace = bdir / "workspace"
        if workspace.exists():
            shutil.rmtree(workspace, ignore_errors=True)
        shutil.copytree(repo, workspace, ignore=COPY_IGNORE)
        record = prepare_and_test(workspace, bdir / "venv", bdir / "logs", rdir, python)
        record.update({"kind": "baseline", "evidence_type": "EXECUTION-VERIFIED", "commit": (scan.get("git") or {}).get("commit"),
                       "host": {"platform": platform.platform(), "runner": "uv" if shutil.which("uv") else "venv+pip"},
                       "completed_at": _now(), "isolation": ISOLATION_NOTE})
        record_file.write_text(json.dumps(record, indent=2), encoding="utf-8")
        return record


# --------------------------------------------------------------------------- proposals

def _edit_manifests(repo: Path, pkg: dict, new_requirement: str | None) -> dict[str, str]:
    """Return {relative_path: new_content} replacing (or removing) every declaration of pkg."""
    edits: dict[str, str] = {}
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
            use_ai_code_changes: bool = True) -> dict:
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

    code_proposal = {"status": "not_requested"}
    if kind != "upgrade" or use_ai_code_changes:
        source_files = (pkg.get("usage") or {}).get("source_files", [])
        if not source_files:
            code_proposal = {"status": "not_needed",
                             "reason": f"No source file imports {package}; only manifests change."}
        elif kind in ("pypi", "stdlib") or (kind == "upgrade" and use_ai_code_changes and ai):
            code_proposal = gemma.propose_code_changes(
                package=package, candidate=candidate, kind=kind,
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
        "manifest_requirement": new_req, "notes": notes, "diff": diff, "diff_file": str(edir / "proposal.diff"),
        "changed_files": sorted(edits), "code_proposal": {k: v for k, v in code_proposal.items() if k != "prompt"},
        "ai_recommendation_used": bool(ai), "approval": None, "isolation": ISOLATION_NOTE,
    }
    (edir / "edits.json").write_text(json.dumps(edits, indent=2), encoding="utf-8")
    _save(edir, record)
    return record


def _save(edir: Path, record: dict) -> None:
    (edir / "experiment.json").write_text(json.dumps(record, indent=2, default=str), encoding="utf-8")


def get_experiment(run_id: str, package: str) -> dict:
    edir = analysis.run_dir(run_id) / "experiments" / package
    if not (edir / "experiment.json").is_file():
        raise FileNotFoundError("No experiment for this package.")
    return json.loads((edir / "experiment.json").read_text(encoding="utf-8"))


def reject(run_id: str, package: str, reason: str = "") -> dict:
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
    """Human approval gate, then apply the reviewed diff to a fresh copy and run baseline + candidate."""
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
        baseline = ensure_baseline(run_id, python)
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
    record = get_experiment(run_id, package)
    if record["state"] == "running":
        return record
    thread = threading.Thread(target=approve_and_run, args=(run_id, package, approved_by, python), daemon=True)
    thread.start()
    time.sleep(0.3)
    return get_experiment(run_id, package)
