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
    metadata = fetch_all(scan["packages"]) if fetch_metadata else {}
    for pkg in scan["packages"]:
        meta = metadata.get(pkg["normalized_name"])
        pkg["metadata"] = meta or {"status": "not_fetched", "reason": "Metadata fetch disabled for this run."}
        pkg["assessment"] = assess_package(pkg, meta)
    scan["packages"].sort(key=lambda p: (-p["assessment"]["score"], p["normalized_name"]))
    commit = (scan.get("git") or {}).get("commit") or "nogit"
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + commit[:7]
    scan["run_id"] = run_id
    scan["created_at"] = datetime.now(timezone.utc).isoformat()
    scan["metadata_fetched"] = fetch_metadata
    _write(runs_dir() / run_id / "scan.json", scan)
    return scan


def list_runs() -> list[dict]:
    out = []
    for path in sorted(runs_dir().iterdir(), reverse=True):
        scan_file = path / "scan.json"
        if scan_file.is_file():
            try:
                scan = _read(scan_file)
            except (OSError, ValueError):
                continue
            out.append({"run_id": path.name, "repository": scan.get("repository"), "created_at": scan.get("created_at"),
                        "commit": (scan.get("git") or {}).get("commit"), "packages": len(scan.get("packages", []))})
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
    return scan


def _package(scan: dict, package: str) -> dict:
    if not PKG_RE.match(package or ""):
        raise ValueError("Invalid package name.")
    for pkg in scan["packages"]:
        if pkg["normalized_name"] == package:
            return pkg
    raise KeyError(f"Package {package} not in run.")


def recommend(run_id: str, package: str) -> dict:
    path = run_dir(run_id)
    scan = _read(path / "scan.json")
    pkg = _package(scan, package)
    evidence = build_evidence(pkg, pkg.get("metadata"), pkg.get("assessment"), scan)
    result = gemma.recommend_migration(evidence)
    result["package"] = package
    result["evidence_sent"] = evidence
    if result.get("status") == "ok":
        result["candidate_validation"] = validate_candidates(result["recommendation"], pkg)
    _write(path / "recommendations" / f"{package}.json", result)
    return result


def recommend_all(run_id: str, *, min_score: int = 1, workers: int = 3) -> dict:
    scan = _read(run_dir(run_id) / "scan.json")
    targets = [p["normalized_name"] for p in scan["packages"] if p["assessment"]["score"] >= min_score]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = dict(zip(targets, pool.map(lambda name: recommend(run_id, name), targets)))
    return {name: r.get("status") for name, r in results.items()}
