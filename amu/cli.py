"""amu — Anti-Messup (TWC Thugs). Typer entrypoint, also installed as `entire-amu` so `entire amu …` dispatches here.

Exit codes: 0 ok · 1 blocking violation / red · 2 stale contract or map · 3 tooling missing.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import typer

from amu import __version__, brand, entire, memory, render, router, state
from amu import docs as docsmod
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
REPO_OPT = typer.Option(".", "--repo", help="repository path")


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
        _repl()


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
         "anthropic_key_present": bool(os.environ.get("ANTHROPIC_API_KEY")), "unparsed": state.config(repo).get("unparsed", []),
         "install": None if ok else entire.INSTALL_HINT}
    _out(d, json_output)
    if not json_output:
        typer.echo(f"entire {d['entire']} · graph {d['graph']} · model key {'present' if d['anthropic_key_present'] else 'absent (manual mode)'} · unparsed {len(d['unparsed'])}")
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
    impacts = {n: entire.impact_json(repo, n, depth, file=(root_file if root_file != "?" else None)) for n in names}
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


def _repl(repo: str = "."):
    brand.banner(__version__, state.repo_name(repo), f"{'enabled' if entire.available() else 'missing'} · graph {entire.graph_version()}")
    lookup = _lookup_factory(repo)
    while True:
        try:
            line = input(brand.PROMPT)
        except (EOFError, KeyboardInterrupt):
            typer.echo("")
            return
        if not line.strip():
            continue
        r = router.route(line, lookup)
        if r["status"] == "command":
            arg = r.get("arg", "")
            cmds = {"map": lambda: _do_map(repo, arg, None, 2, "signature") and render.render_map(state.read_json("map.json", repo)),
                    "plan": lambda: plan(targets="", approve=False, symbol=None, repo=repo, json_output=False),
                    "approve": lambda: plan(targets="", approve=True, symbol=None, repo=repo, json_output=False),
                    "check": lambda: check(phase=int(arg or 1), base_ref=None, head_ref="HEAD", frozen="", scope="", removals="", strict=False, no_tests=False, repo=repo, json_output=False),
                    "done": lambda: done(publish=False, repo=repo, json_output=False),
                    "docs": lambda: docs_cmd(mode=None, apply=None, repo=repo, json_output=False),
                    "verify": lambda: verify(node=arg, attempt_fallback=False, repo=repo, json_output=False),
                    "skills": lambda: skills_list(repo=repo, json_output=False),
                    "why": lambda: typer.echo(json.dumps(next((n for n in state.read_json("map.json", repo, default={"nodes": []})["nodes"] if n["id"] == arg), "no such node"), indent=2)),
                    "feature": lambda: typer.echo(json.dumps(state.read_json("feature_map.json", repo, default={}).get(arg, "unknown feature"))),
                    "help": lambda: typer.echo("/map <file> /plan /approve /check N /done /docs /verify nX /why nX /feature X /skills — or describe the change in words")}
            try:
                cmds.get(r["intent"], cmds["help"])()
            except typer.Exit:
                pass
            continue
        if r["status"] == "ok":
            t = r["targets"][0]
            typer.echo(f"→ amu map --symbol {t['path']}#{t['symbol']} --change {r['change_class']}")
            try:
                m = _do_map(repo, None, f"{t['path']}#{t['symbol']}", 2, r["change_class"])
                render.render_map(m)
            except typer.Exit:
                pass
        else:
            typer.echo(f"router: {r['status']} — name the symbol exactly as `entire graph search` reports it" + (f" (ambiguous: {r.get('ambiguous')})" if r.get("ambiguous") else ""))


if __name__ == "__main__":
    app()
