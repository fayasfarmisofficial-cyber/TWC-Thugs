"""amu — Anti-Messup (TWC Thugs). Typer entrypoint, also installed as `entire-amu` so `entire amu …` dispatches here.

Exit codes: 0 ok · 1 blocking violation / red · 2 stale contract or map · 3 tooling missing.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import typer

from amu import __version__, brand, entire, graphview, keys, memory, render, router, state, workspace
from amu import docs as docsmod
from amu import watch as watchmod
from amu.classify import build_map, classify_consumers
from amu.contract import check_contract, parse_graph_diff, run_contract_check
from amu.graph import capabilities, impact
from amu.harness.orchestrator import Orchestrator
from amu.plan import make_contract, plan_from_buckets, plan_from_map, plan_to_json

app = typer.Typer(help="amu · Anti-Messup · TWC Thugs — scope guardrail for AI code edits, built on the Entire CLI",
                  epilog=brand.EPILOG, no_args_is_help=False, invoke_without_command=True, add_completion=False)
memory_app = typer.Typer(help="self-renovating CLAUDE.md memory block")
skills_app = typer.Typer(help="built-in and repo skills")
app.add_typer(memory_app, name="memory")
app.add_typer(skills_app, name="skills")

JSON_OPT = typer.Option(False, "--json", help="machine-readable output (branding suppressed)")
_NO_REPO_NEEDED = {"doctor", "list", "run", "add", "use", "remove", "sync", "cd", "set", "status", None}


def _resolve_repo_cb(ctx: typer.Context, value: str | None) -> str:
    """--repo flag → repo containing $PWD → workspace active repo → error with the add hint."""
    try:
        return workspace.resolve(value)
    except workspace.WorkspaceError as exc:
        if ctx.command.name in _NO_REPO_NEEDED or ctx.resilient_parsing:
            return value or "."
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=exc.code)


REPO_OPT = typer.Option(None, "--repo", help="repository path (default: repo containing $PWD, else the active workspace repo)", callback=_resolve_repo_cb)
repo_app = typer.Typer(help="workspace: add / list / use / remove / sync repos")
app.add_typer(repo_app, name="repo")
key_app = typer.Typer(help="model credential: set / status / remove (value is never printed)")
app.add_typer(key_app, name="key")


def _out(obj, json_mode: bool):
    if json_mode:
        typer.echo(json.dumps(obj, indent=2))


def _need_entire(json_mode: bool):
    if not entire.available() or not entire.graph_available():
        msg = {"error": "entire CLI or graph plugin missing", "install": entire.INSTALL_HINT}
        typer.echo(json.dumps(msg) if json_mode else f"entire graph is not available. Install:\n  {entire.INSTALL_HINT}", err=not json_mode)
        raise typer.Exit(code=3)


def _lookup_factory(repo: str):
    syms = None

    def lookup(token: str) -> list[dict]:
        nonlocal syms
        if syms is None:
            syms = entire.symbols(repo) if entire.available() else []
        hits = [{"symbol": s.get("qualified_name") or s.get("name"), "path": s.get("file_path")}
                for s in syms if s.get("record_type", "symbol") == "symbol" and token in (s.get("name"), s.get("qualified_name"))]
        return hits
    return lookup


@app.callback()
def main(ctx: typer.Context, version: bool = typer.Option(False, "--version", help="print version and exit")):
    if version:
        typer.echo(f"amu {__version__} · TWC Thugs · entire {entire.version()} · entire-graph {entire.graph_version()}")
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        _repl(None)


# ---------------------------------------------------------------------------
# init / doctor
# ---------------------------------------------------------------------------

@app.command()
def init(repo: str = REPO_OPT, json_output: bool = JSON_OPT):
    """Index the repo with entire graph, snapshot it, draft config / feature map / doc map / repo skills."""
    brand.header("init", state.repo_name(repo), json_output)
    _need_entire(json_output)
    idx = entire.index(repo)
    snap = entire.snapshot(repo, str(state.amu_dir(repo) / "snapshot.ndjson"))
    caps = entire.capabilities(repo)
    cfg = {**state.config(repo), **state.detect_commands(repo), "docs_dir": "docs", "docs": {"mode": "draft"},
           "languages": list((caps.get("languages") or caps.get("parsed_languages") or {}) if isinstance(caps.get("languages"), dict) else []),
           "unparsed": [pf.get("file_path") for pf in idx.get("partial_failures", []) if pf.get("file_path")]}
    state.write_json("config.json", cfg, repo)
    top = sorted({p.split("/")[0] for p in os.listdir(repo) if os.path.isdir(os.path.join(repo, p)) and not p.startswith(".")})
    if not state.read_json("feature_map.json", repo):
        state.write_json("feature_map.json", {d.capitalize(): [f"{d}/**"] for d in top}, repo)
    if not state.read_json("doc-map.json", repo):
        state.write_json("doc-map.json", docsmod.draft_doc_map(repo, cfg["docs_dir"]), repo)
    sk = state.amu_dir(repo) / "skills"
    for name, body in {"run-tests": f"- run tests: `{cfg['test_cmd']}`", "build": f"- build: `{cfg['build_cmd'] or 'none detected'}`",
                       "conventions": "- tests live in tests/, one file per module"}.items():
        (sk / name).mkdir(parents=True, exist_ok=True)
        if not (sk / name / "SKILL.md").exists():
            (sk / name / "SKILL.md").write_text(f"# {name}\n\n{body}\n")
    counts = idx.get("counts", {})
    memory.refresh(repo)
    summary = {"files": counts.get("files"), "symbols": counts.get("symbols"), "relations": counts.get("relations"),
               "snapshot_lines": snap.get("lines"), "unparsed": cfg["unparsed"], "next": "amu map --file <path>"}
    _out(summary, json_output)
    if not json_output:
        typer.echo(f"indexed {summary['files']} files · {summary['symbols']} symbols · {summary['relations']} relations · snapshot {summary['snapshot_lines']} lines")
        typer.echo(f"unparsed  {len(cfg['unparsed'])} file(s): {', '.join(cfg['unparsed'][:5]) or 'none reported by the graph'}")
        typer.echo(f"next      {summary['next']}")


@app.command()
def doctor(repo: str = REPO_OPT, json_output: bool = JSON_OPT):
    """Tooling health: entire, graph plugin, model key presence (never its value), unparsed files."""
    brand.header("doctor", state.repo_name(repo), json_output)
    ok = entire.available() and entire.graph_available()
    d = {"entire": entire.version(), "graph": entire.graph_version(), "doctor": entire.doctor() if ok else {"error": "entire missing"},
         "anthropic_key_present": keys.available(), "anthropic_key_source": keys.source(), "provider": keys.credential().get("provider"),
         "model": keys.credential().get("model") or state.config(repo).get("model", "claude-opus-5"),
         "unparsed": state.config(repo).get("unparsed", []),
         "install": None if ok else entire.INSTALL_HINT}
    _out(d, json_output)
    if not json_output:
        typer.echo(f"entire {d['entire']} · graph {d['graph']} · model {d['model']} · credential {(d['provider'] + ' via ' + d['anthropic_key_source']) if d['anthropic_key_present'] else 'absent (manual mode) → amu key set'} · unparsed {len(d['unparsed'])}")
        if not ok:
            typer.echo(f"install: {entire.INSTALL_HINT}")
    if not ok:
        raise typer.Exit(code=3)


# ---------------------------------------------------------------------------
# map / brief
# ---------------------------------------------------------------------------

def _do_map(repo: str, file: str | None, symbol: str | None, depth: int, change: str) -> dict:
    cfg = state.config(repo)
    caps = capabilities(repo)
    if symbol:
        path, _, name = symbol.rpartition("#")
        root_file, names = (path or "?"), [name]
    else:
        root_file = file
        names = [s.get("qualified_name") or s["name"] for s in entire.symbols(repo)
                 if s.get("record_type", "symbol") == "symbol" and s.get("file_path") == file and s.get("kind") in ("function", "class")
                 and not s.get("name", "_").startswith("_")]
    impacts: dict[str, dict] = {}
    with brand.progress("resolving…") as sp:
        for n in names:
            impacts[n] = entire.impact_json(repo, n, depth, file=(root_file if root_file != "?" else None))
            edges = sum(((impacts[n].get(k) or {}).get("total") or 0) for k in ("callers", "callees", "type_consumers", "data_flows"))
            sp.update(f"resolving callers of {n} · {edges} edges")
    _nav_push(repo, "map", f"{root_file}#{names[0]}" if names else root_file)
    workspace.touch(repo, last_map=root_file)
    if symbol and root_file == "?":
        f = impacts[names[0]].get("focus", {}).get("file_path")
        root_file = f or "?"
    m = build_map(root_file, names, impacts, change, state.read_json("feature_map.json", repo, default={}), caps, depth, cfg.get("test_cmd", "pytest"))
    m["map_hash"] = state.stable_hash([m["root"], [(n["path"], n["symbol"], n["confidence"]) for n in m["nodes"]], change])
    state.validate("map", m)
    state.write_json("map.json", m, repo)
    return m


@app.command()
def map(file: str = typer.Option(None, "--file"), symbol: str = typer.Option(None, "--symbol", help="path#name"),
        depth: int = typer.Option(2, "--depth"), change: str = typer.Option("signature", "--change", help="signature|remove|rename|move|body"),
        repo: str = REPO_OPT, json_output: bool = JSON_OPT):
    """Blast map: sound / guessed / unknown nodes with reason + verify, grouped by feature."""
    brand.header("map", state.repo_name(repo), json_output)
    if not (file or symbol):
        typer.echo("give --file or --symbol path#name", err=True)
        raise typer.Exit(code=2)
    _need_entire(json_output)
    m = _do_map(repo, file, symbol, depth, change)
    _out(m, json_output)
    if not json_output:
        render.render_map(m)


@app.command(hidden=True)
def brief(symbol: str = typer.Option(..., help="Target symbol"), depth: int = typer.Option(2), repo: str = REPO_OPT, json_output: bool = JSON_OPT):
    """v0 alias kept for the noon-Curveball tests: 3-bucket brief from impact text."""
    raw = impact(symbol, depth, repo)
    buckets = classify_consumers(symbol, raw, capabilities(repo))
    payload = {"symbol": symbol, "buckets": buckets}
    if json_output:
        typer.echo(json.dumps(payload, indent=2))
    else:
        typer.echo(f"[WILL BREAK] {len(buckets['will_break'])} · [MIGHT BREAK] {len(buckets['might_break'])} · [UNKNOWN / PARTIAL] {buckets['unknown']}")


# ---------------------------------------------------------------------------
# plan / check / verify
# ---------------------------------------------------------------------------

@app.command()
def plan(targets: str = typer.Option("", "--targets", help="path#sym:class,…"), approve: bool = typer.Option(False, "--approve"),
         symbol: str = typer.Option(None, "--symbol", help="v0: plan from the 3-bucket brief"),
         repo: str = REPO_OPT, json_output: bool = JSON_OPT):
    """4-phase plan (additive → leaves → interior → removal). --approve writes .amu/contract.json."""
    brand.header("plan", state.repo_name(repo), json_output)
    if symbol and not targets:
        buckets = classify_consumers(symbol, impact(symbol, 2, repo), capabilities(repo))
        rp = plan_from_buckets(symbol, buckets)
        typer.echo(plan_to_json(rp) if json_output else rp.pretty())
        return
    m = state.read_json("map.json", repo)
    if not m:
        typer.echo("no map yet — run amu map first", err=True)
        raise typer.Exit(code=2)
    tl = [{"symbol": t.rsplit(":", 1)[0], "change_class": (t.rsplit(":", 1)[1] if ":" in t else m.get("change", "signature"))}
          for t in targets.split(",") if t.strip()] or [{"symbol": f"{m['root']['file']}#*", "change_class": m.get("change", "signature")}]
    phases = plan_from_map(m, tl)
    orch = Orchestrator(repo)
    decision = orch.plan_decision(m)
    path = None
    if approve:
        c = make_contract(m, phases, tl, state.git_head(repo), state.now_iso())
        state.validate("contract", c)
        path = str(state.write_json("contract.json", c, repo))
        state.write_json(f"contracts/{c['created_at'].replace(':', '')}.json", c, repo)
        state.write_json("state.json", {"nodes": {n["id"]: "planned" for n in m["nodes"]}, "violations": [], "history": [], "updated_at": state.now_iso()}, repo)
    out = {"targets": tl, "phases": phases, "planner": decision, "contract": path, "map_hash": m["map_hash"]}
    _out(out, json_output)
    if not json_output:
        typer.echo(f"planner    {decision['decision']} (confidence {decision['confidence']}) · {decision['next']}")
        render.render_plan(phases, path)


def _run_tests(repo: str, phase_tests: list[str], cfg: dict) -> str:
    cmd = cfg.get("test_cmd") or "pytest -q"
    if phase_tests and cmd.startswith("pytest"):
        cmd = f"{cmd} {' '.join(phase_tests)}"
    v = entire.verify(repo, cmd)
    if v["rc"] in (0, 1) and v["verdict"]:
        return v["verdict"].splitlines()[0][:200]
    import subprocess
    r = subprocess.run(cmd, shell=True, cwd=repo, capture_output=True, text=True)
    tail = (r.stdout.strip().splitlines() or ["no output"])[-1]
    return f"{cmd} → exit {r.returncode}: {tail[:160]}"


@app.command()
def check(phase: int = typer.Option(None, "--phase"), base_ref: str = typer.Option(None, "--base-ref", "--base"),
          head_ref: str = typer.Option("HEAD", "--head-ref", "--head"), frozen: str = typer.Option("", help="v0: comma-separated frozen symbols"),
          scope: str = typer.Option("", help="v0: comma-separated in-scope symbols"), removals: str = typer.Option("", help="v0: declared removals"),
          strict: bool = typer.Option(False, "--strict"), no_tests: bool = typer.Option(False, "--no-tests"),
          no_live: bool = typer.Option(False, "--no-live", help="print the static tree instead of the live one"),
          repo: str = REPO_OPT, json_output: bool = JSON_OPT):
    """Contract check for a phase (or v0 --base/--head mode). Exit 1 on a blocking violation."""
    brand.header("check", state.repo_name(repo), json_output)
    if base_ref and phase is None and not state.read_json("contract.json", repo):
        split = lambda s: {x.strip() for x in s.split(",") if x.strip()}  # noqa: E731
        result = run_contract_check(repo=repo, base_ref=base_ref, head_ref=head_ref, frozen_symbols=split(frozen), scope_symbols=split(scope),
                                    declared_removals=split(removals), allow_cli_unavailable=not strict)
        typer.echo(json.dumps(result.to_dict(), indent=2) if json_output else result.pretty())
        if not result.passed:
            raise typer.Exit(code=1)
        return
    contract = state.read_json("contract.json", repo)
    m = state.read_json("map.json", repo)
    if not contract or not m:
        typer.echo("no contract — run amu plan --approve first", err=True)
        raise typer.Exit(code=2)
    if contract["map_hash"] != m["map_hash"]:
        typer.echo("contract is stale: map changed since approval (exit 2)", err=True)
        raise typer.Exit(code=2)
    cfg = state.config(repo)
    base = base_ref or contract["base_sha"]
    diff = entire.diff_json(repo, base, head_ref) if entire.available() else None
    changes = parse_graph_diff(diff) if diff else []
    changed = state.git_changed_files(repo, base)
    unknown_files = {n["path"] for n in m["nodes"] if n["confidence"] == "unknown"}
    amu_files = {"CLAUDE.md", "AGENTS.md", "BUILDATHON.md", "README.md", "BUILD_PLAN.md"}
    result = check_contract(contract, changes, changed, phase, unknown_files, amu_files)
    warnings = [] if diff or not entire.available() else ["entire graph diff returned no data; only file-scope checks ran"]
    if not entire.available():
        warnings.append("entire CLI unavailable: symbol-level checks skipped, file-scope checks ran")
    tests = None if no_tests else _run_tests(repo, (contract["phases"][phase - 1]["tests"] if phase else []), cfg)
    st = state.read_json("state.json", repo, default={"nodes": {}, "violations": [], "history": []})
    red = not result.passed
    phase_nodes = set(contract["phases"][phase - 1]["nodes"]) if phase else {n["id"] for n in m["nodes"]}
    for nid in phase_nodes:
        st["nodes"][nid] = "red" if red else "green"
    for v in result.violations:
        if v.kind.value == "PHASE_DRIFT":
            for n in m["nodes"]:
                if n["path"] == v.symbol:
                    st["nodes"][n["id"]] = "drift"
    st["violations"] = [v.to_dict() for v in result.violations]
    st["history"].append({"phase": phase, "violations": st["violations"], "at": state.now_iso(), "checkpoint": (entire.checkpoint_list() or [{}])[0].get("id", "")})
    st["updated_at"] = state.now_iso()
    state.write_json("state.json", st, repo)
    delta = None
    if red:
        v0 = next(v for v in result.violations if v.severity.value == "ERROR")
        consumers = [n["id"] for n in m["nodes"] if n["path"] == v0.symbol.split("#")[0]]
        delta = {"node": v0.symbol, "consumers": consumers, "why": v0.detail, "verify": "revert or re-plan, then amu check --phase %s" % (phase or 1)}
    out = {"phase": phase, "base": base, "changed_files": changed, "violations": [v.to_dict() for v in result.violations], "warnings": warnings,
           "tests": tests, "passed": result.passed, "delta_brief": delta,
           "next": (f"amu check --phase {phase + 1}" if phase and phase < 4 and not red else ("amu done" if not red else "fix the delta brief, then re-run"))}
    orch = Orchestrator(repo)
    out["checker"] = orch.on_check(out)
    _out(out, json_output)
    if not json_output:
        with render.LiveTree(m, enabled=not no_live and sys.stdout.isatty()) as lt:
            lt.update(st["nodes"])
        render.render_check(out)
        for w in warnings:
            typer.echo(f"  ℹ {w}")
    if red:
        raise typer.Exit(code=1)


@app.command()
def verify(node: str = typer.Option(..., "--node"), attempt_fallback: bool = typer.Option(False, "--attempt-fallback"),
           repo: str = REPO_OPT, json_output: bool = JSON_OPT):
    """Print and run a node's verify path. Never changes the contract."""
    brand.header("verify", state.repo_name(repo), json_output)
    m = state.read_json("map.json", repo)
    n = next((x for x in (m or {}).get("nodes", []) if x["id"] == node), None)
    if not n:
        typer.echo(f"node {node} not in the current map", err=True)
        raise typer.Exit(code=2)
    out = {"node": n, "verify": n["verify"], "result": None, "fallback": None}
    if n["verify"].startswith(("pytest", "npm", "go")):
        out["result"] = _run_tests(repo, [n["verify"].split(" ", 1)[1]], state.config(repo))
    if attempt_fallback and n["symbol"] and entire.available():
        nb = entire.neighbors_json(repo, n["symbol"], internal_only=True)
        out["fallback"] = {"neighbors_matches": len(nb.get("matches", [])), "note": "fallback evidence is heuristic; re-run amu map to recompute confidence"}
    _out(out, json_output)
    if not json_output:
        typer.echo(f"{n['id']} {n['path']}#{n['symbol']} · {n['confidence']} · verify: {n['verify']}")
        typer.echo(f"result     {out['result'] or 'not a runnable test; ask a human or use --attempt-fallback'}")
        if out["fallback"]:
            typer.echo(f"fallback   {out['fallback']}")


