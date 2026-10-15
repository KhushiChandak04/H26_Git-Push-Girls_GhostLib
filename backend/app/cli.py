"""GhostLib command-line interface.

    ghostlib scan PATH [--no-metadata] [--recommend] [--min-score N]
    ghostlib recommend RUN_ID (PACKAGE | --all)
    ghostlib experiment RUN_ID PACKAGE [--candidate NAME --kind KIND] [--approve | --reject] [--python 3.12]
    ghostlib capsule RUN_ID
    ghostlib runs
    ghostlib ai-check

``ghostlib PATH`` (no subcommand) is accepted as ``ghostlib scan PATH``.
"""
from __future__ import annotations

import argparse
import json
import sys

from app.services import analysis, experiment, gemma
from app.services.capsule import generate_for_run

COMMANDS = {"scan", "recommend", "experiment", "capsule", "runs", "ai-check"}


def _print(data) -> None:
    print(json.dumps(data, indent=2, default=str))


def cmd_scan(args) -> int:
    run = analysis.create_run(args.repository, fetch_metadata=not args.no_metadata)
    rid = run["run_id"]
    print(f"Run {rid}: {len(run['manifests'])} manifests, {len(run['packages'])} packages, "
          f"{run['source_files_scanned']} Python files scanned (commit {(run.get('git') or {}).get('commit')})")
    print(f"{'score':>5}  {'band':<7} {'package':<18} indicators")
    for pkg in run["packages"]:
        a = pkg["assessment"]
        print(f"{a['score']:>5}  {a['band']:<7} {pkg['normalized_name']:<18} "
              + ", ".join(i["indicator"] for i in a["indicators"]))
    for u in run["undeclared_imports"]:
        print(f"  undeclared import: {u['import_name']} at "
              + ", ".join(f"{l['file']}:{l['line']}" for l in u["locations"]))
    for c in run["declaration_conflicts"]:
        print(f"  conflicting declarations: {c['package']} "
              + "; ".join(f"{d['source']} {d['specifier']}" for d in c["declarations"]))
    if args.recommend:
        print("Requesting Gemma 4 recommendations...")
        _print(analysis.recommend_all(rid, min_score=args.min_score))
    files = generate_for_run(rid)["files"]
    print("Capsule:", *files, sep="\n  ")
    return 0


def cmd_recommend(args) -> int:
    if args.all:
        _print(analysis.recommend_all(args.run_id, min_score=args.min_score))
    else:
        result = analysis.recommend(args.run_id, args.package)
        _print({k: result.get(k) for k in ("status", "reason", "model", "model_version", "recommendation",
                                            "candidate_validation")})
    generate_for_run(args.run_id)
    return 0


def cmd_experiment(args) -> int:
    if args.reject:
        _print(experiment.reject(args.run_id, args.package, reason="rejected via CLI"))
        generate_for_run(args.run_id)
        return 0
    existing = None
    if args.approve:
        try:
            existing = experiment.get_experiment(args.run_id, args.package)
        except FileNotFoundError:
            existing = None
    if existing and existing.get("state") == "proposed" and args.candidate in (None, existing["candidate"]):
        # Approve exactly the proposal that was reviewed; never regenerate (AI output can differ).
        proposal = existing
        print(f"Approving the existing reviewed proposal (diff sha256 of {len(proposal['diff'])} chars).")
    else:
        proposal = experiment.propose(args.run_id, args.package, candidate=args.candidate, kind=args.kind)
    print(f"Proposed candidate: {proposal['candidate']} ({proposal['kind']})")
    for note in proposal["notes"]:
        print("  note:", note)
    print("\n" + (proposal["diff"] or "(no file changes)"))
    if not args.approve:
        print("Review the diff above. Re-run with --approve to execute baseline and candidate tests, "
              "or --reject to discard.")
        return 0
    print(f"Approved. Running baseline and candidate tests on Python {args.python}...")
    record = experiment.approve_and_run(args.run_id, args.package, approved_by="cli user", python=args.python)
    if record["state"] != "completed":
        print("Experiment failed:", record.get("error"))
        return 1
    for side in ("baseline_run", "candidate_run"):
        r = record[side]
        print(f"{side:<14} {r['status']:<14} py{r.get('python_version')}  {r.get('summary_line') or r.get('blocker')}")
    cmp_ = record["comparison"]
    print("verdict:", cmp_["verdict"], cmp_["counts"])
    for row in cmp_["tests"]:
        if row["change"] != "unchanged_pass":
            print(f"  {row['test']}: {row['baseline']} -> {row['candidate']} ({row['change']})")
    print("original repository unchanged:", record["original_repository_check"]["unchanged"])
    generate_for_run(args.run_id)
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] not in COMMANDS and not argv[0].startswith("-"):
        argv = ["scan", *argv]
    parser = argparse.ArgumentParser(prog="ghostlib", description="Evidence-first dependency resilience.")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("scan", help="Scan a repository, fetch PyPI metadata, assess risk, write a capsule")
    p.add_argument("repository")
    p.add_argument("--no-metadata", action="store_true", help="Skip PyPI requests")
    p.add_argument("--recommend", action="store_true", help="Also request Gemma 4 recommendations")
    p.add_argument("--min-score", type=int, default=1)
    p.add_argument("--out", help=argparse.SUPPRESS)  # accepted for backwards compatibility
    p.add_argument("--fetch-metadata", action="store_true", help=argparse.SUPPRESS)
    p.set_defaults(func=cmd_scan)

    p = sub.add_parser("recommend", help="Request Gemma 4 recommendations for a run")
    p.add_argument("run_id")
    p.add_argument("package", nargs="?")
    p.add_argument("--all", action="store_true")
    p.add_argument("--min-score", type=int, default=1)
    p.set_defaults(func=cmd_recommend)

    p = sub.add_parser("experiment", help="Propose / approve / reject a migration experiment")
    p.add_argument("run_id")
    p.add_argument("package")
    p.add_argument("--candidate")
    p.add_argument("--kind", choices=["upgrade", "pypi", "stdlib", "remove"])
    p.add_argument("--python", default="3.12", choices=["3.12", "3.13"])
    g = p.add_mutually_exclusive_group()
    g.add_argument("--approve", action="store_true")
    g.add_argument("--reject", action="store_true")
    p.set_defaults(func=cmd_experiment)

    p = sub.add_parser("capsule", help="(Re)generate capsule.json and capsule.md for a run")
    p.add_argument("run_id")
    p.set_defaults(func=lambda a: (print(*generate_for_run(a.run_id)["files"], sep="\n"), 0)[1])

    p = sub.add_parser("runs", help="List analysis runs")
    p.set_defaults(func=lambda a: (_print(analysis.list_runs()), 0)[1])

    p = sub.add_parser("ai-check", help="Verify Gemma 4 model access")
    p.set_defaults(func=lambda a: (_print(gemma.verify_model()), 0)[1])

    args = parser.parse_args(argv)
    if args.command == "recommend" and not (args.all or args.package):
        parser.error("recommend needs a PACKAGE or --all")
    try:
        return args.func(args)
    except (ValueError, KeyError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
