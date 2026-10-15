"""Expose the backend package to ``python -m app.cli`` from the repository root."""
from pathlib import Path

__path__ = [str(Path(__file__).resolve().parents[1] / "backend" / "app")]