# ---------------------------------------------------------------------------
# sync / sweep / docs / done
# ---------------------------------------------------------------------------

def _sweep(repo: str) -> dict:
    contract = state.read_json("contract.json", repo, default={})
    m = state.read_json("map.json", repo, default={"nodes": []})
    base = contract.get("base_sha") or "HEAD~1"
    diff = entire.diff_json(repo, base, "HEAD") if entire.available() else None
    changes = parse_graph_diff(diff) if diff else []
    contracted = set(contract.get("allowed_files", []))
    known = {(n["path"], n["symbol"]) for n in m["nodes"]}
    findings = []
    for c in changes:
        if c["kind"] not in ("function", "class", "method") or c["symbol"].split(".")[-1].startswith("_") or c["file"] in contracted:
            continue
        conf = "sound" if (c["file"], c["symbol"]) in known else "guessed"
        findings.append({"path": c["file"], "symbol": c["symbol"], "bucket": "will_break" if c["signature_changed"] or c["change"] == "removed" else "might_break",
                         "confidence": conf, "reason": f"{c['type']} outside the contract · {c['dependents_count']} dependents", "verify": f"amu map --symbol {c['file']}#{c['symbol']} --change {'signature' if c['signature_changed'] else 'body'}"})
    depth = m.get("depth", 2)
    n_files = len({c["file"] for c in changes}) if changes else len(state.git_changed_files(repo, base))
    summary = f"swept {n_files} files at depth {depth}, {len(findings)} findings outside the contract"
    if not diff and entire.available():
        summary += " (graph diff returned no data; sweep is file-scope only)"
    return {"base": base, "findings": findings, "summary": summary, "next": "amu docs" if findings else "amu done"}


