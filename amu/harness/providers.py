"""Bring-your-own-provider clients. Anthropic-family providers use the official SDK clients; the OpenAI-compatible
adapter speaks /v1/chat/completions and presents the same `.messages.create(...)` surface the chat loop expects
(content blocks with .type text|tool_use, .stop_reason end_turn|tool_use)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from types import SimpleNamespace as NS


class ProviderError(RuntimeError):
    pass


def make_client(cred: dict):
    fam, prov = cred.get("family"), cred.get("provider")
    if fam == "openai":
        return OpenAICompatClient(cred["base_url"], cred.get("api_key"), cred.get("provider", "openai-compatible"))
    import anthropic
    if prov == "bedrock":
        return anthropic.AnthropicBedrockMantle(aws_region=cred["region"])
    if prov == "vertex":
        return anthropic.AnthropicVertex(project_id=cred["project_id"], region=cred["region"])
    if prov == "foundry":
        return anthropic.AnthropicFoundry(api_key=cred["api_key"], resource=cred["resource"])
    kw = {}
    if cred.get("api_key"):
        kw["api_key"] = cred["api_key"]
    if cred.get("base_url"):
        kw["base_url"] = cred["base_url"]
    return anthropic.Anthropic(**kw)


def supports_anthropic_params(cred: dict) -> bool:
    return cred.get("family") == "anthropic"


# ---------------------------------------------------------------------------
# OpenAI-compatible adapter (Ollama, LM Studio, OpenRouter, vLLM, …)
# ---------------------------------------------------------------------------

def _post_json(url: str, body: dict, headers: dict, timeout: int = 600) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json", **headers}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as exc:
        raise ProviderError(f"{url} → HTTP {exc.code}: {exc.read().decode(errors='ignore')[:300]}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ProviderError(f"{url} unreachable: {exc}") from exc


def to_openai_tools(tools: list[dict]) -> list[dict]:
    return [{"type": "function", "function": {"name": t["name"], "description": t.get("description", ""), "parameters": t["input_schema"]}} for t in tools or []]


def to_openai_messages(system, messages: list[dict]) -> list[dict]:
    out: list[dict] = []
    sys_text = system if isinstance(system, str) else "".join(b.get("text", "") for b in (system or []))
    if sys_text:
        out.append({"role": "system", "content": sys_text})
    for m in messages:
        role, content = m["role"], m["content"]
        if isinstance(content, str):
            out.append({"role": role, "content": content})
            continue
        if role == "assistant":
            text = "".join(getattr(b, "text", "") for b in content if getattr(b, "type", "") == "text")
            calls = [{"id": b.id, "type": "function", "function": {"name": b.name, "arguments": json.dumps(b.input)}} for b in content if getattr(b, "type", "") == "tool_use"]
            msg = {"role": "assistant", "content": text or None}
            if calls:
                msg["tool_calls"] = calls
            out.append(msg)
        else:
            for b in content:
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    out.append({"role": "tool", "tool_call_id": b["tool_use_id"], "content": str(b.get("content", ""))})
                elif isinstance(b, dict) and b.get("type") == "text":
                    out.append({"role": "user", "content": b["text"]})
    return out


def from_openai_response(resp: dict):
    choice = (resp.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    blocks = []
    if msg.get("content"):
        blocks.append(NS(type="text", text=msg["content"]))
    for tc in msg.get("tool_calls") or []:
        fn = tc.get("function") or {}
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except json.JSONDecodeError:
            args = {"_raw": fn.get("arguments")}
        blocks.append(NS(type="tool_use", id=tc.get("id") or f"call_{len(blocks)}", name=fn.get("name"), input=args))
    finish = choice.get("finish_reason")
    stop = "tool_use" if any(b.type == "tool_use" for b in blocks) else ("max_tokens" if finish == "length" else ("refusal" if finish == "content_filter" else "end_turn"))
    return NS(content=blocks, stop_reason=stop, model=resp.get("model"), usage=resp.get("usage"))


class _Messages:
    def __init__(self, base_url: str, api_key: str | None, provider: str):
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        if provider == "openrouter":
            self.headers["HTTP-Referer"] = "https://github.com/fayasfarmisofficial-cyber/TWC-Thugs"

    def create(self, *, model: str, max_tokens: int, messages: list[dict], system=None, tools=None, **_ignored):
        body = {"model": model, "max_tokens": max_tokens, "messages": to_openai_messages(system, messages)}
        if tools:
            body["tools"] = to_openai_tools(tools)
        return from_openai_response(_post_json(self.url, body, self.headers))


class OpenAICompatClient:
    """Duck-types the slice of anthropic.Anthropic the harness uses: client.messages.create(...). No streaming."""

    def __init__(self, base_url: str, api_key: str | None, provider: str = "openai-compatible"):
        self.messages = _Messages(base_url, api_key, provider)
        self.provider = provider
