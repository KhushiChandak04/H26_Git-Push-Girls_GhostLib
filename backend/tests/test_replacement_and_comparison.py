from app.services.replacement import validate_recommendation
from app.services.simulator import validate_migration_plan
from app.services.equivalence import compare_results


def test_replacement_candidate_shape_validation():
    assert validate_recommendation({"package": "my_pkg"})["valid"]
    assert not validate_recommendation({"package": ""})["valid"]


def test_migration_plan_rejects_shell_command_type():
    result = validate_migration_plan({"actions": [{"type": "run_shell", "reason": "test"}]})
    assert not result["valid"]
    assert result["execution_status"] == "not_executed"


def test_comparison_detects_test_count_difference():
    result = compare_results(
        {"exit_code": 0, "passed": 10, "failed": 0, "skipped": 0},
        {"exit_code": 1, "passed": 9, "failed": 1, "skipped": 0},
    )
    assert result["status"] == "differences_detected"
