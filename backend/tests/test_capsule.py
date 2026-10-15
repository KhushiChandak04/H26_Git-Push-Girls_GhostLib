import json

from app.services.capsule import build_capsule, write_capsule
from app.services.metadata import fetch_all  # noqa: F401  (import check)
from app.services.risk_engine import assess_package
from app.services.scanner import scan_repository


def test_capsule_from_scan_without_ai_or_experiments(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "requirements.txt").write_text("toml==0.10.2\n", encoding="utf-8")
    (repo / "app.py").write_text("import toml\ntoml.load('x')\n", encoding="utf-8")
    run = scan_repository(repo)
    for pkg in run["packages"]:
        pkg["metadata"] = {"status": "not_fetched"}
        pkg["assessment"] = assess_package(pkg, None)
    run["run_id"] = "test-run"
    capsule = build_capsule(run)
    paths = write_capsule(capsule, tmp_path / "out")
    data = json.loads((tmp_path / "out" / "capsule.json").read_text(encoding="utf-8"))
    md = (tmp_path / "out" / "capsule.md").read_text(encoding="utf-8")
    assert len(paths) == 2
    dep = data["dependencies"][0]
    assert dep["recommendation"]["status"] == "not_requested"
    assert dep["experiment"]["state"] == "not_run"
    assert any("No candidate experiment executed" in g["gap"] for g in dep["compatibility_gaps"])
    assert "`app.py:1` `import toml`" in md
    assert "AI-RECOMMENDED" in md
