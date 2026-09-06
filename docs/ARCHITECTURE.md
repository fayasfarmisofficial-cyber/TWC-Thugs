# amu architecture (as of Phase 0, 6 Sep 2026)

## What each module does today
| Module | Today | After BUILD_PLAN |
|---|---|---|
| `amu/graph.py` | subprocess wrappers: `impact()` (text), `capabilities()` (json). Never raise; return error strings / fallback dicts. | kept as a shim over `amu/entire.py`, which owns every `entire …` call (impact/neighbors/diff/search/def/symbols/snapshot/verify/doctor/checkpoint). |
| `amu/classify.py` | `classify_consumers(symbol, raw_impact_text, caps)` → `{will_break[], might_break[], unknown{unresolved_callsites, dynamic_dispatch_sites, out_of_coverage, notes}}`. Line-based heuristic over impact text. | kept verbatim (noon-Curveball proof); new `classify_nodes()` adds the confidence axis (sound/guessed/unknown) + reason/verify per node from impact JSON. |
| `amu/plan.py` | `build_plan()` graphlib topo sort → 4 phases (additive/migration/interior/removal); cycles → warnings. `plan_from_buckets()` bridges the 3 buckets. | kept; `plan_from_map()` builds phases from map nodes and `--approve` writes `.amu/contract.json`. |
| `amu/contract.py` | `check_diff(changes, frozen, scope, removals)` → FROZEN_SIGNATURE / OUT_OF_SCOPE / UNDECLARED_REMOVAL; `run_contract_check()` degrades to pass+warning when `entire` is absent. | kept; adds PHASE_DRIFT (block), UNGUARDED_CHANGE + UNKNOWN_TOUCHED (warn) and a real-shape parser for `entire graph diff --json` (`files[].changes[]{type,kind,name,…}`). |
| `amu/cli.py` | Typer: `brief`, `plan`, `check --base-ref --head-ref`. | Typer: `init map plan check verify sync sweep done docs skills doctor memory`; `brief` stays as hidden alias. Also exposed as `entire-amu` so `entire amu …` dispatches. |

## What the graph told us (docs/evidence/)
- `01-search-classifier.json`: `entire graph search` ranks `amu/classify.py#classify_consumers` first, with signals `graph:callers`, `complete-symbol`, and a narrow verify command `python -m pytest tests/test_classify.py -k …`.
- `03-impact-classifier.txt`: 30 direct callers (cli.brief, cli.plan, 28 tests), 2 data flows, 0 co-change, 0 siblings.
- Real `entire graph impact --format json` shape: `focus, callers{total,direct,entries[{endpoint{name,file_path,start_line},relation,direction,depth,call_site}]}, callees, type_consumers, data_flows, co_changes, siblings, warnings, partial_failures, completeness`.
- Real `entire graph diff --json` shape: `{base, head, files[{path,status,language,changes[{type: added|removed|body_changed|signature_changed|renamed, kind, name, new_signature?, dependents_count}]}]}`. No worktree mode — amu commits nothing, so `check` diffs `contract.base_sha..HEAD` and overlays `git status` for uncommitted files.

## What stays invariant (tested)
- unknown bucket never drops partial analysis; `check` degrades when `entire` is absent; cycles become warnings.
- No output summarises with safe / clean / verified / OK.

## Phase 9 additions (navigation, live rendering, gold)
| Module | Role |
|---|---|
| `amu/workspace.py` | `~/.amu/workspace.json` (override `AMU_HOME`): add local/GitHub repos (clone into `~/.amu/repos/<owner>__<repo>`, reuse with fetch), use/remove/sync, `resolve()` = `--repo` → repo containing `$PWD` → active → error with the add hint. Cloning is the only network call. |
| `amu/graphview.py` | `payload_from_impact()` → `{focus, nodes, edges, counts, status, candidates}`; `to_ascii / to_mermaid / to_dot`, deterministic (sorted), ids hashed for uniqueness. Ambiguous names list candidates with the exact `amu graph path#name` to run. |
| `amu/watch.py` | pure `resolve_change(path, contract, map, phase)` → node states + warning lines; `run()` via watchfiles (300 ms debounce, stop_event) with stat-polling fallback. Never runs tests. |
| `amu/render.py` | `LiveTree` (Rich Live, 4 fps, state column), `render_find`, `render_repo_table`, `render_dir_tree`; still computes nothing. |
| `amu/brand.py` | gold palette tokens + Rich theme; confidence colours are semantic and never gold; `progress()` spinner names the relation and is silent off-TTY. |
