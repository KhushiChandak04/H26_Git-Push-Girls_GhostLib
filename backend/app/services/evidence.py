"""Structured evidence records for reports and future execution logs."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib


def evidence_record(kind: str, claim: str, source: str | None = None,
                    status: str = "observed", details: dict | None = None) -> dict:
    return {
        "kind": kind, "claim": claim, "source": source, "status": status,
        "details": details or {},
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }


def file_evidence(path: str | Path, root: str | Path) -> dict:
    file_path, root_path = Path(path).resolve(), Path(root).resolve()
    digest = hashlib.sha256(file_path.read_bytes()).hexdigest()
    try:
        relative = file_path.relative_to(root_path).as_posix()
    except ValueError:
        relative = str(file_path)
    return evidence_record("file", f"Read file {relative}", relative,
                           details={"sha256": digest, "bytes": file_path.stat().st_size})
