# amu — Anti-Messup · BUILDATHON (TWC Thugs)

Track: Entire main challenge · Track 2 Graph Intelligence
Fork/repo: https://github.com/fayasfarmisofficial-cyber/TWC-Thugs
Final commit SHA: the commit after cc1c73b titled `chore(p8): buildathon submission` (`git rev-parse HEAD` on main)
Project URL (Vercel): not deployed — the CLI runs locally next to the repo (Phase 7 web page was cut for time; the MCP server `amu/mcp_server.py` and `scripts/install.sh` are in place).
Demo: docs/DEMO.md · recorded outputs in docs/evidence/

## Environment
Entire CLI 0.10.5 · entire-graph plugin v0.4.0 · Python 3.13.9 · macOS arm64 · installed via `brew tap entireio/tap && brew trust entireio/tap && brew install --cask entire && entire plugin install graph`.

## Problem and innovation
Agents break what they can't see. amu builds the blast map from `entire graph impact`, turns it into an ordered contract
(additive → leaves → interior → removal), gates every phase with `entire graph diff` + the working tree, and closes the loop
with a sweep + doc candidates. Honesty model: **sound** only with a resolved graph edge, **guessed** for co-change/siblings,
**unknown** for unresolved/partial parse; every non-sound node carries `reason` and `verify`; no output ever summarises with
safe/clean/verified/OK (tested in `tests/test_honesty.py`); a `0 unknown` line always carries its qualifier.

Memory: amu owns one managed block in `CLAUDE.md`/`AGENTS.md` and rewrites it after every `amu done` from hot spots,
approved contracts, answered unknowns, features, conventions, open questions — each entry cites its evidence and the Entire
checkpoint id (`entire checkpoint list --json`), and goes **stale** automatically when the cited file's hash moves. Human text
outside the markers is byte-identical after a refresh (tested).

## Setup / Run (clean checkout)
    ./scripts/install.sh
    amu init
    amu map --file amu/classify.py
    amu plan --targets amu/classify.py#classify_consumers:signature --approve
    amu check --phase 1
    amu done
Run tests: `pytest -q` (118 tests; the suite hides the real `entire` and replays fixtures via `tests/fake_entire.py`).

## Entire Checkpoints
| Checkpoint | Commit | Checkpoint ID | Link | Proves |
|---|---|---|---|---|
| init-understanding | 34f6324 | none listed by `entire checkpoint list` (see note) | — | graph-first read before edits: docs/evidence/00–03 |
| pre-curveball-stable | cc1c73b | none listed (see note) | — | loop closes end-to-end, 118 tests green |
| curveball-response | — | — | — | not reached before the 15:00 deadline |
| final-verification | chore(p8) commit on main | none listed (see note) | — | clean-checkout rehearsal in /tmp: clone → pip install -e . → 118 passed → amu init → amu map (docs/evidence/20-final-semantic-diff.txt) |

**Note (honest):** `entire enable --agent claude-code` was run at 14:12 IST *inside* an already-running Claude Code session.
`entire doctor` reports hooks OK, but `entire checkpoint list --json` returned `[]` at every protocol run
(docs/evidence/checkpoints.jsonl, docs/evidence/checkpoint-diagnostic.txt). We did not fabricate IDs. The named checkpoint
commits exist on `main` (`git log --grep checkpoint:`); if the session hooks flush later, `entire graph checkpoint <ID>` can
be run against them.

## Entire Graph evidence
- Definition/search lookup: docs/evidence/01-search-classifier.json (search ranks `classify_consumers` #1 with `graph:callers` signal), 02-def-classify.txt
- Impact analysis: docs/evidence/03-impact-classifier.txt (30 direct callers, 2 data flows), 11-amu-map-classify.json (amu's map: 35 sound · 9 guessed · 0 unknown + qualifier)
- A real red: docs/evidence/12-delta-brief.json — `amu check --phase 1` blocked on OUT_OF_SCOPE files with a delta brief
- Semantic diff: docs/evidence/20-final-semantic-diff.txt (`entire graph diff --base 34f6324 --head HEAD`)
- Commands used: search, def, impact, neighbors, diff, verify, symbols, snapshot, index, checkpoint, doctor, capabilities, init-agents

## Response to the Curveball
The noon Curveball (partial analysis / dynamic dispatch) is covered by the v0 modules kept verbatim: unknown bucket never
drops partial analysis, `check` degrades when `entire` is absent, cycles become warnings (tests/test_classify.py,
test_plan.py, test_contract.py, test_amu.py untouched, still green). The afternoon Curveball response protocol (BUILD_PLAN.md
Phase 6) was not executed — time ran out.

## How amu builds on the Entire CLI (not beside it)
`entire-amu` console script ⇒ `entire amu map …` dispatches through Entire's plugin mechanism (verified: `entire amu doctor`).
Every graph fact is an `entire graph …` call routed through `amu/entire.py`; no parsing/indexing is re-implemented.
`amu check` uses `entire graph verify` for the test verdict when available. Memory lines cite `entire checkpoint list` ids.

## Tests
- test_classify / test_plan / test_contract / test_amu — v0 noon-Curveball behaviour (untouched)
- test_map — sound/guessed/unknown assignment, reason+verify on every non-sound node, qualifier on 0 unknown
- test_honesty — banned verdict words across map/plan/contract/agent-card/rendered output; schema validation
- test_contract_phase — PHASE_DRIFT, FROZEN_SIGNATURE, OUT_OF_SCOPE block; UNKNOWN_TOUCHED warns; real diff shape parses
- test_done — sweep finding outside contract with verify; depth line never "nothing found"; done exits 0 with findings
- test_docs — SUGGESTED draft for mapped signature change; body ⇒ unknown; unmapped ⇒ flag; auto never applies unknown
- test_router — never invents a symbol; silent-on-params ⇒ signature; multi_target; ambiguous
- test_roles — tool not granted raises; write guard; checker cannot downgrade a block; 3rd retry escalates
- test_cli_smoke / test_brand — exit 3 + install hint without entire; key never printed; brand on stderr only, absent from --json
- test_memory — markers idempotent; human text byte-identical; stale flips on hash change; caps + overflow; secret rejected

## Databricks
Not applicable.

## What's next
Vercel agent card + report API (web/), `amu done --publish`, `verify --attempt-fallback` with SCIP, `docs --mode auto` in CI,
mapper ripple review, live checkpoint ids once the session hooks flush.

(No secrets. Model key is read from ANTHROPIC_API_KEY at runtime; roles run in manual mode without it.)
