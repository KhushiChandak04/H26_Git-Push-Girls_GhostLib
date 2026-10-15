from pathlib import Path
from fastapi import APIRouter, HTTPException
from app.services.scanner import scan_repository
from app.services.capsule import build_capsule, write_capsule
from app.services.metadata import get_package_metadata

router = APIRouter(tags=["capsule"])

@router.post("/capsule")
def generate_capsule(repository: str, output_dir: str = "artifacts", fetch_metadata: bool = False):
    path = Path(repository).expanduser().resolve()
    if not path.is_dir():
        raise HTTPException(status_code=400, detail="Repository path must be an existing directory.")
    result = scan_repository(path)
    metadata = {}
    if fetch_metadata:
        for dep in result["dependencies"]:
            name = dep.get("normalized_name")
            if name and name not in metadata:
                metadata[name] = get_package_metadata(name, allow_network=True)
    capsule = build_capsule(result, metadata)
    files = write_capsule(capsule, Path(output_dir))
    return {"capsule": capsule, "files": files}
