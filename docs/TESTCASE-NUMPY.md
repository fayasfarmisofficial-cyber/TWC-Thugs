# Test case · amu on numpy/numpy

**Purpose:** prove `amu` (TWC Thugs) works on a real, large, mixed-language repository — not just on itself — and record what broke.
**Date:** 6 Sep 2026, 14:35–14:45 IST · **amu** 0.2.0 · **Entire CLI** 0.10.5 · **entire-graph** v0.4.0 · macOS arm64
**Fix commit:** `093c3df` · **Entire checkpoint:** `01M1TZXJP22S864ME7QTF1MNRN`

## 1. Setup

```bash
git clone --depth 50 https://github.com/numpy/numpy.git /tmp/numpy   # HEAD 65b30cf
cd /tmp/numpy
amu init
```

| Metric (from `entire graph index`) | Value |
|---|---|
| files | 1,666 |
| symbols | 27,709 |
| relations | 97,968 |
| snapshot lines | 164,706 |
| **unparsed files reported by amu on the first line** | **323** (Fortran `.f90`, YAML workflows, C headers) |
| wall time | 2 min 40 s |

Pass criterion: `amu init` exits 0 and prints the unparsed count (honesty line) — **pass**.

## 2. Target

`numpy/_core/numeric.py#ones` — `def ones(shape, dtype=None, order='C', *, device=None, like=None)` — change class `signature`.
Chosen because it is public, widely called, and **defined twice** in the repo (`numpy/_core/numeric.py`, `numpy/matlib.py`), which is exactly the ambiguity the router/map must not paper over.

## 3. Steps, expected, actual

| # | Command | Expected | Actual (before fix) | Actual (after fix `093c3df`) |
|---|---|---|---|---|
| 1 | `amu map --symbol numpy/_core/numeric.py#ones --change signature` | tree of consumers; non-sound nodes carry reason + verify | **crash** `TypeError: 'NoneType' object is not iterable` | 6 sound · 0 guessed · 0 unknown, qualifier present, 1.2 s |
| 2 | same, after crash fix only | consumers of `ones` | **0 consumers, silently**; 323 unknown nodes (one per unparsed file repo-wide) | — |
| 3 | `amu plan --targets numpy/_core/numeric.py#ones:signature --approve` | 4 phases, contract written, planner decision | not reached | `proceed` (0.8); phase 3 = 6 nodes / 4 files; `.amu/contract.json` written |
| 4 | `amu check --phase 1 --no-tests` | 0 blocking, exit 0 | not reached | `blocking 0 · warnings 0`, exit 0 |
| 5 | `echo "# drift" >> numpy/lib/_polynomial_impl.py` (a phase-3 file) then `amu check --phase 1 --no-tests` | `PHASE_DRIFT` + delta brief, exit 1 | not reached | `✖ PHASE_DRIFT numpy/lib/_polynomial_impl.py` · delta brief: 3 consumers · **exit 1** |
| 6 | `git checkout numpy/lib/_polynomial_impl.py && amu check --phase 1 --no-tests` | green again, exit 0 | not reached | exit 0 |
| 7 | `amu done` | sweep summary, doc candidates, memory block written; exit 0 | not reached | 0 findings outside contract · 0 doc candidates · **26 memory entries** written into numpy's `CLAUDE.md`/`AGENTS.md` |

`--no-tests` because numpy's test suite needs a compiled build; `amu check` otherwise runs the phase's tests through `entire graph verify`.

### Final map (after fix)

```
radius     4 files · 2 packages · 1 exports · 6 consumers · 0 tests
resolution 6 sound · 0 guessed · 0 unknown — graph reported 0 unresolved sites at depth 2;
           dynamic dispatch and files outside parser coverage (none listed) are not counted;
           323 files unparsed repo-wide (not counted as nodes)
next       amu plan --targets numpy/_core/numeric.py#ones:signature --approve

n1 ● sound will_break  numpy/lib/_polynomial_impl.py#roots         resolved CALLS edge at depth 1
n2 ● sound will_break  numpy/lib/_polynomial_impl.py#polyint       resolved CALLS edge at depth 1
n3 ● sound might_break numpy/lib/_polynomial_impl.py#poly1d.integ  resolved CALLS edge at depth 2
n4 ● sound will_break  (re-export, no file)#numpy.ones             resolved CALLS edge at depth 1
n5 ● sound will_break  numpy/_core/multiarray.py#copyto            resolved CALLS edge at depth 1
n6 ● sound will_break  numpy/matlib.py#empty                       resolved CALLS edge at depth 1
```

