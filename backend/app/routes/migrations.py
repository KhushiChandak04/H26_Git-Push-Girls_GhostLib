from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.services.workspace import create_workspace
from app.services.simulator import validate_migration_plan

router = APIRouter(tags=["migrations"])

class WorkspaceRequest(BaseModel):
    repository: str

class PlanRequest(BaseModel):
    plan: dict

@router.post("/migrations/workspace")
def prepare_workspace(request: WorkspaceRequest):
    try:
        return create_workspace(request.repository)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

@router.post("/migrations/validate-plan")
def validate_plan(request: PlanRequest):
    return validate_migration_plan(request.plan)
