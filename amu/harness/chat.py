"""Interactive assistant for the REPL: a tool-using loop over read-only graph tools and amu commands.
amu never writes source code, so the assistant has no write tool. Facts come from `entire graph` output the
tools return; the model can widen a map or ask, never enlarge a contract or promote confidence."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Callable

from amu import entire, graphview, state
from amu.classify import build_map
from amu.harness import model as modelmod
from amu.harness import providers
from amu.harness.prompts import CLOSING, PREAMBLE
from amu.harness.roles import ToolNotGranted, make_role

ASSISTANT_SYSTEM = PREAMBLE.replace(
    'You answer with exactly one JSON object of the shape {"decision": str, "confidence": float, "escalate": bool, "evidence": [str], "next": str}.',
    "You are the interactive assistant (role: assistant). Answer in short plain prose with counts and buckets; cite files as path:line "
    "and symbols verbatim as the tools return them. Prefer one tool call that answers the question over several. When the user "
    "describes a change, run amu_map and then propose the exact next amu command.") + "\n\n" + CLOSING


def _cli(repo: str, *args: str) -> str:
    r = subprocess.run([sys.executable, "-I", "-m", "amu.cli", *args, "--json", "--repo", repo], capture_output=True, text=True, timeout=600)
    return r.stdout if r.stdout.strip() else json.dumps({"error": r.stderr[-800:], "exit": r.returncode})


def tool_definitions() -> list[dict]:
    """Stable order (cache-friendly). All tools are read-only against the repo."""
    s = lambda **props: {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}  # noqa: E731
    return [
        {"name": "graph_search", "description": "Find code for a plain-language question via `entire graph search`; returns ranked hits with the signals that ranked them. Use this before naming any symbol.", "input_schema": s(query={"type": "string"}), "strict": True},
        {"name": "graph_def", "description": "What a name IS: declaration, signature, and method surface via `entire graph def`.", "input_schema": s(symbol={"type": "string"}), "strict": True},
        {"name": "amu_map", "description": "Blast map for `path#symbol` (or a file path) under a change class: sound/guessed/unknown nodes with reason + verify.", "input_schema": s(target={"type": "string"}, change={"type": "string", "enum": ["signature", "remove", "rename", "move", "body"]}), "strict": True},
        {"name": "amu_graph", "description": "Relation graph payload for `path#symbol` from `entire graph impact` (callers, callees, type consumers, data flows, co-change).", "input_schema": s(symbol={"type": "string"}), "strict": True},
        {"name": "amu_where", "description": "Definition site, feature, and whether a symbol is frozen in the current contract.", "input_schema": s(symbol={"type": "string"}), "strict": True},
        {"name": "amu_state", "description": "Current map, contract phases, node states, and open questions from .amu/.", "input_schema": s(), "strict": True},
        {"name": "read_lines", "description": "Read up to 120 lines of a repo file (read-only). Anything read here is heuristic, never sound.", "input_schema": s(path={"type": "string"}, start={"type": "integer"}, end={"type": "integer"}), "strict": True},
        {"name": "answer_unknown", "description": "Record the human's answer to an unknown node so memory stops re-asking. Never promotes confidence.", "input_schema": s(node={"type": "string"}, answer={"type": "string"}), "strict": True},
    ]


class Assistant:
    def __init__(self, repo: str, out: Callable[[str], None] | None = None, stream: bool = True, client=None):
        self.repo = repo
        self.out = out or (lambda t: print(t, end="", flush=True))
        self.stream = stream
        self.role = make_role("assistant")
        self.cred = modelmod.credential()
        self.model = modelmod.model_id(repo)
        self.effort = state.config(repo).get("effort", "medium")
        self.messages: list[dict] = []
        self._client = client

    # ----- tools ---------------------------------------------------------
    def _tool(self, name: str, inp: dict) -> str:
        fn = {
            "graph_search": lambda: json.dumps({k: v for k, v in entire.search(self.repo, inp["query"]).items() if k in ("results", "verify_command", "coverage_note", "error")}, default=str)[:12000],
            "graph_def": lambda: entire.definition(self.repo, inp["symbol"].split("#")[-1])[:6000],
            "amu_map": lambda: self._map(inp["target"], inp["change"]),
            "amu_graph": lambda: json.dumps(graphview.payload_from_impact(inp["symbol"].split("#")[-1], entire.impact_json(self.repo, inp["symbol"].split("#")[-1], 2, file=(inp["symbol"].rpartition("#")[0] or None))))[:12000],
            "amu_where": lambda: _cli(self.repo, "where", inp["symbol"]),
            "amu_state": lambda: json.dumps({"map": {k: v for k, v in (state.read_json("map.json", self.repo) or {}).items() if k != "nodes"},
                                             "nodes": (state.read_json("map.json", self.repo) or {}).get("nodes", [])[:40],
                                             "contract": state.read_json("contract.json", self.repo), "state": state.read_json("state.json", self.repo)})[:12000],
            "read_lines": lambda: self._read(inp["path"], inp["start"], inp["end"]),
            "answer_unknown": lambda: self._answer(inp["node"], inp["answer"]),
        }.get(name)
        if fn is None:
            raise ToolNotGranted(name)
        return self.role.call(f"chat.{name}", fn)

    def _map(self, target: str, change: str) -> str:
        path, _, name = target.rpartition("#")
        if name:
            imp = {name: entire.impact_json(self.repo, name, 2, file=path or None)}
            root = path or (imp[name].get("focus") or {}).get("file_path") or "?"
            names = [name]
        else:
            root = target
            names = [s.get("qualified_name") or s["name"] for s in entire.symbols(self.repo) if s.get("file_path") == target and s.get("kind") in ("function", "class") and not s.get("name", "_").startswith("_")]
            imp = {n: entire.impact_json(self.repo, n, 2, file=target) for n in names}
        m = build_map(root, names, imp, change, state.read_json("feature_map.json", self.repo, default={}), {}, 2, state.config(self.repo).get("test_cmd", "pytest"))
        m["map_hash"] = state.stable_hash([m["root"], [(n["path"], n["symbol"], n["confidence"]) for n in m["nodes"]], change])
        state.write_json("map.json", m, self.repo)
        return json.dumps({**m, "nodes": m["nodes"][:60]})[:14000]

    def _read(self, path: str, start: int, end: int) -> str:
        p = (Path(self.repo) / path).resolve()
        if not str(p).startswith(str(Path(self.repo).resolve())) or not p.is_file():
            return json.dumps({"error": "outside the repo or not a file"})
        lines = p.read_text(errors="ignore").splitlines()
        start, end = max(1, start), min(len(lines), end, start + 119)
        return "\n".join(f"{i}: {ln}" for i, ln in enumerate(lines[start - 1:end], start)) + "\n(heuristic: read from source, not from the graph)"

    def _answer(self, node: str, answer: str) -> str:
        from amu.memory import SECRET_RX
        if SECRET_RX.search(answer):
            return json.dumps({"error": "answer looks like a secret; not recorded"})
        run = state.amu_dir(self.repo) / "run"
        run.mkdir(exist_ok=True)
        n = len(list(run.glob("human-*.json"))) + 1
        m = state.read_json("map.json", self.repo, default={"nodes": []})
        q = next((f"{x['path']}: {x['reason']}" for x in m["nodes"] if x["id"] == node), node)
        state.write_json(f"run/human-{n}.json", {"decision": "answered", "confidence": 0.0, "escalate": False, "evidence": [node], "next": "amu memory refresh",
                                               "task": "chat", "answers": [{"question": q, "answer": answer, "who": "human", "date": state.now_iso()}]}, self.repo)
        return json.dumps({"recorded": node, "note": "confidence unchanged; memory will carry the answer"})

    # ----- loop ----------------------------------------------------------
    def _context(self) -> str:
        mem = state.read_json("memory.json", self.repo, default={"entries": []})["entries"][:30]
        m = state.read_json("map.json", self.repo)
        c = state.read_json("contract.json", self.repo)
        return json.dumps({"repo": state.repo_name(self.repo), "memory": [f"[{e['kind']}] {e['text']}" for e in mem],
                           "current_map": {k: m[k] for k in ("root", "resolution", "next")} if m else None,
                           "contract": {"targets": c["targets"], "phases": [(p["n"], p["kind"], len(p["files"])) for p in c["phases"]]} if c else None})

    def _call(self, client, tools):
        kwargs = dict(model=self.model, max_tokens=16000, system=[{"type": "text", "text": ASSISTANT_SYSTEM, "cache_control": {"type": "ephemeral"}}],
                      tools=tools, messages=self.messages, **modelmod.request_kwargs(self.cred, self.effort))
        if not self.stream or not hasattr(client.messages, "stream"):
            msg = client.messages.create(**kwargs)
            if self.stream:  # non-streaming provider: print the text once
                self.out("".join(getattr(b, "text", "") for b in msg.content if b.type == "text"))
            return msg
        with client.messages.stream(**kwargs) as s:
            for ev in s:
                if ev.type == "content_block_delta" and getattr(ev.delta, "type", "") == "text_delta":
                    self.out(ev.delta.text)
            return s.get_final_message()

    def _fail(self, text: str) -> str:
        self.messages = [m for m in self.messages if m["role"] != "user" or not isinstance(m["content"], str) or not m["content"].startswith("<context>")] and self.messages[:-1]
        self.out(f"✗ {text}\n")
        return text

    def ask(self, text: str, max_turns: int = 8) -> str:
        if not modelmod.available():
            return "manual mode: no credential — run `amu key set [--provider …]` (or export ANTHROPIC_API_KEY / OPENAI_BASE_URL) to make the session interactive"
        client = self._client or modelmod.client()
        if not self.messages:
            text = f"<context>{self._context()}</context>\n\n{text}"
        self.messages.append({"role": "user", "content": text})
        tools = tool_definitions()
        final = ""
        import anthropic
        for _ in range(max_turns):
            try:
                msg = self._call(client, tools)
            except anthropic.AuthenticationError:
                return self._fail("credential rejected (401) — the key is wrong or revoked: type /key add to replace it")
            except (anthropic.APIStatusError, anthropic.APIConnectionError, providers.ProviderError) as exc:
                msg = str(exc)[:240]
                hint = " — the key was rejected: /key add to replace it" if "401" in msg else (" — check the model id: /key add" if "404" in msg or "400" in msg else " — endpoint unreachable?")
                return self._fail(f"model call failed: {type(exc).__name__}: {msg}{hint}")
            self.messages.append({"role": "assistant", "content": msg.content})
            text_out = "".join(b.text for b in msg.content if b.type == "text")
            final = text_out or final
            if msg.stop_reason == "refusal":
                return final or "the model declined this request"
            if msg.stop_reason != "tool_use":
                break
            results = []
            for b in msg.content:
                if b.type != "tool_use":
                    continue
                self.out(f"\n  ⚙ {b.name} {json.dumps(b.input)[:100]}\n")
                try:
                    content = self._tool(b.name, b.input)
                    results.append({"type": "tool_result", "tool_use_id": b.id, "content": content})
                except ToolNotGranted as exc:
                    results.append({"type": "tool_result", "tool_use_id": b.id, "content": f"tool not granted: {exc}", "is_error": True})
                except Exception as exc:  # noqa: BLE001 — a failed tool is reported to the model, never crashes the REPL
                    results.append({"type": "tool_result", "tool_use_id": b.id, "content": f"{type(exc).__name__}: {exc}", "is_error": True})
            self.messages.append({"role": "user", "content": results})
        return final
