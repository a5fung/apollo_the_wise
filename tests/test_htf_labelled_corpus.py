"""HTF labelled corpus — replay the SHIPPED detector over trader-labelled names.

Members + labels: `tests/fixtures/htf_labelled.py`. Bars: `tests/fixtures/htf_labelled_bars.psv`.
State is threaded day by day the way `flag_scan` threads it (the three 5-day-lookback
queries: prior pivot, yesterday's stage, recent stages), from the variant's own prior
outputs — not from stored rows.

#697 item 6: every member carries a `label_kind` (htf / consolidation / pointer / negative) and the
suite asserts BY KIND (`check_member`, applied to the replay of every member):
  - htf / consolidation (positives): a pushable stage (TIGHTENING or better) inside the
    `_PRE_TRADE_SESSIONS` scan sessions strictly before `label_date`, OR a declared KNOWN MISS that
    names the gate (`known_miss_gate` == the recorded rejection prefix) — and a declared miss the
    detector now catches FAILS, so a closed miss cannot stay on the books.
  - pointer: recorded, never scored — pinned as not-a-hit.
  - negative: never a hit; a negative whose raw function output is still actionable must name the
    layer above the function that closes it (`closed_by`).
The checker is pure (member + replay in, AssertionError out) so
`tests/test_697_corpus_label_kinds.py` can prove it bites on deliberately wrong members.
"""
from __future__ import annotations

import bisect
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import pytest

from agents.market_intelligence import flag_detector as fd
from tests.fixtures.htf_labelled import HTF_LABELLED, LABEL_KINDS, POSITIVE_KINDS, HTFLabelledMember

_BARS = Path(__file__).parent / "fixtures" / "htf_labelled_bars.psv"
_ACTIONABLE = ("WATCH", "TIGHTENING", "COILED", "TRIGGERED")
# "Pushable" = what the digest / Friday list actually surfaces: TIGHTENING or better
# (`flag_detector._PUSH_STAGES` + TRIGGERED). WATCH is on the board but is not pushed.
_PUSHABLE = ("TIGHTENING", "COILED", "TRIGGERED")
# "Caught it" = pushable inside this many SCAN sessions before the label date — the scope doc's own
# measure (htf_scope_2026-10-10.md §2a: the 09-17 row "is exactly the 5th scan day before the 09-24 label").
_PRE_TRADE_SESSIONS = 5
_REPLAY_FROM = date(2026, 6, 15)     # two weeks of state before the earliest labelled window


def _load_bars() -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for line in _BARS.read_text().splitlines():
        if not line.strip():
            continue
        t, d, o, h, l, c, v = line.split("|")
        out[t].append({"trade_date": date.fromisoformat(d), "open_price": float(o),
                       "high_price": float(h), "low_price": float(l), "close": float(c),
                       "volume": float(v)})
    for t in out:
        out[t].sort(key=lambda r: r["trade_date"])
    return out


def _replay(ticker: str, bars: list[dict], through: date,
            replay_from: date | None = None) -> dict[date, dict]:
    """Shipped compute_flag_metrics, one scan per trading day, prod-style state threading.

    `replay_from` defaults to `_REPLAY_FROM`; a member whose window starts earlier sets its own
    (`HTFLabelledMember.replay_from`) — the default is NOT moved, because a different cold-start
    day re-threads the recorded pivots of the existing members (OUST: $49.39 instead of $48.83)."""
    start = replay_from or _REPLAY_FROM
    dates = [r["trade_date"] for r in bars]
    prior: list[dict] = []
    out: dict[date, dict] = {}
    for d in dates:
        if d < start or d > through:
            continue
        # Row-count slice, matching get_recent_daily_history's TRADING-day semantics
        # (2026-09-05 fix) — fd._HISTORY_DAYS is now a row count, not a calendar span, so
        # the window here must be "last N rows ending at d", not "d minus N calendar days".
        hi = bisect.bisect_right(dates, d)
        lo = max(0, hi - fd._HISTORY_DAYS)
        rows = bars[lo:hi]
        cutoff = d - timedelta(days=5)
        window = [m for m in prior if cutoff <= m["scan_date"] < d]
        ppiv = next(((m["pivot_high_date"], m["pivot_high_price"])
                     for m in reversed(window) if m["pivot_high_date"] is not None), None)
        m = fd.compute_flag_metrics(
            rows, ticker=ticker,
            yesterday_stage=window[-1]["stage"] if window else None,
            # #697 item 5: prod hands the hysteresis whether yesterday's STORED row was itself a hold,
            # so a hold is never followed by a hold — thread it exactly as run_flag_scan does.
            yesterday_was_held=bool(window[-1].get("held_from_stage")) if window else False,
            recent_stages=[w["stage"] for w in window],
            prior_pivot_date=ppiv[0] if ppiv else None,
            prior_pivot_high=ppiv[1] if ppiv else None,
        )
        m["scan_date"] = d
        prior.append(m)
        out[d] = m
    return out


