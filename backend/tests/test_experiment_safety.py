import pytest

from app.services import analysis, experiment


def test_repository_test_execution_is_blocked_without_a_sandbox(tmp_path):
    record = experiment.prepare_and_test(
        tmp_path / "workspace",
        tmp_path / "venv",
        tmp_path / "logs",
        tmp_path,
        "3.12",
    )
    assert record["status"] == "blocked"
    assert record["evidence_type"] == "UNKNOWN"
    assert "sandbox" in record["blocker"].lower()
    assert record["commands"] == []


def test_run_command_never_executes_project_code_on_host(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    with pytest.raises(RuntimeError, match="sandbox"):
        experiment.run_command(["python", "-c", "print('should not run')"], workspace,
                              tmp_path / "logs", "test", 10, tmp_path)


def test_approval_records_not_run_instead_of_fake_test_results(tmp_path, monkeypatch):
    monkeypatch.setattr(analysis, "ARTIFACTS_DIR", tmp_path)
    run_dir = tmp_path / "runs" / "test-run"
    experiment_dir = run_dir / "experiments" / "requests"
    experiment_dir.mkdir(parents=True)
    (experiment_dir / "experiment.json").write_text(
        '{"package":"requests","candidate":"requests","kind":"upgrade","state":"proposed"}',
        encoding="utf-8",
    )

    result = experiment.approve_and_run("test-run", "requests", approved_by="test", python="3.12")

    assert result["state"] == "blocked"
    assert result["verification"]["status"] == "not_run"
    assert "sandbox" in result["error"].lower()
    assert "baseline_run" not in result
    assert "candidate_run" not in result


@pytest.mark.parametrize("package", ["../outside", "requests/../../outside"])
def test_experiment_package_path_is_validated(package):
    with pytest.raises(ValueError, match="Invalid package"):
        experiment.get_experiment("test-run", package)
