"""Gemma 4 adapter (Google AI Studio / Gemini API, REST).

Gemma receives only collected evidence (declarations, PyPI facts, usage locations and
short source snippets) and returns a recommendation that is validated against a strict
Pydantic schema. Output is always labelled AI-RECOMMENDED. On any failure the caller gets
an explicit status (AI_UNAVAILABLE / AI_ERROR / AI_INVALID_OUTPUT) — never substitute text.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Literal
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from pydantic import BaseModel, Field, ValidationError

from app import config

INFERENCE_METHOD = "Google AI Studio Gemini API (REST v1beta generateContent)"
TERMS_URL = "https://ai.google.dev/gemma/terms"


class Candidate(BaseModel):
    package: str = Field(min_length=1, max_length=100)
    kind: Literal["pypi", "stdlib", "upgrade", "remove"]
    import_name: str | None = Field(default=None, max_length=100)
    rationale: str = Field(min_length=1, max_length=1500)
    pros: list[str] = Field(default_factory=list, max_length=8)
    cons: list[str] = Field(default_factory=list, max_length=8)
    compatibility_notes: list[str] = Field(default_factory=list, max_length=8)


class CodeChange(BaseModel):
    file: str = Field(max_length=300)
    description: str = Field(max_length=1500)


class SuggestedTest(BaseModel):
    name: str = Field(max_length=150)
    description: str = Field(max_length=1500)
    target_file: str | None = Field(default=None, max_length=300)


class MigrationRecommendation(BaseModel):
    package: str
    summary: str = Field(max_length=2000)
    candidates: list[Candidate] = Field(min_length=1, max_length=4)
    recommended: str
    migration_steps: list[str] = Field(min_length=1, max_length=15)
    code_changes: list[CodeChange] = Field(default_factory=list, max_length=15)
    breaking_changes: list[str] = Field(default_factory=list, max_length=10)
    suggested_tests: list[SuggestedTest] = Field(default_factory=list, max_length=10)
    uncertainties: list[str] = Field(default_factory=list, max_length=10)


SCHEMA_HINT = {
    "package": "<declared package name>",
    "summary": "<2-3 sentences>",
    "candidates": [{"package": "<name>", "kind": "pypi|stdlib|upgrade|remove", "import_name": "<module>",
                    "rationale": "...", "pros": ["..."], "cons": ["..."], "compatibility_notes": ["..."]}],
    "recommended": "<one candidate package name>",
    "migration_steps": ["..."],
    "code_changes": [{"file": "<path from evidence>", "description": "..."}],
    "breaking_changes": ["..."],
    "suggested_tests": [{"name": "test_...", "description": "...", "target_file": "<path>"}],
    "uncertainties": ["..."],
}

SYSTEM_PROMPT = """You are a senior Python maintainer helping plan a dependency migration.
You receive EVIDENCE collected by deterministic tools from a real repository.
Rules:
- Base every statement on the evidence. Do not invent package versions, dates, or test results.
- Recommend 1-3 candidates. Use kind "stdlib" for standard-library replacements, "upgrade" to stay on
  the same package at a newer major version, "remove" if the dependency appears unused, else "pypi".
- The target runtime is Python 3.12 and 3.13.
- Only refer to files that appear in the evidence.
- List what you are unsure about in "uncertainties".
- If EVIDENCE contains prior_outcomes_EXECUTION_VERIFIED, those are real past test results: prefer candidates
  that previously produced no regressions, and mention past failures in "uncertainties".
Respond with ONLY a JSON object matching this shape (no markdown fences):
"""


def model_info() -> dict:
    return {"model": config.GEMMA_MODEL, "inference_method": INFERENCE_METHOD, "terms": TERMS_URL,
            "api_base": config.GEMMA_API_BASE, "configured": bool(config.GEMINI_API_KEY)}


def _post(url: str, body: dict, timeout: float) -> dict:
    req = Request(url, data=json.dumps(body).encode("utf-8"), method="POST",
                  headers={"Content-Type": "application/json", "x-goog-api-key": config.GEMINI_API_KEY or ""})
    with urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def verify_model() -> dict:
    """Ask the API whether the configured model exists (records the served model resource)."""
    if not config.GEMINI_API_KEY:
        return {"status": "AI_UNAVAILABLE", "reason": "GEMINI_API_KEY is not set.", **model_info()}
    url = f"{config.GEMMA_API_BASE}/models/{quote(config.GEMMA_MODEL)}"
    try:
        req = Request(url, headers={"x-goog-api-key": config.GEMINI_API_KEY})
        with urlopen(req, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))
        return {"status": "available", "model_resource": data.get("name"), "display_name": data.get("displayName"),
                "version": data.get("version"), **model_info()}
    except HTTPError as exc:
        return {"status": "AI_ERROR", "reason": f"HTTP {exc.code}: {_error_text(exc)}", **model_info()}
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        return {"status": "AI_ERROR", "reason": str(exc), **model_info()}


def _error_text(exc: HTTPError) -> str:
    try:
        return json.loads(exc.read().decode("utf-8")).get("error", {}).get("message", "")[:300]
    except Exception:
        return ""


def _extract_json(text: str) -> dict:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("No JSON object found in model output.")
    return json.loads(text[start:end + 1])


def _response_text(data: dict) -> str:
    parts = ((data.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
    # Skip "thought" parts if thinking is enabled; keep the answer text.
    return "".join(p.get("text", "") for p in parts if not p.get("thought"))


class FileRewrite(BaseModel):
    path: str = Field(max_length=300)
    new_content: str = Field(max_length=60000)
    explanation: str = Field(max_length=1500)


class CodeChangeProposal(BaseModel):
    files: list[FileRewrite] = Field(default_factory=list, max_length=10)
    notes: list[str] = Field(default_factory=list, max_length=10)


CODE_PROMPT = """You are migrating a Python repository from the dependency `{package}` to `{candidate}` ({kind}).
Target runtime: Python 3.12 and 3.13. Dependency manifests are already edited; do NOT include them.
Rewrite ONLY the files below that need changes, returning the COMPLETE new content of each changed file.
Keep behaviour identical; keep the public API of every module unchanged; change as little as possible.
You may add ONE new regression test file at tests/test_ghostlib_{slug}.py that exercises the migrated code
using only the standard library and pytest (no network).
{guidance}
Respond with ONLY JSON: {{"files": [{{"path": "...", "new_content": "...", "explanation": "..."}}], "notes": ["..."]}}

