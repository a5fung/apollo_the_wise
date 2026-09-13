"""The replay harness must not be able to emit a misleading summary.

Operator, 2026-09-05: "how can we make sure this study works going forward without all the
caveats you listed, that is the more important point."

Four traps bit one evening's work, and every one was caught by him reading the output rather
than by the harness. These pin the three that are decidable in the summary path:

  1. CENSORING — a settled-only read drops open_at_horizon rows, and a looser exit rule's
     entire benefit is that it keeps positions open. The 09-05 breakeven A/B lost CRWD that
     way; #327's watch lane reads -0.75R for the same reason.
  2. NEAR-ZERO STOPS — a two-cent stop makes R meaningless. Two such rows once carried more R
     than a 1,577-row population. Every study was expected to remember to exclude them.
  3. THE WRONG STATISTIC — "big tail is the key ingredient, median can be somewhat managed
     with entry and exit." Ranking by median produced three conclusions that all dissolved.

2026-09-13 (#653 cleanup): these used to pin `scripts/ep_replay.py`'s SOURCE TEXT (reading the
file and grepping for `_NEAR_ZERO_STOP_PCT`, `"mark_r"` inside a hand-sliced window of the
source). That is exactly the brittle shape #653 measures: a harmless refactor of `phase_replay`
(reordering a helper, renaming a local, reformatting an f-string) breaks the test even though
the OPERATOR-FACING report is unchanged, and a real regression in the printed report could slip
through as long as the literal snippets the test grepped for stayed in the file somewhere.

Converted to call the REAL `phase_replay(args)` end-to-end (only the data-loading boundary —
`_scoring_context` / `load_minutes` / `load_daily` / `DATA` — is faked with a small synthetic
alert/bar universe built from the SAME real mechanics `test_ep_replay.py` already drives
directly: `entry_walk`, `walk_campaign`'s ORB-from-9:30-bar derivation, `RULESETS["era_c"]`).
Every guard now runs for real and is asserted against the REAL stdout / REAL written TSV.
"""
from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import scripts.ep_replay as ep_replay_mod

_ET = ZoneInfo("America/New_York")
DAY = date(2026, 8, 3)  # a Monday inside the captured window, well before LAST_SETTLED


def _validate_orb_entry(orb_high, orb_low, atr_14):
    """A faithful copy of backtester/filters.py::validate_orb_entry (zero-range reject,
    range > 1.5x ATR reject) — see tests/test_ep_replay.py::_real_orb_validation for why:
    tests/conftest.py stubs the real module with a MagicMock that cannot be unpacked."""
    orb_range = orb_high - orb_low
    if orb_range <= 0:
        return False, "setup:zero_range"
    if atr_14 and atr_14 > 0 and orb_range > 1.5 * atr_14:
        return False, f"setup:stop_too_wide: {orb_range:.2f} > 1.5x ATR {atr_14:.2f}"
    return True, None


def _mbar(hhmm: str, o, h, l, c, d: date = DAY):
    hh, mm = map(int, hhmm.split(":"))
    return {"m": datetime(d.year, d.month, d.day, hh, mm, tzinfo=_ET),
            "o": o, "h": h, "l": l, "c": c}


def _alert(ticker: str, alert_id: str | None = None, alert_date: date = DAY,
           detected_at_et: str | None = None):
    return {"id": alert_id or ticker, "ticker": ticker, "alert_date": alert_date.isoformat(),
            "detected_at_et": detected_at_et, "score_tier": "HIGH", "gap_pct": "20",
            "rel_volume": "5", "catalyst_quality": "", "vol_percentile": "80",
            "in_active_theme": False}


