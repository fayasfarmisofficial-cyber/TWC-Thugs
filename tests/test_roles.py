import pytest

from amu.harness.roles import Budget, ToolNotGranted, WriteRefused, checker_decide, make_role

RED = {"violations": [{"kind": "PHASE_DRIFT", "symbol": "a.py", "detail": "d", "severity": "ERROR"}]}


def test_role_cannot_call_ungranted_tool():
    with pytest.raises(ToolNotGranted):
        make_role("sweeper").call("files.write_allowed", lambda: None)


def test_builder_write_guard(tmp_path):
    r = make_role("builder", {"a.py"})
    with pytest.raises(WriteRefused):
        r.write_path("b.py", "x", str(tmp_path))
    assert r.write_path("a.py", "x", str(tmp_path)).read_text() == "x"


def test_checker_cannot_downgrade_blocking():
    assert checker_decide(RED, Budget())["decision"] != "proceed"


def test_third_retry_escalates():
    b = Budget()
    decisions = [checker_decide(RED, b)["decision"] for _ in range(3)]
    assert decisions[-1] == "escalate" and checker_decide(RED, b)["escalate"] is True
