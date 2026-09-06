"""Compatibility shim over amu.entire (v0 API kept for classify_consumers + legacy tests)."""

from amu import entire

_FALLBACK_CAPS = {"out_of_coverage": [], "unresolved_patterns": ["dynamic_dispatch", "reflection"]}


def impact(symbol: str, depth: int = 2, repo: str = ".") -> str:
    """Runs entire graph impact and captures output. Never raises; returns an error string on failure."""
    return entire.impact_text(repo, symbol, depth)


def capabilities(repo: str = ".") -> dict:
    """Graph parser capabilities feeding the unknown bucket; conservative fallback dict when the CLI is absent."""
    caps = entire.capabilities(repo)
    if "error" in caps:
        return dict(_FALLBACK_CAPS)
    return caps
