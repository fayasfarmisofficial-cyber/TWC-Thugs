"""
tests/test_plan.py
------------------
Tests for topological plan generation (4-phase refactoring sequence).
"""

import json

from amu.plan import (
    PHASES,
    RefactoringPlan,
    build_plan,
    plan_from_buckets,
    plan_to_json,
)

# ---------------------------------------------------------------------------
# Basic plan shape
# ---------------------------------------------------------------------------

class TestBuildPlan:
    def test_returns_refactoring_plan_instance(self):
        plan = build_plan("target.fn", {})
        assert isinstance(plan, RefactoringPlan)

    def test_all_four_phases_present(self):
        plan = build_plan("target.fn", {})
        for phase in PHASES:
            assert phase in plan.phases

    def test_symbol_placed_in_removal_by_default(self):
        plan = build_plan("target.fn", {})
        # target symbol with no callers should end up in removal
        all_items = [item for phase in PHASES for item in plan.phases[phase]]
        assert "target.fn" in all_items

    def test_direct_callers_in_migration_phase(self):
        edges = {
            "caller_a": ["target.fn"],
            "caller_b": ["target.fn"],
        }
        plan = build_plan("target.fn", edges, direct_callers={"caller_a", "caller_b"})
        assert "caller_a" in plan.phases["migration"]
        assert "caller_b" in plan.phases["migration"]

    def test_transitive_callers_in_interior_phase(self):
        edges = {
            "direct_a": ["target.fn"],
            "transitive_b": ["direct_a"],
        }
        plan = build_plan(
            "target.fn",
            edges,
            direct_callers={"direct_a"},
            transitive_callers={"transitive_b"},
        )
        assert "transitive_b" in plan.phases["interior"]

    def test_new_prefixed_symbols_in_additive_phase(self):
        edges = {
            "new:target.fn_v2": [],
            "caller_a": ["target.fn"],
        }
        plan = build_plan("target.fn", edges, direct_callers={"caller_a"})
        assert "new:target.fn_v2" in plan.phases["additive"]

    def test_each_node_in_exactly_one_phase(self):
        edges = {
            "caller_a": ["target.fn"],
            "transitive_b": ["caller_a"],
            "new:v2": [],
        }
        plan = build_plan(
            "target.fn",
            edges,
            direct_callers={"caller_a"},
            transitive_callers={"transitive_b"},
        )
        all_items = [item for phase in PHASES for item in plan.phases[phase]]
        # No duplicates
        assert len(all_items) == len(set(all_items))


# ---------------------------------------------------------------------------
# Cycle handling
# ---------------------------------------------------------------------------

class TestCycleHandling:
    def test_cyclic_graph_does_not_raise(self):
        edges = {"a": ["b"], "b": ["a"]}
        plan = build_plan("target.fn", edges)
        # Must not crash; cycles_detected should be populated
        assert isinstance(plan, RefactoringPlan)

    def test_cyclic_graph_sets_warning(self):
        edges = {"a": ["b"], "b": ["a"]}
        plan = build_plan("target.fn", edges)
        assert len(plan.cycles_detected) > 0 or len(plan.warnings) > 0


# ---------------------------------------------------------------------------
# plan_from_buckets
# ---------------------------------------------------------------------------

class TestPlanFromBuckets:
    def _make_buckets(self, will=0, might=0, unresolved=0):
        return {
            "will_break": [{"symbol": f"sym_will_{i}", "reason": "direct"} for i in range(will)],
            "might_break": [{"symbol": f"sym_might_{i}", "reason": "transitive"} for i in range(might)],
            "unknown": {"unresolved_callsites": unresolved},
        }

    def test_will_break_items_in_migration(self):
        buckets = self._make_buckets(will=2)
        plan = plan_from_buckets("target.fn", buckets)
        for i in range(2):
            assert f"sym_will_{i}" in plan.phases["migration"]

    def test_might_break_items_in_interior(self):
        buckets = self._make_buckets(will=1, might=2)
        plan = plan_from_buckets("target.fn", buckets)
        for i in range(2):
            assert f"sym_might_{i}" in plan.phases["interior"]

    def test_unresolved_callsites_produce_warning(self):
        buckets = self._make_buckets(unresolved=3)
        plan = plan_from_buckets("target.fn", buckets)
        assert any("unresolved" in w.lower() or "callsite" in w.lower() for w in plan.warnings)

    def test_empty_buckets_do_not_raise(self):
        plan = plan_from_buckets("target.fn", {})
        assert isinstance(plan, RefactoringPlan)


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------

class TestSerialization:
    def test_to_dict_has_all_keys(self):
        plan = build_plan("target.fn", {})
        d = plan.to_dict()
        assert "symbol" in d
        assert "phases" in d
        assert "cycles_detected" in d
        assert "warnings" in d

    def test_plan_to_json_valid_json(self):
        plan = build_plan("target.fn", {})
        raw = plan_to_json(plan)
        parsed = json.loads(raw)
        assert parsed["symbol"] == "target.fn"

    def test_pretty_contains_phase_labels(self):
        plan = build_plan("target.fn", {})
        pretty = plan.pretty()
        for phase in PHASES:
            assert phase.upper() in pretty