Raw payloads: `/tmp/numpy-ones-impact.json` (impact), `/tmp/numpy-ones-map.json` (map) at the time of the run; the memory block
written into numpy's `CLAUDE.md` starts with `## What amu has learned about this repo (TWC Thugs · updated 2026-09-06T09:13:45Z …)`.

## 4. Bugs found and how they were fixed

| # | Root cause | Why it matters | Fix (`amu/…`) | Regression test |
|---|---|---|---|---|
| B1 | `entire graph impact` returns `"entries": null` for empty sections on large repos; `build_map` iterated it | hard crash on any symbol with an empty callee/type section | `classify.py`: `.get("entries") or []`, `.get("endpoint") or {}` | `tests/test_map.py::test_ambiguous_symbol_is_unknown_not_silent` (uses `"entries": None`) |
| B2 | `ones` has two definitions → impact sets `disambiguation_required: true` and returns **no edges**; amu passed the bare name | the map reported **0 consumers** for a function numpy calls everywhere — the worst possible failure for a blast-radius tool, because it looks like a clean answer | `entire.py`: `impact_json(..., file=…)` passes `--file`; `cli.py` always sends the path from `path#name`; `classify.py`: a still-ambiguous symbol becomes an **unknown** node whose reason lists the competing definitions | `test_ambiguous_symbol_is_unknown_not_silent` |
| B3 | every repo-wide `partial_failures` entry became an unknown node | 323 (then 238 C/H) nodes drowned the 6 real consumers | `classify.py`: only `E_PARSE_ERROR` files in the root's own package **and** language become nodes; everything else is counted in the qualifier as `N files unparsed repo-wide (not counted as nodes)` | `test_syntax_error_file_in_root_package_becomes_unknown_node` |
| P1 | impact ran against the working-tree snapshot (uncached) | ~80 s per symbol; `--file` mode multiplies that by the number of exports | `entire.py`: `--head` (cached committed tree) by default — a map is taken *before* editing, so the committed tree is the right baseline | timing only (80 s → 1.2 s) |

A fourth, environmental finding: the clean-checkout rehearsal's `pip install -e /tmp/amu-clean` had re-pointed the `amu` command at the
throw-away clone, so the first fix appeared not to work. `python3 -c "import amu; print(amu.__file__)"` is now part of the checklist.

## 5. Honesty checks that held on numpy

- The 323 unparsed files were reported on the first line of `amu init`, and again in every map's qualifier — never hidden, never inflated into fake nodes.
- After B2, ambiguity is an *unknown* node with the reason `ambiguous: 2 definitions of ones (numpy/_core/numeric.py, numpy/matlib.py); no edges returned` rather than a silent zero.
- No output contains safe / clean / verified / OK (`tests/test_honesty.py`).
- `PHASE_DRIFT` fired on a file in a later phase and exited 1; reverting returned exit 0; a re-mapped symbol made the contract stale and `check` exited 2 until re-approved.

## 6. Reproduce

```bash
./scripts/install.sh
git clone --depth 50 https://github.com/numpy/numpy.git /tmp/numpy && cd /tmp/numpy
amu init
amu map --symbol numpy/_core/numeric.py#ones --change signature
amu plan --targets numpy/_core/numeric.py#ones:signature --approve
amu check --phase 1 --no-tests
echo "# drift" >> numpy/lib/_polynomial_impl.py && amu check --phase 1 --no-tests; echo "exit=$?"   # expect PHASE_DRIFT, exit 1
git checkout numpy/lib/_polynomial_impl.py && amu done
```
Automated: `pytest -q tests/test_map.py` (9 tests, fixture-driven, no real `entire` needed).