# ── the three synthetic campaigns every test below composes from ──────────────────────
# NEARZ: orb_high=10.00, orb_low=9.99 -> era_c stop = 2*9.99-10.00 = 9.98, a stop only 0.2%
#        of entry wide (< the 0.5% floor) -> must be EXCLUDED from every R statistic.
# NORMAL: orb_high=10.0, orb_low=9.0 -> stop 8.0 (20% wide, not excluded); settles -1.0R,
#        the same clean day-0 stop-out shape test_ep_replay.py::test_day0_stop_out_... uses.
# OPENH: same ORB as NORMAL, entry fills but no further day-0 bars and no daily bars ->
#        never closes -> open_at_horizon at LAST_SETTLED, same shape
#        test_ep_replay.py's era_b "no daily bars supplied -> stays open" case uses.
_MINUTES = {
    # The fill bar itself must not touch the 9.98 stop or the 10.02 target (both would be
    # "unknowable ordering" abstains, `day0_fill_bar_stop_and_target` /
    # `day0_fill_bar_straddles_stop`) — the stop-hit happens cleanly on the NEXT bar instead.
    ("NEARZ", DAY): [_mbar("09:30", 9.995, 10.00, 9.99, 9.995),
                     _mbar("09:31", 9.99, 10.01, 9.985, 10.00),
                     _mbar("09:32", 9.985, 9.99, 9.70, 9.75)],
    ("NORMAL", DAY): [_mbar("09:30", 9.5, 10.0, 9.0, 9.5),
                      _mbar("09:31", 9.8, 10.05, 9.7, 10.0),
                      _mbar("09:32", 9.5, 9.6, 7.95, 8.2)],
    ("OPENH", DAY): [_mbar("09:30", 9.5, 10.0, 9.0, 9.5),
                     _mbar("09:31", 9.8, 10.05, 9.7, 10.0)],
}
_ALERTS = [_alert("NEARZ"), _alert("NORMAL"), _alert("OPENH")]


def _run_replay(monkeypatch, tmp_path, alerts, minutes, out_name="campaigns.tsv"):
    """Drive the REAL phase_replay end-to-end: fake only the data-loading boundary and the
    output directory. Every guard under test — near-zero-stop exclusion, the dedup pass,
    the censoring warning, tail-first ordering, mark_r emission — runs for real."""
    monkeypatch.setattr(ep_replay_mod, "_scoring_context",
                        lambda: ({"ALERTS": alerts}, {}, {}, {}, []))
    monkeypatch.setattr(ep_replay_mod, "load_minutes", lambda: minutes)
    monkeypatch.setattr(ep_replay_mod, "load_daily", lambda: {})
    monkeypatch.setattr(ep_replay_mod, "DATA", tmp_path)
    monkeypatch.setattr(ep_replay_mod, "validate_orb_entry", _validate_orb_entry)
    args = SimpleNamespace(ruleset="era_c", out=out_name)
    ep_replay_mod.phase_replay(args)
    return tmp_path / out_name


def test_near_zero_stops_are_excluded_by_default(monkeypatch, tmp_path, capsys):
    """MUTATION TARGET: the exclusion filter (`w < _NEAR_ZERO_STOP_PCT`) removed or
    inverted so the near-zero-stop row (NEARZ, a 0.2%-wide stop) is counted alongside a
    real trade — its -1.0R would then silently dilute a real population, the #621/#623
    class the operator caught (two such rows once outweighed 1,577 real ones)."""
    _run_replay(monkeypatch, tmp_path, _ALERTS, _MINUTES)
    out = capsys.readouterr().out
    line = next(l for l in out.splitlines() if l.strip().startswith("R [all alerts]"))
    # Only NORMAL settles at a real stop width; NEARZ must not be in the pool.
    assert "n=1" in line, f"the near-zero-stop row leaked into the population: {line!r}"


def test_the_exclusion_is_announced_not_silent(monkeypatch, tmp_path, capsys):
    """MUTATION TARGET: the exclusion print statement deleted while the filter itself
    stays — a silent exclusion is its own trap (a reader has no way to know a row was
    dropped, or which one)."""
    _run_replay(monkeypatch, tmp_path, _ALERTS, _MINUTES)
    out = capsys.readouterr().out
    assert "excluded 1 settled row" in out, \
        f"the near-zero-stop exclusion must be announced by name/count: {out!r}"
    assert "NEARZ" in out, "the excluded ticker must be named, not just counted"


def test_open_rows_are_reported_on_every_summary_line(monkeypatch, tmp_path, capsys):
    """MUTATION TARGET: the STILL-OPEN warning line deleted from the summary loop.
    open_at_horizon rows (OPENH) must be stated beside every R line — the 09-05 breakeven
    A/B lost CRWD exactly by reading a settled-only summary as if it were complete."""
    _run_replay(monkeypatch, tmp_path, _ALERTS, _MINUTES)
    out = capsys.readouterr().out
    assert "1 row(s) STILL OPEN" in out, \
        f"the one open_at_horizon row (OPENH) must be counted beside the R summary: {out!r}"
    assert "never compare rule-sets on settled" in out, \
        "the warning must say WHY it matters, not just that rows exist"


