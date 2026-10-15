"""Gemma 4 adapter boundary.

The event's inference restrictions must be confirmed before selecting an adapter.
This module deliberately does not make an undocumented hosted API call.
"""
class GemmaNotConfigured(RuntimeError):
    pass


def recommend_migration(evidence: dict) -> dict:
    raise GemmaNotConfigured(
        "Gemma 4 is not configured. Add an organizer-approved inference adapter, "
        "record model/version/access terms, and validate its output before use."
    )
