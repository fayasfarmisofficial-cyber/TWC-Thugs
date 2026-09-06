"""
tests/test_contract.py
-----------------------
Tests for contract guardrail checks (FROZEN_SIGNATURE, OUT_OF_SCOPE, UNDECLARED_REMOVAL)
and safe fallback when the entire CLI is unavailable.
"""

from amu.contract import (
    Severity,
    ViolationKind,
    _parse_diff,
    check_diff,
    run_contract_check,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_change(symbol: str, change: str = "modified", sig_changed: bool = False) -> dict:
    return {"symbol": symbol, "change": change, "signature_changed": sig_changed}


# ---------------------------------------------------------------------------
# FROZEN_SIGNATURE
# ---------------------------------------------------------------------------

class TestFrozenSignature:
    def test_frozen_sig_change_raises_violation(self):
        changes = [_make_change("api.MyClass.method", sig_changed=True)]
        result = check_diff(changes, frozen_symbols={"api.MyClass.method"})
        assert not result.passed
        kinds = [v.kind for v in result.violations]
        assert ViolationKind.FROZEN_SIGNATURE in kinds

    def test_frozen_sig_unchanged_passes(self):
        changes = [_make_change("api.MyClass.method", sig_changed=False)]
        result = check_diff(changes, frozen_symbols={"api.MyClass.method"})
        frozen_violations = [v for v in result.violations if v.kind == ViolationKind.FROZEN_SIGNATURE]
        assert len(frozen_violations) == 0

    def test_non_frozen_sig_change_does_not_trigger(self):
        changes = [_make_change("api.OtherMethod", sig_changed=True)]
        result = check_diff(changes, frozen_symbols={"api.MyClass.method"})
        frozen_violations = [v for v in result.violations if v.kind == ViolationKind.FROZEN_SIGNATURE]
        assert len(frozen_violations) == 0

    def test_frozen_violation_is_error_severity(self):
        changes = [_make_change("api.fn", sig_changed=True)]
        result = check_diff(changes, frozen_symbols={"api.fn"})
        for v in result.violations:
            if v.kind == ViolationKind.FROZEN_SIGNATURE:
                assert v.severity == Severity.ERROR


# ---------------------------------------------------------------------------
# OUT_OF_SCOPE
# ---------------------------------------------------------------------------

class TestOutOfScope:
    def test_modified_out_of_scope_symbol_triggers_violation(self):
        changes = [_make_change("internal.Helper", change="modified")]
        result = check_diff(changes, scope_symbols={"api.PublicFn"})
        kinds = [v.kind for v in result.violations]
        assert ViolationKind.OUT_OF_SCOPE in kinds

    def test_in_scope_symbol_does_not_trigger(self):
        changes = [_make_change("api.PublicFn", change="modified")]
        result = check_diff(changes, scope_symbols={"api.PublicFn"})
        oos = [v for v in result.violations if v.kind == ViolationKind.OUT_OF_SCOPE]
        assert len(oos) == 0

    def test_empty_scope_allows_all_symbols(self):
        changes = [_make_change("any.Symbol", change="modified")]
        result = check_diff(changes, scope_symbols=set())
        oos = [v for v in result.violations if v.kind == ViolationKind.OUT_OF_SCOPE]
        assert len(oos) == 0

    def test_added_symbol_not_flagged_out_of_scope(self):
        # 'added' changes should not be flagged as out-of-scope (only modified/removed)
        changes = [_make_change("new.Symbol", change="added")]
        result = check_diff(changes, scope_symbols={"api.PublicFn"})
        oos = [v for v in result.violations if v.kind == ViolationKind.OUT_OF_SCOPE]
        assert len(oos) == 0


# ---------------------------------------------------------------------------
# UNDECLARED_REMOVAL
# ---------------------------------------------------------------------------

class TestUndeclaredRemoval:
    def test_public_symbol_removed_without_declaration_triggers(self):
        changes = [_make_change("api.PublicFn", change="removed")]
        result = check_diff(changes, declared_removals=set())
        kinds = [v.kind for v in result.violations]
        assert ViolationKind.UNDECLARED_REMOVAL in kinds

    def test_declared_removal_passes(self):
        changes = [_make_change("api.PublicFn", change="removed")]
        result = check_diff(changes, declared_removals={"api.PublicFn"})
        undecl = [v for v in result.violations if v.kind == ViolationKind.UNDECLARED_REMOVAL]
        assert len(undecl) == 0

    def test_private_symbol_removal_not_flagged(self):
        changes = [_make_change("module._private_fn", change="removed")]
        result = check_diff(changes, declared_removals=set())
        undecl = [v for v in result.violations if v.kind == ViolationKind.UNDECLARED_REMOVAL]
        assert len(undecl) == 0

    def test_undeclared_removal_is_error_severity(self):
        changes = [_make_change("api.PublicFn", change="removed")]
        result = check_diff(changes, declared_removals=set())
        for v in result.violations:
            if v.kind == ViolationKind.UNDECLARED_REMOVAL:
                assert v.severity == Severity.ERROR


# ---------------------------------------------------------------------------
# Safe fallback (CLI unavailable)
# ---------------------------------------------------------------------------

class TestSafeFallback:
    def test_cli_unavailable_returns_passing_by_default(self):
        """When entire CLI is not found, allow_cli_unavailable=True must pass."""
        result = run_contract_check(
            repo=".",
            base_ref="main",
            head_ref="HEAD",
            allow_cli_unavailable=True,
        )
        # entire is not installed in test env; should pass gracefully
        assert result.passed is True

    def test_cli_unavailable_with_warning(self):
        result = run_contract_check(
            repo=".",
            base_ref="main",
            head_ref="HEAD",
            allow_cli_unavailable=True,
        )
        assert len(result.warnings) > 0

    def test_empty_changes_list_passes(self):
        result = check_diff([])
        assert result.passed is True
        assert result.violations == []

    def test_multiple_violations_all_collected(self):
        changes = [
            _make_change("api.Fn1", sig_changed=True),
            _make_change("api.Fn2", change="removed"),
            _make_change("internal.X", change="modified"),
        ]
        result = check_diff(
            changes,
            frozen_symbols={"api.Fn1"},
            scope_symbols={"api.Fn1"},
            declared_removals=set(),
        )
        assert len(result.violations) >= 2


# ---------------------------------------------------------------------------
# Diff parser
# ---------------------------------------------------------------------------

class TestParseDiff:
    def test_empty_dict_returns_empty_list(self):
        assert _parse_diff({}) == []

    def test_missing_changes_key_returns_empty_list(self):
        assert _parse_diff({"other_key": []}) == []

    def test_valid_changes_returned(self):
        data = {"changes": [{"symbol": "a.b", "change": "modified"}]}
        result = _parse_diff(data)
        assert len(result) == 1
        assert result[0]["symbol"] == "a.b"

    def test_non_list_changes_returns_empty(self):
        data = {"changes": "not a list"}
        assert _parse_diff(data) == []
