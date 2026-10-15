"""Experience memory: GhostLib learns from its own *verified* experiment outcomes.

There is no hand-entered knowledge and no separate database. Memory is replayed from
``artifacts/runs/*`` every time it is needed, so each new scan or experiment — on any
repository — automatically becomes training data.

What is learned (a small, explainable reinforcement-learning setup, a multi-armed bandit):

* Reward of an experiment (from real test executions, never from the model):
    1.0  no regressions and at least one previously failing test fixed
    0.5  no regressions, nothing fixed
    0.0  regressions, tests missing, or the candidate could not run
* Candidate policy: each arm is (package, kind, candidate). Its value is the Beta(1,1)
  posterior mean of rewards; an exploration bonus (UCB1) favours arms that were tried
  less often. The arm with the highest upper bound is the "best bet from experience".
* Indicator learning: for each risk rule, how often a package flagged by that rule turned
  out to be worth migrating (reward >= 1.0). This yields a *learned priority* shown next
  to — never replacing — the transparent rule score.

Limits (reported with every result): small sample sizes, outcomes depend on each
repository's test suite, and identical experiments are deduplicated.
"""
from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path

from app.services import analysis


def _reward(exp: dict) -> float | None:
    if exp.get("state") != "completed":
        return None
    cmp_ = exp.get("comparison") or {}
    counts = cmp_.get("counts") or {}
    if cmp_.get("verdict") in ("regressions_detected", "insufficient_evidence"):
        return 0.0
    if (exp.get("candidate_run") or {}).get("status") == "could_not_run":
        return 0.0
    return 1.0 if counts.get("fixed", 0) > 0 else 0.5


