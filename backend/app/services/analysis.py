"""Analysis runs: scan + metadata + risk + (optional) Gemma recommendations, persisted to disk.

A run lives in ``artifacts/runs/<run_id>/``. The CLI and the API both use these functions,
so the dashboard always shows exactly what the CLI would produce.
"""
from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from app.config import ARTIFACTS_DIR
from app.services import gemma
from app.services.metadata import fetch_all
from app.services.replacement import build_evidence, validate_candidates
from app.services.risk_engine import assess_package
from app.services.scanner import scan_repository

RUN_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
PKG_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,99}$")


def runs_dir() -> Path:
    path = Path(ARTIFACTS_DIR) / "runs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def run_dir(run_id: str) -> Path:
    if not RUN_ID_RE.match(run_id or ""):
        raise ValueError("Invalid run id.")
    path = runs_dir() / run_id
    if not path.is_dir():
        raise FileNotFoundError(f"Run not found: {run_id}")
    return path


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def create_run(repository: str | Path, *, fetch_metadata: bool = True) -> dict:
    scan = scan_repository(repository)
    if not scan["manifests"] and scan["source_files_scanned"] == 0:
        raise ValueError(f"No Python project found at {scan['repository']}: 0 dependency manifests and 0 .py files "
                         "(after skipping .git, venvs, node_modules and build folders). Check that the path is the "
                         "repository's top folder. Nothing was saved.")
    metadata = fetch_all(scan["packages"]) if fetch_metadata else {}
    from app.services import advisories
    vulns = advisories.check(scan["packages"]) if fetch_metadata else {}
    for pkg in scan["packages"]:
        meta = metadata.get(pkg["normalized_name"])
        pkg["metadata"] = meta or {"status": "not_fetched", "reason": "Metadata fetch disabled for this run."}
        pkg["assessment"] = assess_package(pkg, meta)
        pkg["advisories"] = vulns.get(pkg["normalized_name"]) or {
            "status": "not_checked", "evidence_type": "UNKNOWN", "reason": "Network lookups disabled for this run."}
    scan["packages"].sort(key=lambda p: (-p["assessment"]["score"], p["normalized_name"]))
    commit = (scan.get("git") or {}).get("commit") or "nogit"
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + commit[:7]
    scan["run_id"] = run_id
    scan["created_at"] = datetime.now(timezone.utc).isoformat()
    scan["metadata_fetched"] = fetch_metadata
    _write(runs_dir() / run_id / "scan.json", scan)
    return scan


def refresh_advisories(run_id: str) -> dict:
    """Run the OSV.dev lookup for an existing run's pinned versions and store it on the run."""
    from app.services import advisories
    path = run_dir(run_id) / "scan.json"
    scan = _read(path)
    results = advisories.check(scan["packages"])
    for pkg in scan["packages"]:
        pkg["advisories"] = results.get(pkg["normalized_name"])
    _write(path, scan)
    return {k: (v["status"], v.get("unique_issues")) for k, v in results.items()}


def set_input_info(run_id: str, target: dict) -> None:
    """Record how the repository was provided (local path or GitHub URL clone)."""
    path = run_dir(run_id) / "scan.json"
    scan = _read(path)
    scan["input"] = {k: str(v) for k, v in target.items()}
    _write(path, scan)


def list_runs() -> list[dict]:
    out = []
    for path in sorted(runs_dir().iterdir(), reverse=True):
        scan_file = path / "scan.json"
        if scan_file.is_file():
            try:
                scan = _read(scan_file)
            except (OSError, ValueError):
                continue
            exp_dir, rec_dir = path / "experiments", path / "recommendations"
            completed = 0
            for f in exp_dir.glob("*/experiment.json") if exp_dir.is_dir() else []:
                try:
                    completed += _read(f).get("state") == "completed"
                except (OSError, ValueError):
                    pass
            out.append({"run_id": path.name, "repository": scan.get("repository"), "created_at": scan.get("created_at"),
                        "commit": (scan.get("git") or {}).get("commit"), "packages": len(scan.get("packages", [])),
                        "recommendations": len(list(rec_dir.glob("*.json"))) if rec_dir.is_dir() else 0,
                        "experiments_completed": completed,
                        "at_risk": sum(1 for p in scan.get("packages", []) if (p.get("assessment") or {}).get("score", 0) > 0),
                        "input": (scan.get("input") or {}).get("source", "local")})
    return out


