# amu — Anti-Messup Agent

> Track 2 · Graph Intelligence · Bengaluru Tech Week Buildathon 2026

`amu` is a CLI guardrail that wraps the `entire` graph engine to give AI coding agents (and humans) a structured pre-edit impact brief **before** touching any symbol.

## Commands

| Command | What it does |
|---------|-------------|
| `amu brief --symbol <sym>` | 3-bucket blast-radius report (will_break / might_break / unknown) |
| `amu plan  --symbol <sym>` | 4-phase topological refactoring sequence |
| `amu check --base main --head HEAD` | Contract guardrail — blocks on FROZEN_SIGNATURE / OUT_OF_SCOPE / UNDECLARED_REMOVAL |

## Architecture

```
amu/
├── graph.py      # subprocess wrappers → entire graph impact / diff / capabilities
├── classify.py   # 3-bucket classifier (handles dynamic dispatch / unknown)
├── plan.py       # graphlib.TopologicalSorter → 4-phase plan
├── contract.py   # entity-level diff parser + violation checker
└── cli.py        # Typer entrypoint
tests/
├── test_classify.py   # unknown bucket + safe-fallback tests
├── test_plan.py       # topological phase assignment + cycle recovery
└── test_contract.py   # violation detection + CLI-unavailable fallback
```

## Curveball Compliance (Noon Track 2)

- **Unknown bucket** always emits `unresolved_callsites`, `dynamic_dispatch_sites`, `out_of_coverage`, and `notes` – never silently drops partial analysis.
- **Contract check** gracefully degrades when `entire` CLI is absent (`allow_cli_unavailable=True`).
- **Cycle detection** in `plan.py` surfaces cycles as warnings rather than crashing.
