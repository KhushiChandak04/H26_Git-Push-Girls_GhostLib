"""Redact common credential formats from prompts and persisted evidence."""
from __future__ import annotations

import re
from typing import Any

_PATTERNS = (
    (re.compile(r"(?i)\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"), "[REDACTED]"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[REDACTED]"),
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{8,}"), "Bearer [REDACTED]"),
    (re.compile(r"(?i)(https?://)[^/\s:@]+:[^/\s@]+@"), r"\1[REDACTED]@"),
    (re.compile(
        r"""(?i)(["']?\b(?:api[_-]?key|access[_-]?token|auth(?:orization)?|client[_-]?secret|password|passwd|secret|token)\b["']?)"""
        r"""(\s*[:=]\s*)(["']?)[^\s,;"']{8,}"""),
     r"\1\2\3[REDACTED]"),
)


def redact_text(value: str) -> str:
    for pattern, replacement in _PATTERNS:
        value = pattern.sub(replacement, value)
    return value


def redact_data(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, list):
        return [redact_data(item) for item in value]
    if isinstance(value, tuple):
        return [redact_data(item) for item in value]
    if isinstance(value, dict):
        return {key: redact_data(item) for key, item in value.items()}
    return value
