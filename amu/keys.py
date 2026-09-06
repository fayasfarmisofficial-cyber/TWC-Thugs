"""API-key store: ~/.amu/credentials.json (mode 0600, AMU_HOME-aware). The value is never printed or logged."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from amu.workspace import home

ENV = "ANTHROPIC_API_KEY"


def _path() -> Path:
    return home() / "credentials.json"


def set_key(value: str) -> str:
    value = value.strip()
    if not value.startswith("sk-ant-") or len(value) < 20:
        raise ValueError("that does not look like an Anthropic API key (expected sk-ant-…)")
    p = _path()
    p.write_text(json.dumps({"anthropic_api_key": value}) + "\n")
    os.chmod(p, 0o600)
    return str(p)


def remove_key() -> bool:
    p = _path()
    if p.exists():
        p.unlink()
        return True
    return False


def _stored() -> str | None:
    p = _path()
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text()).get("anthropic_api_key") or None
    except (json.JSONDecodeError, OSError):
        return None


def _ant_profile() -> bool:
    if not shutil.which("ant"):
        return False
    try:
        r = subprocess.run(["ant", "auth", "status"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0 and "no " not in r.stdout.lower()[:200]


def source() -> str:
    """Where a credential would come from: env | file | ant-profile | absent. Never the value."""
    if os.environ.get(ENV):
        return "env"
    if _stored():
        return "file"
    if _ant_profile():
        return "ant-profile"
    return "absent"


def resolve() -> str | None:
    """Return the key for the SDK constructor, or None to let the SDK resolve an `ant auth login` profile."""
    return os.environ.get(ENV) or _stored()


def available() -> bool:
    return source() != "absent"


def masked() -> str:
    k = resolve()
    return f"sk-ant-…{k[-4:]}" if k else "(profile)"
