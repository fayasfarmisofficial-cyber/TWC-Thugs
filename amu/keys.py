"""Credential store: ~/.amu/credentials.json (mode 0600, AMU_HOME-aware). Bring your own provider.
Secrets are never printed or logged; `source()`/`masked()` are the only things callers may show."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from amu.workspace import home

ENV = "ANTHROPIC_API_KEY"

PROVIDERS = {
    # name: (family, default model, default base_url, needs_key)
    "anthropic": ("anthropic", "claude-opus-5", None, True),
    "bedrock": ("anthropic", "anthropic.claude-opus-5", None, False),      # AWS credentials from the environment
    "vertex": ("anthropic", "claude-opus-5", None, False),                 # GCP ADC
    "foundry": ("anthropic", "claude-opus-5", None, True),                 # resource + key
    "openai-compatible": ("openai", None, None, False),                    # any /v1/chat/completions endpoint
    "ollama": ("openai", "llama3.1", "http://localhost:11434/v1", False),
    "lmstudio": ("openai", None, "http://localhost:1234/v1", False),
    "openrouter": ("openai", None, "https://openrouter.ai/api/v1", True),
}


def _path() -> Path:
    return home() / "credentials.json"


def _read() -> dict:
    p = _path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _write(d: dict) -> str:
    p = _path()
    p.write_text(json.dumps(d) + "\n")
    os.chmod(p, 0o600)
    return str(p)


def set_credential(provider: str = "anthropic", api_key: str | None = None, base_url: str | None = None, model: str | None = None,
                   region: str | None = None, project_id: str | None = None, resource: str | None = None) -> str:
    if provider not in PROVIDERS:
        raise ValueError(f"unknown provider {provider}; choose one of {', '.join(PROVIDERS)}")
    family, default_model, default_url, needs_key = PROVIDERS[provider]
    api_key = (api_key or "").strip() or None
    if provider == "anthropic" and api_key and not api_key.startswith("sk-ant-"):
        raise ValueError("that does not look like an Anthropic API key (expected sk-ant-…)")
    if needs_key and not api_key:
        raise ValueError(f"provider {provider} needs an API key")
    if provider == "vertex" and not (project_id and region):
        raise ValueError("vertex needs --project and --region")
    if provider == "bedrock" and not region:
        raise ValueError("bedrock needs --region")
    if provider == "foundry" and not resource:
        raise ValueError("foundry needs --resource")
    if family == "openai" and not (base_url or default_url):
        raise ValueError(f"provider {provider} needs --base-url")
    if family == "openai" and not (model or default_model):
        raise ValueError(f"provider {provider} needs --model")
    if provider == "openrouter" and "/" not in (model or ""):
        raise ValueError("openrouter models are namespaced, e.g. anthropic/claude-opus-5 or openai/gpt-4o — see openrouter.ai/models")
    rec = {"provider": provider, "family": family, "api_key": api_key, "base_url": base_url or default_url, "model": model or default_model,
           "region": region, "project_id": project_id, "resource": resource}
    return _write({k: v for k, v in rec.items() if v is not None})


def set_key(value: str) -> str:
    """Back-compat: plain Anthropic key."""
    return set_credential("anthropic", api_key=value)


def remove_key() -> bool:
    p = _path()
    if p.exists():
        p.unlink()
        return True
    return False


def _ant_profile() -> bool:
    if not shutil.which("ant"):
        return False
    try:
        r = subprocess.run(["ant", "auth", "status"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0 and "no " not in r.stdout.lower()[:200]


def credential() -> dict:
    """Effective credential record. Env wins: ANTHROPIC_API_KEY / OPENAI_API_KEY(+OPENAI_BASE_URL) / AMU_PROVIDER, then the file, then an `ant` profile."""
    if os.environ.get(ENV):
        return {"provider": "anthropic", "family": "anthropic", "api_key": os.environ[ENV], "base_url": os.environ.get("ANTHROPIC_BASE_URL"),
                "model": os.environ.get("AMU_MODEL") or "claude-opus-5", "source": "env"}
    if os.environ.get("OPENAI_BASE_URL") or os.environ.get("AMU_PROVIDER") in ("openai-compatible", "ollama", "lmstudio", "openrouter"):
        prov = os.environ.get("AMU_PROVIDER") or "openai-compatible"
        return {"provider": prov, "family": "openai", "api_key": os.environ.get("OPENAI_API_KEY"), "base_url": os.environ.get("OPENAI_BASE_URL") or PROVIDERS[prov][2],
                "model": os.environ.get("AMU_MODEL") or PROVIDERS[prov][1], "source": "env"}
    f = _read()
    if f.get("provider"):
        return {**f, "source": "file"}
    if f.get("anthropic_api_key"):  # pre-provider file shape
        return {"provider": "anthropic", "family": "anthropic", "api_key": f["anthropic_api_key"], "model": "claude-opus-5", "source": "file"}
    if _ant_profile():
        return {"provider": "anthropic", "family": "anthropic", "api_key": None, "model": "claude-opus-5", "source": "ant-profile"}
    return {"provider": None, "family": None, "source": "absent"}


def source() -> str:
    return credential()["source"]


def available() -> bool:
    return source() != "absent"


def resolve() -> str | None:
    return credential().get("api_key")


def masked() -> str:
    c = credential()
    k = c.get("api_key")
    tail = f"…{k[-4:]}" if k else "(no key: ambient credentials)"
    return f"{c.get('provider')} · {c.get('model')} · {tail}" + (f" · {c['base_url']}" if c.get("base_url") else "")
