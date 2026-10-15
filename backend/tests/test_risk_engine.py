from app.services.risk_engine import assess_dependency, assess_package


def test_unconstrained_dependency_gets_explainable_indicator():
    result = assess_dependency({"name": "demo", "specifier": ""})
    assert result["risk_status"] == "attention"
    assert result["indicators"][0]["indicator"] == "version_not_pinned_or_constrained"


def _pkg(**usage):
    return {"normalized_name": "toml", "import_names": ["toml"],
            "declarations": [{"source": "requirements.txt", "line": 1, "specifier": "==0.10.2", "raw": "toml==0.10.2"}],
            "usage": {"status": "observed", "source_files": ["a.py"], "relevant_tests": ["tests/t.py"], **usage},
            "locations": []}


def test_sourced_signals_carry_source_and_points():
    meta = {"status": "fetched", "source": "https://pypi.org/pypi/toml/json", "latest_version": "0.10.2",
            "most_recent_upload": "2020-11-01T00:00:00Z", "python_classifiers": ["3.7", "3.8", "3.9"],
            "pinned": {"version": "0.10.2", "exists_on_pypi": True, "release_date": "2020-11-01T00:00:00Z",
                       "requires_python": ">=2.6", "yanked": False}}
    result = assess_package(_pkg(), meta)
    keys = {i["indicator"] for i in result["indicators"]}
    assert {"no_release_in_years", "target_python_not_declared", "pinned_release_old"} <= keys
    assert all(i["evidence_type"] == "SOURCED" and i["source"] for i in result["indicators"])
    assert result["score"] == sum(i["points"] for i in result["indicators"])


def test_missing_metadata_is_unknown_not_risky():
    result = assess_package(_pkg(), {"status": "fetch_error", "reason": "offline"})
    assert result["indicators"][0]["evidence_type"] == "UNKNOWN"
    assert result["score"] == 0


def test_recent_package_without_issues_scores_zero():
    meta = {"status": "fetched", "source": "x", "latest_version": "1.0", "most_recent_upload": None,
            "python_classifiers": ["3.12", "3.13"]}
    assert assess_package(_pkg(), meta)["band"] == "none"
