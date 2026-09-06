import json
import re
from pathlib import Path

from amu import render, state
from amu.classify import build_map
from amu.plan import make_contract, plan_from_map

BANNED = re.compile(r"\b(safe|clean|verified|OK)\b")
IMP = json.loads((Path(__file__).parent / "fixtures" / "impact.json").read_text())


def _m():
    m = build_map("amu/classify.py", ["classify_consumers"], {"classify_consumers": IMP}, "signature", {}, {}, 2)
    m["map_hash"] = state.stable_hash(m["nodes"])
    return m


def test_map_plan_contract_json_have_no_banned_verdict_words():
    m = _m()
    phases = plan_from_map(m, [{"symbol": "a#b", "change_class": "signature"}])
    c = make_contract(m, phases, [{"symbol": "a#b", "change_class": "signature"}], "sha", "now")
    for obj in (m, phases, c, render.agent_card(m)):
        assert not BANNED.search(json.dumps(obj)), json.dumps(obj)[:200]


def test_rendered_map_has_no_banned_words(capsys):
    render.render_map(_m())
    assert not BANNED.search(capsys.readouterr().out)


def test_schemas_validate():
    m = _m()
    state.validate("map", m)
    phases = plan_from_map(m, [{"symbol": "a#b", "change_class": "signature"}])
    state.validate("contract", make_contract(m, phases, [], "sha", "now"))
    state.validate("handoff", {"decision": "x", "confidence": 0.1, "escalate": False, "evidence": [], "next": "y"})