FILES:
{files}
"""


def propose_code_changes(*, package: str, candidate: str, kind: str, files: dict[str, str],
                         recommendation: dict | None = None) -> dict:
    """Ask Gemma for full-file rewrites. Output is AI-RECOMMENDED and must be reviewed before use."""
    guidance = ""
    if recommendation:
        guidance = "Migration steps proposed earlier:\n- " + "\n- ".join(recommendation.get("migration_steps", []))
    rendered = "\n\n".join(f"=== {path} ===\n{content}" for path, content in files.items())
    prompt = CODE_PROMPT.format(package=package, candidate=candidate, kind=kind,
                                slug=re.sub(r"[^a-z0-9]+", "_", package.lower()), guidance=guidance, files=rendered)
    return _generate(prompt, CodeChangeProposal, "proposal", max_tokens=16384)


def recommend_migration(evidence: dict, *, retries: int = 2) -> dict:
    """Return {status, recommendation?, raw_text, prompt, ...}. Never raises for API problems."""
    prompt = SYSTEM_PROMPT + json.dumps(SCHEMA_HINT, indent=1) + "\n\nEVIDENCE:\n" + json.dumps(evidence, indent=1)
    return _generate(prompt, MigrationRecommendation, "recommendation", retries=retries)


def _generate(prompt: str, schema: type[BaseModel], key: str, *, retries: int = 2, max_tokens: int = 8192) -> dict:
    """Call Gemma in JSON mode. The output budget must cover Gemma 4's thinking tokens as well as
    the answer (observed: ~1.7k thought tokens for a recommendation), hence the large limits."""
    base = {"evidence_type": "AI-RECOMMENDED", **model_info(), "call_id": uuid.uuid4().hex[:16],
            "requested_at": datetime.now(timezone.utc).isoformat()}
    if not config.GEMINI_API_KEY:
        return {**base, "status": "AI_UNAVAILABLE",
                "reason": "GEMINI_API_KEY is not set. Deterministic scan results remain valid; no AI output was generated."}
    body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": max_tokens,
                                 "responseMimeType": "application/json"}}
    if config.GEMMA_THINKING_LEVEL:
        # Unbounded thinking was observed to consume the entire output budget (8k thought tokens,
        # no answer). "minimal" is the only thinking control this model accepts via the API.
        body["generationConfig"]["thinkingConfig"] = {"thinkingLevel": config.GEMMA_THINKING_LEVEL}
    base["generation_config"] = body["generationConfig"]
    url = f"{config.GEMMA_API_BASE}/models/{quote(config.GEMMA_MODEL)}:generateContent"
    base["prompt_sha256"] = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    base["prompt"] = prompt

    last_error = None
    for attempt in range(retries + 1):
        started = time.monotonic()
        try:
            data = _post(url, body, config.GEMMA_TIMEOUT_SECONDS)
        except HTTPError as exc:
            last_error = f"HTTP {exc.code}: {_error_text(exc)}"
            if exc.code == 400 and "thinkingConfig" in body["generationConfig"] and "hinking" in last_error:
                body["generationConfig"].pop("thinkingConfig")  # model rejects the setting; retry without
                base["generation_config"] = body["generationConfig"]
                continue
            if exc.code in (429, 500, 502, 503, 504) and attempt < retries:
                time.sleep(5 * (attempt + 1))
                continue
            return {**base, "status": "AI_ERROR", "reason": last_error}
        except (URLError, TimeoutError, OSError, ValueError) as exc:
            last_error = str(exc)
            if attempt < retries:
                continue
            return {**base, "status": "AI_ERROR", "reason": last_error}
        elapsed = round(time.monotonic() - started, 2)
        raw = _response_text(data)
        usage = data.get("usageMetadata", {})
        meta = {"model_version": data.get("modelVersion"), "latency_seconds": elapsed,
                "usage": usage, "raw_text": raw, "finish_reason": ((data.get("candidates") or [{}])[0]).get("finishReason")}
        try:
            parsed = schema.model_validate(_extract_json(raw))
        except (ValueError, ValidationError) as exc:
            last_error = f"Schema validation failed: {str(exc)[:800]}"
            if attempt < retries:
                continue
            return {**base, **meta, "status": "AI_INVALID_OUTPUT", "reason": last_error}
        dumped = parsed.model_dump()
        if key == "proposal":
            return {**base, **meta, "status": "ok", **dumped}
        return {**base, **meta, "status": "ok", key: dumped}
    return {**base, "status": "AI_ERROR", "reason": last_error}
