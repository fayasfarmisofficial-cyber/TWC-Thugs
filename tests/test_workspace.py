import json
import subprocess
import sys

import pytest

from amu import workspace


def _amu(args, cwd):
    return subprocess.run([sys.executable, "-m", "amu.cli", *args], cwd=cwd, capture_output=True, text=True)


def _git_repo(tmp_path, name="proj"):
    d = tmp_path / name
    d.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=d)
    (d / "a.py").write_text("def f():\n    return 1\n")
    subprocess.run(["git", "add", "."], cwd=d)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init"], cwd=d)
    return d


def test_add_rejects_non_git_path(tmp_path):
    (tmp_path / "plain").mkdir()
    with pytest.raises(workspace.WorkspaceError) as exc:
        workspace.add(str(tmp_path / "plain"), do_index=False)
    assert exc.value.code == 2 and "not inside a Git worktree" in str(exc.value)


def test_add_local_indexes_and_activates(fake_entire, tmp_path):
    d = _git_repo(tmp_path)
    e = workspace.add(str(d))
    ws = workspace.load()
    assert ws["active"] == e["name"] and e["counts"]["symbols"] == 12 and (d / ".amu" / "snapshot.ndjson").exists()


def test_use_list_remove(fake_entire, tmp_path):
    a, b = _git_repo(tmp_path, "aa"), _git_repo(tmp_path, "bb")
    workspace.add(str(a), do_index=False)
    workspace.add(str(b), do_index=False)
    assert workspace.load()["active"] == "bb"
    workspace.use("aa")
    assert workspace.load()["active"] == "aa"
    r = workspace.remove("aa")
    assert r["deleted_clone"] is False and workspace.load()["active"] == "bb" and a.exists()


def test_remove_never_deletes_outside_managed_dir(tmp_path):
    d = _git_repo(tmp_path)
    workspace.add(str(d), do_index=False)
    r = workspace.remove(d.name, delete_clone=True)
    assert r["deleted_clone"] is False and d.exists()


def test_resolve_order(tmp_path, monkeypatch):
    d = _git_repo(tmp_path)
    workspace.add(str(d), do_index=False)
    monkeypatch.chdir(tmp_path)  # not a git worktree → falls to the active repo
    assert workspace.resolve(None) == str(d)
    assert workspace.resolve("/explicit") == "/explicit"
    workspace.remove(d.name)
    with pytest.raises(workspace.WorkspaceError):
        workspace.resolve(None)


def test_remote_spec_detection():
    assert workspace.is_remote_spec("numpy/numpy") and workspace.is_remote_spec("https://github.com/numpy/numpy.git")
    assert not workspace.is_remote_spec(".")


def test_cli_repo_list_and_cd(fake_entire, tmp_path):
    d = _git_repo(tmp_path)
    r = _amu(["repo", "add", str(d), "--json"], tmp_path)
    assert r.returncode == 0, r.stderr
    lst = json.loads(_amu(["repo", "list", "--json"], tmp_path).stdout)
    assert lst["active"] == d.name and lst["repos"][0]["active"] is True
    assert _amu(["cd", d.name], tmp_path).stdout.strip() == str(d)
    assert _amu(["cd", "nope"], tmp_path).returncode == 2
