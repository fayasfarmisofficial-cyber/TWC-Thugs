"""Model access for the harness. Bring your own provider: `amu key set --provider …`.
Credential order: ANTHROPIC_API_KEY / OPENAI_BASE_URL env → ~/.amu/credentials.json → `ant auth login` profile.
No credential ⇒ `manual` mode. Secrets are never printed."""

from __future__ import annotations

import json

from amu import keys, state
from amu.harness import providers

DEFAULT_MODEL = "claude-opus-5"


def available() -> bool:
    return keys.available()


def credential() -> dict:
    return keys.credential()


def model_id(repo: str = ".") -> str:
    c = credential()
    return c.get("model") or state.config(repo).get("model") or DEFAULT_MODEL


def client():
    return providers.make_client(credential())


def request_kwargs(cred: dict, effort: str = "medium") -> dict:
    """Anthropic-only parameters are dropped for other families (an OpenAI-compatible endpoint would reject them)."""
    return {"output_config": {"effort": effort}} if providers.supports_anthropic_params(cred) else {}


def _manual(next_: str) -> dict:
    return {"decision": "manual", "confidence": 0.0, "escalate": True, "evidence": [], "next": next_}


def ask_json(system: str, user: str, model: str | None = None) -> dict:
    """One JSON object out; retries once on non-JSON. Never raises on a missing credential."""
    if not available():
        return _manual("run `amu key set` or export ANTHROPIC_API_KEY, or answer by hand")
    cred = credential()
    try:
        c = client()
    except ImportError:
        return _manual("pip install anthropic")
    import anthropic
    for _ in range(2):
        try:
            msg = c.messages.create(model=model or model_id(), max_tokens=4000, system=system, messages=[{"role": "user", "content": user}],
                                    **request_kwargs(cred))
        except anthropic.AuthenticationError:
            return _manual("credential rejected: run `amu key set` again")
        except (anthropic.APIStatusError, anthropic.APIConnectionError, providers.ProviderError) as exc:
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
