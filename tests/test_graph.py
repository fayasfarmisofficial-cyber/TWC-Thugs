import json
import re
from pathlib import Path

from amu import graphview

IMP = json.loads((Path(__file__).parent / "fixtures" / "impact.json").read_text())


def _p():
    return graphview.payload_from_impact("classify_consumers", IMP)


def test_payload_has_focus_nodes_edges_with_confidence():
    p = _p()
    assert p["focus"].endswith("classify_consumers") and p["counts"]["callers"] > 0
    assert all(n["confidence"] in ("sound", "guessed", "unknown") and n["reason"] and n["verify"] for n in p["nodes"])
    assert all(e["relation"] for e in p["edges"])


def test_deterministic():
    assert graphview.to_ascii(_p()) == graphview.to_ascii(_p()) and graphview.to_mermaid(_p()) == graphview.to_mermaid(_p())


def test_mermaid_is_valid_shape():
    m = graphview.to_mermaid(_p())
    lines = m.splitlines()
    assert lines[0] == "graph TD"
    edge_lines = [ln for ln in lines if "-->" in ln]
    assert edge_lines and all(re.match(r"^\s+n_\w+ -->\|[A-Z_]+\| n_\w+$", ln) for ln in edge_lines)
    assert all(re.match(r'^\s+n_\w+(\[\[|\(|\[)".*"(\]\]|\)|\])$', ln) for ln in lines if '"' in ln and "-->" not in ln)


def test_dot_is_a_digraph():
    d = graphview.to_dot(_p())
    assert d.startswith("digraph amu {") and d.rstrip().endswith("}") and '-> "n_' in d


def test_ascii_has_glyphs_and_relation_labels():
    a = graphview.to_ascii(_p())
    assert "●" in a and "CALLS" in a and "callers" in a and "edges " in a


def test_ambiguous_focus_is_unknown():
    p = graphview.payload_from_impact("x", {**IMP, "disambiguation_required": True, "definitions": [{}, {}]})
    f = next(n for n in p["nodes"] if n["id"] == p["focus"])
    assert f["confidence"] == "unknown" and "ambiguous" in f["reason"]


def test_relation_filter():
    p = graphview.payload_from_impact("classify_consumers", IMP, relation="DATA_FLOWS")
    assert all(e["relation"] == "DATA_FLOWS" for e in p["edges"])
