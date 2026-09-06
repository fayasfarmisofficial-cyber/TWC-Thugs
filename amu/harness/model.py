"""Anthropic client wrapper. No ANTHROPIC_API_KEY ⇒ `manual` mode: the caller prints the brief and waits for a human."""

from __future__ import annotations

import json
import os


def available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def ask_json(system: str, user: str, model: str = "claude-sonnet-4-6") -> dict:
    """One JSON object out; retries once on non-JSON. Never raises on missing key — returns manual-mode marker."""
    if not available():
        return {"decision": "manual", "confidence": 0.0, "escalate": True, "evidence": [], "next": "set ANTHROPIC_API_KEY or answer by hand"}
    try:
        import anthropic  # noqa: WPS433
    except ImportError:
        return {"decision": "manual", "confidence": 0.0, "escalate": True, "evidence": [], "next": "pip install anthropic"}
    client = anthropic.Anthropic()
    for _ in range(2):
        msg = client.messages.create(model=model, max_tokens=800, system=system, messages=[{"role": "user", "content": user}])
        text = "".join(getattr(b, "text", "") for b in msg.content)
        try:
            start, end = text.index("{"), text.rindex("}") + 1
            return json.loads(text[start:end])
        except (ValueError, json.JSONDecodeError):
            user = "Respond with exactly one JSON object and nothing else.\n" + user
    return {"decision": "manual", "confidence": 0.0, "escalate": True, "evidence": [], "next": "model returned non-JSON twice"}
