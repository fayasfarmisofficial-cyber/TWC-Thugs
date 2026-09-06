# amu · 3-minute demo script (TWC Thugs)

1. `amu` — banner, REPL. Type `/map amu/classify.py` → tree of ● sound / ◐ guessed / ○ unknown nodes, every non-sound one with reason + verify; the `resolution` line always carries its qualifier.
2. `amu plan --targets amu/classify.py#classify_consumers:signature --approve` → 4 phases + contract written; planner decision shown.
3. Edit a file that belongs to phase 3 (e.g. `amu/cli.py`), then `amu check --phase 1` → **red**: `PHASE_DRIFT` + delta brief (see `docs/evidence/12-delta-brief.json` for a recorded red).
4. Revert, `amu check --phase 1` → `blocking 0`, tests line from `entire graph verify`.
5. `amu done` → sweep summary ("swept N files at depth 2, K findings outside the contract"), doc candidates, and the memory block in `CLAUDE.md` rewritten with checkpoint id + stale detection.
6. `entire amu doctor` — same tool through the Entire plugin dispatch.
7. `amu repo add numpy/numpy --depth 1 && amu repo list` — a second repo in the workspace; `amu find "where is ones defined"`; `amu graph numpy/_core/numeric.py#ones --format mermaid`.
8. `amu key set --provider ollama --model <name>` (or an Anthropic key) then in the REPL: `what breaks if I rename classify_consumers?` — the assistant answers through `graph_search`/`amu_map` and proposes the next amu command; `amu watch --phase 1` in a second pane shows nodes flip to `↯` as you edit.

Fallback: `docs/evidence/*` holds recorded outputs.
