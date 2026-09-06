"""S1→S4 loop with budgets. Every handoff is one JSON object written to .amu/run/<role>-<n>.json; nothing passes by prose."""

from __future__ import annotations

from pathlib import Path

from amu import state
from amu.harness import model
from amu.harness.prompts import system_prompt
from amu.harness.roles import Budget, checker_decide, make_role


class Orchestrator:
    def __init__(self, repo: str = ".", task: str = "t1"):
        self.repo = repo
        self.task = task
        self.n = 0
        self.budget = Budget()
        self.memory = state.read_json("memory.json", repo, default={"entries": []})
        (state.amu_dir(repo) / "run").mkdir(exist_ok=True)

    def handoff(self, role: str, payload: dict) -> dict:
        self.n += 1
        payload = {**{"decision": "", "confidence": 0.0, "escalate": False, "evidence": [], "next": ""}, **payload, "task": self.task, "role": role}
        state.validate("handoff", payload)
        state.write_json(f"run/{role}-{self.n}.json", payload, self.repo)
        return payload

    def answered(self) -> dict[str, str]:
        return {e["text"].split(" → ")[0]: e["text"] for e in self.memory.get("entries", []) if e["kind"] == "answered_unknown"}

    def plan_decision(self, amu_map: dict) -> dict:
        res = amu_map["resolution"]
        hot = [e["text"] for e in self.memory.get("entries", []) if e["kind"] == "hot_spot"]
        if res["unknown"] and not self.answered():
            d = {"decision": "ask", "confidence": 0.5, "escalate": True, "evidence": [n["id"] for n in amu_map["nodes"] if n["confidence"] == "unknown"],
                 "next": "answer the unknown nodes (amu verify --node nX) or approve with them open"}
        else:
            d = {"decision": "proceed", "confidence": 0.8 if not hot else 0.7, "escalate": False,
                 "evidence": [f"sound {res['sound']}", f"guessed {res['guessed']}"] + hot[:3], "next": amu_map["next"]}
        if model.available():
            m = model.ask_json(system_prompt("planner"), state.json.dumps({"map": amu_map, "hot_spots": hot}))
            if m.get("decision") in ("proceed", "narrow", "ask"):
                d = m
        return self.handoff("planner", d)

    def phase_brief(self, contract: dict, phase: int, amu_map: dict) -> dict:
        p = contract["phases"][phase - 1]
        role = make_role("builder", set(p["files"]))
        nodes = [n for n in amu_map["nodes"] if n["id"] in p["nodes"]]
        brief = {"decision": "brief", "confidence": 1.0, "escalate": not model.available(), "evidence": p["nodes"],
                 "next": p["verify"], "phase": p, "nodes": nodes, "frozen_signatures": contract["frozen_signatures"],
                 "allowed_files": sorted(role.allowed_files), "mode": "model" if model.available() else "manual",
                 "skills": [Path(s).parent.name for s in (state.amu_dir(self.repo) / "skills").glob("*/SKILL.md")]}
        return self.handoff("builder", brief)

    def brief_markdown(self, brief: dict) -> str:
        p = brief["phase"]
        lines = [f"## amu phase {p['n']} · {p['kind']} (TWC Thugs)", f"reason: {p['reason']}", f"allowed files: {', '.join(brief['allowed_files']) or '—'}",
                 f"frozen signatures: {', '.join(brief['frozen_signatures']) or '—'}", "nodes:"]
        lines += [f"- {n['id']} {n['path']}#{n['symbol']} · {n['confidence']} · {n['risk']} · verify: {n['verify']}" for n in brief["nodes"]]
        lines.append(f"when done: `{p['verify']}`")
        return "\n".join(lines)

    def on_check(self, check_result: dict) -> dict:
        return self.handoff("checker", checker_decide(check_result, self.budget))
