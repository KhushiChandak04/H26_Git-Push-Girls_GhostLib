"""Configuration defaults. Keep secrets out of source control.

Values come from the process environment; ``backend/.env`` and the repo-root ``.env``
(both git-ignored) are loaded as fallbacks without overriding variables already set.
"""
from pathlib import Path
import os

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


for _env in (PROJECT_ROOT / "backend" / ".env", PROJECT_ROOT / ".env"):
    _load_env_file(_env)

_artifacts = Path(os.getenv("GHOSTLIB_ARTIFACTS_DIR", PROJECT_ROOT / "artifacts"))
ARTIFACTS_DIR = (_artifacts if _artifacts.is_absolute() else (PROJECT_ROOT / "backend" / _artifacts)).resolve()
MAX_SOURCE_FILE_BYTES = int(os.getenv("GHOSTLIB_MAX_SOURCE_FILE_BYTES", "1000000"))

# Gemma 4 via Google AI Studio (Gemini API). The key is never logged or written to artifacts.
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
GEMMA_MODEL = os.getenv("GEMMA_MODEL", "gemma-4-26b-a4b-it")
GEMMA_API_BASE = os.getenv("GEMMA_API_BASE", "https://generativelanguage.googleapis.com/v1beta")
GEMMA_TIMEOUT_SECONDS = float(os.getenv("GEMMA_TIMEOUT_SECONDS", "300"))
# "minimal" keeps Gemma 4's hidden reasoning from exhausting the output budget; set empty to disable.
GEMMA_THINKING_LEVEL = os.getenv("GEMMA_THINKING_LEVEL", "minimal")
