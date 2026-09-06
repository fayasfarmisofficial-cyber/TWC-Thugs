"""Feature 2: docs that follow the graph. Candidates come from `entire graph diff`; nothing is applied
unless a human confirms a SUGGESTED draft or `--mode auto` applies sound+mapped candidates in one commit."""

from __future__ import annotations

import glob
import re
from pathlib import Path

from amu import state
from amu.contract import parse_graph_diff

DOC_CLASSES = {"added": "add_export", "removed": "remove", "renamed": "rename", "signature_changed": "signature", "moved": "move"}


def doc_map(repo: str = ".") -> dict:
    return state.read_json("doc-map.json", repo, default={})


def draft_doc_map(repo: str = ".", docs_dir: str = "docs") -> dict:
    """Seed `path#symbol → [{file, section}]` from headings that mention a symbol-looking token."""
    out: dict = {}
    for md in glob.glob(str(Path(repo) / docs_dir / "**" / "*.md"), recursive=True):
        rel = str(Path(md).relative_to(repo))
        for line in Path(md).read_text(errors="ignore").splitlines():
            if line.startswith("#"):
                for tok in re.findall(r"`([A-Za-z_][\w./#]*)`", line):
                    out.setdefault(tok, []).append({"file": rel, "section": line.strip()})
    return out


def candidates(diff_data: dict | None, dmap: dict) -> list[dict]:
    """Public-export changes in doc-relevant classes ⇒ candidate; body ⇒ candidate marked unknown."""
    if not diff_data:
        return []
    out = []
    for c in parse_graph_diff(diff_data):
        if c["kind"] not in ("function", "class", "method") or c["symbol"].split(".")[-1].startswith("_"):
            continue
        cls = DOC_CLASSES.get(c["type"])
        key = f"{c['file']}#{c['symbol']}"
        mapped = dmap.get(key) or dmap.get(c["symbol"]) or []
        if cls:
            out.append({"id": f"d{len(out)+1}", "candidate": key, "class": cls, "confidence": "sound" if mapped else "guessed",
                        "old": c.get("old_signature"), "new": c.get("new_signature"), "targets": mapped,
                        "reason": f"{cls} on a public export" + ("" if mapped else " (no doc-map entry)")})
        elif c["type"] == "body_changed":
            out.append({"id": f"d{len(out)+1}", "candidate": key, "class": "body", "confidence": "unknown", "old": None, "new": None,
                        "targets": mapped, "reason": "body changed; whether docs describe the old behaviour is not derivable from the graph"})
    return out


def other_mentions(symbol: str, repo: str = ".", docs_dir: str = "docs") -> list[str]:
    name = symbol.split("#")[-1].split(".")[-1]
    hits = []
    for md in glob.glob(str(Path(repo) / docs_dir / "**" / "*.md"), recursive=True):
        for i, line in enumerate(Path(md).read_text(errors="ignore").splitlines(), 1):
            if name in line:
                hits.append(f"{Path(md).relative_to(repo)}:{i}")
    return hits[:20]


def draft(c: dict) -> str:
    if c["class"] == "body":
        return f"SUGGESTED (unknown): `{c['candidate']}` body changed — a human must decide whether the documented behaviour still holds."
    old = f"`{c['old']}`" if c.get("old") else "(no previous signature recorded)"
    new = f"`{c['new']}`" if c.get("new") else "(removed)"
    return f"SUGGESTED: `{c['candidate']}` — {c['class']}. Was {old}; now {new}. Update the section to match the new shape."


def packet(c: dict, repo: str = ".", docs_dir: str = "docs") -> dict:
    t = c["targets"][0] if c["targets"] else {"file": None, "section": None}
    return {"candidate": c["candidate"], "doc_file": t["file"], "section": t["section"], "old": c.get("old"), "new": c.get("new"),
            "consistent_with_diff": c["confidence"] != "unknown", "concerns": [] if c["confidence"] == "sound" else [c["reason"]],
            "other_mentions": other_mentions(c["candidate"], repo, docs_dir), "next": f"amu docs --apply {c['id']}", "draft": draft(c)}


def apply(c: dict, repo: str = ".") -> bool:
    """Append the draft under the mapped section. Only called for a human-confirmed or sound+mapped candidate."""
    if not c["targets"]:
        return False
    t = c["targets"][0]
    p = Path(repo) / t["file"]
    if not p.exists():
        return False
    lines = p.read_text().splitlines()
    try:
        idx = next(i for i, ln in enumerate(lines) if ln.strip() == t["section"])
    except StopIteration:
        return False
    lines.insert(idx + 1, "\n" + draft(c).replace("SUGGESTED: ", ""))
    p.write_text("\n".join(lines) + "\n")
    return True
