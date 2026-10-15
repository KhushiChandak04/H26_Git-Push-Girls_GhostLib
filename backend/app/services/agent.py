"""GhostLib agent: scan -> rank -> recommend -> choose -> prepare -> (approved) test -> learn.

The agent plans with the experience memory (see memory.py) and Gemma 4, but it never runs a
candidate without approval: by default it stops after preparing reviewable diffs. Passing
``approve_all=True`` is an explicit, up-front human approval for this invocation only.
Every executed experiment becomes new experience, so the next run ranks and chooses better.
"""
from __future__ import annotations

import math

from app.services import analysis, experiment, memory


def _choose(pkg: dict, rec: dict | None, exps: list[dict]) -> dict:
    """Pick a candidate with UCB1 over memory arms; untried options get an exploration bonus."""
    name = pkg["normalized_name"]
    options = []
    if rec and rec.get("status") == "ok":
        for c in rec["recommendation"]["candidates"]:
            options.append({"candidate": c["package"], "kind": c["kind"], "from": "gemma",
                            "gemma_recommended": c["package"] == rec["recommendation"]["recommended"]})
    if not any(o["kind"] == "upgrade" and o["candidate"] == name for o in options):
        options.append({"candidate": name, "kind": "upgrade", "from": "deterministic", "gemma_recommended": False})
    arms = memory.arm_stats(exps)
    total = max(1, len(exps))
    for o in options:
        arm = arms.get((name, o["kind"], o["candidate"]))
        if arm:
            o.update(value=arm["value"], ucb=arm["ucb"], tries=arm["tries"])
        else:  # never tried: prior mean 0.5 plus the maximum exploration bonus
            o.update(value=0.5, ucb=round(0.5 + math.sqrt(2 * math.log(total + 1)), 3), tries=0)
    options.sort(key=lambda o: (-o["ucb"], -o["gemma_recommended"], o["kind"] != "upgrade"))
    best = options[0]
    best["why"] = (f"Highest upper confidence bound ({best['ucb']}); "
                   + (f"tried {best['tries']}x with mean reward {best['value']}." if best["tries"]
                      else "never tried before, so the agent explores it.")
                   + (" Gemma's top pick." if best["gemma_recommended"] else ""))
    return {"chosen": best, "options": options}


def auto(repository: str, *, top: int = 3, approve_all: bool = False, python: str = "3.12",
         ask_gemma: bool = True, log=print) -> dict:
    run = analysis.create_run(repository)
    rid = run["run_id"]
    log(f"[scan] run {rid}: {len(run['packages'])} packages")
    run = analysis.get_run(rid)  # includes learned priorities
    ranked = sorted(run["packages"], key=lambda p: (-p["learned"]["priority"]["value"], -p["assessment"]["score"]))
    targets = [p for p in ranked if p["assessment"]["score"] > 0][:top]
    exps = memory.experiences()
    plan = []
    for pkg in targets:
        name = pkg["normalized_name"]
        log(f"[rank] {name}: rule score {pkg['assessment']['score']}, learned priority {pkg['learned']['priority']['value']}")
        rec = analysis.recommend(rid, name) if ask_gemma else None
        if rec:
            log(f"[gemma] {name}: {rec['status']}" + (f" -> {rec['recommendation']['recommended']}" if rec.get("status") == "ok" else ""))
        choice = _choose(pkg, rec, exps)
        c = choice["chosen"]
        log(f"[choose] {name}: {c['kind']} {c['candidate']} - {c['why']}")
        step = {"package": name, "choice": choice}
        try:
            proposal = experiment.propose(rid, name, candidate=c["candidate"], kind=c["kind"])
            step["proposal"] = {"state": proposal["state"], "changed_files": proposal["changed_files"],
                                "diff_file": proposal["diff_file"]}
            log(f"[propose] {name}: diff ready ({len(proposal['changed_files'])} files) at {proposal['diff_file']}")
        except (ValueError, KeyError, FileNotFoundError) as exc:
            step["error"] = str(exc)
            log(f"[propose] {name}: could not prepare ({exc})")
            plan.append(step)
            continue
        if approve_all:
            result = experiment.approve_and_run(rid, name, approved_by="ghostlib auto --approve-all (user pre-approval)",
                                                python=python)
            step["result"] = {"state": result["state"], "verdict": (result.get("comparison") or {}).get("verdict"),
                              "counts": (result.get("comparison") or {}).get("counts"), "error": result.get("error")}
            log(f"[test] {name}: {step['result']['verdict'] or result.get('error')}")
        plan.append(step)
    from app.services.capsule import generate_for_run
    generate_for_run(rid)
    learned = memory.summary()
    log(f"[learn] memory now holds {learned['experiments_learned_from']} verified experiments "
        f"from {learned['repositories_experimented']} repositories")
    if not approve_all:
        log("Diffs are prepared but NOT executed. Review them, then run: "
            f"ghostlib experiment {rid} <package> --approve")
    return {"run_id": rid, "plan": plan, "approved": approve_all, "memory": {k: learned[k] for k in (
        "experiments_learned_from", "repositories_experimented", "repositories_scanned")}}
