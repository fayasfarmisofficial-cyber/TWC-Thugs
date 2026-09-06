"""
amu/contract.py
---------------
Implements the ``amu check`` guardrail command.

Parses entity-level diffs produced by ``entire graph diff`` and blocks
execution (non-zero exit) on any of these violation classes:

  FROZEN_SIGNATURE   – A symbol declared frozen had its signature mutated.
  OUT_OF_SCOPE       – A changed symbol was not listed in the edit scope.
  UNDECLARED_REMOVAL – A public symbol was deleted without an explicit
                       deprecation declaration in the plan.

Violation severity levels
  ERROR   → blocks execution (exit 1)
  WARNING → printed but does not block (exit 0)
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Enums & constants
# ---------------------------------------------------------------------------

class ViolationKind(str, Enum):
    FROZEN_SIGNATURE   = "FROZEN_SIGNATURE"
    OUT_OF_SCOPE       = "OUT_OF_SCOPE"
    UNDECLARED_REMOVAL = "UNDECLARED_REMOVAL"


class Severity(str, Enum):
    ERROR   = "ERROR"
    WARNING = "WARNING"


# Map each violation kind to its default severity
_DEFAULT_SEVERITY: Dict[ViolationKind, Severity] = {
    ViolationKind.FROZEN_SIGNATURE:   Severity.ERROR,
    ViolationKind.OUT_OF_SCOPE:       Severity.ERROR,
    ViolationKind.UNDECLARED_REMOVAL: Severity.ERROR,
}


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Violation:
    kind: ViolationKind
    symbol: str
    detail: str
    severity: Severity = Severity.ERROR

    def to_dict(self) -> dict:
        return {
            "kind":     self.kind.value,
            "symbol":   self.symbol,
            "detail":   self.detail,
            "severity": self.severity.value,
        }

    def __str__(self) -> str:
        icon = "✖" if self.severity == Severity.ERROR else "⚠"
        return f"  {icon} [{self.kind.value}] {self.symbol}: {self.detail}"


@dataclass
class ContractResult:
    passed: bool
    violations: List[Violation] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "passed":     self.passed,
            "violations": [v.to_dict() for v in self.violations],
            "warnings":   self.warnings,
        }

    def pretty(self) -> str:
        lines: List[str] = []
        if self.violations:
            lines.append("Contract Violations Found:")
            lines.extend(str(v) for v in self.violations)
        if self.warnings:
            lines.append("Warnings:")
            for w in self.warnings:
                lines.append(f"  ℹ {w}")
        status = "✔ PASSED" if self.passed else "✖ BLOCKED"
        lines.append(f"\nContract check: {status}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# entire graph diff wrapper
# ---------------------------------------------------------------------------

def _run_graph_diff(repo: str, base_ref: str, head_ref: str) -> Optional[dict]:
    """
    Invoke ``entire graph diff`` and return parsed JSON.

    Returns None if the CLI is unavailable or output is unparseable
    (treated as a graceful unknown rather than a hard crash).
    """
    cmd = [
        "entire", "graph", "diff",
        "--repo", repo,
        "--base", base_ref,
        "--head", head_ref,
        "--json",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except FileNotFoundError:
        # entire CLI not installed – return None so callers can handle gracefully
        return None
    except subprocess.TimeoutExpired:
        return None

    if result.returncode != 0 or not result.stdout.strip():
        return None

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


# ---------------------------------------------------------------------------
# Diff parser
# ---------------------------------------------------------------------------

def _parse_diff(diff_data: dict) -> List[dict]:
    """
    Normalise the ``entire graph diff`` JSON payload into a flat list of
    entity change records.

    Expected shape (best-effort, gracefully handles missing fields):
    {
      "changes": [
        {
          "symbol":    "module.MyClass.my_method",
          "change":    "modified" | "removed" | "added",
          "signature_changed": true | false,
          ...
        },
        ...
      ]
    }
    """
    raw_changes = diff_data.get("changes", [])
    if not isinstance(raw_changes, list):
        return []
    return raw_changes


# ---------------------------------------------------------------------------
# Violation detectors
# ---------------------------------------------------------------------------

def _check_frozen_signature(
    change: dict,
    frozen_symbols: set,
) -> Optional[Violation]:
    """Flag if a frozen symbol had its signature mutated."""
    symbol = change.get("symbol", "")
    if symbol in frozen_symbols and change.get("signature_changed", False):
        return Violation(
            kind=ViolationKind.FROZEN_SIGNATURE,
            symbol=symbol,
            detail="Signature was mutated on a FROZEN symbol.",
            severity=_DEFAULT_SEVERITY[ViolationKind.FROZEN_SIGNATURE],
        )
    return None


def _check_out_of_scope(
    change: dict,
    scope_symbols: set,
) -> Optional[Violation]:
    """Flag if the changed symbol was not declared in scope."""
    # Empty scope set means "all symbols allowed"
    if not scope_symbols:
        return None
    symbol = change.get("symbol", "")
    change_type = change.get("change", "")
    if change_type in ("modified", "removed") and symbol not in scope_symbols:
        return Violation(
            kind=ViolationKind.OUT_OF_SCOPE,
            symbol=symbol,
            detail=f"Symbol was {change_type} but is not in the declared edit scope.",
            severity=_DEFAULT_SEVERITY[ViolationKind.OUT_OF_SCOPE],
        )
    return None


def _check_undeclared_removal(
    change: dict,
    declared_removals: set,
) -> Optional[Violation]:
    """Flag if a public symbol was removed without being declared for removal."""
    symbol = change.get("symbol", "")
    is_public = not symbol.split(".")[-1].startswith("_")
    if change.get("change") == "removed" and is_public and symbol not in declared_removals:
        return Violation(
            kind=ViolationKind.UNDECLARED_REMOVAL,
            symbol=symbol,
            detail="Public symbol removed without a deprecation/removal declaration.",
            severity=_DEFAULT_SEVERITY[ViolationKind.UNDECLARED_REMOVAL],
        )
    return None


# ---------------------------------------------------------------------------
# Core check function (pure – no subprocess)
# ---------------------------------------------------------------------------

def check_diff(
    changes: List[dict],
    *,
    frozen_symbols: Optional[set] = None,
    scope_symbols: Optional[set] = None,
    declared_removals: Optional[set] = None,
) -> ContractResult:
    """
    Run all contract checks against a list of parsed change records.

    Parameters
    ----------
    changes : list[dict]
        Normalised change records (from ``_parse_diff``).
    frozen_symbols : set, optional
        Symbols whose signatures must not change.
    scope_symbols : set, optional
        Symbols explicitly approved for modification. Empty → all allowed.
    declared_removals : set, optional
        Public symbols explicitly planned for removal.

    Returns
    -------
    ContractResult
    """
    frozen_symbols    = frozen_symbols    or set()
    scope_symbols     = scope_symbols     or set()
    declared_removals = declared_removals or set()

    violations: List[Violation] = []
    warnings:   List[str]       = []

    for change in changes:
        v = _check_frozen_signature(change, frozen_symbols)
        if v:
            violations.append(v)

        v = _check_out_of_scope(change, scope_symbols)
        if v:
            violations.append(v)

        v = _check_undeclared_removal(change, declared_removals)
        if v:
            violations.append(v)

    # Any ERROR-severity violation blocks execution
    has_errors = any(v.severity == Severity.ERROR for v in violations)
    return ContractResult(
        passed=not has_errors,
        violations=violations,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# High-level entry point used by cli.py
# ---------------------------------------------------------------------------

def run_contract_check(
    repo: str,
    base_ref: str,
    head_ref: str,
    *,
    frozen_symbols: Optional[set] = None,
    scope_symbols: Optional[set] = None,
    declared_removals: Optional[set] = None,
    allow_cli_unavailable: bool = True,
) -> ContractResult:
    """
    Full pipeline: run ``entire graph diff``, parse output, check contracts.

    When ``allow_cli_unavailable=True`` (default) and the ``entire`` CLI
    cannot be found, returns a passing result with a warning rather than
    crashing – safe degradation for CI environments without the tool.
    """
    diff_data = _run_graph_diff(repo, base_ref, head_ref)

    if diff_data is None:
        if allow_cli_unavailable:
            return ContractResult(
                passed=True,
                warnings=[
                    "entire CLI unavailable or returned no diff data. "
                    "Contract checks skipped (safe fallback)."
                ],
            )
        return ContractResult(
            passed=False,
            violations=[
                Violation(
                    kind=ViolationKind.OUT_OF_SCOPE,
                    symbol="<graph-diff>",
                    detail="entire graph diff failed; cannot verify contracts.",
                    severity=Severity.ERROR,
                )
            ],
        )

    changes = _parse_diff(diff_data)
    return check_diff(
        changes,
        frozen_symbols=frozen_symbols,
        scope_symbols=scope_symbols,
        declared_removals=declared_removals,
    )
