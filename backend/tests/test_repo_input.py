import subprocess

import pytest

from app import config
from app.services import repo_input
from app.services.repo_input import RepoInputError, clone_github, parse_github_url, resolve


def test_local_path_ok(tmp_path):
    r = resolve(str(tmp_path))
    assert r["source"] == "local" and r["path"] == tmp_path.resolve()


@pytest.mark.parametrize("value, msg", [
    ("C:/definitely/missing/folder", "not found"),
    ("", "Enter a local repository path"),
])
def test_local_path_errors(value, msg):
    with pytest.raises(RepoInputError, match=msg):
        resolve(value)


def test_file_instead_of_folder(tmp_path):
    f = tmp_path / "x.txt"
    f.write_text("x")
    with pytest.raises(RepoInputError, match="file, not a folder"):
        resolve(str(f))


def test_refuses_ghostlib_itself():
    with pytest.raises(RepoInputError, match="GhostLib's own folder"):
        resolve(str(config.PROJECT_ROOT))


def test_mode_mismatch(tmp_path):
    with pytest.raises(RepoInputError, match="entered a URL"):
        resolve("https://github.com/rishrek/LinkWatch", mode="local")
    with pytest.raises(RepoInputError, match="entered a local path"):
        resolve(str(tmp_path), mode="github")


@pytest.mark.parametrize("url, owner, repo", [
    ("https://github.com/rishrek/LinkWatch", "rishrek", "LinkWatch"),
    ("https://github.com/rishrek/LinkWatch/", "rishrek", "LinkWatch"),
    ("https://github.com/rishrek/LinkWatch.git", "rishrek", "LinkWatch"),
])
def test_github_url_normalised(url, owner, repo):
    assert parse_github_url(url) == (owner, repo)


@pytest.mark.parametrize("url, msg", [
    ("http://github.com/a/b", "https://"),
    ("git@github.com:a/b.git", "https://"),
    ("https://gitlab.com/a/b", "github.com"),
    ("https://user:token@github.com/a/b", "credentials"),
    ("https://github.com/a", "owner"),
    ("https://github.com/a/b/tree/main", "owner"),
    ("https://github.com/../etc", "owner"),
    ("https://github.com/a/b?x=1", "query"),
])
def test_github_url_rejected(url, msg):
    with pytest.raises(RepoInputError, match=msg):
        parse_github_url(url)


def test_credentials_never_echoed():
    with pytest.raises(RepoInputError) as exc:
        parse_github_url("https://alice:s3cr3t@github.com/a/b")
    assert "s3cr3t" not in str(exc.value)


def _fake_git(returncode=0, stderr=""):
    calls = []

    def run(argv, **kw):
        calls.append((argv, kw))
        dest = argv[-1]
        if returncode == 0:
            import os
            os.makedirs(dest, exist_ok=True)
        return subprocess.CompletedProcess(argv, returncode, "", stderr)
    return run, calls


def test_clone_uses_list_args_unique_dirs_and_no_prompt(tmp_path, monkeypatch):
    monkeypatch.setattr(repo_input, "ARTIFACTS_DIR", tmp_path)
    run, calls = _fake_git()
    a = clone_github("https://github.com/rishrek/LinkWatch", runner=run)
    b = clone_github("https://github.com/rishrek/LinkWatch", runner=run)
    assert a["path"] != b["path"]  # each scan gets its own checkout
    argv, kw = calls[0]
    assert isinstance(argv, list) and argv[0] == "git" and "--depth" in argv
    assert argv[-2] == "https://github.com/rishrek/LinkWatch.git"
    assert kw["env"]["GIT_TERMINAL_PROMPT"] == "0" and kw["timeout"] > 0
    assert str(tmp_path / "checkouts") in str(a["path"])


def test_clone_failure_and_timeout(tmp_path, monkeypatch):
    monkeypatch.setattr(repo_input, "ARTIFACTS_DIR", tmp_path)
    run, _ = _fake_git(returncode=128, stderr="fatal: repository not found")
    with pytest.raises(RepoInputError, match="repository not found"):
        clone_github("https://github.com/nobody/private", runner=run)

    def slow(argv, **kw):
        raise subprocess.TimeoutExpired(argv, kw["timeout"])
    with pytest.raises(RepoInputError, match="timed out"):
        clone_github("https://github.com/a/b", runner=slow)
