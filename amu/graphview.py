"""`amu graph`: a relation graph payload from `entire graph impact`, rendered as ASCII, Graphviz dot, or Mermaid.
Deterministic: nodes and edges are sorted, so the same input always draws the same picture."""

from __future__ import annotations

import hashlib
import re

from amu.render import GLYPH

_EDGE = {"callers": ("in", "sound"), "callees": ("out", "sound"), "type_consumers": ("in", "sound"), "data_flows": ("in", "sound"),
         "co_changes": ("side", "guessed"), "siblings": ("side", "guessed")}


def payload_from_impact(symbol: str, imp: dict, relation: str | None = None) -> dict:
    focus = imp.get("focus") or {}
    fid = focus.get("id") or symbol
    nodes = {fid: {"id": fid, "name": focus.get("qualified_name") or focus.get("name") or symbol, "path": focus.get("file_path") or "?",
                   "kind": focus.get("kind") or "?", "confidence": "sound" if focus.get("id") else "unknown", "section": "focus",
                   "reason": "the target" if focus.get("id") else "graph returned no focus (ambiguous or not found)",
                   "verify": f"entire graph def {symbol}"}}
    edges = []
    for section, (direction, conf) in _EDGE.items():
        for e in (imp.get(section) or {}).get("entries") or []:
            ep = e.get("endpoint") or e
            rel = e.get("relation") or section.upper()
            if relation and rel != relation:
                continue
            nid = ep.get("id") or f"{ep.get('file_path')}#{ep.get('name')}"
            depth = e.get("depth", 1)
            nodes.setdefault(nid, {"id": nid, "name": ep.get("qualified_name") or ep.get("name") or "?", "path": ep.get("file_path") or "?",
                                   "kind": ep.get("kind") or "?", "confidence": conf, "section": section, "depth": depth,
                                   "reason": f"resolved {rel} edge at depth {depth}" if conf == "sound" else f"{section.replace('_', '-')} only, no resolved edge",
                                   "verify": f"entire graph neighbors --symbol {ep.get('name')} --relation {rel}"})
            src, dst = (nid, fid) if direction == "in" else (fid, nid)
            edges.append({"from": src, "to": dst, "relation": rel, "direction": direction, "section": section, "depth": depth})
    candidates = [{"kind": d.get("kind"), "path": d.get("file_path"), "name": d.get("qualified_name") or d.get("name"),
                   "next": f"amu graph {d.get('file_path')}#{d.get('qualified_name') or d.get('name')}"} for d in imp.get("definitions") or []]
    if imp.get("disambiguation_required"):
        nodes[fid]["confidence"] = "unknown"
        nodes[fid]["reason"] = f"ambiguous: {len(candidates)} definitions match '{symbol}' ({'fuzzy ' + imp['fuzzy_match_kind'] if imp.get('fuzzy_match') else 'exact'}); no edges returned"
        nodes[fid]["verify"] = candidates[0]["next"] if candidates else f"entire graph search --query '{symbol}'"
    seen = set()
    uniq = []
    for e in sorted(edges, key=lambda e: (e["section"], e["depth"], e["from"], e["to"], e["relation"])):
        k = (e["from"], e["to"], e["relation"])
        if k not in seen:
            seen.add(k)
            uniq.append(e)
    return {"focus": fid, "symbol": symbol, "depth": imp.get("depth", 2),
            "nodes": sorted(nodes.values(), key=lambda n: (n["section"] != "focus", n["section"], n.get("depth", 0), n["name"], n["path"])),
            "edges": uniq, "counts": {s: len([e for e in uniq if e["section"] == s]) for s in _EDGE},
            "status": "ambiguous" if imp.get("disambiguation_required") else ("not_found" if not focus.get("id") else "ok"),
            "candidates": candidates if imp.get("disambiguation_required") else [],
            "warnings": [w.get("code") for w in imp.get("warnings") or []]}


def _label(n: dict) -> str:
    return f"{GLYPH[n['confidence']]} {n['name']}  {n['path']}"


