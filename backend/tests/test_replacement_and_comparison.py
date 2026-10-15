from app.services.experiment import _edit_manifests, compare, run_command
from app.services.replacement import validate_recommendation


def test_replacement_candidate_shape_validation():
    assert validate_recommendation({"package": "my_pkg"})["valid"]
    assert not validate_recommendation({"package": ""})["valid"]
    assert not validate_recommendation({"package": "evil; rm -rf /"})["valid"]


def _run(cases, status="passed", installed=None):
    return {"status": status, "installed": installed or {},
            "tests": {"cases": {k: {"outcome": v} for k, v in cases.items()}}}


def test_comparison_classifies_fixed_and_regression():
    result = compare(_run({"a": "failed", "b": "passed", "c": "passed"}, "tests_failed", {"x": "1"}),
                     _run({"a": "passed", "b": "failed", "c": "passed"}, "tests_failed", {"x": "2"}))
    changes = {r["test"]: r["change"] for r in result["tests"]}
    assert changes == {"a": "fixed", "b": "regression", "c": "unchanged_pass"}
    assert result["verdict"] == "regressions_detected"
    assert result["installed_version_changes"] == {"x": {"baseline": "1", "candidate": "2"}}


def test_comparison_without_results_is_insufficient():
    assert compare({}, {})["verdict"] == "insufficient_evidence"


def test_manifest_edit_replaces_requirement_line(tmp_path):
    (tmp_path / "requirements.txt").write_text("toml==0.10.2\nJinja2==2.11.3\n", encoding="utf-8")
    pkg = {"declarations": [{"source": "requirements.txt", "line": 2, "raw": "Jinja2==2.11.3"}]}
    edits = _edit_manifests(tmp_path, pkg, "Jinja2==3.1.6")
    assert edits["requirements.txt"] == "toml==0.10.2\nJinja2==3.1.6\n"
    assert _edit_manifests(tmp_path, pkg, None)["requirements.txt"] == "toml==0.10.2\n"


def test_run_command_refuses_cwd_outside_boundary(tmp_path):
    inside, outside = tmp_path / "box", tmp_path / "other"
    inside.mkdir()
    outside.mkdir()
    try:
        run_command(["python", "--version"], outside, tmp_path / "logs", "x", 10, inside)
    except ValueError:
        return
    raise AssertionError("expected refusal")
