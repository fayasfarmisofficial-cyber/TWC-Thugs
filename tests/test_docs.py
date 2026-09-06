import json
from pathlib import Path

from amu import docs

DIFF = json.loads((Path(__file__).parent / "fixtures" / "diff.json").read_text())
DMAP = {"amu/classify.py#classify_consumers": [{"file": "docs/x.md", "section": "## classify"}]}


def test_signature_change_on_mapped_export_is_suggested_draft():
    c = next(x for x in docs.candidates(DIFF, DMAP) if x["candidate"].endswith("classify_consumers"))
    assert c["confidence"] == "sound" and docs.draft(c).startswith("SUGGESTED")


def test_body_change_is_unknown_candidate():
    c = next(x for x in docs.candidates(DIFF, DMAP) if x["candidate"].endswith("build_plan"))
    assert c["confidence"] == "unknown" and c["class"] == "body"


def test_unmapped_is_guessed_flag_only():
    c = next(x for x in docs.candidates(DIFF, DMAP) if x["candidate"].endswith("capabilities"))
    assert c["confidence"] == "guessed" and not c["targets"]


def test_auto_never_applies_unknown(tmp_path):
    for c in docs.candidates(DIFF, DMAP):
        if c["confidence"] != "sound":
            assert docs.apply(c, str(tmp_path)) is False
