from amu.router import change_class, route

SYMS = {"classify_consumers": [{"symbol": "classify_consumers", "path": "amu/classify.py"}],
        "build_plan": [{"symbol": "build_plan", "path": "amu/plan.py"}],
        "impact": [{"symbol": "impact", "path": "amu/graph.py"}, {"symbol": "impact", "path": "amu/entire.py"}]}
lookup = lambda t: SYMS.get(t, [])  # noqa: E731


def test_never_invents_a_symbol():
    assert route("change the FooBarBaz thing", lookup)["status"] == "not_found"


def test_silent_on_params_means_signature():
    assert change_class("update classify_consumers") == "signature"
    assert route("update classify_consumers", lookup)["change_class"] == "signature"


def test_two_targets_is_multi_target():
    assert route("rename classify_consumers and build_plan", lookup)["status"] == "multi_target"


def test_duplicate_name_is_ambiguous():
    assert route("fix impact body", lookup)["status"] == "ambiguous"


def test_slash_commands():
    assert route("/verify n5", lookup) == {"intent": "verify", "arg": "n5", "status": "command", "targets": [], "change_class": None}