def to_ascii(p: dict) -> str:
    by = {n["id"]: n for n in p["nodes"]}
    focus = by[p["focus"]]
    above = [n for n in p["nodes"] if n["section"] in ("callers",)]
    below = [n for n in p["nodes"] if n["section"] == "callees"]
    types = [n for n in p["nodes"] if n["section"] == "type_consumers"]
    flows = [n for n in p["nodes"] if n["section"] == "data_flows"]
    guessed = [n for n in p["nodes"] if n["section"] in ("co_changes", "siblings")]
    rel_of = {(e["from"], e["to"]): e["relation"] for e in p["edges"]}
    out = []
    if above:
        out.append("callers")
        for n in above:
            out.append(f"  {_label(n)}")
            out.append(f"      │ {rel_of.get((n['id'], focus['id']), 'CALLS')} (depth {n.get('depth', 1)})")
        out.append("      ▼")
    out.append(f"┌─ {_label(focus)} ─┐  [{focus['kind']}] {focus['reason']}")
    if p.get("candidates"):
        out.append("candidates (pick one — amu never guesses a symbol)")
        for c in p["candidates"]:
            out.append(f"  {c['kind']:<9} {c['path']}#{c['name']}   → {c['next']}")
    if types or flows:
        for n in types:
            out.append(f"  ◀─ {rel_of.get((n['id'], focus['id']), 'USES_TYPE')} ── {_label(n)}")
        for n in flows:
            out.append(f"  ◀─ {rel_of.get((n['id'], focus['id']), 'DATA_FLOWS')} ── {_label(n)}")
    if below:
        out.append("      ▼")
        out.append("callees")
        for n in below:
            out.append(f"      │ {rel_of.get((focus['id'], n['id']), 'CALLS')}")
            out.append(f"  {_label(n)}")
    if guessed:
        out.append("guessed (no resolved edge)")
        for n in guessed:
            out.append(f"  {_label(n)}  — {n['reason']} · verify: {n['verify']}")
    c = p["counts"]
    out.append(f"edges  callers {c['callers']} · callees {c['callees']} · type {c['type_consumers']} · data {c['data_flows']} · co-change {c['co_changes']} · siblings {c['siblings']}")
    return "\n".join(out)


def _mid(s: str) -> str:
    """Mermaid/dot-safe id: readable tail + short hash so two long ids with the same tail never collide."""
    return "n_" + re.sub(r"[^A-Za-z0-9]", "_", s)[-32:] + "_" + hashlib.sha1(s.encode()).hexdigest()[:6]


def to_mermaid(p: dict) -> str:
    lines = ["graph TD"]
    for n in p["nodes"]:
        label = f"{GLYPH[n['confidence']]} {n['name']}<br/>{n['path']}".replace('"', "'")
        shape = ("[[", "]]") if n["id"] == p["focus"] else (("(", ")") if n["confidence"] == "guessed" else ("[", "]"))
        lines.append(f'    {_mid(n["id"])}{shape[0]}"{label}"{shape[1]}')
    for e in p["edges"]:
        lines.append(f'    {_mid(e["from"])} -->|{e["relation"]}| {_mid(e["to"])}')
    lines.append("    classDef sound stroke:#3CB371;\n    classDef guessed stroke:#E08A1E,stroke-dasharray:4;\n    classDef unknown stroke:#8A8578;")
    for conf in ("sound", "guessed", "unknown"):
        ids = [_mid(n["id"]) for n in p["nodes"] if n["confidence"] == conf]
        if ids:
            lines.append(f"    class {','.join(ids)} {conf};")
    return "\n".join(lines)


def to_dot(p: dict) -> str:
    col = {"sound": "#3CB371", "guessed": "#E08A1E", "unknown": "#8A8578"}
    lines = ["digraph amu {", '  rankdir=TB; node [shape=box, fontname="monospace"]; bgcolor="#161412"; fontcolor="#FDF6E3";']
    for n in p["nodes"]:
        pen = 3 if n["id"] == p["focus"] else 1
        lines.append(f'  "{_mid(n["id"])}" [label="{GLYPH[n["confidence"]]} {n["name"]}\\n{n["path"]}", color="{col[n["confidence"]]}", fontcolor="#FDF6E3", penwidth={pen}];')
    for e in p["edges"]:
        style = "dashed" if e["section"] in ("co_changes", "siblings") else "solid"
        lines.append(f'  "{_mid(e["from"])}" -> "{_mid(e["to"])}" [label="{e["relation"]}", style={style}, color="#E08A1E", fontcolor="#8A8578"];')
    lines.append("}")
    return "\n".join(lines)
