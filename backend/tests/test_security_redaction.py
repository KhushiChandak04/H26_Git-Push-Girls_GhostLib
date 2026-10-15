import json

from app.services import analysis, gemma
from app.services.security import redact_data, redact_text


def test_redacts_api_tokens_and_password_assignments():
    value = "api_key=long-test-secret https://user:password@example.org/x Bearer abcdefghijklmnop"
    result = redact_text(value)
    assert "long-test-secret" not in result
    assert "user:password" not in result
    assert "abcdefghijklmnop" not in result


def test_gemma_sends_only_redacted_prompt_and_hashes_that_prompt(monkeypatch):
    sent = {}
    monkeypatch.setattr(gemma.config, "GEMINI_API_KEY", "test-key")

    def fake_post(url, body, timeout):
        sent["text"] = body["contents"][0]["parts"][0]["text"]
        return {"candidates": [{"content": {"parts": [{"text": json.dumps({
            "package": "demo", "summary": "Use demo.", "candidates": [
                {"package": "demo2", "kind": "pypi", "rationale": "Supported alternative."}],
            "recommended": "demo2", "migration_steps": ["Update imports."],
        })}]}, "finishReason": "STOP"}]}

    monkeypatch.setattr(gemma, "_post", fake_post)
    result = gemma.recommend_migration({"api_key": "long-test-secret-value"})

    assert result["status"] == "ok"
    assert "long-test-secret-value" not in sent["text"]
    assert "long-test-secret-value" not in result["prompt"]


def test_persisted_run_json_is_redacted(tmp_path, monkeypatch):
    monkeypatch.setattr(analysis, "ARTIFACTS_DIR", tmp_path)
    output = tmp_path / "run.json"
    analysis._write(output, {"source": "token=long-secret-value", "count": 3})
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved == {"source": "token=[REDACTED]", "count": 3}


def test_nested_data_redaction_preserves_non_text_values():
    assert redact_data({"items": ["secret=long-value-here"], "count": 2}) == {
        "items": ["secret=[REDACTED]"], "count": 2,
    }