@app.command()
def sync(repo: str = REPO_OPT, json_output: bool = JSON_OPT):
    """Re-index + re-snapshot; writes .amu/sync-state.json."""
    brand.header("sync", state.repo_name(repo), json_output)
    idx = entire.index(repo) if entire.available() else {"error": "entire missing"}
    snap = entire.snapshot(repo, str(state.amu_dir(repo) / "snapshot.ndjson")) if "error" not in idx else {}
    out = {"sha": state.git_head(repo), "counts": idx.get("counts"), "snapshot_lines": snap.get("lines"), "at": state.now_iso(), "error": idx.get("error")}
    state.write_json("sync-state.json", out, repo)
    _out(out, json_output)
    if not json_output:
        typer.echo(f"synced at {out['sha'][:7]} · {out['counts'] or out['error']}")


@app.command()
def sweep(repo: str = REPO_OPT, json_output: bool = JSON_OPT):
    """Every changed public export since the contract's base_sha that is not in the contract. Never exits 1."""
    brand.header("sweep", state.repo_name(repo), json_output)
    out = _sweep(repo)
    _out(out, json_output)
    if not json_output:
        render.render_findings("sweep", out["findings"], out["summary"], out["next"])


@app.command(name="docs")
def docs_cmd(mode: str = typer.Option(None, "--mode", help="flag|draft|auto"), apply: str = typer.Option(None, "--apply", help="candidate id"),
             repo: str = REPO_OPT, json_output: bool = JSON_OPT):
    """Doc candidates from entire graph diff. draft = SUGGESTED paragraphs; auto applies sound+mapped only."""
    brand.header("docs", state.repo_name(repo), json_output)
    cfg = state.config(repo)
    mode = mode or cfg.get("docs", {}).get("mode", "draft")
    contract = state.read_json("contract.json", repo, default={})
    base = contract.get("base_sha") or "HEAD~1"
    diff = entire.diff_json(repo, base, "HEAD") if entire.available() else None
    cands = docsmod.candidates(diff, docsmod.doc_map(repo))
    applied, skipped = [], []
    if apply:
        c = next((x for x in cands if x["id"] == apply), None)
        if c and docsmod.apply(c, repo):
            applied.append(c["id"])
        else:
            skipped.append({"id": apply, "why": "not found or no mapped section"})
    elif mode == "auto":
        for c in cands:
            if c["confidence"] == "sound" and c["targets"] and docsmod.apply(c, repo):
                applied.append(c["id"])
            else:
                skipped.append({"id": c["id"], "why": f"{c['confidence']} · {c['reason']}"})
    out = {"mode": mode, "candidates": [docsmod.packet(c, repo, cfg.get("docs_dir", "docs")) if mode != "flag" else c for c in cands],
           "applied": applied, "not_applied": skipped, "commit_hint": "docs: amu auto-update" if applied and mode == "auto" else None,
           "next": "review SUGGESTED drafts; nothing here claims the docs are up to date"}
    _out(out, json_output)
    if not json_output:
        typer.echo(f"docs · mode {mode} · {len(cands)} candidates · applied {len(applied)} · not applied {len(skipped)}")
        for c in out["candidates"]:
            typer.echo(f"  {c.get('draft') or c['id'] + ' ' + c['candidate'] + ' ' + c['class']}")
        typer.echo(f"next       {out['next']}")


