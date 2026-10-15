"""Transparent, rule-based dependency-resilience indicators.

Each indicator states its evidence type (OBSERVED from the repository, SOURCED from
PyPI), the evidence itself, and the points it contributes. The total is a triage
ranking aid only: it is not a probability, and it is not a security assessment.
Vulnerability data is deliberately not part of this score.
"""
from __future__ import annotations

from datetime import datetime, timezone

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

TARGET_PYTHONS = ("3.12", "3.13")
STALE_YEARS = 3
SCORE_BANDS = ((6, "high"), (3, "medium"), (1, "low"), (0, "none"))
RUBRIC = {
    "declaration_conflict": 3,
    "pinned_python_incompatible": 3,
    "pinned_version_yanked": 3,
    "inactive_development_status": 3,
    "no_release_in_years": 2,
    "pinned_major_behind_latest": 2,
    "private_api_usage": 2,
    "runtime_monkeypatch_target": 1,
    "pinned_release_old": 1,
    "target_python_not_declared": 1,
    "declared_not_imported": 1,
    "no_relevant_tests": 1,
    "unconstrained_version": 0,
    "metadata_unavailable": 0,
}


def _years_since(iso: str | None) -> float | None:
    if not iso:
        return None
    try:
        when = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (datetime.now(timezone.utc) - when).days / 365.25


def _indicator(key: str, evidence_type: str, evidence: str, source: str | None = None, **details) -> dict:
    return {"indicator": key, "points": RUBRIC[key], "evidence_type": evidence_type,
            "evidence": evidence, "source": source, "details": details}


