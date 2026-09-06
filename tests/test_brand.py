import json
import re
import subprocess
import sys

from amu import brand

ANSI = re.compile(r"\x1b\[")


def _run(*args, cwd=".", env=None):
    import os
    e = {**os.environ, **(env or {})}
    return subprocess.run([sys.executable, "-m", "amu.cli", *args], cwd=cwd, capture_output=True, text=True, env=e)


def _repo(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path)
    return tmp_path


def test_palette_constants():
    assert brand.PALETTE == {"gold": "#F5B32E", "amber": "#E08A1E", "ember": "#C2410C", "sand": "#FDF6E3", "ash": "#8A8578", "bg": "#161412"}
    assert brand.SEMANTIC["guessed"] == brand.PALETTE["amber"] and brand.SEMANTIC["risk"] == brand.PALETTE["ember"]
    assert brand.PALETTE["gold"] not in brand.SEMANTIC.values()  # confidence glyphs are never gold


def test_header_on_stderr_no_color(fake_entire, tmp_path):
    r = _run("map", "--symbol", "amu/classify.py#classify_consumers", cwd=_repo(tmp_path))
    assert "TWC Thugs · amu map" in r.stderr and not ANSI.search(r.stderr) and not ANSI.search(r.stdout)  # NO_COLOR=1 in conftest
    assert "● sound" in r.stdout  # glyph + word survive without colour


def test_json_output_has_no_branding_and_no_ansi(fake_entire, tmp_path):
    r = _run("map", "--symbol", "amu/classify.py#classify_consumers", "--json", cwd=_repo(tmp_path), env={"NO_COLOR": ""})
    json.loads(r.stdout)
    assert "TWC" not in r.stdout and not ANSI.search(r.stdout) and r.stderr.strip() == ""


def test_version_line():
    assert "TWC Thugs" in _run("--version").stdout