@app.command()
def done(publish: bool = typer.Option(False, "--publish"), repo: str = REPO_OPT, json_output: bool = JSON_OPT):
    """sync → sweep → docs → memory refresh → report. Never exits 1."""
    brand.header("done", state.repo_name(repo), json_output)
    contract = state.read_json("contract.json", repo, default={})
    idx = entire.index(repo) if entire.available() else {"error": "entire missing"}
    sw = _sweep(repo)
    diff = entire.diff_json(repo, contract.get("base_sha") or "HEAD~1", "HEAD") if entire.available() else None
    cands = docsmod.candidates(diff, docsmod.doc_map(repo))
    mem = memory.refresh(repo)
    st = state.read_json("state.json", repo, default={"nodes": {}})
    report = {"declared": {"targets": contract.get("targets", []), "files": contract.get("allowed_files", [])},
              "actual": {"changed_files": state.git_changed_files(repo, contract.get("base_sha")), "node_states": st.get("nodes", {})},
              "findings": sw["findings"], "sweep": sw["summary"], "docs": {"candidates": len(cands), "mode": state.config(repo).get("docs", {}).get("mode", "draft")},
              "memory": mem, "sync": idx.get("counts") or idx.get("error"), "at": state.now_iso(),
              "next": "commit with `chore: amu memory refresh` if CLAUDE.md changed; open findings need a human decision" if sw["findings"] or mem["changed_files"] else "start the next task with amu map"}
    state.write_json("report.json", report, repo)
    if publish and state.config(repo).get("web", {}).get("report_url"):
        report["published"] = "publishing requires network; not attempted in this build"
    _out(report, json_output)
    if not json_output:
        render.render_report(report)


# ---------------------------------------------------------------------------
# workspace: repo add / list / use / remove / sync / cd
# ---------------------------------------------------------------------------

def _ws_fail(exc: workspace.WorkspaceError, json_output: bool):
    typer.echo(json.dumps({"error": str(exc), "exit": exc.code}) if json_output else str(exc), err=not json_output)
    raise typer.Exit(code=exc.code)


@repo_app.command("add")
def repo_add(spec: str = typer.Argument(..., help="local path, owner/repo, or GitHub URL"), branch: str = typer.Option(None, "--branch"),
             depth: int = typer.Option(None, "--depth"), json_output: bool = JSON_OPT):
    """Register a repo (clone if remote), index + snapshot it with entire graph, make it active."""
    brand.header("repo add", spec, json_output)
    if not (entire.available() and entire.graph_available()):
        _need_entire(json_output)
    try:
        with brand.progress("cloning / indexing…"):
            entry = workspace.add(spec, branch, depth)
    except workspace.WorkspaceError as exc:
        _ws_fail(exc, json_output)
    _out(entry, json_output)
    if not json_output:
        c = entry["counts"]
        typer.echo(f"active     {entry['name']} · {entry['branch']} · {c.get('files')} files · {c.get('symbols')} symbols · {c.get('relations')} relations")
        typer.echo('next       amu map --file <path>   (or: amu find "what does X do")')


@repo_app.command("list")
def repo_list(json_output: bool = JSON_OPT):
    ws = workspace.load()
    rows = [{**r, "indexed_rel": workspace.relative(r.get("indexed_at", "")), "active": r["name"] == ws["active"]} for r in ws["repos"]]
    _out({"active": ws["active"], "repos": rows}, json_output)
    if not json_output:
        brand.header("repo list", f"{len(rows)} repos", False)
        render.render_repo_table(rows, ws["active"]) if rows else typer.echo("no repos yet — amu repo add <path|owner/repo>")


@repo_app.command("use")
def repo_use(name: str, json_output: bool = JSON_OPT):
    try:
        r = workspace.use(name)
    except workspace.WorkspaceError as exc:
        _ws_fail(exc, json_output)
    _out(r, json_output)
    brand.header("repo use", r["name"], json_output)


@repo_app.command("remove")
def repo_remove(name: str, delete_clone: bool = typer.Option(False, "--delete-clone", help="delete files only if the clone lives under ~/.amu/repos"), json_output: bool = JSON_OPT):
    try:
        r = workspace.remove(name, delete_clone)
    except workspace.WorkspaceError as exc:
        _ws_fail(exc, json_output)
    _out(r, json_output)
    if not json_output:
        typer.echo(f"removed {r['name']} · clone {'deleted' if r['deleted_clone'] else 'kept'}")


@repo_app.command("sync")
def repo_sync(name: str = typer.Argument(None), all_repos: bool = typer.Option(False, "--all"), json_output: bool = JSON_OPT):
    """git fetch + re-index + re-snapshot; entity-level changes via entire graph diff."""
    ws = workspace.load()
    names = [r["name"] for r in ws["repos"]] if all_repos else [name or ws["active"]]
    out = []
    for n in names:
        if not n:
            continue
        try:
            out.append(workspace.sync(n))
        except workspace.WorkspaceError as exc:
            _ws_fail(exc, json_output)
    _out(out, json_output)
    if not json_output:
        for r in out:
            typer.echo(f"{r['name']} · {r['old_sha'][:7]}→{r['sha'][:7]} · {r['files_changed']} files · {r['entity_changes']} entity changes")


