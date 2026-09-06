import json
import subprocess
import sys


def _amu(args, cwd):
    return subprocess.run([sys.executable, "-m", "amu.cli", *args], cwd=cwd, capture_output=True, text=True)


def test_sweep_reports_findings_outside_contract_with_verify(fake_entire, tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path)
    (tmp_path / ".amu").mkdir()
    (tmp_path / ".amu" / "contract.json").write_text(json.dumps({"base_sha": "HEAD~1", "allowed_files": ["amu/classify.py"], "phases": [], "targets": [], "frozen_signatures": [], "map_hash": "h", "created_at": "n"}))
    r = _amu(["sweep", "--json"], tmp_path)
    out = json.loads(r.stdout)
    assert r.returncode == 0
    assert any(f["path"] == "amu/graph.py" and f["verify"].startswith("amu map") for f in out["findings"])
    assert "findings outside the contract" in out["summary"] and "nothing found" not in out["summary"]


def test_sweep_never_exits_1_and_reports_depth(fake_entire, tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path)
    r = _amu(["sweep", "--json"], tmp_path)
    assert r.returncode == 0 and "at depth" in json.loads(r.stdout)["summary"]


def test_done_exits_0_with_findings(fake_entire, tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path)
    r = _amu(["done", "--json"], tmp_path)
    assert r.returncode == 0
    rep = json.loads(r.stdout)
    assert rep["findings"] and rep["memory"]["entries"] >= 0
