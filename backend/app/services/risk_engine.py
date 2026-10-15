"""Evidence-based indicators. Deliberately does not fabricate a single risk score."""
from __future__ import annotations


def assess_dependency(dependency: dict, python_requirement: str | None = None) -> dict:
    indicators = []
    if dependency.get("parse_status") == "unparsed":
        indicators.append({
            "indicator": "declaration_not_fully_parsed",
            "severity": "medium",
            "evidence": dependency.get("parse_error") or "Declaration was not parsed as a standard requirement.",
        })
    if not dependency.get("specifier"):
        indicators.append({
            "indicator": "version_not_pinned_or_constrained",
            "severity": "low",
            "evidence": "No version specifier was parsed from this declaration.",
        })
    usage = dependency.get("usage") or {}
    if usage.get("status") == "not_observed_static":
        indicators.append({
            "indicator": "no_static_import_observed",
            "severity": "info",
            "evidence": "The scanner did not find a matching top-level Python import in scanned files.",
        })
    if python_requirement:
        indicators.append({
            "indicator": "python_compatibility_requires_review",
            "severity": "info",
            "evidence": f"Repository declares Python requirement {python_requirement}; candidate compatibility still needs verification.",
        })
    return {
        "package": dependency.get("name"),
        "risk_status": "review" if any(x["severity"] in {"medium", "high"} for x in indicators)
                      else ("attention" if indicators else "no_flagged_indicators"),
        "indicators": indicators,
        "score": None,
        "disclaimer": "Indicators are triage signals, not a validated probability or security assessment.",
    }
