<!-- entire-graph:begin -->
This repo has the entire-graph code graph installed. Before exploring code with
grep/find/whole-file reads, read .entire/graph-agent.md — resolution-first guidance
for using graph retrieval, focused source inspection, and verification.
@.entire/graph-agent.md
<!-- entire-graph:end -->

## amu project rules
- Search first: `entire graph search --repo . --profile full --query "…"` before opening files. Never guess a symbol name.
- Before editing any symbol: `amu map --symbol <path#name> --change <class>`; then `amu plan --approve`; edit one phase; `amu check --phase N`.
- Never write "safe", "clean", "verified" or "OK" as a verdict in code, tests, docs or commit messages.
- All `entire` subprocess calls go through `amu/entire.py`. No other module shells out.
- Tests use `tests/fake_entire.py` fixtures; never require the real binary.
- Each phase of BUILD_PLAN.md ends with: `pytest -q` green → `ruff check .` clean → commit (given message) → `git push origin main`.
- Checkpoints: follow BUILD_PLAN.md §3 exactly; record IDs in BUILDATHON.md; never invent an ID or link.
- Never commit keys. `amu doctor` reports whether ANTHROPIC_API_KEY is present, never its value.

<!-- amu:memory start · do not edit inside · regenerate with `amu memory refresh` -->
## What amu has learned about this repo  (TWC Thugs · updated 2026-09-06T08:56:57Z · checkpoint none-yet)
### Hot spots (history: went red in past checks)
- `amu/__init__.py` — red 2/2 · last: OUT_OF_SCOPE (chk n/a) · verify: amu check
- `amu/__pycache__/__init__.cpython-313.pyc` — red 2/2 · last: OUT_OF_SCOPE (chk n/a) · verify: amu check
- `amu/__pycache__/classify.cpython-313.pyc` — red 2/2 · last: OUT_OF_SCOPE (chk n/a) · verify: amu check
- `amu/__pycache__/contract.cpython-313.pyc` — red 2/2 · last: OUT_OF_SCOPE (chk n/a) · verify: amu check
- `amu/__pycache__/plan.cpython-313.pyc` — red 2/2 · last: OUT_OF_SCOPE (chk n/a) · verify: amu check
- `amu/brand.py` — red 2/2 · last: OUT_OF_SCOPE (chk n/a) · verify: amu check
- `amu/cli.py` — red 2/2 · last: PHASE_DRIFT (chk n/a) · verify: amu check
- `amu/contract.py` — red 2/2 · last: PHASE_DRIFT (chk n/a) · verify: amu check
### Frozen / risky interfaces (from approved contracts)
- `amu/cli.py#brief` — signature frozen in 1 of last 1 tasks
- `amu/cli.py#plan` — signature frozen in 1 of last 1 tasks
- `tests/test_amu.py#TestUnknownBucketRouting.test_dynamic_dispatch_line_increments_unresolved` — signature frozen in 1 of last 1 tasks
- `tests/test_amu.py#TestUnknownBucketRouting.test_multiple_dynamic_lines_all_counted` — signature frozen in 1 of last 1 tasks
- `tests/test_amu.py#TestUnknownBucketRouting.test_dynamic_dispatch_not_in_will_break` — signature frozen in 1 of last 1 tasks
- `tests/test_amu.py#TestUnknownBucketRouting.test_dynamic_dispatch_not_in_might_break` — signature frozen in 1 of last 1 tasks
- `tests/test_amu.py#TestUnknownBucketRouting.test_unresolved_reference_routed_to_unknown` — signature frozen in 1 of last 1 tasks
- `tests/test_amu.py#TestUnknownBucketRouting.test_partial_analysis_notes_always_present` — signature frozen in 1 of last 1 tasks
### Features → paths
- Amu: amu/**
- Amu.egg-info: amu.egg-info/**
- Docs: docs/**
- Scripts: scripts/**
- Tests: tests/**
### Conventions the graph confirmed
- - build: `python -m build` (source: build)
- - tests live in tests/, one file per module (source: conventions)
- - run tests: `pytest -q` (source: run-tests)
### Open questions (carry into the next task)
- docs/evidence/00-capabilities.json was not parsed by the graph; its consumers are invisible → amu verify --attempt-fallback
- docs/evidence/01-search-classifier.json was not parsed by the graph; its consumers are invisible → amu verify --attempt-fallback
+47 more in .amu/memory.md
<!-- amu:memory end -->
