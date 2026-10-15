"""Evidence packaging for Gemma and deterministic validation of its replacement candidates.

Validation establishes only what can be checked (package exists on PyPI, declared
Python support, stdlib module present in the running interpreter). It never proves that
a candidate is a compatible or suitable replacement.
"""
from __future__ import annotations

import importlib.util
import platform
import sys
from pathlib import Path

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.utils import canonicalize_name

from app.services.metadata import get_package_metadata

TARGET_PYTHONS = ("3.12", "3.13")
MAX_LOCATIONS = 12
SNIPPET_CONTEXT = 3


def normalize_candidate(package_name: str) -> str:
    return canonicalize_name(package_name.strip())


def validate_recommendation(candidate: dict) -> dict:
    """Reject malformed suggestions; does not prove compatibility or package legitimacy."""
    if not isinstance(candidate, dict):
        return {"valid": False, "errors": ["Candidate must be an object."]}
    name = candidate.get("package")
    if not isinstance(name, str) or not name.strip():
        return {"valid": False, "errors": ["Candidate package name is required."]}
    if any(ch in name for ch in "/\\ ;&|`$"):
        return {"valid": False, "errors": ["Package name contains disallowed characters."]}
    return {"valid": True, "normalized_name": normalize_candidate(name), "errors": [],
            "note": "Name shape validated only; package existence and compatibility remain unverified."}


def _snippet(root: Path, rel: str, line: int) -> str | None:
    path = (root / rel).resolve()
    if root not in path.parents:
        return None
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    lo, hi = max(0, line - 1 - SNIPPET_CONTEXT), min(len(lines), line + SNIPPET_CONTEXT)
    return "\n".join(f"{i + 1}: {lines[i]}" for i in range(lo, hi))


def _function_bodies(root: Path, rel: str, symbols: list[str]) -> list[str]:
    """Return the source of functions in ``rel`` that reference any used symbol (bounded)."""
    import ast
    path = root / rel
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source)
    except (OSError, SyntaxError):
        return []
    tails = {s.split(".")[-1] for s in symbols} | {s.split(".")[0] for s in symbols}
    bodies = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            seg = ast.get_source_segment(source, node) or ""
            if any(t and t in seg for t in tails) and len(seg) < 2500:
                bodies.append(f"# {rel}:{node.lineno}\n{seg}")
    return bodies[:4]


def build_evidence(pkg: dict, metadata: dict | None, assessment: dict | None, scan: dict) -> dict:
    """Collect the facts Gemma may use. Everything here is OBSERVED or SOURCED."""
    root = Path(scan["repository"])
    locations = pkg.get("locations", [])[:MAX_LOCATIONS]
    usage = pkg.get("usage") or {}
    files = sorted({loc["file"] for loc in locations if not loc["is_test"]})
    bodies = []
    for f in files[:4]:
        syms = sorted({s for loc in locations if loc["file"] == f for s in loc["symbols_used"] + loc["imported_names"]})
        bodies += _function_bodies(root, f, syms)
    meta = metadata or {}
    return {
        "repository": {"name": (scan.get("project") or {}).get("name"), "commit": (scan.get("git") or {}).get("commit"),
                       "declared_requires_python": scan.get("python_requirement"), "target_runtime": "Python 3.12 / 3.13"},
        "dependency": {
            "name": pkg["normalized_name"],
            "declarations": pkg.get("declarations"),
            "groups": pkg.get("groups"),
            "import_names": pkg.get("import_names"),
        },
        "pypi_metadata_SOURCED": {k: meta.get(k) for k in (
            "status", "source", "latest_version", "most_recent_upload", "requires_python", "python_classifiers",
            "development_status", "summary", "pinned")} if meta else {"status": "not_fetched"},
        "risk_indicators": [{k: i[k] for k in ("indicator", "evidence_type", "evidence")}
                            for i in (assessment or {}).get("indicators", [])],
        "usage_OBSERVED": {
            "status": usage.get("status"),
            "locations": [{"file": l["file"], "line": l["line"], "statement": l["statement"],
                           "symbols_used": l["symbols_used"], "is_test": l["is_test"],
                           "snippet": _snippet(root, l["file"], l["line"])} for l in locations],
            "functions_using_dependency": bodies,
            "relevant_tests": usage.get("relevant_tests"),
            "coverage_gap": usage.get("coverage_gap"),
        },
    }


def _python_support(requires_python: str | None, classifiers: list[str] | None) -> dict:
    result = {}
    for v in TARGET_PYTHONS:
        if requires_python:
            try:
                ok = SpecifierSet(requires_python).contains(f"{v}.0")
                result[v] = "allowed_by_requires_python" if ok else "excluded_by_requires_python"
                continue
            except InvalidSpecifier:
                pass
        result[v] = "classifier_listed" if v in (classifiers or []) else "not_declared"
    return result


def validate_candidates(recommendation: dict, pkg: dict) -> list[dict]:
    """Deterministically check each AI candidate. Returns one record per candidate."""
    checks = []
    for cand in recommendation.get("candidates", []):
        shape = validate_recommendation(cand)
        record = {"package": cand.get("package"), "kind": cand.get("kind"), "checks": [], "status": "unverified"}
        if not shape["valid"]:
            record.update(status="rejected", checks=[{"check": "name_shape", "result": "fail", "detail": shape["errors"]}])
            checks.append(record)
            continue
        kind = cand.get("kind")
        if kind == "stdlib":
            module = cand.get("import_name") or cand["package"]
            top = module.split(".")[0]
            in_stdlib = top in sys.stdlib_module_names
            importable = importlib.util.find_spec(top) is not None if in_stdlib else False
            record["checks"] += [
                {"check": "is_stdlib_module", "result": "pass" if in_stdlib else "fail", "evidence_type": "EXECUTION-VERIFIED",
                 "detail": f"'{top}' {'is' if in_stdlib else 'is not'} in sys.stdlib_module_names on Python {platform.python_version()}"},
                {"check": "importable_here", "result": "pass" if importable else "fail", "evidence_type": "EXECUTION-VERIFIED",
                 "detail": f"importlib.util.find_spec('{top}') on Python {platform.python_version()}"},
            ]
            record["status"] = "exists" if in_stdlib and importable else "rejected"
        elif kind in ("pypi", "upgrade"):
            meta = get_package_metadata(normalize_candidate(cand["package"]))
            exists = meta.get("status") == "fetched"
            record["metadata"] = {k: meta.get(k) for k in ("status", "source", "latest_version", "most_recent_upload",
                                                           "requires_python", "python_classifiers", "license", "summary")}
            record["checks"].append({"check": "exists_on_pypi", "result": "pass" if exists else "fail",
                                     "evidence_type": "SOURCED", "detail": meta.get("source")})
            if exists:
                support = _python_support(meta.get("requires_python"), meta.get("python_classifiers"))
                record["checks"].append({"check": "declared_python_support", "result": support, "evidence_type": "SOURCED",
                                         "detail": f"requires_python={meta.get('requires_python')!r}"})
            record["status"] = "exists" if exists else "rejected"
        elif kind == "remove":
            unused = (pkg.get("usage") or {}).get("status") == "not_observed_static"
            record["checks"].append({"check": "no_static_import_observed", "result": "pass" if unused else "fail",
                                     "evidence_type": "OBSERVED",
                                     "detail": "Scanner found no static import" if unused else "Scanner found imports; removal would break code"})
            record["status"] = "consistent_with_scan" if unused else "contradicted_by_scan"
        record["note"] = "Existence/declared-support checks only. Compatibility is NOT established until tests run."
        checks.append(record)
    return checks
