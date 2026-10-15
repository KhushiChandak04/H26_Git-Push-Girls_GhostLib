import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_python_module_cli_imports_from_repository_root():
    result = subprocess.run(
        [sys.executable, "-m", "app.cli", "--help"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "pipeline" in result.stdout


def test_new_run_ids_are_unique():
    from app.services.analysis import new_run_id

    assert new_run_id("deadbeef") != new_run_id("deadbeef")
