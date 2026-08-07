"""The theme engine was deleting its own death certificates (#539, 2026-08-07).

`_save_themes` ends with a same-day cleanup that removes `source='live'` rows whose name is not in
this run's final list. That is right for merged-away themes. It was also eating the RETIRED
tombstones the engine itself had written moments earlier, because a retired theme is — by
construction — absent from the next run's final list.

Measured on prod:

    08-04 run 1   lifecycle-retires `Bitcoin Mining & Crypto Infrastructure Operators`,
                  writes the engine-drop tombstone (stage='Retired', source='live')
    08-04 run 2/3 (17:10, 17:12) no longer see it -> this DELETE removes the tombstone
                  -> mi_themes ends the night with ZERO rows for 08-04
    08-05         get_active_themes(7) finds the surviving 08-03 row and reloads it whole

The theme was dead-and-walking for three weeks: {CIFR,HUT} in every row 07-20 -> 08-06, named
"Bitcoin Mining" while its own thesis says "AI data center lease" / "Nvidia".

The #214 RETIRED-GAP guard in `get_active_themes` is correct and was defeated only because the row
it reads had been destroyed — which is why the fix lives in the DELETE, not in the reader.
"""
import pathlib
import re

import pytest

SRC = pathlib.Path("agents/market_intelligence/theme_engine.py").read_text(encoding="utf-8")


def _cleanup_delete() -> str:
    """The same-day cleanup DELETE, extracted from source so the tests read the REAL statement.

    Asserting against a copy would pass forever while the statement drifted — the same
    stale-copy failure mode that produced the bug being fixed.
    """
    m = re.search(r"DELETE FROM mi_themes\s*\n(.*?)\"\"\"", SRC, re.S)
    assert m, "could not find the same-day cleanup DELETE in theme_engine.py"
    return m.group(1)


def test_the_cleanup_no_longer_deletes_retired_tombstones():
    """The regression itself."""
    stmt = _cleanup_delete()
    assert "stage != 'Retired'" in stmt, (
        "the same-day cleanup can delete RETIRED tombstones again — a same-day engine rerun "
        "will resurrect dead themes (#539)")


def test_the_cleanup_is_still_scoped_to_live_rows():
    """Guard the guard: the #226 protection for shadow_promoted rows must survive this fix."""
    stmt = _cleanup_delete()
    assert "source = 'live'" in stmt, (
        "cleanup lost its source='live' scope — a same-day rerun can now clobber "
        "shadow_promoted graduation rows (#226)")


def test_the_cleanup_still_deletes_something():
    """A fix that neutered the DELETE entirely would also 'pass' the test above. Merged-away
    themes must still be removed, or every superseded name lingers on the board."""
    stmt = _cleanup_delete()
    assert "name != ALL(" in stmt, "cleanup no longer removes merged/retired names at all"
    assert "theme_date = $1" in stmt, "cleanup is no longer scoped to today"


def test_the_retired_gap_reader_is_still_the_other_half():
    """The fix assumes get_active_themes honours a Retired tombstone once it survives. If that
    guard is ever removed, this fix silently stops mattering and the zombie returns."""
    db = pathlib.Path("agents/market_intelligence/db.py").read_text(encoding="utf-8")
    m = re.search(r"async def get_active_themes.*?(?=\nasync def |\ndef )", db, re.S)
    assert m, "get_active_themes not found"
    body = m.group(0)
    assert "Retired" in body, (
        "get_active_themes no longer references Retired — the #214 RETIRED-GAP guard that this "
        "fix feeds may be gone, which would make the tombstone useless again")


def test_ONLY_retired_is_exempt_no_other_stage():
    """Only the tombstone is spared. If the exemption ever widens to another stage, a merged-away
    theme in that stage would linger on the board every night.

    Live counts on prod when this shipped — Fading 293, Mainstream 269, Nascent 139,
    Accelerating 63, Retired 62 — so the exemption covers a real but bounded slice.

    ⚠ Replaces a parametrised version whose assertion was tangled enough to pass vacuously. A
    test that cannot fail is worse than no test, and this file exists because of a bug that hid
    in plain sight.
    """
    stmt = _cleanup_delete()
    exempted = re.findall(r"stage\s*!=\s*'([A-Za-z]+)'", stmt)
    assert exempted == ["Retired"], (
        f"expected exactly one stage exemption ('Retired'), found {exempted}")
    for stage in ("Fading", "Mainstream", "Nascent", "Accelerating"):
        assert f"!= '{stage}'" not in stmt, f"{stage} must NOT be exempt from the cleanup"
