from app.services.capsule import build_capsule, write_capsule

def test_capsule_writes_json_and_markdown(tmp_path):
    capsule = build_capsule({
        "repository": "/example", "python_requirement": ">=3.12",
        "manifests": ["requirements.txt"],
        "dependencies": [{"name": "requests", "normalized_name": "requests",
                          "specifier": ">=2", "source": "requirements.txt",
                          "parse_status": "parsed"}],
        "usage": [], "limitations": [],
    })
    paths = write_capsule(capsule, tmp_path)
    assert len(paths) == 2
    assert (tmp_path / "dependency-exit-capsule.json").is_file()
    assert (tmp_path / "dependency-exit-capsule.md").is_file()
