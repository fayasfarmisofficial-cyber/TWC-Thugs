# Anti-Messup Agent (`amu`)
> **A CLI safety harness for AI coding agents that wraps `entire-graph` to measure blast radius, enforce scope contracts, and generate topologically-safe refactoring sequences before the first keystroke.**

---

## 1. Problem & Track 2 Fit

### The Problem — Silent AI Agent Breakage

AI coding agents (Copilot, Cursor, Claude, etc.) edit code at machine speed — without knowing who else depends on what they're touching. The result is **silent breakage**:

- A shared utility is renamed; 47 callers break at runtime
- A frozen API signature is mutated; a downstream team's contract is violated
- A public symbol is deleted; a plugin using dynamic dispatch explodes in production

Tests pass. CI is green. Production is on fire.

**`amu` forces AI agents to pause, measure impact, and follow a safe edit sequence — before any code changes.**

### Track 2 Fit — `entire-graph` at the Core

`amu` is built entirely on top of the `entire` graph engine, using three primitives:

| `entire` Command | `amu` Command | Purpose |
|------------------|---------------|---------|
| `entire graph impact` | `amu brief` | Blast-radius analysis rooted at target symbol |
| `entire graph capabilities` | (feeds `amu brief`) | Declare what the engine *cannot* see — seeds the `unknown` bucket |
| `entire graph diff` | `amu check` | Entity-level diff parsed for contract violations |

---

## 2. Noon Curveball Adaptation — Partial Analysis & Dynamic Dispatch

The Track 2 Curveball constraint requires handling the reality that **static graph analysis is never complete**. Dynamic dispatch, reflection patterns, and out-of-coverage modules are invisible to any parser.

### Our Solution: The `unknown` Bucket

Every `amu brief` response produces **three explicit buckets** — never two:

```json
{
  "will_break":  [ ... ],
  "might_break": [ ... ],
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

### Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Never discard partial evidence** | `unresolved_callsites` is always counted — never silently zeroed |
| **Inherit engine limits** | `capabilities()` seeds `out_of_coverage` directly from what `entire` reports it cannot parse |
| **Stable schema invariant** | `unknown` always has the same 4 keys regardless of input — agents can reliably read `unknown.unresolved_callsites > 0` as *"human review required"* |
| **Safe CLI fallback** | If `entire` is absent (CI bootstrap, offline), `capabilities()` returns a conservative default listing `dynamic_dispatch` and `reflection` as unresolved — no crash, no silent pass |
| **Graceful cycle recovery** | `graphlib.CycleError` in plan generation is caught and surfaced as a warning; the agent gets an approximate order and an explicit flag to review manually |

### Curveball Compliance Contract (for AI Agents)

```python
brief = amu_brief("module.MyFn", json=True)

if brief["buckets"]["unknown"]["unresolved_callsites"] > 0:
    escalate_to_human_review()
elif brief["buckets"]["will_break"]:
    run_plan_and_migrate()
else:
    proceed_with_edit()
```

---

## 3. Architecture Overview

```
amu/
├── graph.py      # Subprocess wrappers → entire graph impact / diff / capabilities
│                 #   └── FileNotFoundError + OSError caught; graceful str/dict fallback
├── classify.py   # 3-bucket classifier
│                 #   └── dynamic/unresolved lines → unknown, never dropped or misclassified
├── plan.py       # graphlib.TopologicalSorter → 4-phase refactoring sequence
│                 #   └── CycleError caught, surfaced as warning, not crash
├── contract.py   # Entity diff parser + violation checker
│                 #   └── FROZEN_SIGNATURE / OUT_OF_SCOPE / UNDECLARED_REMOVAL
└── cli.py        # Typer entrypoint — three commands

tests/
├── test_classify.py   # Unknown bucket, fallback, classification accuracy  (15 tests)
├── test_plan.py       # Phase assignment, cycle recovery, serialisation     (21 tests)
├── test_contract.py   # Violation detection + CLI-unavailable fallback      (15 tests)
└── test_amu.py        # Integration: unknown routing + graph fallback safety (21 tests)
                                                              Total: 72 tests ✅
