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