@app.command("cd")
def cd_cmd(name: str):
    """Print the repo path only, so `cd "$(amu cd <name>)"` works."""
    r = workspace.get(name)
    if not r:
        typer.echo(f"no repo named {name}", err=True)
        raise typer.Exit(code=2)
    typer.echo(r["path"])


# ---------------------------------------------------------------------------
# in-repo navigation: find / open / tree / neighbors / where / back / recent
# ---------------------------------------------------------------------------

def _nav_push(repo: str, kind: str, target: str) -> None:
    nav = state.read_json("nav.json", repo, default={"stack": []})
    nav["stack"] = (nav["stack"] + [{"kind": kind, "target": target, "at": state.now_iso()}])[-20:]
    state.write_json("nav.json", nav, repo)


def _hits(sr: dict) -> list[dict]:
    return [{"rank": r.get("rank"), "file_path": r.get("file_path"), "focus_line": r.get("focus_line") or r.get("start_line"),
             "symbol_name": r.get("symbol_name") or r.get("qualified_name") or "", "kind": r.get("kind"), "signals": r.get("signals") or [],
             "signature": r.get("signature")} for r in sr.get("results") or []]


@app.command()
def find(query: str, open_hit: str = typer.Option(None, "--open", help="print file:line of hit nN"), repo: str = REPO_OPT, json_output: bool = JSON_OPT):
    """Ranked hits from `entire graph search`, each with the signals that ranked it."""
    brand.header("find", state.repo_name(repo), json_output)
    _need_entire(json_output)
    sr = entire.search(repo, query)
    hits = _hits(sr)
    _nav_push(repo, "find", query)
    if open_hit:
        i = int(open_hit.lstrip("n")) - 1
        if 0 <= i < len(hits):
            typer.echo(f"{hits[i]['file_path']}:{hits[i]['focus_line']}")
            return
        typer.echo(f"no hit {open_hit}", err=True)
        raise typer.Exit(code=2)
    out = {"query": query, "hits": hits, "verify_command": sr.get("verify_command"), "coverage_note": sr.get("coverage_note"), "error": sr.get("error")}
    _out(out, json_output)
    if not json_output:
        render.render_find(hits, query, sr.get("verify_command"))


@app.command("open")
def open_cmd(target: str, repo: str = REPO_OPT, json_output: bool = JSON_OPT):
    """`entire graph def` for a symbol (or list a file's symbols), then the one-line next."""
    brand.header("open", state.repo_name(repo), json_output)
    _need_entire(json_output)
    _nav_push(repo, "open", target)
    if "/" in target and "#" not in target and Path(repo, target).exists():
        syms = [s for s in entire.symbols(repo) if s.get("file_path") == target and s.get("record_type", "symbol") == "symbol"]
        out = {"file": target, "symbols": [{"name": s.get("qualified_name"), "kind": s.get("kind"), "line": s.get("start_line"), "signature": s.get("signature")} for s in syms],
               "next": f"amu map --file {target}"}
        _out(out, json_output)
        if not json_output:
            for x in out["symbols"]:
                typer.echo(f"  {x['line']:>5}  {x['kind']:<9} {x['signature'] or x['name']}")
            if not out["symbols"]:
                typer.echo("  (no exported symbols in the graph for this file)")
            typer.echo(f"read       /cat {target} 1 80   ·   next       {out['next']}")
        return
    name = target.split("#")[-1]
    text = entire.definition(repo, name)
    out = {"symbol": name, "definition": text, "next": f"amu map --symbol {target} --change signature"}
    _out(out, json_output)
    if not json_output:
        typer.echo(text.rstrip())
        typer.echo(f"next       {out['next']}")


@app.command()
def tree(path: str = typer.Argument("."), depth: int = typer.Option(2, "--depth"), repo: str = REPO_OPT, json_output: bool = JSON_OPT):
    """Directory tree annotated with export counts and feature labels from feature_map.json."""
    brand.header("tree", state.repo_name(repo), json_output)
    root = Path(repo, path).resolve()
    fm = state.read_json("feature_map.json", repo, default={})
    counts: dict[str, int] = {}
    if entire.available():
        for s_ in entire.symbols(repo):
            if s_.get("record_type", "symbol") == "symbol" and s_.get("kind") in ("function", "class") and not str(s_.get("name", "_")).startswith("_"):
                counts[s_["file_path"]] = counts.get(s_["file_path"], 0) + 1
    from amu.classify import _feature_for
    rows = {}
    for p in root.rglob("*"):
        if p.is_file() and not any(seg in p.parts for seg in (".git", ".amu", "__pycache__", "node_modules")):
            rel = str(p.relative_to(Path(repo).resolve()))
            feat, src = _feature_for(rel, fm)
            rows[str(p.relative_to(root))] = {"exports": counts.get(rel, 0), "feature": feat + ("" if src == "map" else " (derived)")}
    _out({"root": str(root), "files": rows}, json_output)
    if not json_output:
        render.render_dir_tree(root, rows, depth)


@app.command()
def neighbors(symbol: str, relation: str = typer.Option("CALLS", "--relation"), direction: str = typer.Option("in", "--direction"),
              repo: str = REPO_OPT, json_output: bool = JSON_OPT):
    """Thin wrapper over `entire graph neighbors`."""
    brand.header("neighbors", state.repo_name(repo), json_output)
    _need_entire(json_output)
    nb = entire.neighbors_json(repo, symbol.split("#")[-1], relation, direction)
    _out(nb, json_output)
    if not json_output:
        for m_ in nb.get("matches") or []:
            for e in m_.get("neighbors") or m_.get("entries") or []:
                ep = e.get("endpoint") or e.get("symbol") or e
                typer.echo(f"  {e.get('relation', relation)} {direction}  {ep.get('file_path')}#{ep.get('name')}")
        typer.echo(f"matches    {len(nb.get('matches') or [])} · truncated {nb.get('truncated', False)}")


@app.command()
def where(symbol: str, repo: str = REPO_OPT, json_output: bool = JSON_OPT):
    """Def site + the file's feature + whether it is frozen in the current contract."""
    brand.header("where", state.repo_name(repo), json_output)
    _need_entire(json_output)
    name = symbol.split("#")[-1]
    defs = [s_ for s_ in entire.symbols(repo) if s_.get("record_type", "symbol") == "symbol" and name in (s_.get("name"), s_.get("qualified_name"))]
    if "#" in symbol:
        defs = [d for d in defs if d.get("file_path") == symbol.split("#")[0]] or defs
    contract = state.read_json("contract.json", repo, default={})
    fm = state.read_json("feature_map.json", repo, default={})
    from amu.classify import _feature_for
    out = {"symbol": name, "status": "ok" if len(defs) == 1 else ("not_found" if not defs else "ambiguous"),
           "definitions": [{"file": d.get("file_path"), "line": d.get("start_line"), "kind": d.get("kind"), "feature": _feature_for(d.get("file_path", ""), fm)[0],
                            "frozen": f"{d.get('file_path')}#{d.get('qualified_name')}" in set(contract.get("frozen_signatures", []))} for d in defs]}
    _out(out, json_output)
    if not json_output:
        for d in out["definitions"]:
            typer.echo(f"  {d['file']}:{d['line']}  {d['kind']}  feature {d['feature']}  {'FROZEN in contract' if d['frozen'] else 'not frozen'}")
        typer.echo(f"status     {out['status']}")


