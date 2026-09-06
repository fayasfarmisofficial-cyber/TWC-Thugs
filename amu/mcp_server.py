"""TWC Thugs · amu MCP server (stdio): thin wrappers that shell out to the CLI with --json."""

from __future__ import annotations

import json
import subprocess
import sys


def _cli(*args: str) -> str:
    r = subprocess.run([sys.executable, "-m", "amu.cli", *args, "--json"], capture_output=True, text=True)
    return r.stdout or json.dumps({"error": r.stderr[-500:], "exit": r.returncode})


TOOLS = {
    "amu_map": (lambda file, change="signature": _cli("map", "--file", file, "--change", change), "Blast map for a file (TWC Thugs · amu)"),
    "amu_plan": (lambda targets, approve=False: _cli("plan", "--targets", targets, *(["--approve"] if approve else [])), "4-phase plan; approve writes the contract"),
    "amu_check": (lambda phase=1: _cli("check", "--phase", str(phase)), "Contract check for a phase"),
    "amu_done": (lambda: _cli("done"), "sync → sweep → docs → memory → report"),
    "amu_verify": (lambda node: _cli("verify", "--node", node), "Run the verify path of a node"),
}


def main() -> None:
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError:
        print("pip install mcp", file=sys.stderr)
        raise SystemExit(3)
    server = FastMCP("TWC Thugs · amu")
    for name, (fn, desc) in TOOLS.items():
        server.tool(name=name, description=desc)(fn)
    server.run()


if __name__ == "__main__":
    main()