def get_run(run_id: str) -> dict:
    path = run_dir(run_id)
    scan = _read(path / "scan.json")
    recs = {}
    for f in sorted((path / "recommendations").glob("*.json")) if (path / "recommendations").is_dir() else []:
        recs[f.stem] = _read(f)
    experiments = {}
    for f in sorted((path / "experiments").glob("*/experiment.json")) if (path / "experiments").is_dir() else []:
        experiments[f.parent.name] = _read(f)
    scan["recommendations"] = recs
    scan["experiments"] = experiments
    scan["run_status"] = run_status(scan, recs, experiments)
    from app.services import memory  # local import: memory replays runs via this module
    memory.annotate_run(scan)
    return scan


def _package(scan: dict, package: str) -> dict:
    if not PKG_RE.match(package or ""):
        raise ValueError("Invalid package name.")
    for pkg in scan["packages"]:
        if pkg["normalized_name"] == package:
            return pkg
    raise KeyError(f"Package {package} not in run.")


def log_ai_call(run_id: str, purpose: str, package: str, result: dict, output_ref: str | None = None) -> None:
    """Append one Gemma request to the run's audit log (ai_calls.jsonl). Never stores keys; prompt as hash only."""
    usage = result.get("usage") or {}
    record = {
        "call_id": result.get("call_id"), "run_id": run_id, "purpose": purpose, "package": package,
        "status": result.get("status"), "error": result.get("reason") if result.get("status") != "ok" else None,
        "model_requested": result.get("model"), "model_version_returned": result.get("model_version"),
        "inference_method": result.get("inference_method"), "requested_at": result.get("requested_at"),
        "latency_seconds": result.get("latency_seconds"), "prompt_tokens": usage.get("promptTokenCount"),
        "output_tokens": usage.get("candidatesTokenCount"), "thought_tokens": usage.get("thoughtsTokenCount"),
        "finish_reason": result.get("finish_reason"), "prompt_sha256": result.get("prompt_sha256"),
        "output_ref": output_ref,
    }
    with (run_dir(run_id) / "ai_calls.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")


def read_ai_calls(run_id: str) -> list[dict] | None:
    path = run_dir(run_id) / "ai_calls.jsonl"
    if not path.is_file():
        return None
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def run_status(scan: dict, recs: dict, experiments: dict) -> dict:
    """How complete a run is. Only executed experiments count as tested."""
    at_risk = [p["normalized_name"] for p in scan.get("packages", []) if (p.get("assessment") or {}).get("score", 0) > 0]
    rec_ok = [k for k, v in recs.items() if v.get("status") == "ok"]
    tested = [k for k, v in experiments.items() if v.get("state") == "completed"]
    running = [k for k, v in experiments.items() if v.get("state") == "running"]
    failed = [k for k, v in experiments.items() if v.get("state") == "failed"]
    untested = [p for p in at_risk if p not in tested]
    if running:
        status = "running"
    elif at_risk and not untested and all(p in rec_ok for p in at_risk):
        status = "complete"
    elif rec_ok or tested:
        status = "partial"
    else:
        status = "scan_only"
    return {"status": status, "packages": len(scan.get("packages", [])), "at_risk": len(at_risk),
            "recommendations_ok": len(rec_ok), "experiments_completed": len(tested), "experiments_failed": failed,
            "untested_at_risk": untested, "running": running}


def recommend(run_id: str, package: str) -> dict:
    path = run_dir(run_id)
    scan = _read(path / "scan.json")
    pkg = _package(scan, package)
    evidence = build_evidence(pkg, pkg.get("metadata"), pkg.get("assessment"), scan)
    from app.services import memory
    past = memory.for_package(package)
    if past["history"]:
        evidence["prior_outcomes_EXECUTION_VERIFIED"] = {
            "note": "Real results of earlier GhostLib experiments for this package (possibly other repositories).",
            "history": past["history"],
        }
    result = gemma.recommend_migration(evidence)
    result["package"] = package
    result["evidence_sent"] = evidence
    if result.get("status") == "ok":
        result["candidate_validation"] = validate_candidates(result["recommendation"], pkg)
    _write(path / "recommendations" / f"{package}.json", result)
    if result.get("status") != "AI_UNAVAILABLE":
        log_ai_call(run_id, "replacement recommendation", package, result, f"recommendations/{package}.json")
    return result


def recommend_all(run_id: str, *, min_score: int = 1, workers: int = 3) -> dict:
    scan = _read(run_dir(run_id) / "scan.json")
    targets = [p["normalized_name"] for p in scan["packages"] if p["assessment"]["score"] >= min_score]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = dict(zip(targets, pool.map(lambda name: recommend(run_id, name), targets)))
    return {name: r.get("status") for name, r in results.items()}