@app.command()
def back(repo: str = REPO_OPT, json_output: bool = JSON_OPT):
    """Return to the previous navigation target (map / find / open) from .amu/nav.json."""
    nav = state.read_json("nav.json", repo, default={"stack": []})
    if len(nav["stack"]) < 2:
        typer.echo("nothing to go back to", err=True)
        raise typer.Exit(code=2)
    nav["stack"].pop()
    prev = nav["stack"][-1]
    state.write_json("nav.json", nav, repo)
    _out(prev, json_output)
    if not json_output:
        typer.echo(f"back to {prev['kind']} {prev['target']}")
        if prev["kind"] == "map":
            path, _, name = prev["target"].rpartition("#")
            render.render_map(_do_map(repo, None if name else path, prev["target"] if name else None, 2, state.read_json("map.json", repo, default={}).get("change", "signature")))


@app.command()
def recent(repo: str = REPO_OPT, json_output: bool = JSON_OPT):
    nav = state.read_json("nav.json", repo, default={"stack": []})
    _out(nav["stack"], json_output)
    if not json_output:
        for i, e in enumerate(reversed(nav["stack"]), 1):
            typer.echo(f"  {i:>2}  {e['kind']:<5} {e['target']}  [{e['at']}]")


# ---------------------------------------------------------------------------
# live rendering: graph / watch
# ---------------------------------------------------------------------------

@app.command()
def graph(symbol: str, depth: int = typer.Option(2, "--depth"), relation: str = typer.Option(None, "--relation"),
          fmt: str = typer.Option("text", "--format", help="text|json|dot|mermaid"), repo: str = REPO_OPT, json_output: bool = JSON_OPT):
    """ASCII relation graph from `entire graph impact`; --format dot / mermaid for PR descriptions."""
    if fmt == "json":
        json_output = True
    brand.header("graph", state.repo_name(repo), json_output or fmt in ("dot", "mermaid"))
    _need_entire(json_output)
    path, _, name = symbol.rpartition("#")
    imp = entire.impact_json(repo, name, depth, file=path or None)
    p = graphview.payload_from_impact(name, imp, relation)
    if json_output:
        typer.echo(json.dumps(p, indent=2))
    elif fmt == "mermaid":
        typer.echo(graphview.to_mermaid(p))
    elif fmt == "dot":
        typer.echo(graphview.to_dot(p))
    else:
        typer.echo(graphview.to_ascii(p))
        if p["warnings"]:
            typer.echo(f"warnings   {', '.join(p['warnings'])}")


@app.command("watch")
def watch_cmd(phase: int = typer.Option(None, "--phase"), no_live: bool = typer.Option(False, "--no-live"),
              seconds: float = typer.Option(None, "--seconds", hidden=True), repo: str = REPO_OPT):
    """Watch the working tree; update node states (▸ editing · ↯ drift) against the active contract. Never runs tests."""
    brand.header("watch", state.repo_name(repo), False)
    m = state.read_json("map.json", repo)
    if not m:
        typer.echo("no map yet — run amu map first", err=True)
        raise typer.Exit(code=2)
    st = state.read_json("state.json", repo, default={"nodes": {}})
    with render.LiveTree(m, enabled=not no_live and sys.stdout.isatty()) as lt:
        lt.update(st["nodes"])

        def on_update(path, new_state, warnings):
            lt.update(new_state["nodes"], warnings or [f"▸ {path}"])
        try:
            watchmod.run(repo, phase, on_update, stop_after=seconds)
        except KeyboardInterrupt:
            pass


# ---------------------------------------------------------------------------
# key: set / status / remove  (the value is never echoed, logged, or committed)
# ---------------------------------------------------------------------------

@key_app.command("set")
def key_set(value: str = typer.Option(None, "--value", help="API key (prefer the hidden prompt or an env var)"),
            provider: str = typer.Option("anthropic", "--provider", help="anthropic|bedrock|vertex|foundry|openai-compatible|ollama|lmstudio|openrouter"),
            base_url: str = typer.Option(None, "--base-url"), model: str = typer.Option(None, "--model"),
            region: str = typer.Option(None, "--region"), project: str = typer.Option(None, "--project"), resource: str = typer.Option(None, "--resource"),
            json_output: bool = JSON_OPT):
    """Bring your own provider. Stores ~/.amu/credentials.json (mode 0600); the key is never printed."""
    brand.header("key set", provider, json_output)
    needs_key = keys.PROVIDERS.get(provider, (None, None, None, True))[3]
    v = value if value is not None else (typer.prompt(f"{provider} API key", hide_input=True) if needs_key or provider in ("openai-compatible",) else None)
    try:
        path = keys.set_credential(provider, api_key=v, base_url=base_url, model=model, region=region, project_id=project, resource=resource)
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2)
    out = {"stored": path, "source": keys.source(), "masked": keys.masked()}
    _out(out, json_output)
    if not json_output:
        typer.echo(f"stored     {path} (0600) · {out['masked']} · run `amu` for the interactive session")


@key_app.command("status")
def key_status(json_output: bool = JSON_OPT):
    c = keys.credential()
    out = {"source": c["source"], "provider": c.get("provider"), "model": c.get("model"), "base_url": c.get("base_url"), "masked": keys.masked() if keys.available() else None,
           "providers": list(keys.PROVIDERS)}
    _out(out, json_output)
    if not json_output:
        typer.echo(f"credential {out['source']}" + (f" · {out['masked']}" if out["masked"] else " · run `amu key set [--provider …]`; providers: " + ", ".join(keys.PROVIDERS)))


@key_app.command("remove")
def key_remove():
    typer.echo("removed ~/.amu/credentials.json" if keys.remove_key() else "no stored key (ANTHROPIC_API_KEY, if set, is untouched)")


@app.command()
def ask(question: str, no_stream: bool = typer.Option(False, "--no-stream"), repo: str = REPO_OPT, json_output: bool = JSON_OPT):
    """Ask the model about this repo; it answers through the graph tools (read-only) and proposes the next amu command."""
    from amu.harness.chat import Assistant
    brand.header("ask", state.repo_name(repo), json_output)
    a = Assistant(repo, out=(lambda t: None) if (json_output or no_stream) else None, stream=not (json_output or no_stream))
    answer = a.ask(question)
    if json_output:
        typer.echo(json.dumps({"question": question, "answer": answer, "model": a.model, "turns": len(a.messages)}))
    elif no_stream:
        typer.echo(answer)
    else:
        typer.echo("")


# ---------------------------------------------------------------------------
# memory / skills / repl
# ---------------------------------------------------------------------------

@memory_app.command("refresh")
def memory_refresh(no_commit: bool = typer.Option(True, "--no-commit/--commit"), repo: str = REPO_OPT, json_output: bool = JSON_OPT):
    """Rebuild .amu/memory.json and rewrite the managed block in CLAUDE.md + AGENTS.md."""
    brand.header("memory refresh", state.repo_name(repo), json_output)
    out = memory.refresh(repo)
    if not no_commit and out["changed_files"]:
        import subprocess
        subprocess.run(["git", "add", *out["changed_files"]], cwd=repo)
        subprocess.run(["git", "commit", "-qm", "chore: amu memory refresh"], cwd=repo)
        out["committed"] = True
    _out(out, json_output)
    if not json_output:
        typer.echo(f"memory · {out['entries']} entries · {out['stale']} stale · block {out['block_lines']} lines · changed {out['changed_files'] or 'nothing'}")


