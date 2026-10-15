import json

from app import config
from app.services import gemma

VALID = {
    "package": "toml", "summary": "Use tomllib.",
    "candidates": [{"package": "tomllib", "kind": "stdlib", "import_name": "tomllib", "rationale": "In stdlib 3.11+."}],
    "recommended": "tomllib", "migration_steps": ["Replace toml.load with tomllib.load in binary mode."],
}


def _fake_response(text):
    return {"candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}],
            "modelVersion": "gemma-4-26b-a4b-it"}


def test_missing_key_is_explicitly_unavailable(monkeypatch):
    monkeypatch.setattr(config, "GEMINI_API_KEY", None)
    result = gemma.recommend_migration({"x": 1})
    assert result["status"] == "AI_UNAVAILABLE"
    assert "recommendation" not in result


def test_valid_output_in_code_fence_is_parsed(monkeypatch):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(gemma, "_post", lambda *a: _fake_response("```json\n" + json.dumps(VALID) + "\n```"))
    result = gemma.recommend_migration({"x": 1})
    assert result["status"] == "ok"
    assert result["evidence_type"] == "AI-RECOMMENDED"
    assert result["recommendation"]["recommended"] == "tomllib"


def test_malformed_output_is_rejected_not_substituted(monkeypatch):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(gemma, "_post", lambda *a: _fake_response('{"package": "toml", "candidates": []}'))
    result = gemma.recommend_migration({"x": 1}, retries=0)
    assert result["status"] == "AI_INVALID_OUTPUT"
    assert "recommendation" not in result
