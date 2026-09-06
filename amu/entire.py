"""All subprocess calls to the `entire` CLI live here. Nothing raises; failures come back as
`{"error": "..."}` dicts / `None` / error strings so every caller degrades instead of crashing."""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import Any

INSTALL_HINT = "brew tap entireio/tap && brew trust entireio/tap && brew install --cask entire && entire plugin install graph"


def _run(args: list[str], timeout: int = 180) -> tuple[int, str, str]:
    try:
        r = subprocess.run(["entire", *args], capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        return 127, "", "entire CLI not found (not installed or not on PATH)"
    except subprocess.TimeoutExpired:
        return 124, "", f"entire {' '.join(args[:2])} timed out after {timeout}s"
    except (ValueError, OSError) as exc:
        return 1, "", str(exc)
    return r.returncode, r.stdout, r.stderr


def _json(args: list[str], timeout: int = 180) -> dict[str, Any]:
    rc, out, err = _run(args, timeout)
    if rc != 0 or not out.strip():
        return {"error": err.strip() or f"exit {rc}", "rc": rc}
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return {"error": "non-JSON output", "raw": out[:500]}
    return data if isinstance(data, dict) else {"data": data}


def available() -> bool:
    return shutil.which("entire") is not None


def graph_available() -> bool:
    rc, out, _ = _run(["graph", "version"], 30)
    return rc == 0 and bool(out.strip())


def version() -> str:
    rc, out, _ = _run(["version"], 30)
    return out.splitlines()[0].replace("Entire CLI ", "").strip() if rc == 0 and out else "missing"


def graph_version() -> str:
    rc, out, _ = _run(["graph", "version"], 30)
    return out.strip() if rc == 0 else "missing"


def index(repo: str = ".") -> dict:
    return _json(["graph", "index", "--repo", repo])


def snapshot(repo: str, out_path: str) -> dict:
    rc, out, err = _run(["graph", "snapshot", "--repo", repo, "--format", "compact-ndjson"], 300)
    if rc != 0:
        return {"error": err.strip() or f"exit {rc}"}
    with open(out_path, "w") as fh:
        fh.write(out)
    return {"lines": out.count("\n"), "path": out_path}


def capabilities(repo: str = ".") -> dict:
    return _json(["graph", "capabilities", "--json", "--repo", repo], 60)


def search(repo: str, query: str) -> dict:
    return _json(["graph", "search", "--repo", repo, "--profile", "full", "--query", query, "--format", "json"])


def definition(repo: str, symbol: str) -> str:
    rc, out, err = _run(["graph", "def", symbol, "--repo", repo], 60)
    return out if rc == 0 else f"Error running def: {err}"


def impact_json(repo: str, symbol: str, depth: int = 2, limit: int = 50, file: str | None = None, head: bool = True) -> dict:
    """`file` disambiguates a name defined in several files; `head` queries the cached committed tree (fast) —
    a map is taken before editing, so the committed tree is the right baseline."""
    args = ["graph", "impact", "--repo", repo, "--symbol", symbol, "--depth", str(depth), "--limit", str(limit), "--profile", "full", "--format", "json"]
    if file:
        args += ["--file", file]
    if head:
        args.append("--head")
    return _json(args)


def impact_text(repo: str, symbol: str, depth: int = 2) -> str:
    rc, out, err = _run(["graph", "impact", "--symbol", symbol, "--depth", str(depth), "--repo", repo, "--profile", "full"])
    if rc == 127:
        return "Error running impact: entire CLI not found (not installed or not on PATH)"
    if rc != 0:
        return f"Error running impact: {err}"
    return out


def neighbors_json(repo: str, symbol: str, relation: str = "CALLS", direction: str = "in", internal_only: bool = False) -> dict:
    args = ["graph", "neighbors", "--repo", repo, "--symbol", symbol, "--relation", relation, "--direction", direction, "--format", "json"]
    if internal_only:
        args.append("--internal-only")
    return _json(args)


def diff_json(repo: str, base: str, head: str = "HEAD") -> dict | None:
    d = _json(["graph", "diff", "--repo", repo, "--base", base, "--head", head, "--json"])
    return None if "error" in d else d


def diff_text(repo: str, base: str, head: str = "HEAD") -> str:
    rc, out, err = _run(["graph", "diff", "--repo", repo, "--base", base, "--head", head])
    return out if rc == 0 else f"Error running diff: {err}"


def symbols(repo: str, worktree: bool = True) -> list[dict]:
    args = ["graph", "symbols", "--repo", repo, "--format", "ndjson"]
    if worktree:
        args.append("--worktree")
    rc, out, _ = _run(args, 300)
    if rc != 0:
        return []
    rows = []
    for line in out.splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def verify(repo: str, test_cmd: str) -> dict:
    rc, out, err = _run(["graph", "verify", "--repo", repo, "--test", test_cmd], 600)
    return {"rc": rc, "verdict": out.strip(), "stderr": err.strip()[-500:]}


def doctor() -> dict:
    return _json(["graph", "doctor", "--json"], 60)


def checkpoint_list() -> list[dict]:
    d = _json(["checkpoint", "list", "--json"], 60)
    if "error" in d:
        return []
    data = d.get("data", d)
    return data if isinstance(data, list) else data.get("checkpoints", [])


def graph_checkpoint(checkpoint_id: str, repo: str = ".") -> str:
    rc, out, err = _run(["graph", "checkpoint", checkpoint_id, "--repo", repo])
    return out if rc == 0 else f"Error running checkpoint: {err}"


def status_text() -> str:
    rc, out, err = _run(["status"], 30)
    return out.strip() if rc == 0 else f"entire status unavailable: {err.strip()}"
