import json
import subprocess
import sys
from types import SimpleNamespace as NS

import pytest

from amu import keys
from amu.harness import chat, model, providers


def test_set_credential_validation():
    with pytest.raises(ValueError):
        keys.set_credential("vertex")            # needs project + region
    with pytest.raises(ValueError):
        keys.set_credential("openai-compatible")  # needs base_url + model
    with pytest.raises(ValueError):
        keys.set_credential("nope")
    keys.set_credential("ollama", model="qwen2.5-coder")
    c = keys.credential()
    assert c["family"] == "openai" and c["base_url"] == "http://localhost:11434/v1" and c["model"] == "qwen2.5-coder" and keys.available()


def test_env_openai_base_url_selects_openai_family(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:8000/v1")
    monkeypatch.setenv("AMU_MODEL", "local-model")
    c = keys.credential()
    assert c["family"] == "openai" and c["source"] == "env" and model.model_id() == "local-model"
    assert model.request_kwargs(c) == {}  # no Anthropic-only params for other families


def test_anthropic_env_keeps_effort(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api03-x-000000000000")
    assert model.request_kwargs(keys.credential(), "high") == {"output_config": {"effort": "high"}}


def test_openai_message_and_tool_mapping():
    tools = chat.tool_definitions()[:1]
    ot = providers.to_openai_tools(tools)
    assert ot[0]["type"] == "function" and ot[0]["function"]["name"] == "graph_search"
    msgs = [{"role": "user", "content": "hi"},
            {"role": "assistant", "content": [NS(type="text", text="calling"), NS(type="tool_use", id="c1", name="graph_search", input={"query": "q"})]},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "c1", "content": "{}"}]}]
    om = providers.to_openai_messages([{"type": "text", "text": "SYS"}], msgs)
    assert om[0] == {"role": "system", "content": "SYS"} and om[2]["tool_calls"][0]["function"]["name"] == "graph_search"
    assert om[3] == {"role": "tool", "tool_call_id": "c1", "content": "{}"}


def test_openai_response_mapping():
    r = providers.from_openai_response({"choices": [{"finish_reason": "tool_calls", "message": {"content": None, "tool_calls": [
        {"id": "c9", "function": {"name": "graph_def", "arguments": "{\"symbol\": \"x\"}"}}]}}]})
    assert r.stop_reason == "tool_use" and r.content[0].type == "tool_use" and r.content[0].input == {"symbol": "x"}
    assert providers.from_openai_response({"choices": [{"finish_reason": "stop", "message": {"content": "done"}}]}).stop_reason == "end_turn"


def test_chat_loop_over_openai_compatible_adapter(fake_entire, tmp_path, monkeypatch):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path)
    keys.set_credential("openai-compatible", base_url="http://fake/v1", model="m")
    script = [{"choices": [{"finish_reason": "tool_calls", "message": {"content": None, "tool_calls": [{"id": "c1", "function": {"name": "graph_def", "arguments": "{\"symbol\": \"classify_consumers\"}"}}]}}]},
              {"choices": [{"finish_reason": "stop", "message": {"content": "classify_consumers is a function in amu/classify.py"}}]}]
    seen = []

    def fake_post(url, body, headers, timeout=600):
        seen.append((url, body))
        return script.pop(0)
    monkeypatch.setattr(providers, "_post_json", fake_post)
    a = chat.Assistant(str(tmp_path), out=lambda t: None, stream=True)   # stream requested, adapter has none → falls back
    ans = a.ask("what is classify_consumers?")
    assert "amu/classify.py" in ans and seen[0][0] == "http://fake/v1/chat/completions"
    assert seen[1][1]["messages"][-1]["role"] == "tool" and "output_config" not in seen[0][1]


def test_provider_error_is_reported_not_raised(fake_entire, tmp_path, monkeypatch):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path)
    keys.set_credential("ollama", model="m")
    monkeypatch.setattr(providers, "_post_json", lambda *a, **k: (_ for _ in ()).throw(providers.ProviderError("http://localhost:11434/v1 unreachable")))
    a = chat.Assistant(str(tmp_path), out=lambda t: None, stream=False)
    assert "unreachable" in a.ask("x")


def test_cli_key_set_provider_and_status():
    r = subprocess.run([sys.executable, "-m", "amu.cli", "key", "set", "--provider", "ollama", "--model", "llama3.1", "--json"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    s = json.loads(subprocess.run([sys.executable, "-m", "amu.cli", "key", "status", "--json"], capture_output=True, text=True).stdout)
    assert s["provider"] == "ollama" and s["base_url"].endswith("11434/v1") and "openrouter" in s["providers"]