@pytest.fixture(scope="module")
def bars():
    b = _load_bars()
    assert b, "htf_labelled_bars.psv is empty"
    return b


def pushable_before(label_date: date, res: dict[date, dict],
                    sessions: int = _PRE_TRADE_SESSIONS) -> list[tuple[date, str]]:
    """The (scan_date, stage) pairs that were TIGHTENING-or-better inside the `sessions` scan
    sessions STRICTLY before `label_date` (the label day itself and anything after do not count —
    the point is whether the board had it before the trade)."""
    prior = sorted(d for d in res if d < label_date)[-sessions:]
    return [(d, res[d]["stage"]) for d in prior if res[d]["stage"] in _PUSHABLE]


def check_member_static(member: HTFLabelledMember) -> None:
    """Fixture-level contract — no replay needed."""
    tag = f"{member.ticker} {member.label_date}"
    assert member.label_kind in LABEL_KINDS, (
        f"{tag}: label_kind must be one of {LABEL_KINDS}, got {member.label_kind!r}")
    assert member.label_source and "operator" in member.label_source, (
        f"{tag}: label_source must name where the operator-shared label came from")
    assert member.expected == "actionable" or member.expected.startswith("rejected:"), (
        f"{tag}: expected must be 'actionable' or 'rejected:<reason-prefix>', got {member.expected!r}")
    assert member.assert_dates, f"{tag}: at least one assert date"
    if member.label_kind in ("consolidation", "pointer"):
        # the new kinds are exactly where a label could be invented: demand the verbatim source
        assert member.quote_file, (
            f"{tag}: a {member.label_kind} member must name the repo doc that holds his words "
            f"verbatim (quote_file) — labels come from his own words, never inference")
    if member.label_kind != "negative":
        assert not member.closed_by, f"{tag}: closed_by only applies to a negative"
    if member.label_kind not in POSITIVE_KINDS:
        assert not member.known_miss_gate, (
            f"{tag}: known_miss_gate only applies to htf / consolidation (a {member.label_kind} "
            f"never asserts a hit, so there is no miss to declare)")