@memory_app.command("show")
def memory_show(repo: str = REPO_OPT, json_output: bool = JSON_OPT):
    mem = state.read_json("memory.json", repo, default={"entries": []})
    for e in mem["entries"]:
        state.validate("memory_entry", e)
    _out(mem, json_output)
    if not json_output:
        for e in mem["entries"]:
            typer.echo(f"{e['id']} [{e['kind']}] {e['text']} · evidence {e['evidence']}{' · STALE: ' + e['stale'] if e.get('stale') else ''}{' 📌' if e['pinned'] else ''}")


@memory_app.command("pin")
def memory_pin(entry_id: str, repo: str = REPO_OPT):
    typer.echo("pinned" if memory.pin(entry_id, repo, True) else "no such entry")


@memory_app.command("unpin")
def memory_unpin(entry_id: str, repo: str = REPO_OPT):
    typer.echo("unpinned" if memory.pin(entry_id, repo, False) else "no such entry")


@memory_app.command("forget")
def memory_forget(entry_id: str, repo: str = REPO_OPT):
    typer.echo("forgotten (kept in history)" if memory.forget(entry_id, repo) else "no such entry")


@app.command()
def stale(repo: str = REPO_OPT, json_output: bool = JSON_OPT):
    """Contract/map staleness plus memory entries whose evidence hash moved."""
    m, c = state.read_json("map.json", repo), state.read_json("contract.json", repo)
    mem = state.read_json("memory.json", repo, default={"entries": []})
    out = {"contract_stale": bool(m and c and m["map_hash"] != c["map_hash"]),
           "memory_stale": [e["id"] for e in mem["entries"] if e.get("file") and e["file_hash"] and state.file_hash(e["file"], repo) != e["file_hash"]]}
    _out(out, json_output)
    if not json_output:
        typer.echo(f"contract stale: {out['contract_stale']} · memory entries with moved evidence: {len(out['memory_stale'])}")


def _skill_dirs(repo: str):
    yield from (Path(__file__).parent / "skills").glob("*/SKILL.md")
    yield from (state.amu_dir(repo) / "skills").glob("*/SKILL.md")


@skills_app.command("list")
def skills_list(repo: str = REPO_OPT, json_output: bool = JSON_OPT):
    items = [{"name": p.parent.name, "path": str(p), "builtin": "amu/skills" in str(p)} for p in _skill_dirs(repo)]
    _out(items, json_output)
    if not json_output:
        for i in items:
            typer.echo(f"{'builtin' if i['builtin'] else 'repo   '} {i['name']}")


@skills_app.command("run")
def skills_run(name: str, repo: str = REPO_OPT):
    p = next((p for p in _skill_dirs(repo) if p.parent.name == name), None)
    typer.echo(p.read_text() if p else f"no skill {name}")


@skills_app.command("add")
def skills_add(name: str, text: str = typer.Option("", "--text"), repo: str = REPO_OPT):
    d = state.amu_dir(repo) / "skills" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(text or f"# {name}\n\n- (describe the steps)\n")
    typer.echo(f"wrote {d / 'SKILL.md'}")



# ---------------------------------------------------------------------------
# model status + guided key setup (REPL)
# ---------------------------------------------------------------------------

_PROVIDER_MENU = [
    ("anthropic", "Anthropic API key (claude-opus-5)", ["key"]),
    ("ollama", "Ollama, local, no key", ["model"]),
    ("lmstudio", "LM Studio, local, no key", ["model"]),
    ("openrouter", "OpenRouter (key + model, e.g. anthropic/claude-opus-5)", ["key", "model"]),
    ("openai-compatible", "Any OpenAI-compatible endpoint (base URL + model, key optional)", ["base_url", "model", "key?"]),
    ("bedrock", "Amazon Bedrock (AWS credentials from your environment)", ["region"]),
    ("vertex", "Google Vertex AI (gcloud ADC)", ["project", "region"]),
    ("foundry", "Microsoft Foundry (resource + key)", ["resource", "key"]),
]



PALETTE_ROWS = [
    ("explore", "/find <words> · /open <file|sym> · /cat <file> [start] [end] · /tree [path] · /where <sym> · /graph <sym> · /back"),
    ("guard",   "/map <file> · /plan · /approve · /check N · /verify nX · /why nX · /done · /docs"),
    ("session", "/repo · /use <name> · /key [add|remove] · /skills · /help · /quit   — slash optional: `open amu/plan.py` works too"),
    ("talk",    "a change request (\"rename classify_consumers\") maps it; any other sentence goes to the model when ● on"),
]


def print_palette() -> None:
    from rich.markup import escape
    c = brand.err_console()
    for label, row in PALETTE_ROWS:
        c.print(f"  [brand.label]{label:<8}[/] [brand.body]{escape(row)}[/]")

def model_status_line() -> str:
    """One line for the banner: ● on with provider/model, or ○ off with the two-step guide."""
    if keys.available():
        c = keys.credential()
        return f"[conf.sound]● model on[/] · {c.get('provider')} · {c.get('model')} · via {c['source']}"
    return "[conf.unknown]○ model off[/] · no API key added · type [brand]/key add[/] (2 steps) or run [brand]amu key set[/] — the graph commands work without it"


def guided_key_setup() -> bool:
    """Interactive, provider-aware. Returns True when a credential was stored."""
    c = brand.err_console()
    c.print("[brand]add a model[/] [brand.muted]— pick a provider; keys are stored in ~/.amu/credentials.json (0600) and never printed[/]")
    for i, (name, desc, _) in enumerate(_PROVIDER_MENU, 1):
        c.print(f"  [brand.muted]{i}[/]  {name:<18} [brand.body]{desc}[/]")
    try:
        choice = typer.prompt("provider (number or name)", default="1").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    name = choice
    if choice.isdigit() and 1 <= int(choice) <= len(_PROVIDER_MENU):
        name = _PROVIDER_MENU[int(choice) - 1][0]
    entry = next((e for e in _PROVIDER_MENU if e[0] == name), None)
    if not entry:
        c.print(f"[risk]unknown provider {choice}[/] — choose 1-{len(_PROVIDER_MENU)}")
        return False
    fields: dict = {}
    try:
        for f in entry[2]:
            if f == "key":
                fields["api_key"] = typer.prompt(f"{name} API key", hide_input=True)
            elif f == "key?":
                v = typer.prompt("API key (blank if none)", default="", hide_input=True, show_default=False)
                fields["api_key"] = v or None
            elif f == "model":
                default = keys.PROVIDERS[name][1] or ""
                fields["model"] = typer.prompt("model", default=default) if default else typer.prompt("model")
            elif f == "base_url":
                fields["base_url"] = typer.prompt("base URL (…/v1)")
            elif f == "region":
                fields["region"] = typer.prompt("region")
            elif f == "project":
                fields["project_id"] = typer.prompt("GCP project id")
            elif f == "resource":
                fields["resource"] = typer.prompt("Foundry resource")
    except (EOFError, KeyboardInterrupt):
        c.print("[brand.muted]cancelled — nothing stored[/]")
        return False
    try:
        path = keys.set_credential(name, **fields)
    except ValueError as exc:
        c.print(f"[risk]{exc}[/]")
        return False
    c.print(f"[conf.sound]● model on[/] · stored {path} (0600) · {keys.masked()}")
    return True

