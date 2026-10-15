from app.services.scanner import scan_repository

def test_scan_reads_requirements(tmp_path):
    (tmp_path / "requirements.txt").write_text("requests>=2.0\n# comment\n", encoding="utf-8")
    result = scan_repository(tmp_path)
    assert len(result["dependencies"]) == 1
    assert result["dependencies"][0]["name"] == "requests"
    assert result["dependencies"][0]["specifier"] == ">=2.0"