```

### `amu brief` — Blast Radius Analysis

Wraps `entire graph impact --profile full` and classifies every consumer into one of three buckets. Dynamic dispatch / unresolved references are **explicitly** routed to `unknown`, never silently dropped.

```
[WILL BREAK]         2 item(s)   ← direct callers, hop 1, statically resolved
[MIGHT BREAK]        5 item(s)   ← transitive callers, hop 2, statically resolved
[UNKNOWN / PARTIAL]  3 unresolved callsites, out_of_coverage: [legacy_module]
```

### `amu plan` — Topological 4-Phase Refactoring Sequence

Uses Python stdlib `graphlib.TopologicalSorter` on the reverse-dependency graph to produce a safe edit order:

| Phase | Who | Rule |
|-------|-----|------|
| **1 · Additive** | `new:*`-prefixed symbols | Introduce new API — zero breakage |
| **2 · Migration** | Direct callers (hop 1) | Update call sites before old signature is removed |
| **3 · Interior** | Transitive callers (hop 2+) | Safe to update once direct callers are migrated |
| **4 · Removal** | Target symbol | Delete old symbol only after all consumers are migrated |

### `amu check` — Contract Guardrail (CI Gate)

Parses `entire graph diff` output and blocks on any of three violation classes:

| Violation | Trigger | Exit |
|-----------|---------|------|
| `FROZEN_SIGNATURE` | Frozen symbol's signature mutated | `exit 1` |
| `OUT_OF_SCOPE` | Changed symbol not in declared edit scope | `exit 1` |
| `UNDECLARED_REMOVAL` | Public symbol deleted without plan entry | `exit 1` |

Wire as a pre-merge CI gate — no AI-generated PR that breaks contracts can land without human review.

---

## 4. Setup & Usage

### Installation

```bash
# Clone the repo
git clone https://github.com/fayasfarmisofficial-cyber/TWC-Thugs.git
cd TWC-Thugs

# Install with dev dependencies
pip install -e ".[dev]"
```

### `amu brief` — Pre-edit impact analysis

```bash
# Human-readable output
amu brief --symbol mypackage.api.create_user --depth 2

# JSON for agent consumption
amu brief --symbol mypackage.api.create_user --depth 2 --json
```

### `amu plan` — Generate safe refactoring sequence

```bash
# Pretty-print the 4-phase plan
amu plan --symbol mypackage.api.create_user

# JSON output (pipe into your agent)
amu plan --symbol mypackage.api.create_user --json
```

### `amu check` — Run contract guardrail

```bash
# Basic check (between main and HEAD)
amu check --base main --head HEAD

# With frozen symbols, declared scope, and planned removals
amu check \
  --base main \
  --head HEAD \
  --frozen  "mypackage.api.create_user" \
  --scope   "mypackage.api.create_user,mypackage.api.create_user_v2" \
  --removals "mypackage.api.legacy_create"

# Strict mode: treat missing entire CLI as a hard failure (for enforced CI)
amu check --base main --head HEAD --strict
```

### Run the Test Suite

```bash
# All 72 tests
pytest

# Verbose with coverage
pytest tests/ -v --tb=short
```

Expected output:
```
72 passed in 0.09s
```

---

## 5. Entire Checkpoints

> Fill in your checkpoint IDs after running `entire enable -y && entire status`

| # | Checkpoint Description | Entire ID / Link |
|---|----------------------|-----------------|
| 1 | Initial skeleton — `graph.py`, `classify.py`, `cli.py` | `<!-- PASTE ID HERE -->` |
| 2 | `plan.py` — topological 4-phase refactoring plan | `<!-- PASTE ID HERE -->` |
| 3 | `contract.py` — FROZEN / OUT_OF_SCOPE / UNDECLARED_REMOVAL checks | `<!-- PASTE ID HERE -->` |
| 4 | Final post-curveball — `test_amu.py` + hardened graph fallback | `<!-- PASTE ID HERE -->` |

To generate your checkpoint after each phase:

```bash
entire enable -y
entire status
# Copy the ID from the output and paste it into the table above
```

---

## 6. Why `amu` Wins Track 2

| Judging Criterion | What `amu` Delivers |
|-------------------|-------------------|
| `entire-graph` depth | All 3 primitives used: `impact`, `capabilities`, `diff` |
| Curveball compliance | `unknown` bucket with stable 4-key schema; dynamic dispatch never silently dropped |
| Graph intelligence | `graphlib.TopologicalSorter` 4-phase plan from reverse-dep edges |
| Production safety | `exit 1` on violations; graceful CLI fallback; cycle recovery with explicit warnings |
| Test coverage | **72 passing tests** across all 4 modules |
| CI-embeddable | `amu check` is a drop-in pre-merge gate |

> **`amu` doesn't just analyze blast radius. It prevents the messup before the first keystroke.**
