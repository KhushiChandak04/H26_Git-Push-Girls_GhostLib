"""Resolve what the user typed into a local repository folder.

Two input modes (both feed the same scan pipeline):
  * local  — an existing folder, e.g. D:\\GitHub\\LinkWatch or "." for the current folder. Never cloned or modified.
  * github — a public https://github.com/<owner>/<repo> URL. Shallow-cloned non-interactively into a *new*,
             per-scan folder artifacts/checkouts/<owner>__<repo>__<timestamp>-<random>, so concurrent or repeated
             scans never share or overwrite a checkout. Checkouts are kept (experiments and reproducibility need
             them); delete artifacts/checkouts/* to reclaim space.
Anything else gets a clear, actionable error. Error messages never echo credentials.
"""
from __future__ import annotations

import os
import re
import secrets
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from app.config import ARTIFACTS_DIR, PROJECT_ROOT

NAME = r"[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,98}[A-Za-z0-9_])?"
GITHUB_PATH_RE = re.compile(rf"^/({NAME})/({NAME}?)(?:\.git)?/?$")
CLONE_TIMEOUT = int(os.getenv("GHOSTLIB_CLONE_TIMEOUT", "180"))


class RepoInputError(ValueError):
    pass


def looks_like_url(value: str) -> bool:
    v = value.strip().lower()
    return v.startswith(("http://", "https://", "git@", "ssh://", "git://", "file://")) or v.startswith("github.com/")


def resolve(value: str, mode: str | None = None) -> dict:
    raw = (value or "").strip().strip('"').strip("'")
    if not raw:
        raise RepoInputError("Enter a local repository path (e.g. D:\\GitHub\\LinkWatch) or a public GitHub URL.")
    is_url = looks_like_url(raw)
    if mode == "local" and is_url:
        raise RepoInputError("You chose 'Local repository path' but entered a URL. Switch to 'GitHub URL', "
                             "or clone it yourself and enter the folder path.")
    if mode == "github" and not is_url:
        raise RepoInputError("You chose 'GitHub URL' but entered a local path. Switch to 'Local repository path'.")
    if is_url:
        return clone_github(raw)
    path = Path(raw).expanduser()
    if not path.exists():
        raise RepoInputError(f"Local path not found: {raw}. Check the folder exists on this machine "
                             "(the backend reads files locally).")
    if not path.is_dir():
        raise RepoInputError(f"That is a file, not a folder: {raw}. Point to the repository's top folder.")
    resolved = path.resolve()
    if resolved == Path(PROJECT_ROOT).resolve():
        raise RepoInputError("That is GhostLib's own folder. Point to the repository you want to analyse, "
                             "e.g. targets\\LinkWatch.")
    return {"path": resolved, "source": "local", "input": raw}


def parse_github_url(url: str) -> tuple[str, str]:
    """Validate a public GitHub HTTPS URL and return (owner, repo). Raises RepoInputError."""
    parts = urlsplit(url.strip())
    if parts.scheme != "https":
        raise RepoInputError("Only https:// GitHub URLs are supported (no ssh, git, http or file URLs).")
    if parts.username or parts.password or "@" in parts.netloc:
        raise RepoInputError("URLs with embedded credentials are not allowed. Use a public repository URL.")
    if parts.hostname not in ("github.com", "www.github.com") or parts.port:
        raise RepoInputError("Only github.com repositories are supported. For other hosts, clone it yourself "
                             "and enter the local path.")
    if parts.query or parts.fragment:
        raise RepoInputError("Remove the ?query or #fragment: use https://github.com/<owner>/<repo>.")
    m = GITHUB_PATH_RE.match(parts.path)
    if not m or m.group(2) in ("", ".", ".."):
        raise RepoInputError("Expected https://github.com/<owner>/<repo> (a repository root, not a file, branch or tree URL).")
    return m.group(1), m.group(2).removesuffix(".git")


def _git_env() -> dict:
    keep = {"PATH", "SYSTEMROOT", "TEMP", "TMP", "HOME", "USERPROFILE", "HOMEDRIVE", "HOMEPATH"}
    env = {k: v for k, v in os.environ.items() if k.upper() in keep}
    # Never prompt for or use stored credentials: private repositories fail fast.
    env.update({"GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never", "GIT_ASKPASS": "", "SSH_ASKPASS": ""})
    return env


def clone_github(url: str, *, runner=subprocess.run) -> dict:
    owner, repo = parse_github_url(url)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = Path(ARTIFACTS_DIR) / "checkouts" / f"{owner}__{repo}__{stamp}-{secrets.token_hex(3)}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    clean_url = f"https://github.com/{owner}/{repo}.git"
    argv = ["git", "-c", "credential.helper=", "clone", "--depth", "1", "--no-tags", "--", clean_url, str(dest)]
    try:
        proc = runner(argv, capture_output=True, text=True, timeout=CLONE_TIMEOUT, env=_git_env())
    except FileNotFoundError as exc:
        raise RepoInputError("git is not installed, so GitHub URLs cannot be cloned. Clone manually and enter the local path.") from exc
    except subprocess.TimeoutExpired as exc:
        raise RepoInputError(f"Cloning {owner}/{repo} timed out after {CLONE_TIMEOUT}s. Check your network, or clone manually.") from exc
    if proc.returncode != 0:
        detail = ((proc.stderr or "").strip().splitlines() or ["unknown error"])[-1][:200]
        raise RepoInputError(f"Could not clone {owner}/{repo}: {detail}. It may be private, renamed or misspelled; "
                             "clone it yourself and enter the local path.")
    return {"path": dest.resolve(), "source": "github", "input": f"https://github.com/{owner}/{repo}",
            "clone": "shallow clone (depth 1)", "checkout": str(dest.resolve())}
