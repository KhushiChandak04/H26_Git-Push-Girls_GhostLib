from app.services.risk_engine import assess_dependency

def test_unconstrained_dependency_gets_explainable_indicator():
    result = assess_dependency({"name": "demo", "specifier": ""})
    assert result["risk_status"] == "attention"
    assert result["score"] is None
    assert result["indicators"][0]["indicator"] == "version_not_pinned_or_constrained"
