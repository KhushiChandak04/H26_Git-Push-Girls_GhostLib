from app.services.scanner import scan_repository


def test_scan_reads_requirements(tmp_path):
    (tmp_path / "requirements.txt").write_text("requests>=2.0\n# comment\n", encoding="utf-8")
    result = scan_repository(tmp_path)
    assert len(result["dependencies"]) == 1
    assert result["dependencies"][0]["name"] == "requests"
    assert result["dependencies"][0]["specifier"] == ">=2.0"


def _sample_project(tmp_path):
    (tmp_path / "requirements.txt").write_text("toml==0.10.2\nrequests==2.31.0\nsix\n# PyYAML==5.1\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="demo"\nrequires-python=">=3.10"\ndependencies=["toml>=0.10"]\n', encoding="utf-8")
    sub = tmp_path / "services" / "api"
    sub.mkdir(parents=True)
    (sub / "requirements-dev.txt").write_text("pytest\n", encoding="utf-8")
    pkg = tmp_path / "demo"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "config.py").write_text("import toml\n\ndef load(p):\n    return toml.load(p)\n", encoding="utf-8")
    (pkg / "net.py").write_text(
        "import certifi\nfrom requests.utils import _parse_content_type_header\n", encoding="utf-8")
    (pkg / "cli.py").write_text("def main():\n    from .config import load\n    return load\n", encoding="utf-8")
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_cli.py").write_text("from demo.cli import main\n", encoding="utf-8")
    venv = tmp_path / ".venv" / "lib"
    venv.mkdir(parents=True)
    (venv / "requirements.txt").write_text("ignored==1.0\n", encoding="utf-8")
    return tmp_path


def test_nested_manifests_discovered_and_venv_skipped(tmp_path):
    result = scan_repository(_sample_project(tmp_path))
    paths = {m["path"] for m in result["manifests"]}
    assert "services/api/requirements-dev.txt" in paths
    assert not any(".venv" in p for p in paths)
    assert result["python_requirement"] == ">=3.10"


def test_usage_locations_have_line_and_symbols(tmp_path):
    result = scan_repository(_sample_project(tmp_path))
    toml_pkg = next(p for p in result["packages"] if p["normalized_name"] == "toml")
    loc = toml_pkg["locations"][0]
    assert loc["file"] == "demo/config.py" and loc["line"] == 1
    assert "toml.load" in loc["symbols_used"]
    # Test reaches config.py transitively via a function-level relative import in cli.py.
    assert toml_pkg["usage"]["relevant_tests"] == ["tests/test_cli.py"]


def test_conflicts_private_api_undeclared_and_commented(tmp_path):
    result = scan_repository(_sample_project(tmp_path))
    assert [c["package"] for c in result["declaration_conflicts"]] == ["toml"]
    requests_pkg = next(p for p in result["packages"] if p["normalized_name"] == "requests")
    assert requests_pkg["usage"]["private_api_uses"][0]["private_api"] == ["_parse_content_type_header"]
    assert [u["import_name"] for u in result["undeclared_imports"]] == ["certifi"]
    assert result["commented_out_requirements"][0]["raw"] == "# PyYAML==5.1"
    six_pkg = next(p for p in result["packages"] if p["normalized_name"] == "six")
    assert six_pkg["usage"]["status"] == "not_observed_static"
