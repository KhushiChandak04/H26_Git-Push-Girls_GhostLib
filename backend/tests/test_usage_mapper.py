from app.services.scanner import scan_repository

def test_usage_mapper_finds_import(tmp_path):
    (tmp_path / "requirements.txt").write_text("requests>=2\n", encoding="utf-8")
    (tmp_path / "example.py").write_text("import requests\n", encoding="utf-8")
    result = scan_repository(tmp_path)
    assert result["usage"][0]["status"] == "observed"
    assert "example.py" in result["usage"][0]["files"]
