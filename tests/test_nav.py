import json
import subprocess
import sys

from amu.router import route


def _amu(args, cwd):
    return subprocess.run([sys.executable, "-m", "amu.cli", *args], cwd=cwd, capture_output=True, text=True)


def _repo(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path)
    return tmp_path


def test_find_returns_ranked_hits_with_signals(fake_entire, tmp_path):
    r = _amu(["find", "where is the classifier", "--json"], _repo(tmp_path))
    out = json.loads(r.stdout)
    assert out["hits"][0]["symbol_name"] == "classify_consumers" and "graph:callers" in out["hits"][0]["signals"]
    assert out["verify_command"]["command"].startswith("python -m pytest")


def test_find_open_prints_file_line(fake_entire, tmp_path):
    r = _amu(["find", "classifier", "--open", "n1"], _repo(tmp_path))
    assert r.stdout.strip() == "amu/classify.py:3"


def test_find_human_output_shows_why(fake_entire, tmp_path):
    r = _amu(["find", "classifier"], _repo(tmp_path))
    assert "why:" in r.stdout and "graph:callers" in r.stdout


def test_back_and_recent(fake_entire, tmp_path):
    d = _repo(tmp_path)
    _amu(["find", "one"], d)
    _amu(["find", "two"], d)
    rec = json.loads(_amu(["recent", "--json"], d).stdout)
    assert [e["target"] for e in rec] == ["one", "two"]
    b = json.loads(_amu(["back", "--json"], d).stdout)
    assert b["target"] == "one"
    assert _amu(["back"], d).returncode == 2


def test_open_symbol_uses_def(fake_entire, tmp_path):
    r = _amu(["open", "amu/classify.py#classify_consumers", "--json"], _repo(tmp_path))
    out = json.loads(r.stdout)
    assert "def classify_consumers" in out["definition"] and out["next"].startswith("amu map --symbol")


def test_router_explore_intent():
    assert route("amu/classify.py", lambda t: [])["status"] == "explore"
    assert route("/tree amu", lambda t: [])["intent"] == "tree"
    assert route("/graph classify_consumers", lambda t: [])["arg"] == "classify_consumers"


def test_no_repo_gives_add_hint(tmp_path):
    r = _amu(["find", "x"], tmp_path)  # not a git worktree, empty isolated workspace
    assert r.returncode == 2 and "amu repo add" in r.stderr
