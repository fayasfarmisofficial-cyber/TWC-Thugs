"""Roles with fixed tool sets. A role literally cannot call a tool outside its set."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


class ToolNotGranted(PermissionError):
    pass


class WriteRefused(PermissionError):
    pass


TOOL_MATRIX = {
    "router": {"graph.search", "graph.def", "memory.read"},
    "mapper": {"graph.impact", "graph.neighbors", "graph.def", "memory.read"},
    "planner": {"map.read", "memory.read", "plan.write"},
    "builder": {"map.read", "contract.read", "skills.read", "files.write_allowed", "tests.run"},
    "checker": {"check.read", "graph.diff", "tests.run", "memory.read"},
    "sweeper": {"graph.diff", "graph.impact", "contract.read", "memory.read"},
    "doc_agent": {"graph.diff", "docs.read", "docs.draft"},
    "memory": {"state.read", "contract.read", "run.read", "memory.write"},
}


@dataclass(frozen=True)
class Role:
    name: str
    tools: frozenset = field(default_factory=frozenset)
    allowed_files: frozenset = field(default_factory=frozenset)

    def call(self, tool: str, fn, *args, **kwargs):
        if tool not in self.tools:
            raise ToolNotGranted(f"role {self.name} has no tool {tool}")
        return fn(*args, **kwargs)

    def write_path(self, path: str, content: str, repo: str = ".") -> Path:
        if "files.write_allowed" not in self.tools:
            raise ToolNotGranted(f"role {self.name} cannot write files")
        if path not in self.allowed_files:
            raise WriteRefused(f"{path} is outside the contract's allowed_files")
        p = Path(repo) / path
        p.write_text(content)
        return p


def make_role(name: str, allowed_files: set | None = None) -> Role:
    return Role(name, frozenset(TOOL_MATRIX[name]), frozenset(allowed_files or ()))


class Budget:
    """Checker budget: max 2 retries, max 2 widenings, 1 sweep; the 3rd retry escalates."""

    def __init__(self, retries: int = 2, widenings: int = 2, sweeps: int = 1):
        self.max = {"retry": retries, "widen": widenings, "sweep": sweeps}
        self.used = {"retry": 0, "widen": 0, "sweep": 0}

    def spend(self, kind: str) -> bool:
        if self.used[kind] >= self.max[kind]:
            return False
        self.used[kind] += 1
        return True

    def as_str(self) -> str:
        return " ".join(f"{k} {v}/{self.max[k]}" for k, v in self.used.items())


def checker_decide(check_result: dict, budget: Budget) -> dict:
    """Deterministic checker: blocking violations cannot be downgraded; budget exhaustion escalates."""
    blocking = [v for v in check_result.get("violations", []) if v["severity"] == "ERROR"]
    if not blocking:
        return {"decision": "proceed", "confidence": 1.0, "escalate": False, "evidence": [], "next": "amu check --phase next"}
    kinds = {v["kind"] for v in blocking}
    if "OUT_OF_SCOPE" in kinds and budget.spend("widen"):
        return {"decision": "widen", "confidence": 0.6, "escalate": False, "evidence": [v["symbol"] for v in blocking], "next": "amu map --depth 2 then amu plan --approve"}
    if budget.spend("retry"):
        return {"decision": "retry", "confidence": 0.5, "escalate": False, "evidence": [v["symbol"] for v in blocking], "next": "revert the drifted file and re-run amu check"}
    return {"decision": "escalate", "confidence": 0.9, "escalate": True, "evidence": [v["symbol"] for v in blocking],
            "next": "human: the same blocking violation persisted after the retry budget"}
