import json
from pathlib import Path

from amu import state
from amu.classify import build_map

IMP = json.loads((Path(__file__).parent / "fixtures" / "impact.json").read_text())


def _map(change="signature", imp=None):
    return build_map("amu/classify.py", ["classify_consumers"], {"classify_consumers": IMP if imp is None else imp}, change, {}, {}, 2)


def test_sound_needs_resolved_edge():
    m = _map()
    assert all(n["confidence"] == "sound" for n in m["nodes"] if n["evidence"][0].startswith("impact:callers"))


def test_every_non_sound_node_has_reason_and_verify():
    m = _map(imp={"error": "boom"})
    m["map_hash"] = "x"
    state.validate("map", m)
    assert all(n["reason"] and n["verify"] for n in m["nodes"] if n["confidence"] != "sound")


def test_failed_impact_is_unknown_not_dropped():
    m = _map(imp={"error": "unresolved"})
    assert m["resolution"]["unknown"] == 1 and "unresolved" in m["nodes"][0]["reason"]


def test_syntax_error_file_in_root_package_becomes_unknown_node():
    imp = {**IMP, "partial_failures": [{"code": "E_PARSE_ERROR", "file_path": "amu/broken.py", "effect_on_semantic_completeness": "incomplete"},
                                       {"code": "E_UNSUPPORTED_LANGUAGE", "file_path": "doc/x.f90", "effect_on_semantic_completeness": "omitted"}]}
    m = _map(imp=imp)
    assert any(n["confidence"] == "unknown" and n["path"] == "amu/broken.py" for n in m["nodes"])
    assert not any(n["path"] == "doc/x.f90" for n in m["nodes"])
    assert "2 files unparsed repo-wide" in m["resolution"]["qualifier"]


def test_ambiguous_symbol_is_unknown_not_silent():
    imp = {**IMP, "callers": {"total": 0, "entries": []}, "data_flows": {"total": 0, "entries": None},
           "disambiguation_required": True, "definitions": [{"file_path": "a.py"}, {"file_path": "b.py"}]}
    m = _map(imp=imp)
    assert m["resolution"]["unknown"] == 1 and "ambiguous: 2 definitions" in m["nodes"][0]["reason"]


def test_zero_unknown_line_carries_qualifier():
    m = _map()
    assert m["resolution"]["unknown"] == 0 and "not counted" in m["resolution"]["qualifier"]


def test_body_change_never_will_break():
    assert all(n["risk"] != "will_break" for n in _map("body")["nodes"])


def test_next_is_runnable():
    assert _map()["next"].startswith("amu plan --targets")