def _completer(repo: str):
    try:
        from prompt_toolkit.completion import WordCompleter
    except ImportError:
        return None
    words = list(router.SLASH) + [r["name"] for r in workspace.load()["repos"]]
    snap = state.amu_dir(repo) / "snapshot.ndjson"
    if snap.exists():
        import re as _re
        words += _re.findall(r'"name":"([A-Za-z_][A-Za-z0-9_.]*)"', snap.read_text()[:2_000_000])[:5000]
    for n in state.read_json("map.json", repo, default={"nodes": []})["nodes"]:
        words.append(n["id"])
    return WordCompleter(sorted(set(words)), ignore_case=True)


def _read_line(repo: str) -> str:
    if sys.stdin.isatty():
        try:
            from prompt_toolkit import PromptSession
            from prompt_toolkit.formatted_text import FormattedText
            session = PromptSession(completer=_completer(repo))
            return session.prompt(FormattedText([(brand.PALETTE["gold"], "twc-thugs "), (brand.PALETTE["amber"], "❯ ")]) if brand.color_enabled()
                                  else brand.PROMPT)
        except ImportError:
            pass
    return input(brand.PROMPT)


def _repl(repo: str | None = None):
    try:
        repo = workspace.resolve(repo)
    except workspace.WorkspaceError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=exc.code)
    brand.banner(__version__, state.repo_name(repo), f"{'enabled' if entire.available() else 'missing'} · graph {entire.graph_version()}")
    from amu.harness.chat import Assistant
    assistant = Assistant(repo) if keys.available() else None
    brand.err_console().print(model_status_line())
    print_palette()
    lookup = _lookup_factory(repo)

    def _cat(arg: str):
        parts = arg.split()
        if not parts:
            typer.echo("usage: /cat <file> [start] [end]")
            return
        p = Path(repo, parts[0])
        if not p.is_file():
            typer.echo(f"no such file: {parts[0]} — try /tree or /find")
            return
        lines = p.read_text(errors="ignore").splitlines()
        start = int(parts[1]) if len(parts) > 1 else 1
        end = int(parts[2]) if len(parts) > 2 else min(len(lines), start + 79)
        for i in range(max(1, start), min(len(lines), end) + 1):
            typer.echo(f"{i:>5}  {lines[i - 1]}")
        if end < len(lines):
            typer.echo(f"… {len(lines) - end} more lines · /cat {parts[0]} {end + 1} {end + 80}")

    def _key_cmd(arg: str):
        nonlocal assistant
        if arg in ("add", "set", "on"):
            if guided_key_setup():
                assistant = Assistant(repo)
        elif arg in ("remove", "off"):
            keys.remove_key()
            assistant = None
            brand.err_console().print(model_status_line())
        else:
            brand.err_console().print(model_status_line())
            if not keys.available():
                brand.err_console().print("[brand.muted]  /key add  → guided setup (provider, key or model)   ·   /key remove  → forget the stored key[/]")
    while True:
        try:
            line = _read_line(repo)
        except (EOFError, KeyboardInterrupt):
            typer.echo("")
            return
        if not line.strip():
            print_palette()
            continue
        r = router.route(line, lookup)
        if r["status"] == "command":
            arg = r.get("arg", "")
            cmds = {"map": lambda: render.render_map(_do_map(repo, arg, None, 2, "signature")),
                    "plan": lambda: plan(targets="", approve=False, symbol=None, repo=repo, json_output=False),
                    "approve": lambda: plan(targets="", approve=True, symbol=None, repo=repo, json_output=False),
                    "check": lambda: check(phase=int(arg or 1), base_ref=None, head_ref="HEAD", frozen="", scope="", removals="", strict=False, no_tests=False, no_live=True, repo=repo, json_output=False),
                    "done": lambda: done(publish=False, repo=repo, json_output=False),
                    "docs": lambda: docs_cmd(mode=None, apply=None, repo=repo, json_output=False),
                    "verify": lambda: verify(node=arg, attempt_fallback=False, repo=repo, json_output=False),
                    "skills": lambda: skills_list(repo=repo, json_output=False),
                    "why": lambda: typer.echo(json.dumps(next((n for n in state.read_json("map.json", repo, default={"nodes": []})["nodes"] if n["id"] == arg), "no such node"), indent=2)),
                    "feature": lambda: typer.echo(json.dumps(state.read_json("feature_map.json", repo, default={}).get(arg, "unknown feature"))),
                    "repo": lambda: repo_list(json_output=False),
                    "use": lambda: repo_use(arg, json_output=False),
                    "find": lambda: find(arg, open_hit=None, repo=repo, json_output=False),
                    "open": lambda: open_cmd(arg, repo=repo, json_output=False),
                    "tree": lambda: tree(arg or ".", depth=2, repo=repo, json_output=False),
                    "back": lambda: back(repo=repo, json_output=False),
                    "graph": lambda: graph(arg, depth=2, relation=None, fmt="text", repo=repo, json_output=False),
                    "ask": lambda: (typer.echo(assistant.ask(arg)) if not assistant or not arg else (assistant.ask(arg), typer.echo(""))),
                    "key": lambda: _key_cmd(arg),
                    "cat": lambda: _cat(arg),
                    "where": lambda: where(arg, repo=repo, json_output=False),
                    "recent": lambda: recent(repo=repo, json_output=False),
                    "neighbors": lambda: neighbors(arg, relation="CALLS", direction="in", repo=repo, json_output=False),
                    "quit": lambda: (_ for _ in ()).throw(EOFError()),
                    "help": print_palette}
            try:
                if r["intent"] not in cmds:
                    typer.echo(f"unknown command /{r['intent']} — here is what works:")
                cmds.get(r["intent"], cmds["help"])()
                if r["intent"] == "use" and workspace.get(arg):
                    repo = workspace.get(arg)["path"]
                    lookup = _lookup_factory(repo)
            except EOFError:
                typer.echo("")
                return
            except typer.Exit:
                pass
            continue
        if r["status"] == "explore":
            try:
                open_cmd(r["arg"], repo=repo, json_output=False)
            except typer.Exit:
                pass
            continue
        if r["status"] == "ok":
            t = r["targets"][0]
            typer.echo(f"→ amu map --symbol {t['path']}#{t['symbol']} --change {r['change_class']}")
            try:
                render.render_map(_do_map(repo, None, f"{t['path']}#{t['symbol']}", 2, r["change_class"]))
            except typer.Exit:
                pass
        elif assistant:
            hint = f" (router: {r['status']}{', ambiguous ' + str(r.get('ambiguous')) if r.get('ambiguous') else ''})"
            assistant.ask(line + hint)
            typer.echo("")
        else:
            typer.echo(f"router: {r['status']} — name the symbol exactly as `entire graph search` reports it" + (f" (ambiguous: {r.get('ambiguous')})" if r.get("ambiguous") else ""))
            brand.err_console().print("[conf.unknown]○ model off[/] — free-text questions need a model: type [brand]/key add[/] to connect one (Anthropic, Ollama, OpenRouter, …); slash commands and change requests work without it")


if __name__ == "__main__":
    app()
