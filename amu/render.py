"""Rich terminal rendering + agent-card JSON. This module never computes anything; it formats what it is given."""

from __future__ import annotations

import json
import shutil

from rich.console import Console
from rich.tree import Tree

GLYPH = {"sound": "●", "guessed": "◐", "unknown": "○"}
RISK_TAG = {"will_break": "will_break", "might_break": "might_break", "unknown": "unknown", "none": "no-risk"}


def _console() -> Console:
    return Console(highlight=False, soft_wrap=True)


def _narrow() -> bool:
    return shutil.get_terminal_size((100, 20)).columns < 100


def render_map(m: dict) -> None:
    c = _console()
    r = m["root"]
    tree = Tree(f"[bold]{r['file']}[/] · {r['exports']} exports · feature {r['feature']} ({r['feature_source']}) · change {m.get('change', '?')}")
    for n in m["nodes"]:
        bits = [GLYPH[n["confidence"]], n["confidence"], RISK_TAG.get(n["risk"], n["risk"]), f"[bold]{n['path']}[/]" + (f"#{n['symbol']}" if n["symbol"] else "")]
        if not _narrow():
            bits.append(f"[dim]{n['feature']}[/]")
            if n["via"]:
                bits.append(f"[dim]via {n['via']}[/]")
        leaf = tree.add(f"{n['id']:>4} " + " ".join(bits))
        leaf.add(f"[dim]reason:[/] {n['reason']}")
        leaf.add(f"[dim]verify:[/] {n['verify']}")
    c.print(tree)
    f = " · ".join(f"{k} {v}" for k, v in m["features"].items()) or "none"
    rad = m["radius"]
    res = m["resolution"]
    c.print(f"features   {f}")
    c.print(f"radius     {rad['files']} files · {rad['packages']} packages · {rad['exports']} exports · {rad['consumers']} consumers · {rad['tests']} tests")
    c.print(f"resolution {res['sound']} sound · {res['guessed']} guessed · {res['unknown']} unknown — {res['qualifier']}")
    c.print(f"next       {m['next']}")


def render_plan(phases: list[dict], contract_path: str | None) -> None:
    c = _console()
    for p in phases:
        t = Tree(f"[bold]phase {p['n']} · {p['kind']}[/] · {len(p['nodes'])} nodes · {len(p['files'])} files")
        t.add(f"[dim]reason:[/] {p['reason']}")
        t.add(f"[dim]nodes:[/] {', '.join(p['nodes']) or '—'}")
        t.add(f"[dim]files:[/] {', '.join(p['files']) or '—'}")
        t.add(f"[dim]verify:[/] {p['verify']}")
        c.print(t)
    q = phases[0].get("open_questions", []) if phases else []
    c.print(f"open questions {len(q)}" + (": " + " | ".join(q) if q else ""))
    c.print(f"contract   {'written to ' + contract_path if contract_path else 'not written (add --approve)'}")


def render_check(result: dict) -> None:
    c = _console()
    v = result["violations"]
    blocking = [x for x in v if x["severity"] == "ERROR"]
    warn = [x for x in v if x["severity"] != "ERROR"]
    c.print(f"phase {result.get('phase', 'all')} · changed files {len(result.get('changed_files', []))} · blocking {len(blocking)} · warnings {len(warn)}")
    for x in v:
        c.print(f"  {'✖' if x['severity'] == 'ERROR' else '⚠'} {x['kind']} {x['symbol']}: {x['detail']}")
    if result.get("tests"):
        c.print(f"tests      {result['tests']}")
    if result.get("delta_brief"):
        d = result["delta_brief"]
        c.print(f"delta brief: {d['node']} · consumers {len(d['consumers'])} · {d['why']}")
    c.print(f"next       {result['next']}")


def render_findings(title: str, findings: list[dict], summary: str, nxt: str) -> None:
    c = _console()
    c.print(f"[bold]{title}[/] · {summary}")
    for f in findings:
        c.print(f"  {GLYPH.get(f.get('confidence', 'unknown'), '○')} {f.get('bucket', '?')} {f['path']}#{f.get('symbol')} — {f['reason']} · verify: {f['verify']}")
    c.print(f"next       {nxt}")


def render_report(report: dict) -> None:
    c = _console()
    c.print("[bold]amu done[/]")
    for k in ("declared", "actual", "findings", "docs", "memory", "next"):
        val = report.get(k)
        if isinstance(val, (list, dict)):
            val = json.dumps(val)
        c.print(f"{k:<10} {val}")


def agent_card(m: dict) -> dict:
    return {"brand": "TWC Thugs", "tiles": {**{k: m["resolution"][k] for k in ("sound", "guessed", "unknown")}, "ripples": len(m.get("ripples", []))},
            "rows": [{"id": n["id"], "path": n["path"], "symbol": n["symbol"], "badges": [n["confidence"], n["risk"]], "verify": n["verify"]} for n in m["nodes"]],
            "approve_enabled": m.get("planner_decision") == "proceed"}
