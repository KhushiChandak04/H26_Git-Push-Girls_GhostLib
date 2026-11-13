import asyncio

import pytest
from fastapi import HTTPException, Request
from fastapi.responses import Response

from app import config
from app.main import require_hosted_api_token
from app.routes import runs


def _request(path, *, authorization=None):
    headers = []
    if authorization:
        headers.append((b"authorization", authorization.encode()))
    return Request({
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": headers,
        "server": ("testserver", 80),
        "client": ("192.0.2.1", 1234),
    })


def _invoke(request):
    async def call_next(_request):
        return Response("reached endpoint")
    return asyncio.run(require_hosted_api_token(request, call_next))


def test_hosted_api_requires_token_but_keeps_health_public(monkeypatch):
    monkeypatch.setattr(config, "HOSTED_MODE", True)
    monkeypatch.setattr(config, "API_TOKEN", "test-token")

    health = _invoke(_request("/api/health"))
    assert health.status_code == 200
    assert _invoke(_request("/api/rubric")).status_code == 401

    response = _invoke(_request("/api/rubric", authorization="Bearer test-token"))
    assert response.body == b"reached endpoint"


def test_hosted_api_fails_closed_without_token(monkeypatch):
    monkeypatch.setattr(config, "HOSTED_MODE", True)
    monkeypatch.setattr(config, "API_TOKEN", "")

    response = _invoke(_request("/api/rubric"))

    assert response.status_code == 503
    assert b"GHOSTLIB_API_TOKEN" in response.body


def test_hosted_scan_rate_limit(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "HOSTED_MODE", True)
    runs._scan_requests.clear()

    for _ in range(5):
        runs._enforce_scan_rate_limit("192.0.2.1")

    with pytest.raises(HTTPException) as exc:
        runs._enforce_scan_rate_limit("192.0.2.1")
    assert exc.value.status_code == 429
