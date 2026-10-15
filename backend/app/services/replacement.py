"""Deterministic replacement-candidate helpers."""
from packaging.utils import canonicalize_name


def normalize_candidate(package_name: str) -> str:
    return canonicalize_name(package_name.strip())


def validate_recommendation(candidate: dict) -> dict:
    """Reject malformed AI suggestions; does not prove compatibility or package legitimacy."""
    if not isinstance(candidate, dict):
        return {"valid": False, "errors": ["Candidate must be an object."]}
    name = candidate.get("package")
    if not isinstance(name, str) or not name.strip():
        return {"valid": False, "errors": ["Candidate package name is required."]}
    normalized = normalize_candidate(name)
    if any(ch in normalized for ch in "/\\\\"):
        return {"valid": False, "errors": ["Package name must not contain a path."]}
    return {"valid": True, "normalized_name": normalized, "errors": [],
            "note": "Name shape validated only; package existence and compatibility remain unverified."}
