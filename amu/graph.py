import subprocess
import json

def impact(symbol: str, depth: int = 2, repo: str = ".") -> str:
    """Runs entire graph impact and captures output."""
    cmd = ["entire", "graph", "impact", "--symbol", symbol, "--depth", str(depth), "--repo", repo, "--profile", "full"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return f"Error running impact: {result.stderr}"
    return result.stdout

def capabilities(repo: str = ".") -> dict:
    """Fetches graph parser capabilities to feed the unknown bucket (Curveball requirement)."""
    cmd = ["entire", "graph", "capabilities", "--json", "--repo", repo]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0 and result.stdout.strip():
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            pass
    return {"out_of_coverage": [], "unresolved_patterns": ["dynamic_dispatch", "reflection"]}
