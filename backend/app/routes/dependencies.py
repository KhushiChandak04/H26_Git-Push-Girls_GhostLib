from pathlib import Path
from fastapi import APIRouter, HTTPException
from app.services.scanner import scan_repository
from app.services.risk_engine import assess_dependency

router = APIRouter(tags=["dependencies"])

@router.get("/dependencies")
def dependencies(repository: str):
    path = Path(repository).expanduser().resolve()
    if not path.is_dir():
        raise HTTPException(status_code=400, detail="Repository path must be an existing directory.")
    result = scan_repository(path)
    return {"dependencies": [
        {**dep, "assessment": assess_dependency(dep, result.get("python_requirement"))}
        for dep in result["dependencies"]
    ]}
