import json
import subprocess
import sys


def _run(*args, cwd="."):
    return subprocess.run([sys.executable, "-m", "amu.cli", *args], cwd=cwd, capture_output=True, text=True)


def test_header_on_stderr_for_human_output(fake_entire, tmp_path):
    r = _run("map", "--symbol", "amu/classify.py#classify_consumers", cwd=tmp_path)
    assert "TWC Thugs · amu map" in r.stderr and "\033[" not in r.stderr  # NO_COLOR=1 in conftest


def test_json_output_is_untouched_by_branding(fake_entire, tmp_path):
    r = _run("map", "--symbol", "amu/classify.py#classify_consumers", "--json", cwd=tmp_path)
    json.loads(r.stdout)
    assert "TWC" not in r.stdout and r.stderr.strip() == ""


def test_version_line():
    assert "TWC Thugs" in _run("--version").stdout