def test_tail_stats_print_before_the_median(monkeypatch, tmp_path, capsys):
    """The operator's ruling, made mechanical: tail first, median second, on the same
    line. MUTATION TARGET: the print reordered so median comes first — ranking by median
    produced three conclusions that all dissolved once the tail was looked at (operator,
    2026-09-05: "big tail is the key ingredient, median can be somewhat managed")."""
    _run_replay(monkeypatch, tmp_path, _ALERTS, _MINUTES)
    out = capsys.readouterr().out
    line = next(l for l in out.splitlines() if l.strip().startswith("R [all alerts]"))
    assert ">=3R" in line and ">=5R" in line and "p90" in line, \
        f"tail statistics missing from the summary line: {line!r}"
    assert "median" in line
    assert line.index(">=3R") < line.index("median"), \
        "the median must not precede the tail counts"


def test_duplicate_ticker_day_alerts_are_deduped_before_walking(monkeypatch, tmp_path, capsys):
    """MUTATION TARGET: trap 5. The alert feed carries byte-identical duplicate rows, and
    walking both books ONE trade twice — it inflated an era_c read +3.54R -> +3.87R and the
    inflated figure was quoted to the operator. The live system cannot take the same ORB
    entry twice, so replaying the SAME (ticker, alert_date) pair twice must produce exactly
    ONE campaign row, not two."""
    # Same detected_at_et on both duplicate rows — isolates the dedup pass itself from the
    # earliest-detection tie-break (a later detected_at_et changes `submit` and can abstain
    # on entry-window coverage for reasons unrelated to deduping).
    minutes = dict(_MINUTES)
    minutes[("DUPX", DAY)] = _MINUTES[("NORMAL", DAY)]
    alerts = [
        _alert("DUPX", alert_id="a1", detected_at_et=f"{DAY.isoformat()}T09:29:00"),
        _alert("DUPX", alert_id="a2", detected_at_et=f"{DAY.isoformat()}T09:29:00"),
    ]
    out_path = _run_replay(monkeypatch, tmp_path, alerts, minutes)
    captured = capsys.readouterr().out
    assert "deduped 1 duplicate" in captured, \
        f"the duplicate ticker/day alert row must be announced: {captured!r}"
    rows = out_path.read_text().splitlines()[1:]
    dupx_rows = [r for r in rows if r.split("|")[0] == "DUPX"]
    assert len(dupx_rows) == 1, \
        f"the duplicate alert must walk as ONE campaign, not {len(dupx_rows)}"


def test_open_rows_carry_their_mark_so_censoring_is_correctable(monkeypatch, tmp_path):
    """MUTATION TARGET: trap 1, the half that was missing. The summary ANNOUNCED the
    open-at-horizon count but the TSV carried no mark, so a reader who saw the warning
    still had no way to correct for it. It bit hard on 2026-09-06: the loose-trail arms
    held 12-14 positions open (PLTR, TEAM, HTFL — operator-labelled real EPs) against 2 for
    the live trail, and a realized-only sum read them as -19.79R. The written TSV must
    carry `mark_r` as its own column, and the open row must actually populate it."""
    out_path = _run_replay(monkeypatch, tmp_path, _ALERTS, _MINUTES)
    lines = out_path.read_text().splitlines()
    cols = lines[0].split("|")
    assert "mark_r" in cols and "realized_r" in cols and "status" in cols, \
        f"open rows must be able to emit their mark, not just be counted: {cols!r}"
    mark_ix, status_ix, ticker_ix = cols.index("mark_r"), cols.index("status"), cols.index("ticker")
    rows = [l.split("|") for l in lines[1:]]
    openh = next(r for r in rows if r[ticker_ix] == "OPENH")
    assert openh[status_ix] == "open_at_horizon"
    assert openh[mark_ix] != "", "the open row must populate mark_r, not leave it blank"
    normal = next(r for r in rows if r[ticker_ix] == "NORMAL")
    assert normal[status_ix] == "settled"
    assert normal[mark_ix] == "", "a cleanly-settled row has no mark to carry"
