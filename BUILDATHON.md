# BUILDATHON.md — Anti-Messup Agent (`amu`)
### Bengaluru Tech Week Buildathon 2026 · Track 2: Graph Intelligence

---

## The Problem — Silent AI Agent Breakage

Modern AI coding agents (Copilot, Cursor, Claude, etc.) edit code fast. Too fast.

They routinely:

- **Change a shared utility** without knowing 47 callers depend on it
- **Delete a public symbol** that's dynamically dispatched from a plugin layer
- **Mutate a frozen API** that a downstream team treats as a contract

The result is **silent breakage** — tests pass locally, CI goes green on the happy path, and production blows up two deploys later. The agent had no idea because it never asked *"who else depends on this?"*

`amu` (Anti-Messup Agent) is the answer: a CLI guardrail that forces any AI agent to **pause, measure blast radius, and generate a safe refactoring sequence** before touching a single line.

---

## Track 2: How We Use `entire-graph`

`amu` wraps the `entire` graph engine as a subprocess and exposes three purpose-built commands built on top of three `entire` primitives:

### `entire graph impact` → `amu brief`

```
amu brief --symbol module.MyClass.method --depth 2 --json
```

Runs a full-profile, depth-2 graph traversal rooted at the target symbol.  
The raw output is fed into our **3-bucket classifier** (see Curveball section).

**Why `--profile full`**: partial profiles miss transitive consumers introduced through interface abstractions — exactly the class of bug that causes production incidents.

---

### `entire graph capabilities` → unknown bucket seeding

```bash
entire graph capabilities --json --repo .
```

Before classifying any caller, `amu` fetches the graph parser's declared capability envelope.  
This tells us **what the engine itself admits it cannot see** — dynamic dispatch sites, reflection patterns, out-of-coverage modules.

These gaps are fed directly into the `unknown` bucket (see below) rather than being silently swallowed.

---

### `entire graph diff` → `amu check`

```bash
amu check --base main --head HEAD \
          --frozen "api.PublicFn" \
          --scope  "api.PublicFn,api.NewFn" \
          --removals "api.OldFn"
```

Parses entity-level diffs between two refs and enforces three contract rules:

| Violation | Trigger | Exit |
|-----------|---------|------|
| `FROZEN_SIGNATURE` | Frozen symbol's signature mutated | `exit 1` |
| `OUT_OF_SCOPE` | Changed symbol not in declared edit scope | `exit 1` |
| `UNDECLARED_REMOVAL` | Public symbol deleted without plan entry | `exit 1` |

This makes `amu check` **CI-embeddable**: wire it as a pre-merge gate and no AI-generated PR that violates scope or freezes can land without human review.

---

## The Noon Curveball — Partial Analysis & Dynamic Dispatch

The Track 2 Curveball constraint requires submissions to handle the reality that **graph analysis is never complete**:

- Dynamic dispatch (`obj.method()` where `obj` type is unknown at parse time)
- Reflection-based call patterns
- Out-of-coverage modules (vendored code, native extensions, external repos)

### Our Approach: The `unknown` Bucket

Every `amu brief` call produces **three explicit buckets** — not two:

```json
{
  "will_break":  [...],   // Statically resolved direct callers (hop 1)
  "might_break": [...],   // Statically resolved transitive callers (hop 2)
  "unknown": {
    "unresolved_callsites":   3,
    "dynamic_dispatch_sites": 0,
    "out_of_coverage":        ["legacy_module", "vendored_lib"],
    "notes": [
      "Dynamic dispatch or reflection patterns treated as heuristic/incomplete."
    ]
  }
}
```

**Key design decisions:**

1. **Never discard partial evidence** — `unresolved_callsites` is always counted, never silently zeroed.
2. **Inherit engine limits** — `capabilities()` seeds `out_of_coverage` directly from what `entire` tells us it cannot parse. We don't guess.
3. **Stable schema invariant** — the `unknown` bucket has the same four keys regardless of input. Downstream agents can always read `unknown.unresolved_callsites > 0` as *"human review required"*.
4. **Safe fallback** — if `entire` is not installed (CI bootstrap, offline dev), `capabilities()` returns a conservative default that lists `dynamic_dispatch` and `reflection` as unresolved patterns. No crash, no silent pass.

This means an AI agent consuming `amu brief --json` can implement a simple policy:

```python
if brief["buckets"]["unknown"]["unresolved_callsites"] > 0:
    escalate_to_human_review()
```

---

## Architecture

```
amu/
├── graph.py      # Subprocess wrappers: entire graph impact / diff / capabilities
│                 #   └── graceful fallback when CLI absent
├── classify.py   # 3-bucket classifier
│                 #   └── dynamic/unresolved lines → unknown, never dropped
├── plan.py       # graphlib.TopologicalSorter → 4-phase refactoring sequence
│                 #   └── CycleError caught, surfaced as warning, not crash
├── contract.py   # Entity diff parser + FROZEN / OUT_OF_SCOPE / UNDECLARED checks
│                 #   └── allow_cli_unavailable=True for safe CI degradation
└── cli.py        # Typer entrypoint (brief / plan / check)

tests/
├── test_classify.py   # Unknown bucket, fallback, classification accuracy (15 tests)
├── test_plan.py       # Phase assignment, cycle recovery, serialisation (21 tests)
├── test_contract.py   # All 3 violation kinds, severity, fallback (15 tests)
└── test_amu.py        # Integration: unknown routing + graph fallback safety (21 tests)
```

**Total: 72 tests, 0 failures.**

---

## The 4-Phase Refactoring Plan

`amu plan` uses Python's stdlib `graphlib.TopologicalSorter` to sequence edits safely:

| Phase | Who | Rule |
|-------|-----|------|
| **1 · Additive** | `new:*`-prefixed symbols | Introduce new API without removing old — zero breakage |
| **2 · Migration** | Direct callers (hop 1) | Update call sites before signature is removed |
| **3 · Interior** | Transitive callers (hop 2+) | Safe to update once direct callers are migrated |
| **4 · Removal** | Target symbol | Delete old symbol only after all consumers are migrated |

If a cyclic dependency is detected, the cycle is **surfaced as an explicit warning** and the plan degrades gracefully to insertion order — the agent is told to resolve manually rather than receiving a silent wrong answer.

---

## Quickstart

```bash
# Install
pip install -e ".[dev]"

# Pre-edit: measure blast radius
amu brief --symbol mypackage.api.create_user --depth 2

# Generate safe edit sequence
amu plan --symbol mypackage.api.create_user --json

# Post-edit: enforce contract (add to CI)
amu check --base main --head HEAD \
          --frozen "mypackage.api.create_user" \
          --scope  "mypackage.api.create_user,mypackage.api.create_user_v2"

# Run tests
pytest tests/ -v
```

---

## Why This Wins Track 2

| Criterion | What we deliver |
|-----------|----------------|
| `entire-graph` integration | `impact`, `capabilities`, `diff` — all three primitives used |
| Curveball compliance | `unknown` bucket with stable schema; never silent-drops partial evidence |
| Graph intelligence | Topological 4-phase plan from reverse-dep edges |
| Production-safe | Graceful fallback on CLI absence; cycle recovery; non-zero exit on violations |
| Test coverage | 72 passing tests across all modules |
| CI-embeddable | `amu check` exits 1 on violations — drop into any pipeline |

> `amu` doesn't just analyze blast radius. It **prevents the messup before the first keystroke.**
