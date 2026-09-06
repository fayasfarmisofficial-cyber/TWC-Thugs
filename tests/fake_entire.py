# ruff: noqa: E702
"""Recorded-fixture fake of the `entire` CLI. Replays JSON from tests/fixtures/ so tests never need the real binary."""

import json
import os
import sys
from pathlib import Path

FIX = Path(os.environ.get("AMU_FAKE_FIXTURES", Path(__file__).parent / "fixtures"))


def main(argv):
    a = argv[1:]
    if a[:1] == ["version"]:
        print("Entire CLI 0.10.5-fake"); return 0
    if a[:2] == ["graph", "version"]:
        print("v0.4.0-fake"); return 0
    if a[:2] == ["graph", "index"]:
        print(json.dumps({"counts": {"files": 3, "symbols": 12, "relations": 20}, "partial_failures": [{"file_path": "vendor/blob.min.js"}]})); return 0
    if a[:2] == ["graph", "snapshot"]:
        print('{"record_type":"file","path":"amu/classify.py"}'); return 0
    if a[:2] == ["graph", "capabilities"]:
        print(json.dumps({"out_of_coverage": ["vendor/"], "unresolved_patterns": ["dynamic_dispatch"]})); return 0
    if a[:2] == ["graph", "impact"]:
        print((FIX / "impact.json").read_text()); return 0
    if a[:2] == ["graph", "diff"]:
        print((FIX / "diff.json").read_text()); return 0
    if a[:2] == ["graph", "symbols"]:
        print((FIX / "symbols.ndjson").read_text()); return 0
    if a[:2] == ["graph", "neighbors"]:
        print(json.dumps({"matches": [{"symbol": {"name": "x"}}]})); return 0
    if a[:2] == ["graph", "verify"]:
        print("verdict: 0 tests changed state (fake)"); return 0
    if a[:2] == ["graph", "doctor"]:
        print(json.dumps({"no_egress": True})); return 0
    if a[:2] == ["checkpoint", "list"]:
        print("[]"); return 0
    if a[:1] == ["status"]:
        print("● Enabled (fake)"); return 0
    print(f"fake entire: unsupported {a}", file=sys.stderr); return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
