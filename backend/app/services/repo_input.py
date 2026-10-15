"""Resolve what the user typed into a local repository folder.

Accepted:
  * a local folder path (the primary input), e.g. D:\\GitHub\\LinkWatch or "." for the current folder
  * a public GitHub URL, e.g. https://github.com/rishrek/LinkWatch — shallow-cloned once into
    artifacts/clones/<owner>__<repo> (re-used afterwards; never pushed to)
Anything else gets a clear, actionable error instead of a silent failure.
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from app.config import ARTIFACTS_DIR

GITHUB_RE = re.compile(r"^https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?$")
CLONE_TIMEOUT = 180


class RepoInputError(ValueError):
    pass


def resolve(value: str) -> dict:
    raw = (value or "").strip().strip('"').strip("'")
    if not raw:
        raise RepoInputError("Enter a local repository path (e.g. D:\\GitHub\\LinkWatch) or a public GitHub URL.")
    if raw.startswith(("http://", "https://", "git@")) or "github.com" in raw:
        return _clone_github(raw)
    path = Path(raw).expanduser()
    if not path.exists():
        raise RepoInputError(f"Local path not found: {raw}. Check the folder exists on this machine "
                             "(the backend reads files locally).")
    if not path.is_dir():
        raise RepoInputError(f"That is a file, not a folder: {raw}. Point to the repository's top folder.")
    return {"path": path.resolve(), "source": "local", "input": raw}


def _clone_github(url: str) -> dict:
    m = GITHUB_RE.match(url)
    if not m:
        raise RepoInputError("Only public GitHub repository URLs are supported, in the form "
                             "https://github.com/<owner>/<repo>. For anything else, clone it yourself and enter the local path.")
    owner, repo = m.group(1), m.group(2)
    dest = Path(ARTIFACTS_DIR) / "clones" / f"{owner}__{repo}"
    if (dest / ".git").is_dir():
        return {"path": dest.resolve(), "source": "github", "input": url, "clone": "reused existing clone"}
    dest.parent.mkdir(parents=True, exist_ok=True)
    env = {k: v for k, v in os.environ.items() if k.upper() in {"PATH", "SYSTEMROOT", "TEMP", "TMP", "HOME", "USERPROFILE"}}
    env.update({"GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"})  # private repos fail fast, no credential prompt
    try:
        proc = subprocess.run(["git", "clone", "--depth", "1", "--", f"https://github.com/{owner}/{repo}.git", str(dest)],
                              capture_output=True, text=True, timeout=CLONE_TIMEOUT, env=env)
    except FileNotFoundError as exc:
        raise RepoInputError("git is not installed, so GitHub URLs cannot be cloned. Clone manually and enter the local path.") from exc
    except subprocess.TimeoutExpired as exc:
        raise RepoInputError(f"Cloning {url} timed out after {CLONE_TIMEOUT}s. Check your network, or clone manually.") from exc
    if proc.returncode != 0:
        detail = (proc.stderr or "").strip().splitlines()[-1:] or ["unknown error"]
        raise RepoInputError(f"Could not clone {url} ({detail[0]}). It may be private or misspelled; "
                             "clone it yourself and enter the local path.")
    return {"path": dest.resolve(), "source": "github", "input": url, "clone": "shallow clone (depth 1)"}
