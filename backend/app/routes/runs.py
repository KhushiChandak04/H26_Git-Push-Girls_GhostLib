"""REST API for the dashboard. Thin wrappers over the same services the CLI uses."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, Field

from app.services import analysis, experiment, gemma
from app.services.capsule import capsule_for_run, generate_for_run

router = APIRouter(prefix="/api", tags=["ghostlib"])


def _guard(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except (ValueError, KeyError) as exc:
        raise HTTPException(400, str(exc).strip("'")) from exc


class RunRequest(BaseModel):
    repository: str = Field(min_length=1, max_length=1000)
    mode: str | None = Field(default=None, pattern="^(local|github)$")
    fetch_metadata: bool = True


class ProposeRequest(BaseModel):
    candidate: str | None = Field(default=None, max_length=100)
    kind: str | None = Field(default=None, pattern="^(upgrade|pypi|stdlib|remove)$")
    use_ai_code_changes: bool = True
    also: list[str] = Field(default_factory=list, max_length=20)


class ApproveRequest(BaseModel):
    confirm: bool
    approved_by: str = Field(default="dashboard user", max_length=100)
    python: str = Field(default="3.12", pattern=r"^3\.1[23]$")


class OpenRequest(BaseModel):
    file: str = Field(min_length=1, max_length=1000)
    line: int = Field(default=1, ge=1, le=10_000_000)
    scope: str = Field(default="repo", pattern="^(repo|run)$")


class RejectRequest(BaseModel):
    reason: str = Field(default="", max_length=500)


@router.get("/health")
def health():
    from app.services.capsule import LEGEND, TOOL_VERSION
    return {"status": "ok", "project": "GhostLib", "version": TOOL_VERSION, "ai": gemma.model_info(),
            "supported_pythons": sorted(experiment.ALLOWED_PYTHONS), "default_python": experiment.DEFAULT_PYTHON,
            "evidence_legend": LEGEND}


@router.get("/rubric")
def risk_rubric():
    from app.services.risk_engine import rubric
    return rubric()


@router.get("/learning")
def learning():
    from app.services import memory
    return memory.summary()


@router.get("/ai/status")
def ai_status():
    return gemma.verify_model()


@router.get("/runs")
def list_runs():
    return analysis.list_runs()


@router.post("/runs")
def create_run(req: RunRequest):
    from app.services.repo_input import resolve
    target = _guard(resolve, req.repository, req.mode)
    run = _guard(analysis.create_run, target["path"], fetch_metadata=req.fetch_metadata)
    analysis.set_input_info(run["run_id"], target)
    return _guard(analysis.get_run, run["run_id"])


@router.post("/scan")  # backwards-compatible alias
def scan(req: RunRequest):
    return create_run(req)


@router.get("/runs/{run_id}")
def get_run(run_id: str):
    return _guard(analysis.get_run, run_id)


@router.get("/runs/{run_id}/source")
def source(run_id: str, file: str, line: int = 1, context: int = 8):
    run = _guard(analysis.get_run, run_id)
    root = Path(run["repository"]).resolve()
    target = (root / file).resolve()
    if root not in target.parents or not target.is_file():
        raise HTTPException(400, "File is outside the scanned repository or does not exist.")
    lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
    lo, hi = max(1, line - context), min(len(lines), line + context)
    return {"file": file, "line": line, "start": lo,
            "lines": [{"n": n, "text": lines[n - 1]} for n in range(lo, hi + 1)], "evidence_type": "OBSERVED"}


@router.post("/runs/{run_id}/open")
def open_in_editor(run_id: str, req: OpenRequest):
    from app.services.editor import EditorError, open_in_vscode
    try:
        return open_in_vscode(run_id, req.file, req.line, req.scope)
    except EditorError as exc:
        raise HTTPException(400, str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc


class CompareRequest(BaseModel):
    file: str = Field(min_length=1, max_length=1000)


@router.get("/runs/{run_id}/experiments/{package}/workspace")
def workspace_info(run_id: str, package: str):
    from app.services.editor import EditorError, prepare_workspace
    try:
        return prepare_workspace(run_id, package)
    except EditorError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/runs/{run_id}/experiments/{package}/open-workspace")
def open_migrated_workspace(run_id: str, package: str):
    from app.services.editor import EditorError, open_workspace
    try:
        return open_workspace(run_id, package)
    except EditorError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/runs/{run_id}/experiments/{package}/compare")
def compare_in_editor(run_id: str, package: str, req: CompareRequest):
    from app.services.editor import EditorError, compare_file
    try:
        return compare_file(run_id, package, req.file)
    except EditorError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/runs/{run_id}/recommendations/{package}")
def recommend(run_id: str, package: str):
    result = _guard(analysis.recommend, run_id, package)
    return {k: v for k, v in result.items() if k != "prompt"}


@router.post("/runs/{run_id}/recommendations")
def recommend_all(run_id: str, min_score: int = 1):
    result = _guard(analysis.recommend_all, run_id, min_score=min_score)
    return result


@router.post("/runs/{run_id}/experiments/{package}/propose")
def propose(run_id: str, package: str, req: ProposeRequest):
    return _guard(experiment.propose, run_id, package, candidate=req.candidate, kind=req.kind,
                  use_ai_code_changes=req.use_ai_code_changes, also=req.also)


@router.post("/runs/{run_id}/experiments/{package}/approve")
def approve(run_id: str, package: str, req: ApproveRequest):
    if not req.confirm:
        raise HTTPException(400, "Explicit confirmation is required to run the experiment.")
    return _guard(experiment.approve_in_background, run_id, package, req.approved_by, req.python)


@router.post("/runs/{run_id}/experiments/{package}/reject")
def reject(run_id: str, package: str, req: RejectRequest):
    record = _guard(experiment.reject, run_id, package, req.reason)
    return record


@router.get("/runs/{run_id}/experiments/{package}")
def get_experiment(run_id: str, package: str):
    record = _guard(experiment.get_experiment, run_id, package)
    return record


@router.get("/runs/{run_id}/experiments/{package}/logs/{name}", response_class=PlainTextResponse)
def experiment_log(run_id: str, package: str, name: str, side: str = "candidate"):
    if not name.replace("-", "").replace(".", "").isalnum() or ".." in name:
        raise HTTPException(400, "Invalid log name.")
    rdir = _guard(analysis.run_dir, run_id)
    record = _guard(experiment.get_experiment, run_id, package)
    if side == "baseline":
        base = rdir / f"baseline-py{record.get('python_requested', '3.12')}" / "logs"
    else:
        base = rdir / "experiments" / package / "logs"
    path = base / name
    if not path.is_file():
        raise HTTPException(404, "Log not found.")
    return path.read_text(encoding="utf-8", errors="replace")


@router.post("/runs/{run_id}/capsule")
def capsule(run_id: str, force: bool = False):
    return _guard(generate_for_run, run_id) if force else _guard(capsule_for_run, run_id)


@router.get("/runs/{run_id}/capsule.{fmt}")
def capsule_file(run_id: str, fmt: str):
    if fmt not in ("json", "md"):
        raise HTTPException(400, "Format must be json or md.")
    rdir = _guard(analysis.run_dir, run_id)
    path = rdir / "capsule" / f"capsule.{fmt}"
    if not path.is_file():
        generate_for_run(run_id)
    media = "application/json" if fmt == "json" else "text/markdown"
    return FileResponse(path, media_type=media, filename=f"dependency-exit-capsule-{run_id}.{fmt}")
