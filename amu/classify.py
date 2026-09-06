def classify_consumers(symbol: str, raw_impact_output: str, caps: dict) -> dict:
    """
    Classifies consumers into will_break, might_break, and unknown.
    Satisfies Track 2 Curveball requirements by flagging unresolvable/partial analysis explicitly.
    """
    buckets = {
        "will_break": [],
        "might_break": [],
        "unknown": {
            "unresolved_callsites": 0,
            "dynamic_dispatch_sites": 0,
            "out_of_coverage": caps.get("out_of_coverage", []),
            "notes": ["Dynamic dispatch or reflection patterns treated as heuristic/incomplete."]
        }
    }

    lines = raw_impact_output.splitlines()
    for line in lines:
        if "hop: 1" in line or "direct" in line.lower():
            buckets["will_break"].append({"symbol": symbol, "reason": "Direct resolved caller"})
        elif "hop: 2" in line or "transitive" in line.lower():
            buckets["might_break"].append({"symbol": symbol, "reason": "Transitive hop-2 consumer"})
        elif "unresolved" in line.lower() or "dynamic" in line.lower():
            buckets["unknown"]["unresolved_callsites"] += 1

    return buckets


# ---------------------------------------------------------------------------
# Map builder (PRD S2): confidence axis + feature axis + verify lines.
# Rules: resolved graph edge ⇒ sound; co-change / name / sibling ⇒ guessed;
#        unresolved call site / partial parse / dynamic dispatch ⇒ unknown.
# ---------------------------------------------------------------------------

BREAKING_CLASSES = ("signature", "remove", "rename", "move")
_EDGE_SECTIONS = ("callers", "callees", "type_consumers", "data_flows")
_GUESS_SECTIONS = ("co_changes", "siblings")


def _feature_for(path: str, feature_map: dict) -> tuple[str, str]:
    for feature, globs in (feature_map or {}).items():
        for g in globs:
            prefix = g.rstrip("*/")
            if path.startswith(prefix):
                return feature, "map"
    top = path.split("/")[0] if "/" in path else "root"
    return top.capitalize(), "derived"


def _verify_for(path: str, symbol: str | None, node_id: str, test_cmd: str) -> str:
    if "test" in path.split("/")[0] or path.rsplit("/", 1)[-1].startswith("test_"):
        target = f"{path}::{symbol.split('.')[-1]}" if symbol else path
        return f"{test_cmd.split()[0]} {target}"
    return f"amu verify --node {node_id}"


def build_map(root_file: str, root_symbols: list[str], impacts: dict[str, dict], change: str,
              feature_map: dict | None, caps: dict, depth: int, test_cmd: str = "pytest") -> dict:
    """Turn `entire graph impact --format json` payloads (one per root symbol) into the PRD map object."""
    nodes: list[dict] = []
    seen: dict[str, int] = {}
    unresolved_sites = 0
    partial_files: list[str] = []
    breaking = change in BREAKING_CLASSES
    n = 0

    def add(path, symbol, confidence, risk, via, reason, evidence, order):
        nonlocal n
        key = f"{path}#{symbol}"
        if key in seen:
            return
        n += 1
        nid = f"n{n}"
        seen[key] = n
        feature, src = _feature_for(path, feature_map)
        nodes.append({
            "id": nid, "path": path, "symbol": symbol, "confidence": confidence, "risk": risk,
            "feature": feature if src == "map" else f"{feature} (derived)", "order": order,
            "action": "edit" if risk == "will_break" else ("review" if risk == "might_break" else "ask"),
            "via": via, "reason": reason, "verify": _verify_for(path, symbol, nid, test_cmd), "evidence": evidence,
        })

    for sym, imp in impacts.items():
        if not imp or "error" in imp:
            unresolved_sites += 1
            add(root_file, sym, "unknown", "unknown", None,
                f"impact query failed: {imp.get('error', 'no data') if imp else 'no data'}", ["impact:error"], 99)
            continue
        for section in _EDGE_SECTIONS:
            for e in (imp.get(section) or {}).get("entries", []):
                ep = e.get("endpoint", {})
                rel = e.get("relation", section.upper())
                d = e.get("depth", 1)
                risk = "will_break" if (breaking and d == 1) else "might_break"
                site = e.get("call_site") or {}
                via = f"{rel}:{site.get('file_path')}:{site.get('line')}" if site else f"{rel}:depth{d}"
                add(ep.get("file_path", "?"), ep.get("qualified_name") or ep.get("name"), "sound", risk, via,
                    f"resolved {rel} edge at depth {d}", [f"impact:{section}"], d)
        for section in _GUESS_SECTIONS:
            for e in (imp.get(section) or {}).get("entries", []):
                ep = e.get("endpoint", e)
                path = ep.get("file_path") or e.get("file_path") or "?"
                add(path, ep.get("name"), "guessed", "might_break", None,
                    f"{section.replace('_', '-')} only, no resolved edge", [f"impact:{section}"], 3)
        for pf in imp.get("partial_failures", []) or []:
            fp = pf.get("file_path")
            if fp and fp not in partial_files and not fp.startswith("docs/evidence"):
                partial_files.append(fp)
                add(fp, None, "unknown", "unknown", None,
                    f"{pf.get('code', 'partial parse')}: {pf.get('effect_on_semantic_completeness', 'not parsed')}",
                    ["impact:partial_failures"], 98)
    for pattern in (caps or {}).get("unresolved_patterns", []) or []:
        pass  # capability limits are reported in the qualifier, not invented as nodes

    counts = {c: sum(1 for x in nodes if x["confidence"] == c) for c in ("sound", "guessed", "unknown")}
    features: dict[str, int] = {}
    for x in nodes:
        features[x["feature"]] = features.get(x["feature"], 0) + 1
    files = {x["path"] for x in nodes}
    if counts["unknown"]:
        qualifier = f"{unresolved_sites} unresolved impact queries, {len(partial_files)} partially parsed files"
    else:
        qualifier = (f"graph reported 0 unresolved sites at depth {depth}; dynamic dispatch and files outside parser "
                     f"coverage ({', '.join((caps or {}).get('out_of_coverage', [])[:3]) or 'none listed'}) are not counted")
    first_target = root_symbols[0] if root_symbols else root_file
    return {
        "root": {"file": root_file, "exports": len(root_symbols), "internal": 0,
                 "feature": _feature_for(root_file, feature_map)[0], "feature_source": _feature_for(root_file, feature_map)[1]},
        "change": change, "depth": depth, "nodes": nodes, "ripples": [], "features": features,
        "radius": {"files": len(files), "packages": len({p.split('/')[0] for p in files}), "exports": len(root_symbols),
                   "consumers": counts["sound"] + counts["guessed"], "tests": sum(1 for x in nodes if x["verify"].startswith(test_cmd.split()[0]))},
        "resolution": {**counts, "qualifier": qualifier},
        "next": f"amu plan --targets {root_file}#{first_target}:{change} --approve",
    }
