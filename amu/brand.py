"""TWC Thugs branding. Everything here goes to stderr and is never emitted under --json."""

from __future__ import annotations

import os
import sys

NAME = "TWC Thugs"
TAGLINE = "amu · Anti-Messup · built on the Entire CLI"
EPILOG = "Built by TWC Thugs for the Bengaluru Tech Week Buildathon 2026"
PROMPT = "twc-thugs ❯ "

# pyfiglet 'slant' rendering of "TWC THUGS", pasted so pyfiglet is not a runtime dependency.
WORDMARK = r"""
  ______ _       __ ______   ______ __  __ __  __ ______ _____
 /_  __/| |     / // ____/  /_  __// / / // / / // ____// ___/
  / /   | | /| / // /        / /  / /_/ // / / // / __  \__ \
 / /    | |/ |/ // /___     / /  / __  // /_/ // /_/ / ___/ /
/_/     |__/|__/ \____/    /_/  /_/ /_/ \____/ \____/ /____/
""".strip("\n")


def color_enabled() -> bool:
    return not os.environ.get("NO_COLOR") and sys.stderr.isatty()


def _magenta(text: str) -> str:
    return f"\033[1;35m{text}\033[0m" if color_enabled() else text


def header(command: str, repo: str, json_mode: bool = False) -> None:
    """One-line header printed before every non-JSON command."""
    if json_mode:
        return
    print(_magenta(f"{NAME} · amu {command} · {repo}"), file=sys.stderr)


def banner(version: str, repo: str, entire_status: str, json_mode: bool = False) -> None:
    if json_mode:
        return
    lines = [WORDMARK, "", f"  {TAGLINE}", f"  v{version} · {repo} · entire {entire_status}", ""]
    print(_magenta("\n".join(lines)), file=sys.stderr)


def status_line(phase: str, spend: str, open_questions: int) -> str:
    return f"{NAME} · phase {phase} · spend {spend} · open questions {open_questions}"