def experiences() -> list[dict]:
    """All completed experiments across all runs, deduplicated, with their reward."""
    seen: dict[tuple, dict] = {}
    for run_path in sorted(analysis.runs_dir().iterdir()):
        scan_file = run_path / "scan.json"
        if not scan_file.is_file():
            continue
        try:
            scan = json.loads(scan_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        git = scan.get("git") or {}
        repo = git.get("remote_url") or scan.get("repository")
        indicators = {p["normalized_name"]: [i["indicator"] for i in (p.get("assessment") or {}).get("indicators", [])
                                             if i.get("points", 0) > 0]
                      for p in scan.get("packages", [])}
        for exp_file in sorted((run_path / "experiments").glob("*/experiment.json")) if (run_path / "experiments").is_dir() else []:
            try:
                exp = json.loads(exp_file.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            reward = _reward(exp)
            if reward is None:
                continue
            python = (exp.get("candidate_run") or {}).get("python_version")
            key = (repo, git.get("commit"), exp["package"], exp.get("kind"), exp.get("candidate"),
                   exp.get("manifest_requirement"), (python or "")[:4])
            seen[key] = {
                "repository": repo, "commit": git.get("commit"), "run_id": run_path.name,
                "package": exp["package"], "kind": exp.get("kind"), "candidate": exp.get("candidate"),
                "requirement": exp.get("manifest_requirement"), "python": python, "reward": reward,
                "verdict": (exp.get("comparison") or {}).get("verdict"),
                "counts": (exp.get("comparison") or {}).get("counts"),
                "indicators": indicators.get(exp["package"], []),
                "completed_at": exp.get("completed_at"),
            }
    return sorted(seen.values(), key=lambda e: e.get("completed_at") or "")


def _scanned_repos() -> dict[str, set[str]]:
    """package -> set of repositories in which it was declared (from all scans)."""
    out: dict[str, set[str]] = defaultdict(set)
    for run_path in analysis.runs_dir().iterdir():
        scan_file = run_path / "scan.json"
        if not scan_file.is_file():
            continue
        try:
            scan = json.loads(scan_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        repo = (scan.get("git") or {}).get("remote_url") or scan.get("repository")
        for p in scan.get("packages", []):
            out[p["normalized_name"]].add(repo)
    return out


def arm_stats(exps: list[dict]) -> dict[tuple, dict]:
    arms: dict[tuple, dict] = {}
    for e in exps:
        key = (e["package"], e["kind"], e["candidate"])
        a = arms.setdefault(key, {"package": e["package"], "kind": e["kind"], "candidate": e["candidate"],
                                  "tries": 0, "reward_sum": 0.0, "repositories": set(), "requirements": set()})
        a["tries"] += 1
        a["reward_sum"] += e["reward"]
        a["repositories"].add(e["repository"])
        if e.get("requirement"):
            a["requirements"].add(e["requirement"])
    total = max(1, len(exps))
    for a in arms.values():
        a["value"] = round((a["reward_sum"] + 1) / (a["tries"] + 2), 3)  # Beta(1,1) posterior mean
        a["ucb"] = round(a["value"] + math.sqrt(2 * math.log(total + 1) / a["tries"]), 3)
        a["repositories"] = sorted(a["repositories"])
        a["requirements"] = sorted(a["requirements"])
    return arms


def indicator_stats(exps: list[dict]) -> dict[str, dict]:
    stats: dict[str, dict] = {}
    for e in exps:
        for ind in e["indicators"]:
            s = stats.setdefault(ind, {"indicator": ind, "experiments": 0, "worth_migrating": 0})
            s["experiments"] += 1
            s["worth_migrating"] += 1 if e["reward"] >= 1.0 else 0
    for s in stats.values():
        s["precision"] = round((s["worth_migrating"] + 1) / (s["experiments"] + 2), 3)  # smoothed
    return stats


def learned_priority(pkg: dict, ind_stats: dict[str, dict]) -> dict:
    """Rule score weighted by how predictive each fired rule has been in past experiments."""
    fired = [i for i in (pkg.get("assessment") or {}).get("indicators", []) if i.get("points", 0) > 0]
    if not fired:
        return {"value": 0.0, "basis": "No risk rules fired."}
    total, used = 0.0, []
    for i in fired:
        s = ind_stats.get(i["indicator"])
        weight = 2 * s["precision"] if s else 1.0  # unseen rule: neutral weight 1.0
        total += i["points"] * weight
        if s:
            used.append(f"{i['indicator']} ({s['worth_migrating']}/{s['experiments']} past experiments worth it)")
    return {"value": round(total, 2),
            "basis": ("Weighted by experience: " + "; ".join(used)) if used else "No past experiments for these rules yet (neutral weights)."}


def for_package(name: str, exps: list[dict] | None = None) -> dict:
    exps = experiences() if exps is None else exps
    arms = [a for a in arm_stats(exps).values() if a["package"] == name]
    arms.sort(key=lambda a: (-a["ucb"], -a["value"]))
    past = [e for e in exps if e["package"] == name]
    return {
        "evidence_type": "EXECUTION-VERIFIED",
        "past_experiments": len(past),
        "arms": arms,
        "best_bet": arms[0] if arms else None,
        "history": [{k: e[k] for k in ("repository", "candidate", "kind", "requirement", "python", "verdict", "reward")}
                    for e in past[-10:]],
        "repositories_declaring": len(_scanned_repos().get(name, set())),
    }


def summary() -> dict:
    exps = experiences()
    arms = sorted(arm_stats(exps).values(), key=lambda a: (-a["value"], -a["tries"]))
    inds = sorted(indicator_stats(exps).values(), key=lambda s: (-s["precision"], -s["experiments"]))
    repos = _scanned_repos()
    return {
        "evidence_type": "EXECUTION-VERIFIED",
        "experiments_learned_from": len(exps),
        "repositories_experimented": len({e["repository"] for e in exps}),
        "repositories_scanned": len({r for rs in repos.values() for r in rs}),
        "reward_definition": {"1.0": "no regressions and fixed >= 1 failing test", "0.5": "no regressions, nothing fixed",
                              "0.0": "regressions, missing tests, or could not run"},
        "policy": "UCB1 over (package, kind, candidate) arms with Beta(1,1)-smoothed mean reward.",
        "arms": arms,
        "indicators": inds,
        "limitations": [
            "Learns only from experiments GhostLib actually executed; small samples are noisy.",
            "A reward reflects one repository's test suite, which may not exercise the migrated code.",
            "Learned priority re-weights the transparent rule score; it never replaces it.",
        ],
    }


def annotate_run(run: dict) -> None:
    """Attach learned priority and experience to each package of a run (in place)."""
    exps = experiences()
    inds = indicator_stats(exps)
    for pkg in run.get("packages", []):
        pkg["learned"] = {"priority": learned_priority(pkg, inds), **for_package(pkg["normalized_name"], exps)}
