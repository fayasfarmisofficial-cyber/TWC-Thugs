import json
import subprocess
from types import SimpleNamespace as NS

import pytest

from amu import keys, state
from amu.harness import chat
from amu.harness.roles import ToolNotGranted, make_role


class _Msgs:
    """Scripted fake of client.messages: first turn calls a tool, second turn answers."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def create(self, **kw):
        self.calls.append(kw)
        return self.script.pop(0)


def _text(t, stop="end_turn"):
    return NS(content=[NS(type="text", text=t)], stop_reason=stop)


def _tool(name, inp, tid="tu1"):
    return NS(content=[NS(type="tool_use", id=tid, name=name, input=inp)], stop_reason="tool_use")


def _repo(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path)
    return str(tmp_path)


def test_manual_mode_without_credential(tmp_path):
    a = chat.Assistant(_repo(tmp_path), stream=False, client=NS(messages=_Msgs([])))
    assert "manual mode" in a.ask("hello") and a.messages == []


def test_tool_loop_executes_graph_search_and_returns_text(fake_entire, tmp_path):
    keys.set_key("sk-ant-api03-file-value-000000000000")
    msgs = _Msgs([_tool("graph_search", {"query": "classifier"}), _text("classify_consumers in amu/classify.py:3 has 30 callers.")])
    a = chat.Assistant(_repo(tmp_path), out=lambda t: None, stream=False, client=NS(messages=msgs))
    ans = a.ask("where is the classifier?")
    assert "classify_consumers" in ans
    result = a.messages[2]["content"][0]
    assert result["type"] == "tool_result" and "classify_consumers" in result["content"] and not result.get("is_error")
    assert msgs.calls[0]["model"] == "claude-opus-5" and msgs.calls[0]["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert [t["name"] for t in msgs.calls[0]["tools"]] == [t["name"] for t in chat.tool_definitions()]


def test_ungranted_tool_is_reported_not_crashed(fake_entire, tmp_path):
    keys.set_key("sk-ant-api03-file-value-000000000000")
    msgs = _Msgs([_tool("write_file", {"path": "x"}), _text("ok I cannot write.")])
    a = chat.Assistant(_repo(tmp_path), out=lambda t: None, stream=False, client=NS(messages=msgs))
    a.ask("edit the file")
    assert a.messages[2]["content"][0]["is_error"] is True and "not granted" in a.messages[2]["content"][0]["content"]


def test_assistant_role_has_no_write_tool():
    r = make_role("assistant")
    assert not any("write" in t for t in r.tools)
    with pytest.raises(ToolNotGranted):
        r.call("files.write_allowed", lambda: None)


def test_read_lines_stays_inside_repo(tmp_path):
    a = chat.Assistant(_repo(tmp_path), stream=False)
    (tmp_path / "f.py").write_text("a\nb\n")
    assert "heuristic" in a._read("f.py", 1, 2)
    assert "outside" in a._read("../../etc/passwd", 1, 2)


def test_answer_unknown_feeds_memory_and_rejects_secret(tmp_path):
    repo = _repo(tmp_path)
    state.write_json("map.json", {"nodes": [{"id": "n5", "path": "x.py", "reason": "dyn"}]}, repo)
    a = chat.Assistant(repo, stream=False)
    assert "recorded" in a._answer("n5", "internal only")
    assert "secret" in a._answer("n5", "key sk-ant-abc123456789")
    from amu import memory
    kinds = {e["kind"] for e in memory.collect(repo)}
    assert "answered_unknown" in kinds


def test_refusal_stop_reason_handled(fake_entire, tmp_path):
    keys.set_key("sk-ant-api03-file-value-000000000000")
    a = chat.Assistant(_repo(tmp_path), out=lambda t: None, stream=False, client=NS(messages=_Msgs([_text("", stop="refusal")])))
    assert "declined" in a.ask("x")


def test_cli_ask_manual_mode_json(tmp_path):
    import sys
    r = subprocess.run([sys.executable, "-m", "amu.cli", "ask", "hi", "--json"], cwd=_repo(tmp_path), capture_output=True, text=True)
    assert json.loads(r.stdout)["answer"].startswith("manual mode")
