"""Create disposable copies for experiments. This module does not execute code."""
from pathlib import Path
import shutil
import tempfile

IGNORE = shutil.ignore_patterns(
    ".git", ".venv", "venv", "env", "node_modules", "__pycache__", "dist",
    "build", ".pytest_cache", ".mypy_cache", ".ruff_cache"
)


def create_workspace(repository: str, base_directory: str | None = None) -> dict:
    source = Path(repository).expanduser().resolve()
    if not source.is_dir():
        raise ValueError(f"Repository is not a directory: {source}")
    temp_root = Path(tempfile.mkdtemp(prefix="ghostlib-", dir=base_directory))
    destination = temp_root / source.name
    try:
        shutil.copytree(source, destination, ignore=IGNORE)
    except Exception:
        shutil.rmtree(temp_root, ignore_errors=True)
        raise
    return {
        "source": str(source),
        "workspace": str(destination),
        "workspace_root": str(temp_root),
        "status": "created",
        "copied_files_note": "Common VCS/cache/virtualenv directories were excluded.",
        "commands_executed": [],
        "warning": "No migration, installation or tests were executed. Workspace cleanup is manual in this starter.",
    }
