"""Anthropic client wrapper. Credential order: ANTHROPIC_API_KEY → ~/.amu/credentials.json → `ant auth login` profile.
No credential ⇒ `manual` mode: the caller prints the brief and waits for a human. The key value is never printed."""

from __future__ import annotations

import json

from amu import keys, state

DEFAULT_MODEL = "claude-opus-5"


def available() -> bool:
    return keys.available()


def model_id(repo: str = ".") -> str:
    return state.config(repo).get("model") or DEFAULT_MODEL


def client():
    import anthropic  # noqa: WPS433
    k = keys.resolve()
    return anthropic.Anthropic(api_key=k) if k else anthropic.Anthropic()


def _manual(next_: str) -> dict:
    return {"decision": "manual", "confidence": 0.0, "escalate": True, "evidence": [], "next": next_}


def ask_json(system: str, user: str, model: str | None = None) -> dict:
    """One JSON object out; retries once on non-JSON. Never raises on a missing credential."""
    if not available():
        return _manual("run `amu key set` or export ANTHROPIC_API_KEY, or answer by hand")
    try:
        c = client()
    except ImportError:
        return _manual("pip install anthropic")
    import anthropic
    for _ in range(2):
        try:
            msg = c.messages.create(model=model or DEFAULT_MODEL, max_tokens=4000, system=system,
                                    output_config={"effort": "medium"}, messages=[{"role": "user", "content": user}])
        except anthropic.AuthenticationError:
            return _manual("credential rejected: run `amu key set` again")
        except (anthropic.APIStatusError, anthropic.APIConnectionError) as exc:
            return _manual(f"model call failed ({type(exc).__name__}); answer by hand")
        if msg.stop_reason == "refusal":
            return _manual("model declined this request; answer by hand")
        text = "".join(getattr(b, "text", "") for b in msg.content if b.type == "text")
        try:
            start, end = text.index("{"), text.rindex("}") + 1
            return json.loads(text[start:end])
        except (ValueError, json.JSONDecodeError):
            user = "Respond with exactly one JSON object and nothing else.\n" + user
    return _manual("model returned non-JSON twice")
