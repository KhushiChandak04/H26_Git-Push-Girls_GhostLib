"""Open a file at a line in the user's local VS Code (the backend runs on the user's machine).

Only files inside the run's scanned repository or the run's own artifact folder can be opened,
and only through the `code` CLI with a fixed argument list (no shell).
"""
from __future__ import annotations

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
