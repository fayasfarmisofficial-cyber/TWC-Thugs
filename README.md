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
pytest -q                            # 173 tests, no real `entire` needed (tests/fake_entire.py)
```

`entire amu map --file amu/plan.py` works the same way: the `entire-amu` entrypoint is dispatched by the Entire CLI.
Interactive: `amu` (no args) opens the TWC Thugs REPL (gold identity, tab-completion for repos and symbols) — `/map /plan /approve /check N /done /docs /verify nX /why nX /feature X /skills /repo /use <name> /find <words> /open <sym> /tree [path] /graph <sym> /back /ask <question> /key [add|remove]`; a bare path or symbol is an `explore`; with a model connected, any other free text goes to the model, which answers through the graph tools and proposes the next amu command.

The banner tells you whether a model is connected — `● model on · anthropic · claude-opus-5 · via file` or `○ model off · no API key added · type /key add`. `/key add` is a guided, in-session setup (pick a provider, enter only what it needs; keys are hidden and stored 0600); `/key remove` forgets it. Everything except free-text questions works with the model off.

Web (Vercel, static): `web/public` — `/` install page, `/card` agent-card viewer for `amu map --json`, `/graph` d3-force viewer for `amu graph --format json`. Same five gold tokens as the terminal. Import the repo with root dir `web/`.

Bring your own model:
```bash
amu key set                                              # Anthropic key, hidden prompt (or export ANTHROPIC_API_KEY)
amu key set --provider ollama --model qwen2.5-coder      # local, no key
amu key set --provider openrouter --model anthropic/claude-opus-5   # prompts for the key
amu key set --provider bedrock --region us-east-1        # AWS credentials from the environment
amu key set --provider vertex --project my-gcp --region global
OPENAI_BASE_URL=http://localhost:8000/v1 AMU_MODEL=my-model amu ask "…"   # env override, no file
```

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
| `amu repo add <path\|owner/repo\|url>` / `list` / `use` / `remove` / `sync` / `amu cd <name>` | workspace: many repos, one active; `cd "$(amu cd twc-thugs)"` |
| `amu find "<sentence>"` / `open <path\|sym>` / `tree [path]` / `neighbors <sym>` / `where <sym>` / `back` / `recent` | navigation, all backed by `entire graph search / def / symbols / neighbors` |
| `amu graph <path#sym> [--depth 2] [--relation CALLS] [--format text\|json\|dot\|mermaid]` | relation graph: callers above, callees below, glyph per node; Mermaid/dot for PR descriptions |
| `amu key set [--provider …]\|status\|remove` · `amu ask "<question>"` | **Bring your own provider**: `anthropic` (default, `claude-opus-5`), `bedrock`, `vertex`, `foundry` via the official SDK clients, or any OpenAI-compatible endpoint (`ollama`, `lmstudio`, `openrouter`, `openai-compatible --base-url …`). Stored 0600, never printed. `ask` answers through read-only graph tools |
| `amu watch [--phase N]` | live tree: `· planned ▸ editing ✓ green ✗ red ↯ drift` while you edit; never runs tests |
| `amu brief --symbol <sym>` (hidden) | v0 3-bucket report kept for the noon-Curveball tests |

## REPL Slash Commands

`amu` (no args) drops into an interactive REPL. Type `/help` at the prompt to see this list:

| Slash command | What it does |
|---|---|
| `/map <file>` | Blast map for a file |
| `/plan` | Draft refactor plan |
| `/approve` | Write `.amu/contract.json` |
| `/check N` | Check phase N |
| `/done` | Full close-the-loop |
| `/docs` | Doc-staleness surface |
| `/verify nX` | Run a node's verify path |
| `/why nX` | Explain a node (raw JSON) |
| `/feature X` | Look up a feature in the feature map |
| `/skills` | List available skills |
| `/repo` | List workspace repos |
| `/use <name>` | Switch active repo |
| `/find <words>` | Graph search |
| `/open <sym>` | Open a symbol or path |
| `/tree [path]` | Directory tree (depth 2) |
| `/graph <sym>` | Relation graph for a symbol |
| `/back` | Navigation history — go back |
| `/ask <question>` | Ask the AI model (requires `amu key set`) |
| `/key` | Show model key/credential status |
| `/help` | Show this command list |

A bare path or symbol triggers `explore` (opens it). Any other free text routes to the model when a key is set.

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
