"""
amu/plan.py
-----------
Generates a 4-phase topologically-ordered refactoring plan from reverse-dependency edges.

Phases (per Track 2 safe-migration contract):
  1. Additive   – New symbols / overloads that introduce no breakage
  2. Migration  – Callers that must be updated before old signature is removed
  3. Interior   – Internal implementation changes safe after callers migrated
  4. Removal    – Delete / deprecate the original symbol
"""

from graphlib import TopologicalSorter, CycleError
from dataclasses import dataclass, field
from typing import Dict, List, Set, Optional
import json


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

PHASES = ["additive", "migration", "interior", "removal"]


@dataclass
class RefactoringPlan:
    symbol: str
    phases: Dict[str, List[str]] = field(default_factory=lambda: {p: [] for p in PHASES})
    cycles_detected: List[List[str]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "phases": self.phases,
            "cycles_detected": self.cycles_detected,
            "warnings": self.warnings,
        }

    def pretty(self) -> str:
        lines = [f"Refactoring Plan for: {self.symbol}", "=" * 50]
        for idx, phase in enumerate(PHASES, 1):
            items = self.phases[phase]
            lines.append(f"\n  Phase {idx} [{phase.upper()}] ({len(items)} item(s))")
            for item in items:
                lines.append(f"    • {item}")
        if self.cycles_detected:
            lines.append("\n  ⚠  CYCLES DETECTED (manually resolve):")
            for cycle in self.cycles_detected:
                lines.append(f"    {' -> '.join(cycle)}")
        if self.warnings:
            lines.append("\n  ℹ  Warnings:")
            for w in self.warnings:
                lines.append(f"    {w}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Phase classification heuristics
# ---------------------------------------------------------------------------

def _classify_phase(node: str, direct_callers: Set[str], transitive_callers: Set[str]) -> str:
    """
    Assign a node to one of the 4 phases based on its role relative to the
    target symbol's caller graph.

    Rules (deterministic, no ML):
      • 'new:*' prefix  -> additive   (explicitly marked new symbol)
      • direct caller   -> migration  (must update before removal)
      • transitive cal. -> interior   (safe once direct callers migrated)
      • anything else   -> removal    (the target symbol itself, or orphaned)
    """
    if node.startswith("new:"):
        return "additive"
    if node in direct_callers:
        return "migration"
    if node in transitive_callers:
        return "interior"
    return "removal"


# ---------------------------------------------------------------------------
# Core plan builder
# ---------------------------------------------------------------------------

def build_plan(
    symbol: str,
    edges: Dict[str, List[str]],
    direct_callers: Optional[Set[str]] = None,
    transitive_callers: Optional[Set[str]] = None,
) -> RefactoringPlan:
    """
    Build a 4-phase refactoring plan from reverse-dependency edges.

    Parameters
    ----------
    symbol : str
        The symbol being refactored (root node).
    edges : dict
        Adjacency list of reverse-dependency edges:
        ``{ dependent: [dependency, ...], ... }``
        (i.e. "dependent must come *after* dependency")
    direct_callers : set, optional
        Nodes that directly call ``symbol`` (hop-1). If omitted, inferred
        from ``edges`` keys that list ``symbol`` as a dependency.
    transitive_callers : set, optional
        Nodes that transitively call ``symbol`` (hop-2+). If omitted,
        inferred as all nodes not in ``direct_callers``.

    Returns
    -------
    RefactoringPlan
    """
    plan = RefactoringPlan(symbol=symbol)

    # -- Collect all nodes --------------------------------------------------
    all_nodes: Set[str] = set(edges.keys())
    for deps in edges.values():
        all_nodes.update(deps)
    all_nodes.add(symbol)

    # -- Infer caller sets if not provided ----------------------------------
    if direct_callers is None:
        direct_callers = {
            node for node, deps in edges.items() if symbol in deps
        }
    if transitive_callers is None:
        transitive_callers = all_nodes - direct_callers - {symbol}

    # -- Topological sort (stdlib graphlib) ---------------------------------
    sorter = TopologicalSorter(edges)
    try:
        topo_order: List[str] = list(sorter.static_order())
    except CycleError as exc:
        # Gracefully degrade: flatten edges ignoring cycles
        plan.cycles_detected.append(list(exc.args[1]) if exc.args else ["unknown cycle"])
        plan.warnings.append(
            "Cyclic dependency detected; topological order is approximate. "
            "Manually verify phase assignments for cycle members."
        )
        # Fall back to insertion-order flattening
        seen: Set[str] = set()
        topo_order = []
        for node in list(all_nodes):
            if node not in seen:
                topo_order.append(node)
                seen.add(node)

    # -- Assign each node to a phase ----------------------------------------
    for node in topo_order:
        phase = _classify_phase(node, direct_callers, transitive_callers)
        plan.phases[phase].append(node)

    # -- Ensure symbol itself is in removal if not already placed -----------
    if symbol not in plan.phases["removal"] and not any(
        symbol in plan.phases[p] for p in PHASES
    ):
        plan.phases["removal"].append(symbol)

    return plan


# ---------------------------------------------------------------------------
# Convenience: build plan directly from classify_consumers output
# ---------------------------------------------------------------------------

def plan_from_buckets(symbol: str, buckets: dict) -> RefactoringPlan:
    """
    Derive a RefactoringPlan from the 3-bucket output of ``classify_consumers``.

    Edges are reconstructed as:
      will_break items  -> depend on symbol  (direct callers)
      might_break items -> depend on will_break items (transitive)
    """
    direct = {item["symbol"] for item in buckets.get("will_break", [])}
    transitive = {item["symbol"] for item in buckets.get("might_break", [])}

    # Build a minimal edge graph: transitives depend on directs
    edges: Dict[str, List[str]] = {symbol: []}
    for d in direct:
        edges[d] = [symbol]
    for t in transitive:
        edges[t] = list(direct) if direct else [symbol]

    unknown_count = buckets.get("unknown", {}).get("unresolved_callsites", 0)
    plan = build_plan(symbol, edges, direct, transitive)

    if unknown_count:
        plan.warnings.append(
            f"{unknown_count} unresolved callsite(s) excluded from plan "
            "(dynamic dispatch / reflection – manual audit required)."
        )
    return plan


# ---------------------------------------------------------------------------
# JSON serialisation helper
# ---------------------------------------------------------------------------

def plan_to_json(plan: RefactoringPlan) -> str:
    return json.dumps(plan.to_dict(), indent=2)
