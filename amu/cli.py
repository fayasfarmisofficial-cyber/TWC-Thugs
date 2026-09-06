"""
amu/cli.py
----------
Typer entrypoint for the Anti-Messup Agent.

Commands:
  amu brief  – Pre-edit impact brief (will_break / might_break / unknown)
  amu plan   – 4-phase topological refactoring plan
  amu check  – Contract guardrail against entire graph diff output
"""

import json

import typer

from amu.classify import classify_consumers
from amu.contract import run_contract_check
from amu.graph import capabilities, impact
from amu.plan import plan_from_buckets, plan_to_json

app = typer.Typer(
    help="Anti-Messup Agent (amu) – Scope guardrail for AI code edits",
    no_args_is_help=True,
)


# ---------------------------------------------------------------------------
# amu brief
# ---------------------------------------------------------------------------

@app.command()
def brief(
    symbol: str = typer.Option(..., help="Target symbol to analyze"),
    depth: int = typer.Option(2, help="Graph traversal depth"),
    repo: str = typer.Option(".", help="Repository path"),
    json_output: bool = typer.Option(False, "--json", help="Output raw JSON for agent consumption"),
):
    """Generates a pre-edit impact brief separating confirmed and unknown graph evidence."""
    typer.echo(f"Analyzing blast radius for symbol: {symbol} (depth: {depth})...")

    raw_output = impact(symbol, depth, repo)
    caps = capabilities(repo)
    buckets = classify_consumers(symbol, raw_output, caps)

    payload = {"symbol": symbol, "buckets": buckets}

    if json_output:
        typer.echo(json.dumps(payload, indent=2))
    else:
        typer.echo(f"\n[WILL BREAK]:              {len(buckets['will_break'])} item(s)")
        typer.echo(f"[MIGHT BREAK]:             {len(buckets['might_break'])} item(s)")
        typer.echo(f"[UNKNOWN / PARTIAL]:       {buckets['unknown']}")


# ---------------------------------------------------------------------------
# amu plan
# ---------------------------------------------------------------------------

@app.command()
def plan(
    symbol: str = typer.Option(..., help="Target symbol being refactored"),
    depth: int = typer.Option(2, help="Graph traversal depth"),
    repo: str = typer.Option(".", help="Repository path"),
    json_output: bool = typer.Option(False, "--json", help="Output raw JSON"),
):
    """
    Generates a 4-phase topological refactoring plan:
    Additive -> Migration -> Interior -> Removal.
    """
    typer.echo(f"Building refactoring plan for: {symbol}...")

    raw_output = impact(symbol, depth, repo)
    caps = capabilities(repo)
    buckets = classify_consumers(symbol, raw_output, caps)
    refactor_plan = plan_from_buckets(symbol, buckets)

    if json_output:
        typer.echo(plan_to_json(refactor_plan))
    else:
        typer.echo(refactor_plan.pretty())


# ---------------------------------------------------------------------------
# amu check
# ---------------------------------------------------------------------------

@app.command()
def check(
    base_ref: str = typer.Option(..., help="Base git ref (e.g. main)"),
    head_ref: str = typer.Option(..., help="Head git ref (e.g. HEAD or feature branch)"),
    repo: str = typer.Option(".", help="Repository path"),
    frozen: str = typer.Option("", help="Comma-separated frozen symbol names"),
    scope: str = typer.Option("", help="Comma-separated in-scope symbol names (empty = all)"),
    removals: str = typer.Option("", help="Comma-separated declared-removal symbol names"),
    json_output: bool = typer.Option(False, "--json", help="Output raw JSON"),
    strict: bool = typer.Option(False, "--strict", help="Treat CLI unavailability as a hard failure"),
):
    """
    Runs contract guardrail checks against entire graph diff output.

    Blocks (exit 1) on FROZEN_SIGNATURE, OUT_OF_SCOPE, or UNDECLARED_REMOVAL violations.
    """
    frozen_set   = {s.strip() for s in frozen.split(",")   if s.strip()}
    scope_set    = {s.strip() for s in scope.split(",")    if s.strip()}
    removals_set = {s.strip() for s in removals.split(",") if s.strip()}

    result = run_contract_check(
        repo=repo,
        base_ref=base_ref,
        head_ref=head_ref,
        frozen_symbols=frozen_set,
        scope_symbols=scope_set,
        declared_removals=removals_set,
        allow_cli_unavailable=not strict,
    )

    if json_output:
        typer.echo(json.dumps(result.to_dict(), indent=2))
    else:
        typer.echo(result.pretty())

    if not result.passed:
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app()
