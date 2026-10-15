"""Evidence-based test planning placeholder; does not generate or execute test code."""
def propose_regression_tests(evidence: dict) -> dict:
    proposals = []
    for file_path in (evidence or {}).get("usage_files", []):
        proposals.append({
            "kind": "review_existing_tests",
            "target": file_path,
            "reason": "File is associated with a dependency usage finding; inspect relevant tests before migration.",
            "status": "suggested_not_executed",
        })
    return {
        "status": "initial_heuristic",
        "proposals": proposals,
        "note": "This is a review checklist, not AI-generated test code. Verify and run tests in isolation.",
    }
