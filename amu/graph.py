import json
import subprocess


def impact(symbol: str, depth: int = 2, repo: str = ".") -> str:
    """Runs entire graph impact and captures output.

    Returns an error string (never raises) when the CLI is absent or args are invalid,
    so downstream consumers (classify_consumers, tests) always receive a safe str.
    """
    cmd = ["entire", "graph", "impact", "--symbol", symbol, "--depth", str(depth), "--repo", repo, "--profile", "full"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError:
        return "Error running impact: entire CLI not found (not installed or not on PATH)"
    except (ValueError, OSError) as exc:
        return f"Error running impact: {exc}"
    if result.returncode != 0:
        return f"Error running impact: {result.stderr}"
    return result.stdout

def capabilities(repo: str = ".") -> dict:
    """Fetches graph parser capabilities to feed the unknown bucket (Curveball requirement).

    Returns a conservative fallback dict (never raises) when the CLI is absent.
    """
    cmd = ["entire", "graph", "capabilities", "--json", "--repo", repo]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
    except (FileNotFoundError, OSError):
        return {"out_of_coverage": [], "unresolved_patterns": ["dynamic_dispatch", "reflection"]}
    if result.returncode == 0 and result.stdout.strip():
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            pass
    return {"out_of_coverage": [], "unresolved_patterns": ["dynamic_dispatch", "reflection"]}
