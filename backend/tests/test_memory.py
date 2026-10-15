import json

from app.services import agent, analysis, memory


def _write_run(root, run_id, repo, commit, pkg_indicators, experiments):
    run = root / run_id
    (run / "experiments").mkdir(parents=True)
    scan = {"repository": "/x", "git": {"remote_url": repo, "commit": commit},
            "packages": [{"normalized_name": n, "assessment": {"indicators": [{"indicator": i, "points": 2} for i in inds]}}
                         for n, inds in pkg_indicators.items()]}
    (run / "scan.json").write_text(json.dumps(scan), encoding="utf-8")
    for exp in experiments:
        d = run / "experiments" / exp["package"]
        d.mkdir()
        (d / "experiment.json").write_text(json.dumps(exp), encoding="utf-8")


def _exp(pkg, kind, cand, verdict, fixed, completed="2026-01-01"):
    return {"package": pkg, "kind": kind, "candidate": cand, "state": "completed", "completed_at": completed,
            "manifest_requirement": None, "candidate_run": {"status": "passed", "python_version": "3.12.1"},
            "comparison": {"verdict": verdict, "counts": {"fixed": fixed}}}


def test_rewards_dedup_and_learning(tmp_path, monkeypatch):
    monkeypatch.setattr(analysis, "runs_dir", lambda: tmp_path)
    good = _exp("jinja2", "upgrade", "jinja2", "no_regressions_observed", 1)
    _write_run(tmp_path, "r1", "repoA", "c1", {"jinja2": ["pinned_major_behind_latest"], "six": ["declared_not_imported"]},
               [good, _exp("six", "remove", "six", "regressions_detected", 0)])
    _write_run(tmp_path, "r2", "repoA", "c1", {"jinja2": ["pinned_major_behind_latest"]}, [good])  # duplicate
    exps = memory.experiences()
    assert len(exps) == 2  # identical experiment on same commit counted once
    assert {e["package"]: e["reward"] for e in exps} == {"jinja2": 1.0, "six": 0.0}
    inds = memory.indicator_stats(exps)
    assert inds["pinned_major_behind_latest"]["worth_migrating"] == 1
    assert inds["pinned_major_behind_latest"]["precision"] > inds["declared_not_imported"]["precision"]
    prio = memory.learned_priority({"assessment": {"indicators": [{"indicator": "declared_not_imported", "points": 1}]}}, inds)
    assert prio["value"] < 1  # rule that led to a bad outcome is down-weighted


def test_agent_explores_untried_option(tmp_path, monkeypatch):
    monkeypatch.setattr(analysis, "runs_dir", lambda: tmp_path)
    _write_run(tmp_path, "r1", "repoA", "c1", {"toml": []}, [_exp("toml", "upgrade", "toml", "no_regressions_but_failures_remain", 0)])
    rec = {"status": "ok", "recommendation": {"recommended": "tomllib", "candidates": [
        {"package": "tomllib", "kind": "stdlib"}]}}
    choice = agent._choose({"normalized_name": "toml"}, rec, memory.experiences())
    assert choice["chosen"]["candidate"] == "tomllib"  # untried arm gets the larger exploration bonus
    assert choice["chosen"]["tries"] == 0
