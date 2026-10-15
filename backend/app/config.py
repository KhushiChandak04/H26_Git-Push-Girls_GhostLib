"""Configuration defaults. Keep secrets out of source control."""
from pathlib import Path
import os

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS_DIR = Path(os.getenv("GHOSTLIB_ARTIFACTS_DIR", PROJECT_ROOT.parent / "artifacts"))
MAX_SOURCE_FILE_BYTES = int(os.getenv("GHOSTLIB_MAX_SOURCE_FILE_BYTES", "1000000"))
