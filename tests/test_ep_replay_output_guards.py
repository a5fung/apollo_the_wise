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
"""
import pathlib
import re

SRC = "scripts/ep_replay.py"


def _summary_block() -> str:
    with open(SRC, encoding="utf-8") as fh:
        src = fh.read()
    start = src.index("_NEAR_ZERO_STOP_PCT = 0.5")
    return src[start:start + 3500]


def test_near_zero_stops_are_excluded_by_default():
    block = _summary_block()
    assert "_degenerate" in block and "_NEAR_ZERO_STOP_PCT" in block, \
        "near-zero-stop rows must be excluded by the harness, not by each study remembering"
    assert re.search(r"w < _NEAR_ZERO_STOP_PCT", block), "the exclusion comparison is missing"


def test_the_exclusion_is_announced_not_silent():
    assert "excluded" in _summary_block(), \
        "a silent exclusion is its own trap — the count must be printed"


def test_open_rows_are_reported_on_every_summary_line():
    block = _summary_block()
    assert "STILL OPEN" in block, "open_at_horizon rows must be stated beside every R summary"
    assert "openpool" in block, "the open pool must be paired with its settled pool"
    assert "never compare rule-sets on settled" in block, \
        "the warning must say WHY it matters, not just that rows exist"


def test_tail_stats_print_before_the_median():
    """The operator's ruling, made mechanical: tail first, median second, on the same line."""
    block = _summary_block()
    # Anchor to an actual print statement. Matching the first line that merely CONTAINS
    # ">=3R" would evaluate a COMMENT the moment someone documents the format above the
    # print — the test would then pass while asserting nothing. That vacuous-guard class
    # bit twice on 2026-09-05 (the #625 cron parser, and the market-cap mock), so it is
    # closed here by construction rather than by remembering.
    line = next((l for l in block.splitlines()
                 if ">=3R" in l and "print(" in l), None)
    assert line, "no tail PRINT line found in the summary — the guard would be vacuous"
    if "median" in line:
        assert line.index(">=3R") < line.index("median"), \
            "the median must not precede the tail counts"
    for token in (">=3R", ">=5R", "p90"):
        assert token in block, f"tail statistic {token} is missing from the summary"


def test_the_guards_sit_in_the_replay_phase_not_a_probe():
    """A guard in a one-off probe protects one study; here it protects every future run."""
    with open(SRC, encoding="utf-8") as fh:
        src = fh.read()
    phase = src[src.index("def phase_replay"):]
    assert "_NEAR_ZERO_STOP_PCT" in phase[:6000], \
        "the guards must live inside phase_replay so every replay inherits them"


def test_duplicate_ticker_day_alerts_are_deduped_before_walking():
    """MUTATION TARGET: trap 5. The alert feed carries byte-identical duplicate rows, and
    walking both books ONE trade twice — it inflated an era_c read +3.54R -> +3.87R and the
    inflated figure was quoted to the operator. The live system cannot take the same ORB
    entry twice. Anchored on the dedup keying, so deleting it fails the build."""
    src = (pathlib.Path(__file__).resolve().parents[1] / "scripts" / "ep_replay.py").read_text()
    body = src.split("def phase_replay(")[1].split("\ndef ")[0]
    assert 'k = (a["ticker"], a["alert_date"])' in body, "dedup key gone from phase_replay"
    assert "for a in alerts:" in body, "the walk no longer iterates the deduped list"
    assert "deduped" in body, "the drop must be announced, not silent"


def test_open_rows_carry_their_mark_so_censoring_is_correctable():
    """MUTATION TARGET: trap 1, the half that was missing. The summary ANNOUNCED the
    open-at-horizon count but the TSV carried no mark, so a reader who saw the warning still
    had no way to correct for it. It bit hard on 2026-09-06: the loose-trail arms held 12-14
    positions open (PLTR, TEAM, HTFL — operator-labelled real EPs) against 2 for the live
    trail, and a realized-only sum read them as -19.79R. `mark_r` must be an emitted column."""
    src = (pathlib.Path(__file__).resolve().parents[1] / "scripts" / "ep_replay.py").read_text()
    body = src.split("def phase_replay(")[1].split("\ndef ")[0]
    cols = body.split("cols = [")[1].split("]")[0]
    assert '"mark_r"' in cols, "open rows must emit their mark, not just be counted"
    assert '"realized_r"' in cols and '"status"' in cols
