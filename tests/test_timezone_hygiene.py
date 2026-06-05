"""Permanent regression lock for the timezone bug class (2026-06-05).

Two halves:
  1. `_ET` (now ZoneInfo) produces the CORRECT EST/EDT offset in every
     construction path — the exact thing pytz got wrong (LMT -04:56). This is
     the regression test for the #180/#183 LMT bug.
  2. The deploy gate (`preflight_datetime_hygiene`) actually CATCHES pytz /
     naive-now / bare-astimezone and honors the `# tz-ok` escape — so a green
     gate means clean, not broken.
"""
from datetime import datetime, date, time

from shared.dates import _ET
from scripts.preflight_datetime_hygiene import check_file, HygieneVisitor
import ast


# ── 1. _ET offset correctness across DST (the LMT regression lock) ──────────

def _offset_hours(dt: datetime) -> float:
    return dt.utcoffset().total_seconds() / 3600


def test_winter_is_est_minus_5():
    # Jan 15 2026 — standard time. pytz-as-tzinfo gave -04:56 (LMT); must be -5.
    dt = datetime(2026, 1, 15, 9, 31, tzinfo=_ET)
    assert _offset_hours(dt) == -5.0


def test_summer_is_edt_minus_4():
    # May 28 2026 — daylight time (the actual #183 AVAV date). Must be -4, NOT
    # the -04:56 LMT offset that shifted the ORB window +56 min.
    dt = datetime(2026, 5, 28, 9, 31, tzinfo=_ET)
    assert _offset_hours(dt) == -4.0


def test_combine_with_tzinfo_is_correct():
    # datetime.combine(..., tzinfo=_ET) was THE buggy call site. Must be -4 EDT.
    dt = datetime.combine(date(2026, 5, 28), time(9, 31), tzinfo=_ET)
    assert _offset_hours(dt) == -4.0
    assert dt.isoformat() == "2026-05-28T09:31:00-04:00"


def test_replace_tzinfo_is_correct():
    dt = datetime(2026, 5, 28, 9, 31).replace(tzinfo=_ET)
    assert _offset_hours(dt) == -4.0


def test_spring_forward_boundary():
    # DST starts 2026-03-08 02:00. Before = EST -5, after = EDT -4.
    before = datetime(2026, 3, 8, 1, 30, tzinfo=_ET)
    after = datetime(2026, 3, 8, 3, 30, tzinfo=_ET)
    assert _offset_hours(before) == -5.0
    assert _offset_hours(after) == -4.0


# ── 2. the gate catches the footguns ────────────────────────────────────────

def _violations(code: str) -> list[dict]:
    tree = ast.parse(code)
    v = HygieneVisitor("<test>", code.splitlines())
    v.visit(tree)
    return v.violations


def test_gate_flags_import_pytz():
    codes = {v["code"] for v in _violations("import pytz\nx = pytz.timezone('US/Eastern')\n")}
    assert "pytz" in codes


def test_gate_flags_pytz_utc_attribute():
    codes = {v["code"] for v in _violations("import pytz\ny = pytz.UTC\n")}
    assert "pytz" in codes


def test_gate_flags_naive_now():
    codes = {v["code"] for v in _violations("from datetime import datetime\nx = datetime.now()\n")}
    assert "naive_now" in codes


def test_gate_allows_aware_now():
    codes = {v["code"] for v in _violations("from datetime import datetime\nx = datetime.now(_ET)\n")}
    assert "naive_now" not in codes


def test_gate_flags_bare_astimezone():
    codes = {v["code"] for v in _violations("x = some_dt.astimezone()\n")}
    assert "bare_astimezone" in codes


def test_gate_allows_explicit_astimezone():
    codes = {v["code"] for v in _violations("x = some_dt.astimezone(_ET)\n")}
    assert "bare_astimezone" not in codes


def test_escape_comment_suppresses():
    code = "import pytz  # tz-ok: legacy display only\n"
    assert _violations(code) == []
