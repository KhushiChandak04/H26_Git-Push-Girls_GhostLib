from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.services.scanner import scan_repository

router = APIRouter(tags=["scan"])

class ScanRequest(BaseModel):
    repository: str

@router.post("/scan")
def scan(request: ScanRequest):
    path = Path(request.repository).expanduser().resolve()
    if not path.exists() or not path.is_dir():
        raise HTTPException(status_code=400, detail="Repository path must be an existing directory.")
    try:
        return scan_repository(path)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
