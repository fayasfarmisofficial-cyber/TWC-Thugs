import subprocess
import sys


def _repl(stdin: str, cwd, env_extra=None):
    import os
    env = {**os.environ, **(env_extra or {})}
    return subprocess.run([sys.executable, "-m", "amu.cli"], input=stdin, cwd=cwd, capture_output=True, text=True, env=env, timeout=60)


def _repo(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path)
    return tmp_path


def test_banner_shows_model_off_with_guidance(fake_entire, tmp_path):
    r = _repl("/key\n", _repo(tmp_path))
    assert "○ model off" in r.stderr and "/key add" in r.stderr


def test_free_text_without_model_guides_to_key_add(fake_entire, tmp_path):
    r = _repl("what does this repo do\n", _repo(tmp_path))
    assert "○ model off" in r.stderr and "/key add" in r.stderr


def test_guided_add_turns_model_on(fake_entire, tmp_path):
    # /key add → provider 2 (ollama, no key) → model name → banner flips to on; nothing secret echoed
    r = _repl("/key add\n2\nqwen2.5-coder\n/key\n", _repo(tmp_path))
    assert "● model on" in r.stderr and "ollama" in r.stderr and "qwen2.5-coder" in r.stderr


def test_guided_add_anthropic_never_echoes_key(fake_entire, tmp_path):
    r = _repl("/key add\n1\nsk-ant-api03-secret-value-1234567890\n/key\n", _repo(tmp_path))
    assert "● model on" in r.stderr and "secret-value" not in r.stdout + r.stderr and "…7890" in r.stderr


def test_banner_shows_model_on_when_env_key_present(fake_entire, tmp_path):
    r = _repl("/key\n", _repo(tmp_path), {"ANTHROPIC_API_KEY": "sk-ant-api03-env-000000000000"})
    assert "● model on" in r.stderr and "via env" in r.stderr


def test_key_remove_turns_model_off(fake_entire, tmp_path):
    r = _repl("/key add\n2\nm\n/key remove\n", _repo(tmp_path))
    assert r.stderr.count("● model on") >= 1 and "○ model off" in r.stderr.split("● model on")[-1]
