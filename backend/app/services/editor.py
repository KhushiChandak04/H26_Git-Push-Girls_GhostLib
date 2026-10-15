"""Open a file at a line in the user's local VS Code (the backend runs on the user's machine).

Only files inside the run's scanned repository or the run's own artifact folder can be opened,
and only through the `code` CLI with a fixed argument list (no shell).
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from app.services import analysis


class EditorError(ValueError):
    pass


def resolve_target(run_id: str, file: str, scope: str = "repo") -> Path:
    run_dir = analysis.run_dir(run_id)
    if scope == "repo":
        scan = analysis._read(run_dir / "scan.json")
        base = Path(scan["repository"]).resolve()
        target = (base / file).resolve()
    elif scope == "run":
        base = run_dir.resolve()
        target = Path(file).resolve() if Path(file).is_absolute() else (base / file).resolve()
    else:
        raise EditorError("scope must be 'repo' or 'run'.")
    if base != target and base not in target.parents:
        raise EditorError("Refusing to open a file outside the scanned repository or this run's folder.")
    if not target.is_file():
        raise EditorError(f"File not found: {file}")
    return target


def open_in_vscode(run_id: str, file: str, line: int = 1, scope: str = "repo") -> dict:
    target = resolve_target(run_id, file, scope)
    line = max(1, int(line or 1))
    uri = f"vscode://file/{target.as_posix()}:{line}"
    code = shutil.which("code") or shutil.which("code.cmd")
    if not code:
        return {"opened": False, "path": str(target), "line": line, "uri": uri,
                "reason": "The VS Code 'code' command is not on PATH (VS Code: Shell Command: Install 'code' in PATH)."}
    try:
        subprocess.Popen([code, "-g", f"{target}:{line}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as exc:
        return {"opened": False, "path": str(target), "line": line, "uri": uri, "reason": str(exc)}
    return {"opened": True, "path": str(target), "line": line, "uri": uri}


# --------------------------------------------------------------------------- migrated workspace

def _experiment_paths(run_id: str, package: str) -> tuple[dict, dict, Path, Path, Path]:
    import json
    rdir = analysis.run_dir(run_id)
    scan = analysis._read(rdir / "scan.json")
    edir = (rdir / "experiments" / package).resolve()
    if rdir.resolve() not in edir.parents:
        raise EditorError("Invalid package.")
    exp_file = edir / "experiment.json"
    if not exp_file.is_file():
        raise EditorError("No experiment for this package.")
    record = json.loads(exp_file.read_text(encoding="utf-8"))
    workspace = edir / "workspace"
    if not workspace.is_dir():
        raise EditorError("The migrated copy no longer exists (it was deleted or never created). Run the tests again.")
    return scan, record, edir, workspace, Path(scan["repository"]).resolve()


def _git(workspace: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(workspace), "-c", "user.name=GhostLib", "-c", "user.email=ghostlib@localhost",
                           "-c", "core.autocrlf=false", *args], capture_output=True, text=True, timeout=120)


def prepare_workspace(run_id: str, package: str) -> dict:
    """Make the tested copy reviewable in VS Code (idempotent).

    * a local git repo whose first commit is the ORIGINAL code, so Source Control shows every migration
      change as a diff (the copy's own history; nothing is pushed or touched in the user's repository);
    * .vscode/settings.json pointing the Python interpreter at the virtualenv where the tests ran.
    """
    import json
    scan, record, edir, workspace, repo = _experiment_paths(run_id, package)
    edits = json.loads((edir / "edits.json").read_text(encoding="utf-8"))
    venv_py = edir / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not (workspace / ".git").is_dir():
        current = {rel: (workspace / rel).read_text(encoding="utf-8") for rel in edits if (workspace / rel).is_file()}
        for rel in edits:  # temporarily restore the original content to commit it as the baseline
            target = workspace / rel
            if (repo / rel).is_file():
                target.write_text((repo / rel).read_text(encoding="utf-8"), encoding="utf-8")
            elif target.exists():
                target.unlink()
        _git(workspace, "init", "-q")
        (workspace / ".git" / "info").mkdir(parents=True, exist_ok=True)
        (workspace / ".git" / "info" / "exclude").write_text(".vscode/\n__pycache__/\n.pytest_cache/\n*.pyc\n", encoding="utf-8")
        _git(workspace, "add", "-A")
        commit = (scan.get("git") or {}).get("commit") or "unknown"
        _git(workspace, "commit", "-q", "-m", f"Original {scan.get('project', {}).get('name') or 'project'} @ {commit[:7]} "
                                              "(before GhostLib migration)")
        for rel, content in current.items():
            (workspace / rel).parent.mkdir(parents=True, exist_ok=True)
            (workspace / rel).write_text(content, encoding="utf-8")
        new_files = [rel for rel in edits if not (repo / rel).is_file()]
        if new_files:
            _git(workspace, "add", "-N", *new_files)  # show new files as added in Source Control
    settings_dir = workspace / ".vscode"
    settings_dir.mkdir(exist_ok=True)
    settings = {"python.testing.pytestEnabled": True, "python.testing.pytestArgs": ["tests"]}
    if venv_py.exists():
        settings["python.defaultInterpreterPath"] = str(venv_py)
    (settings_dir / "settings.json").write_text(json.dumps(settings, indent=2), encoding="utf-8")
    status = _git(workspace, "status", "--porcelain").stdout.splitlines()
    cand = record.get("candidate_run") or {}
    return {
        "workspace": str(workspace), "interpreter": str(venv_py) if venv_py.exists() else None,
        "changed_files": sorted(edits), "git_changes": status,
        "tests": {"status": cand.get("status"), "summary": cand.get("summary_line") or cand.get("blocker"),
                  "verdict": (record.get("comparison") or {}).get("verdict")},
    }


def open_workspace(run_id: str, package: str) -> dict:
    info = prepare_workspace(run_id, package)
    code = shutil.which("code") or shutil.which("code.cmd")
    if not code:
        return {**info, "opened": False, "reason": "The VS Code 'code' command is not on PATH."}
    first = next((f for f in info["changed_files"] if f.endswith(".py")), None)
    argv = [code, "-n", info["workspace"]] + ([str(Path(info["workspace"]) / first)] if first else [])
    try:
        subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as exc:
        return {**info, "opened": False, "reason": str(exc)}
    return {**info, "opened": True}


def compare_file(run_id: str, package: str, file: str) -> dict:
    """Open VS Code's side-by-side diff: original file (left) vs migrated file (right)."""
    _, _, _, workspace, repo = _experiment_paths(run_id, package)
    new = (workspace / file).resolve()
    if workspace.resolve() not in new.parents or not new.is_file():
        raise EditorError("File is not part of the migrated copy.")
    old = (repo / file).resolve()
    if repo not in old.parents:
        raise EditorError("Invalid path.")
    code = shutil.which("code") or shutil.which("code.cmd")
    if not code:
        return {"opened": False, "reason": "The VS Code 'code' command is not on PATH."}
    if not old.is_file():
        argv = [code, "-r", str(new)]  # a file the migration added: nothing to compare against
    else:
        argv = [code, "-r", "--diff", str(old), str(new)]
    subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return {"opened": True, "original": str(old) if old.is_file() else None, "migrated": str(new)}
