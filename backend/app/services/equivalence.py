"""Transparent baseline/candidate test-result comparison."""
def compare_results(baseline: dict, candidate: dict) -> dict:
    if not isinstance(baseline, dict) or not isinstance(candidate, dict):
        return {"status": "insufficient_evidence", "differences": [],
                "note": "Baseline and candidate must both be result objects."}
    keys = ("exit_code", "passed", "failed", "skipped")
    differences = {
        key: {"baseline": baseline.get(key), "candidate": candidate.get(key)}
        for key in keys if baseline.get(key) != candidate.get(key)
    }
    if "exit_code" not in baseline or "exit_code" not in candidate:
        status = "insufficient_evidence"
    elif differences:
        status = "differences_detected"
    else:
        status = "same_reported_summary"
    return {
        "status": status,
        "differences": differences,
        "note": "Matching test summaries do not prove complete behavioral equivalence; compare environments, output and coverage too.",
    }