def check_member(member: HTFLabelledMember, res: dict[date, dict]) -> None:
    """The by-kind assertion. `res` = the member's replay through the SHIPPED detector
    (scan_date -> metrics). Raises AssertionError on a violation."""
    check_member_static(member)
    tag = f"{member.ticker} {member.label_date} [{member.label_kind}]"
    positive = member.label_kind in POSITIVE_KINDS
    # 1. the recorded verdict on each assert date (what the detector DOES today, not what we wish)
    for d in member.assert_dates:
        m = res.get(d)
        assert m is not None, f"{tag}: no bar on {d}"
        if member.expected == "actionable":
            if positive:
                assert m["stage"] in _ACTIONABLE, (
                    f"{tag} {d}: MUST-NOT-MISS regressed — stage={m['stage']} reason={m['reason']}")
            else:
                # a pointer / negative recorded as actionable is a RECORDED LEAK, not a must-not-miss
                assert m["stage"] in _ACTIONABLE, (
                    f"{tag} {d}: the RECORDED verdict changed (it was actionable at function level, "
                    f"stage={m['stage']} reason={m['reason']}) — if the function now rejects it, "
                    f"update `expected` and drop `closed_by` in the same commit")
        else:
            prefix = member.expected.split(":", 1)[1]
            assert m["stage"] not in _ACTIONABLE and (m["reason"] or "").startswith(prefix), (
                f"{tag} {d}: the RECORDED verdict changed (stage={m['stage']} "
                f"reason={m['reason']}, expected prefix {prefix!r}). If this is deliberate, "
                f"update the member's `expected` AND docs/setups/htf.md § Known limitations "
                f"in the same commit."
            )
            if prefix == "runup_":
                assert m["runup_pct"] is not None and m["runup_pct"] < fd._RUNUP_MIN_RATIO - 1.0
    # 2. the kind contract
    if positive:
        reached = pushable_before(member.label_date, res)
        if member.expected == "actionable":
            assert reached, (
                f"{tag}: MUST-NOT-MISS regressed — no TIGHTENING-or-better in the "
                f"{_PRE_TRADE_SESSIONS} scan sessions before {member.label_date}")
            assert not member.known_miss_gate, (
                f"{tag}: declares a known miss ({member.known_miss_gate!r}) but expected is "
                f"'actionable' — a member is either caught or a declared miss, not both")
        else:
            assert member.known_miss_gate, (
                f"{tag}: not caught, so it must be a DECLARED known miss naming the gate "
                f"(known_miss_gate) — an unexplained miss is a finding, not a fixture entry")
            assert member.expected == f"rejected:{member.known_miss_gate}", (
                f"{tag}: known_miss_gate {member.known_miss_gate!r} does not match the recorded "
                f"rejection {member.expected!r} — the gate named must be the gate that fires")
            assert not reached, (
                f"{tag}: declared a known miss at {member.known_miss_gate!r} but the detector now "
                f"reaches {reached} before {member.label_date} — the miss is CLOSED; retire the "
                f"declaration (expected -> 'actionable', drop known_miss_gate) in the same commit")
    elif member.label_kind == "pointer":
        # recorded, never scored: it must not be asserted as a hit
        assert member.expected.startswith("rejected:"), (
            f"{tag}: a pointer is never asserted as a hit (expected must be 'rejected:<prefix>')")
    else:  # negative
        if member.expected == "actionable":
            assert member.closed_by, (
                f"{tag}: the function output is a hit on a name he said is not an HTF — name the "
                f"layer above the function that closes it (closed_by)")
        else:
            assert not member.closed_by, f"{tag}: closed_by only applies to an actionable negative"


def hit_tally(members, replays: dict[str, dict[date, dict]]) -> dict:
    """The HTF hit count: `htf`-kind members ONLY (a consolidation example or a pointer is never an
    HTF hit, however the detector scores it). `replays` is keyed by `member_id`."""
    htf = [m for m in members if m.label_kind == "htf"]
    return {"n": len(htf),
            "caught": [member_id(m) for m in htf if pushable_before(m.label_date, replays[member_id(m)])]}


def member_id(m: HTFLabelledMember) -> str:
    return f"{m.ticker}_{m.label_date}"


def replay_member(member: HTFLabelledMember, bars: dict[str, list[dict]]) -> dict[date, dict]:
    """The member's replay, through its last assert date AND the session before its label date
    (the pre-trade window is judged on the sessions before the label, which can follow the last
    assert date — GH / HNGE-June are labelled on a Saturday)."""
    assert member.ticker in bars, f"no bars for {member.ticker} in {_BARS.name}"
    return _replay(member.ticker, bars[member.ticker],
                   through=max(max(member.assert_dates), member.label_date),
                   replay_from=member.replay_from)


def test_every_member_has_an_operator_sourced_label():
    for m in HTF_LABELLED:
        check_member_static(m)


@pytest.mark.parametrize("member", HTF_LABELLED, ids=[member_id(m) for m in HTF_LABELLED])
def test_labelled_member_matches_recorded_verdict(member, bars):
    """Replays the member through the SHIPPED detector and asserts BY KIND (`check_member`).

    `expected` is either "actionable" (must be in _ACTIONABLE) or "rejected:<prefix>"
    (must NOT be in _ACTIONABLE and its `reason` must start with `<prefix>`) — generalised
    2026-09-04 (#592/#610 corpus build) from the original runup-only check so a member can
    be rejected by ANY gate (stage2, flag-depth, base-age, runup, ...), not just runup. The
    runup case keeps its extra numeric check for backward-compat rigor. #697 item 6 (2026-10-11)
    adds the kind contract on top: a positive reaches a pushable stage before its date or
    declares the gate that stops it; a pointer / negative is never asserted as a hit.
    """
    check_member(member, replay_member(member, bars))
