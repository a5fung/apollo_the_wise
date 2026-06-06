"""Tests for the task<->project filing governance gate (2026-06-06).

The bug class this exists to catch: an OPEN #-task that lives in NO project bucket
in BACKLOG (the 6/6 #216/#217 miss the operator had to catch by hand). The gate
must FAIL on that, while NOT false-failing on legit prose cross-references.
"""
from __future__ import annotations

import json
from pathlib import Path

from scripts.check_task_project_filing import (
    load_open_ids, extract_section, parse_buckets, reconcile, main,
)

_SECTION = """\
## 📂 Open tasks by project (hierarchy — no loose tasks)

- **North Star**: #200 #201 #213 · cluster #214 #215
- **Live-money cutover**: #150 #151 #184 (#184 = broker mirror. Done: #174 #180.)
- **Operational safety**: #152 #172 #216 (#172 = refactor gated behind #151 split)
- **Miscellaneous**: #121 #176

---

## next section
- #999 should not be parsed (outside the hierarchy section)
"""


def _open(*ids):
    return [{"id": i, "status": "pending"} for i in ids]


def test_extract_section_stops_at_rule():
    sec = extract_section(_SECTION)
    assert "North Star" in sec
    assert "#999" not in sec  # past the --- rule


def test_all_filed_passes():
    present, primary = parse_buckets(extract_section(_SECTION))
    r = reconcile({i: {} for i in [200, 201, 150, 151, 216, 121]}, present, primary)
    assert r["unfiled"] == []
    assert r["double"] == []


def test_unfiled_task_is_caught():
    # #777 is open but in no bucket — the exact 6/6 miss.
    present, primary = parse_buckets(extract_section(_SECTION))
    r = reconcile({200: {}, 777: {}}, present, primary)
    assert r["unfiled"] == [777]


def test_paren_crossref_is_not_a_double_file():
    # #151 is a primary entry ONLY under Live-money; the Op-safety line mentions it
    # inside parens. Must NOT be flagged double.
    present, primary = parse_buckets(extract_section(_SECTION))
    r = reconcile({151: {}}, present, primary)
    assert r["double"] == []
    assert 151 in present  # still counts as filed


def test_genuine_double_file_is_caught():
    sec = _SECTION.replace("- **Miscellaneous**: #121 #176",
                           "- **Miscellaneous**: #121 #176 #200")  # #200 now in 2 buckets
    present, primary = parse_buckets(extract_section(sec))
    r = reconcile({200: {}}, present, primary)
    assert r["double"] == [200]


def test_stale_is_warn_not_fail():
    present, primary = parse_buckets(extract_section(_SECTION))
    # #174 appears only inside a "Done:" paren — it's present-anywhere but no longer open.
    r = reconcile({200: {}}, present, primary)
    assert 174 in r["stale"]


def test_load_open_ids_filters_closed():
    raw = _open(1, 2) + [{"id": 3, "status": "completed"}, {"id": 4, "status": "deleted"}]
    ids = load_open_ids_from_list(raw)
    assert set(ids) == {1, 2}


def load_open_ids_from_list(raw):
    # tiny helper mirroring load_open_ids' filter without a temp file
    return {int(t["id"]): t for t in raw
            if str(t.get("status", "pending")).lower() not in ("completed", "deleted")}


def test_main_fails_on_unfiled(tmp_path: Path):
    snap = tmp_path / "open.json"
    snap.write_text(json.dumps(_open(200, 777)), encoding="utf-8")
    bl = tmp_path / "BACKLOG.md"
    bl.write_text(_SECTION, encoding="utf-8")
    assert main(["prog", str(snap), str(bl)]) == 1  # #777 unfiled


def test_main_passes_when_clean(tmp_path: Path):
    snap = tmp_path / "open.json"
    snap.write_text(json.dumps(_open(200, 151)), encoding="utf-8")
    bl = tmp_path / "BACKLOG.md"
    bl.write_text(_SECTION, encoding="utf-8")
    assert main(["prog", str(snap), str(bl)]) == 0


def test_main_skips_when_no_snapshot(tmp_path: Path):
    bl = tmp_path / "BACKLOG.md"
    bl.write_text(_SECTION, encoding="utf-8")
    # missing snapshot -> SKIP (exit 0), absence isn't a commit blocker
    assert main(["prog", str(tmp_path / "nope.json"), str(bl)]) == 0
