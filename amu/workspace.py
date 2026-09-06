"""Workspace: many repos, one active. State lives in ~/.amu/workspace.json (override with AMU_HOME)."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from amu import entire, state


class WorkspaceError(RuntimeError):
    def __init__(self, msg: str, code: int = 2):
        super().__init__(msg)
        self.code = code


def home() -> Path:
    p = Path(os.environ.get("AMU_HOME") or Path.home() / ".amu")
    p.mkdir(parents=True, exist_ok=True)
    return p


def _ws_path() -> Path:
    return home() / "workspace.json"


def load() -> dict:
    p = _ws_path()
    if p.exists():
        try:
            return json.loads(p.read_text())
        except json.JSONDecodeError:
            pass
    return {"active": None, "repos": []}


def save(ws: dict) -> None:
    _ws_path().write_text(json.dumps(ws, indent=2) + "\n")


def _git(args: list[str], cwd: str | Path | None = None) -> tuple[int, str]:
    try:
        r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=600)
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
        return 1, str(exc)
    return r.returncode, (r.stdout if r.returncode == 0 else r.stderr).strip()


def git_toplevel(path: str | Path) -> str | None:
    rc, out = _git(["rev-parse", "--show-toplevel"], path)
    return out if rc == 0 else None


def _name_for(path: Path, origin: str) -> str:
    m = re.search(r"([^/:]+)/([^/]+?)(?:\.git)?/?$", origin or "")
    return (m.group(2) if m else path.name).lower()


GITHUB_RX = re.compile(r"^(?:https?://github\.com/|git@github\.com:)?([\w.-]+)/([\w.-]+?)(?:\.git)?/?$")


def is_remote_spec(spec: str) -> bool:
    return not Path(spec).expanduser().exists() and bool(GITHUB_RX.match(spec))


def clone(spec: str, branch: str | None = None, depth: int | None = None) -> Path:
    """Clone into ~/.amu/repos/<owner>__<repo>; reuse an existing clone with fetch. Uses the user's git credentials."""
    m = GITHUB_RX.match(spec)
    if not m:
        raise WorkspaceError(f"not a GitHub spec: {spec}", 2)
    owner, repo = m.group(1), m.group(2)
    url = spec if spec.startswith(("http", "git@")) else f"https://github.com/{owner}/{repo}.git"
    dest = home() / "repos" / f"{owner}__{repo}"
    if dest.exists() and git_toplevel(dest):
        rc, out = _git(["fetch", "--quiet"], dest)
        if rc != 0:
            raise WorkspaceError(f"git fetch failed in {dest}: {out}", 3)
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["clone", "--quiet"] + (["--branch", branch] if branch else []) + (["--depth", str(depth)] if depth else []) + [url, str(dest)]
    rc, out = _git(cmd)
    if rc != 0:
        raise WorkspaceError(f"command failed: git {' '.join(cmd)}\n{out}", 3)
    return dest


def index_repo(path: Path) -> dict:
    idx = entire.index(str(path))
    if "error" in idx:
        raise WorkspaceError(f"entire graph index failed: {idx['error']}", 3)
    entire.snapshot(str(path), str(state.amu_dir(str(path)) / "snapshot.ndjson"))
    if not state.read_json("config.json", str(path)):
        state.write_json("config.json", {**state.config(str(path)), **state.detect_commands(str(path))}, str(path))
    return idx


def add(spec: str, branch: str | None = None, depth: int | None = None, do_index: bool = True) -> dict:
    if is_remote_spec(spec):
        path = clone(spec, branch, depth)
    else:
        path = Path(spec).expanduser().resolve()
    top = git_toplevel(path)
    if not top:
        raise WorkspaceError(f"{path} is not inside a Git worktree (git rev-parse --show-toplevel failed)", 2)
    path = Path(top)
    _, origin = _git(["remote", "get-url", "origin"], path)
    _, br = _git(["rev-parse", "--abbrev-ref", "HEAD"], path)
    idx = index_repo(path) if do_index else {}
    counts = idx.get("counts", {})
    entry = {"name": _name_for(path, origin), "path": str(path), "origin": origin if "fatal" not in origin else "",
             "indexed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if do_index else "", "graph_hash": idx.get("tree", ""),
             "sha": state.git_head(str(path)), "counts": counts, "last_map": "", "branch": br}
    ws = load()
    ws["repos"] = [r for r in ws["repos"] if r["path"] != entry["path"] and r["name"] != entry["name"]] + [entry]
    ws["active"] = entry["name"]
    save(ws)
    return entry


def get(name: str) -> dict | None:
    return next((r for r in load()["repos"] if r["name"] == name), None)


def use(name: str) -> dict:
    r = get(name)
    if not r:
        raise WorkspaceError(f"no repo named {name}; see amu repo list", 2)
    ws = load()
    ws["active"] = name
    save(ws)
    return r


def remove(name: str, delete_clone: bool = False) -> dict:
    r = get(name)
    if not r:
        raise WorkspaceError(f"no repo named {name}", 2)
    ws = load()
    ws["repos"] = [x for x in ws["repos"] if x["name"] != name]
    if ws["active"] == name:
        ws["active"] = ws["repos"][-1]["name"] if ws["repos"] else None
    save(ws)
    deleted = False
    managed = str(home() / "repos")
    if delete_clone and r["path"].startswith(managed) and Path(r["path"]).exists():
        shutil.rmtree(r["path"])
        deleted = True
    return {**r, "deleted_clone": deleted}


def sync(name: str) -> dict:
    r = get(name)
    if not r:
        raise WorkspaceError(f"no repo named {name}", 2)
    _git(["fetch", "--quiet"], r["path"])
    old = r.get("sha") or "HEAD~1"
    idx = index_repo(Path(r["path"]))
    new = state.git_head(r["path"])
    diff = entire.diff_json(r["path"], old, new) if old != new else {"files": []}
    changes = sum(len(f.get("changes", [])) for f in (diff or {}).get("files", []))
    r.update({"indexed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "graph_hash": idx.get("tree", ""), "sha": new, "counts": idx.get("counts", {})})
    ws = load()
    ws["repos"] = [r if x["name"] == name else x for x in ws["repos"]]
    save(ws)
    return {**r, "old_sha": old, "entity_changes": changes, "files_changed": len((diff or {}).get("files", []))}


def touch(path: str, last_map: str | None = None) -> None:
    ws = load()
    for r in ws["repos"]:
        if r["path"] == str(Path(path).resolve()) and last_map:
            r["last_map"] = last_map
    save(ws)


def resolve(repo_flag: str | None) -> str:
    """--repo flag → repo containing $PWD → workspace active → error with the add hint."""
    if repo_flag and repo_flag != ".":
        return repo_flag
    top = git_toplevel(os.getcwd())
    if top:
        return top
    ws = load()
    if ws.get("active"):
        r = get(ws["active"])
        if r and Path(r["path"]).exists():
            return r["path"]
    raise WorkspaceError("no repo: not inside a Git worktree and no active workspace repo — run `amu repo add <path|owner/repo>`", 2)


def relative(ts: str) -> str:
    if not ts:
        return "never"
    try:
        dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return ts
    s = int((datetime.now(timezone.utc) - dt).total_seconds())
    for unit, n in (("d", 86400), ("h", 3600), ("m", 60)):
        if s >= n:
            return f"{s // n}{unit} ago"
    return f"{s}s ago"