def assess_package(pkg: dict, metadata: dict | None = None) -> dict:
    """Assess one scanner package record (see scanner._group_packages) with optional PyPI metadata."""
    metadata = metadata or {}
    indicators: list[dict] = []
    decls = pkg.get("declarations", [])
    first = decls[0] if decls else {}
    where = ", ".join(f"{d['source']}:{d['line']}" if d.get("line") else d["source"] for d in decls)
    usage = pkg.get("usage") or {}

    specs = {d.get("specifier") or "" for d in decls}
    if len(specs) > 1:
        indicators.append(_indicator(
            "declaration_conflict", "OBSERVED",
            "Declared with different constraints: " + "; ".join(
                f"{d['source']}:{d.get('line') or '?'} -> {d.get('specifier') or '(any)'}" for d in decls),
            where))
    if specs == {""}:
        indicators.append(_indicator("unconstrained_version", "OBSERVED",
                                     f"No version constraint declared ({where}). Installs are not reproducible.", where))

    if usage.get("status") == "not_observed_static" and not pkg.get("is_test_tooling"):
        indicators.append(_indicator(
            "declared_not_imported", "OBSERVED",
            "No static import of " + ", ".join(pkg.get("import_names", [])) +
            " was found in scanned Python files. It may be unused, or used indirectly/dynamically.", where))
    for loc in usage.get("private_api_uses", []):
        indicators.append(_indicator(
            "private_api_usage", "OBSERVED",
            f"Uses private API {', '.join(loc['private_api'])} — not covered by the package's compatibility promises.",
            f"{loc['file']}:{loc['line']}", statement=loc["statement"]))
    patched = [loc for loc in usage_locations(pkg) if any(s.endswith((".request", ".send")) and "Session" in s
                                                          for s in loc["symbols_used"]) and "patch" in loc["file"]]
    for loc in patched:
        indicators.append(_indicator(
            "runtime_monkeypatch_target", "OBSERVED",
            "Module-level code replaces a library method at import time; upgrades that change the method signature break silently.",
            f"{loc['file']}:{loc['line']}"))
    if usage.get("source_files") and not usage.get("relevant_tests"):
        indicators.append(_indicator(
            "no_relevant_tests", "OBSERVED",
            "Source files using this package are not imported by any test file (directly or transitively).",
            ", ".join(usage["source_files"])))

    if metadata.get("status") != "fetched":
        if metadata:
            indicators.append(_indicator("metadata_unavailable", "UNKNOWN",
                                         f"PyPI metadata unavailable ({metadata.get('status')}: {metadata.get('reason', '')}).",
                                         metadata.get("source")))
    else:
        src = metadata.get("source")
        years = _years_since(metadata.get("most_recent_upload"))
        if years is not None and years >= STALE_YEARS:
            indicators.append(_indicator(
                "no_release_in_years", "SOURCED",
                f"Most recent upload to PyPI was {metadata['most_recent_upload'][:10]} ({years:.1f} years ago). "
                "Signals low maintenance activity; it does not by itself prove abandonment.", src))
        status = metadata.get("development_status") or ""
        if any(s in status for s in ("Inactive", "Obsolete")):
            indicators.append(_indicator("inactive_development_status", "SOURCED",
                                         f"PyPI classifier 'Development Status :: {status}'.", src))
        classifiers = metadata.get("python_classifiers") or []
        if classifiers and not any(v in classifiers for v in TARGET_PYTHONS):
            indicators.append(_indicator(
                "target_python_not_declared", "SOURCED",
                f"Latest release declares Python classifiers {classifiers[0]}–{classifiers[-1]}; "
                f"none for {' / '.join(TARGET_PYTHONS)}. Compatibility is unverified, not disproven.", src))
        pinned = metadata.get("pinned") or {}
        if pinned.get("exists_on_pypi"):
            psrc = pinned.get("source") or src
            if pinned.get("yanked"):
                indicators.append(_indicator("pinned_version_yanked", "SOURCED",
                                             f"Pinned version {pinned['version']} is yanked on PyPI.", psrc))
            rp = pinned.get("requires_python")
            if rp:
                try:
                    bad = [v for v in TARGET_PYTHONS if not SpecifierSet(rp).contains(f"{v}.0")]
                except InvalidSpecifier:
                    bad = []
                if bad:
                    indicators.append(_indicator("pinned_python_incompatible", "SOURCED",
                                                 f"Pinned {pinned['version']} declares Requires-Python '{rp}', excluding {bad}.", psrc))
            page = _years_since(pinned.get("release_date"))
            if page is not None and page >= STALE_YEARS:
                indicators.append(_indicator(
                    "pinned_release_old", "SOURCED",
                    f"Pinned version {pinned['version']} was released {pinned['release_date'][:10]} ({page:.1f} years ago).", psrc))
            try:
                if Version(pinned["version"]).major < Version(metadata["latest_version"]).major:
                    indicators.append(_indicator(
                        "pinned_major_behind_latest", "SOURCED",
                        f"Pinned {pinned['version']} is a major version behind latest {metadata['latest_version']}.", src))
            except (InvalidVersion, TypeError, KeyError):
                pass
        elif pinned and pinned.get("exists_on_pypi") is False:
            indicators.append(_indicator("pinned_version_yanked", "SOURCED",
                                         f"Pinned version {pinned['version']} was not found among PyPI releases.", src))

    score = sum(i["points"] for i in indicators)
    band = next(name for threshold, name in SCORE_BANDS if score >= threshold)
    return {
        "package": pkg.get("normalized_name"),
        "score": score,
        "band": band,
        "indicators": sorted(indicators, key=lambda i: -i["points"]),
        "rubric": "Sum of rule points (see RUBRIC). Bands: >=6 high, >=3 medium, >=1 low.",
        "disclaimer": "Triage ranking from observed and sourced signals; not a probability, "
                      "not proof of abandonment, and not a security assessment.",
        "primary_declaration": {"source": first.get("source"), "line": first.get("line"), "raw": first.get("raw")},
    }


def usage_locations(pkg: dict) -> list[dict]:
    return pkg.get("locations", [])


def assess_dependency(dependency: dict, python_requirement: str | None = None) -> dict:
    """Lightweight per-declaration check kept for the flat dependency list."""
    indicators = []
    if dependency.get("parse_status") in {"unparsed", "error"}:
        indicators.append({"indicator": "declaration_not_fully_parsed", "severity": "medium",
                           "evidence": dependency.get("parse_error") or "Declaration was not parsed."})
    if not dependency.get("specifier"):
        indicators.append({"indicator": "version_not_pinned_or_constrained", "severity": "low",
                           "evidence": "No version specifier was parsed from this declaration."})
    if (dependency.get("usage") or {}).get("status") == "not_observed_static":
        indicators.append({"indicator": "no_static_import_observed", "severity": "info",
                           "evidence": "No matching Python import found in scanned files."})
    return {
        "package": dependency.get("name"),
        "risk_status": "review" if any(x["severity"] in {"medium", "high"} for x in indicators)
        else ("attention" if indicators else "no_flagged_indicators"),
        "indicators": indicators,
        "score": None,
        "disclaimer": "Per-declaration triage signals; see package assessments for the ranked view.",
    }
