# amu — Anti-Messup Agent

> Track 2 · Graph Intelligence · Bengaluru Tech Week Buildathon 2026

`amu` is a CLI guardrail that wraps the `entire` graph engine to give AI coding agents (and humans) a structured pre-edit impact brief **before** touching any symbol.

## Setup / Run from a clean checkout

```bash
./scripts/install.sh                 # Entire CLI + graph plugin + amu (as `amu` and `entire amu`)
amu init                             # index + snapshot + config/feature-map/doc-map/skills + memory seed
amu map --file amu/classify.py       # sound / guessed / unknown nodes, each with reason + verify
amu plan --targets amu/classify.py#classify_consumers:signature --approve
amu check --phase 1                  # exit 1 on a blocking violation, with a delta brief
amu done                             # sync → sweep → docs → memory refresh → report
pytest -q                            # 118 tests, no real `entire` needed (tests/fake_entire.py)
```

`entire amu map --file amu/plan.py` works the same way: the `entire-amu` entrypoint is dispatched by the Entire CLI.
Interactive: `amu` (no args) opens the TWC Thugs REPL — `/map /plan /approve /check N /done /docs /verify nX /why nX`.

MCP (Claude Code / Cursor) — `.mcp.json`:
```json
{"mcpServers": {"amu": {"command": "python", "args": ["-m", "amu.mcp_server"]}}}
```

## Commands (v0.2)

| Command | What it does |
|---------|-------------|
| `amu init` / `amu doctor` | index with `entire graph`, draft config; tooling health (exit 3 + install line when `entire` is missing) |
| `amu map --file F` / `--symbol path#name --change C` | blast map: sound (resolved edge) / guessed (co-change, siblings) / unknown (unresolved, partial parse) |
| `amu plan --targets sym:class --approve` | additive → leaves → interior → removal; `--approve` writes `.amu/contract.json` |
| `amu check --phase N` | `entire graph diff` + working tree vs contract: PHASE_DRIFT / OUT_OF_SCOPE / FROZEN_SIGNATURE / UNDECLARED_REMOVAL block; UNKNOWN_TOUCHED warns; red ⇒ delta brief |
| `amu verify --node nX [--attempt-fallback]` | run a node's verify path; fallback via `entire graph neighbors --internal-only` |
| `amu sweep` / `amu sync` / `amu done` | findings outside the contract (never "nothing found"); re-index; the whole close-the-loop |
| `amu docs --mode flag|draft|auto` | doc candidates from `entire graph diff`; drafts are SUGGESTED; auto applies sound+mapped only |
| `amu memory refresh|show|pin|forget` | self-renovating managed block in CLAUDE.md / AGENTS.md |
| `amu brief --symbol <sym>` (hidden) | v0 3-bucket report kept for the noon-Curveball tests |

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
