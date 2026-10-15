"""Typed capsule schema starter."""
from typing import Any
from pydantic import BaseModel, Field

class DependencyExitCapsule(BaseModel):
    schema_version: str = "0.1"
    generated_at: str
    project: str
    dependencies: list[dict[str, Any]] = Field(default_factory=list)
    evidence_status: str = "partial"
    limitations: list[str] = Field(default_factory=list)
    open_concerns: list[str] = Field(default_factory=list)
