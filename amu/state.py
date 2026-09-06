"""`.amu/` state: JSON read/write, hashes, git helpers, and schema validation (validated on read and write)."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

AMU_DIR = ".amu"

SCHEMAS: dict[str, set[str]] = {
    "map": {"root", "nodes", "ripples", "features", "radius", "resolution", "next", "map_hash"},
    "node": {"id", "path", "symbol", "confidence", "risk", "feature", "order", "action", "via", "reason", "verify"},
    "contract": {"targets", "base_sha", "map_hash", "phases", "frozen_signatures", "allowed_files", "created_at"},
    "state": {"nodes", "violations", "updated_at"},
    "handoff": {"decision", "confidence", "escalate", "evidence", "next"},
    "memory_entry": {"id", "kind", "text", "evidence", "sha", "file_hash", "created", "last_seen", "pinned"},
}
CONFIDENCE = ("sound", "guessed", "unknown")
RISK = ("will_break", "might_break", "unknown", "none")
NODE_STATES = ("planned", "editing", "green", "red", "drift")


class SchemaError(ValueError):
    pass


def validate(kind: str, obj: dict) -> dict:
    missing = SCHEMAS[kind] - set(obj)
    if missing:
        raise SchemaError(f"{kind} missing keys: {sorted(missing)}")
    if kind == "map":
        for n in obj["nodes"]:
            validate("node", n)
            if n["confidence"] not in CONFIDENCE:
                raise SchemaError(f"node {n['id']} bad confidence {n['confidence']}")
            if n["confidence"] != "sound" and not (n.get("reason") and n.get("verify")):
                raise SchemaError(f"node {n['id']} is {n['confidence']} but lacks reason/verify")
    return obj


def amu_dir(repo: str = ".") -> Path:
    p = Path(repo) / AMU_DIR
    p.mkdir(parents=True, exist_ok=True)
    return p


def read_json(name: str, repo: str = ".", default: Any = None) -> Any:
    p = amu_dir(repo) / name
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text())
    except json.JSONDecodeError:
        return default


def write_json(name: str, obj: Any, repo: str = ".", kind: str | None = None) -> Path:
    if kind:
        validate(kind, obj)
    p = amu_dir(repo) / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2, sort_keys=False) + "\n")
    return p


def config(repo: str = ".") -> dict:
    return read_json("config.json", repo, default={
        "language": "unknown", "test_cmd": "pytest -q", "build_cmd": "", "docs_dir": "docs",
        "docs": {"mode": "draft"}, "model": "claude-opus-5", "web": {"report_url": ""},
    })


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def stable_hash(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:16]


def file_hash(path: str, repo: str = ".") -> str:
    p = Path(repo) / path
    if not p.exists() or p.is_dir():
        return "missing"
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16]


def _git(args: list[str], repo: str = ".") -> str:
    try:
        r = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, timeout=30)
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return ""
    return r.stdout.strip() if r.returncode == 0 else ""


def git_head(repo: str = ".") -> str:
    return _git(["rev-parse", "HEAD"], repo) or "no-git"


def git_changed_files(repo: str = ".", base: str | None = None) -> list[str]:
    """Files changed since `base` (committed) plus working-tree modifications and untracked files."""
    files: set[str] = set()
    if base and base != "no-git":
        files.update(f for f in _git(["diff", "--name-only", base, "HEAD"], repo).splitlines() if f)
    files.update(f for f in _git(["diff", "--name-only", "HEAD"], repo).splitlines() if f)
    files.update(f for f in _git(["ls-files", "--others", "--exclude-standard"], repo).splitlines() if f)
    return sorted(f for f in files if "__pycache__" not in f and not f.endswith((".pyc", ".DS_Store")))


def repo_name(repo: str = ".") -> str:
    url = _git(["remote", "get-url", "origin"], repo)
    if url:
        return url.rstrip("/").removesuffix(".git").split("/")[-1]
    return os.path.basename(os.path.abspath(repo))


def detect_commands(repo: str = ".") -> dict:
    r = Path(repo)
    if (r / "pyproject.toml").exists():
        return {"language": "Python", "test_cmd": "pytest -q", "build_cmd": "python -m build"}
    if (r / "package.json").exists():
        return {"language": "TypeScript", "test_cmd": "npm test", "build_cmd": "npm run build"}
    if (r / "go.mod").exists():
        return {"language": "Go", "test_cmd": "go test ./...", "build_cmd": "go build ./..."}
    return {"language": "unknown", "test_cmd": "", "build_cmd": ""}
