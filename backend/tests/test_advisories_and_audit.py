import json
from urllib.error import URLError

import pytest

from app.services import advisories, analysis, editor


PKGS = [{"normalized_name": "jinja2", "pinned_versions": ["2.11.3"]},
        {"normalized_name": "rich", "pinned_versions": []}]


def test_advisories_checked_deduped_and_resolution():
    def post(url, body):
        return {"results": [{"vulns": [{"id": "GHSA-1"}, {"id": "PYSEC-1"}]}]}

    def get(url):
        vid = url.rsplit("/", 1)[1]
        return {"id": vid, "aliases": ["CVE-2024-1"], "summary": "XSS",
                "affected": [{"package": {"name": "jinja2"}, "ranges": [{"events": [{"introduced": "0"}, {"fixed": "3.1.3"},
                                                                                   {"fixed": "abc123def"}]}]}]}
    res = advisories.check(PKGS, post=post, get=get)
    j = res["jinja2"]
    assert j["status"] == "checked" and j["count"] == 2 and j["unique_issues"] == 1
    assert j["vulnerabilities"][0]["fixed_in"] == ["3.1.3"]  # commit hashes dropped
    assert res["rich"]["status"] == "not_checked"  # no exact pin -> not matched, not guessed
    assert advisories.resolved_by(j, "3.1.6")["resolved"] == ["GHSA-1", "PYSEC-1"]
    assert advisories.resolved_by(j, "3.0.0")["not_resolved"] == ["GHSA-1", "PYSEC-1"]


def test_advisories_unavailable_is_unknown_not_clean():
    def post(url, body):
        raise URLError("offline")
    res = advisories.check(PKGS, post=post)
    assert res["jinja2"]["status"] == "unavailable" and res["jinja2"]["evidence_type"] == "UNKNOWN"
    assert "vulnerabilities" not in res["jinja2"]


def test_empty_repository_fails_clearly(tmp_path):
    with pytest.raises(ValueError, match="No Python project found"):
        analysis.create_run(tmp_path, fetch_metadata=False)


def _run(tmp_path, monkeypatch, repo):
    monkeypatch.setattr(analysis, "runs_dir", lambda: tmp_path / "runs")
    (tmp_path / "runs" / "r1").mkdir(parents=True)
    (tmp_path / "runs" / "r1" / "scan.json").write_text(json.dumps({"repository": str(repo), "packages": []}))
    return "r1"


def test_ai_call_log_records_failures_without_secrets(tmp_path, monkeypatch):
    rid = _run(tmp_path, monkeypatch, tmp_path)
    analysis.log_ai_call(rid, "replacement recommendation", "toml",
                         {"call_id": "abc", "status": "AI_ERROR", "reason": "HTTP 500", "model": "gemma-4-26b-a4b-it",
                          "prompt": "SECRET PROMPT BODY", "prompt_sha256": "f00"})
    calls = analysis.read_ai_calls(rid)
    assert calls[0]["call_id"] == "abc" and calls[0]["status"] == "AI_ERROR" and calls[0]["error"] == "HTTP 500"
    raw = (tmp_path / "runs" / rid / "ai_calls.jsonl").read_text()
    assert "SECRET PROMPT BODY" not in raw and "api_key" not in raw.lower()


def test_run_status_only_counts_executed_experiments():
    scan = {"packages": [{"normalized_name": "a", "assessment": {"score": 3}}, {"normalized_name": "b", "assessment": {"score": 0}}]}
    recs = {"a": {"status": "ok"}}
    assert analysis.run_status(scan, recs, {"a": {"state": "proposed"}})["status"] == "partial"
    assert analysis.run_status(scan, recs, {"a": {"state": "completed"}})["status"] == "complete"
    assert analysis.run_status(scan, {}, {})["status"] == "scan_only"


def test_editor_refuses_paths_outside_repo(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.py").write_text("x = 1\n")
    rid = _run(tmp_path, monkeypatch, repo)
    assert editor.resolve_target(rid, "a.py") == (repo / "a.py").resolve()
    for bad in ("../runs/r1/scan.json", str(tmp_path / "outside.txt")):
        with pytest.raises(editor.EditorError):
            editor.resolve_target(rid, bad)
