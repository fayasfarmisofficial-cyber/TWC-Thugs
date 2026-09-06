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
