"""`amu watch`: render node states live while files change. It never runs tests — it renders, it does not verify."""

from __future__ import annotations

import threading
import time
from pathlib import Path

from amu import state

STATE_GLYPH = {"planned": "·", "editing": "▸", "green": "✓", "red": "✗", "drift": "↯"}
_IGNORED = (".amu/", ".git/", "__pycache__/", ".pytest_cache/", ".ruff_cache/")


def resolve_change(path: str, contract: dict, amu_map: dict, phase: int | None) -> dict:
    """Pure: which nodes change state when `path` is saved, and which warning lines to show."""
    if any(seg in path for seg in _IGNORED) or path.endswith((".pyc", ".DS_Store")):
        return {"nodes": {}, "warnings": [], "ignored": True}
    phases = contract.get("phases", [])
    this_phase = {f for p in phases if phase is None or p["n"] <= phase for f in p["files"]}
    later = {f for p in phases if phase is not None and p["n"] > phase for f in p["files"]} - this_phase
    allowed = set(contract.get("allowed_files", []))
    nodes = {n["id"]: n for n in amu_map.get("nodes", [])}
    hit = [nid for nid, n in nodes.items() if n["path"] == path]
    out: dict = {"nodes": {}, "warnings": [], "ignored": False}
    if path in this_phase:
        for nid in hit:
            out["nodes"][nid] = "editing"
        if not hit:
            out["warnings"].append(f"▸ {path} (phase file, no mapped node)")
    elif path in later:
        for nid in hit:
            out["nodes"][nid] = "drift"
        out["warnings"].append(f"↯ PHASE_DRIFT {path}: belongs to a later phase")
    elif allowed and path not in allowed:
        for nid in hit:
            out["nodes"][nid] = "drift"
        out["warnings"].append(f"↯ {path} is outside the contract")
    for nid in hit:
        if nodes[nid]["confidence"] == "unknown":
            out["warnings"].append(f"⚠ UNKNOWN_TOUCHED {path}: graph cannot see its consumers · {nodes[nid]['verify']}")
    return out


def apply(repo: str, resolved: dict) -> dict:
    st = state.read_json("state.json", repo, default={"nodes": {}, "violations": [], "history": []})
    st["nodes"].update(resolved["nodes"])
    st["updated_at"] = state.now_iso()
    state.write_json("state.json", st, repo)
    return st


def run(repo: str, phase: int | None, on_update, debounce_ms: int = 300, stop_after: float | None = None) -> None:
    """Loop until Ctrl-C (or `stop_after` seconds, for tests). Uses watchfiles when present, else stat polling."""
    root = Path(repo).resolve()
    contract = state.read_json("contract.json", repo, default={})
    amu_map = state.read_json("map.json", repo, default={"nodes": []})
    started = time.time()

    def handle(paths: set[str]) -> None:
        for p in sorted(paths):
            rel = str(Path(p).resolve().relative_to(root)) if str(Path(p).resolve()).startswith(str(root)) else p
            r = resolve_change(rel, contract, amu_map, phase)
            if r["ignored"]:
                continue
            on_update(rel, apply(repo, r), r["warnings"])

    try:
        from watchfiles import watch as _watch
        stop = threading.Event()
        if stop_after:
            threading.Timer(stop_after, stop.set).start()
        for changes in _watch(root, debounce=debounce_ms, stop_event=stop, rust_timeout=500):
            handle({c[1] for c in changes})
            if stop_after and time.time() - started > stop_after:
                return
    except ImportError:
        seen: dict[str, float] = {}
        while True:
            changed = set()
            for p in root.rglob("*"):
                if p.is_file() and not any(seg in str(p) for seg in _IGNORED):
                    m = p.stat().st_mtime
                    if seen.get(str(p)) not in (None, m):
                        changed.add(str(p))
                    seen[str(p)] = m
            if changed:
                handle(changed)
            time.sleep(debounce_ms / 1000)
            if stop_after and time.time() - started > stop_after:
                return
