"""#720 — the monthly comprehensive trade review: RUNNER.

Plan: docs/analysis/720_monthly_review_plan_2026-11-08.md (pre-registered 2026-11-08, before any outcome
row of the first window was read; revised the same day against the challenge in the 11-08 session — every
change is a decided item in the plan's §8, none went to the operator). This file holds the queries
(capture/*.sql, read-only) and every computation as a pure function over CSV dicts, so the review can be
unit-tested on INVENTED fixtures (tests/test_720_monthly_review.py, in the units prod writes) and run on
11-29 with no new code.

CAPTURE ONCE, READ MANY. Run day:
    0. python run_review.py --emit-predicates capture/predicates.sql   (the five reviews' predicate_sql, copied
       from data_gated_reviews.yaml by this script — never re-typed; the test pins file == YAML)
    1. for f in capture/*.sql: docker exec -i apollo-postgres psql -q -X -v ON_ERROR_STOP=1 -U <u> -d <db> \
           < $f > runs/<date>/data/<name>.csv            (each .sql begins SET default_transaction_read_only = on)
    2. python run_review.py --manifest runs/<date>      (row counts + md5 + capture timestamp)
    3. python run_review.py --report   runs/<date>      (reads the CSVs, never the database) -> review.md / review.out

Nothing here opens a database connection. THE LINE: the review proposes; any entry / stop / sizing / partial /
exit change goes through CHANGE_PROCESS + N >= 10 + his sign-off.
"""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import re
import statistics
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from math import comb
from pathlib import Path
from typing import Any, Callable, Iterable, Optional
from zoneinfo import ZoneInfo

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from agents.market_intelligence.book_geometry_arms import capped_dollar_r  # noqa: E402
from agents.market_intelligence.live_fill_counterfactuals import GAP_RETRY_SESSIONS  # noqa: E402
from agents.market_intelligence.rule_eras import (  # noqa: E402
    ADMISSION_SWITCHES, BREAKEVEN_ARM_R_VALUE, admission_era_as_of, exit_era_label, exit_era_start, exit_rules_as_of)
from agents.market_intelligence.sell_discipline import trade_realized_r, trade_risk_per_share  # noqa: E402

try:  # the recorder's own calendar; weekdays-only when it cannot load (stated on the page)
    from agents.market_intelligence.trading_calendar import get_market_status as _mkt
    def is_trading_day(dd: date) -> bool:  # noqa: E302
        return bool(_mkt(dd).is_trading_day)
    CALENDAR = "trading_calendar"
except Exception:  # loud-ok: a missing calendar degrades to weekdays and says so
    def is_trading_day(dd: date) -> bool:  # type: ignore[misc]
        return dd.weekday() < 5
    CALENDAR = "weekdays_only"

_ET = ZoneInfo("America/New_York")
_UTC = ZoneInfo("UTC")

# ── pinned constants (the plan, §1 / §2 / §5 / §6 / §8) ─────────────────────────────────────────
FIRST_WINDOW_START = date(2026, 8, 16)     # era C start = the recorder's BACKFILL_FROM (D3)
READABLE_MIN = 3                           # fewer paired / readable trades -> CAN'T TELL
PROPOSE_MIN = 10                           # the CHANGE_PROCESS N
TIE = 0.05
FIDELITY_ABS = 0.25
FIDELITY_REL = 0.10                        # tol = max(0.25, 0.10 x |live R|) — nothing else (§5)
SMALL_POSITION_SHARES = 3                  # the whole-share CLASS (a label on a miss, never a bound)
TAIL_WIN_R = 4.0
TAIL_LOSS_R = -1.5
MISSED_WALK_SESSIONS = 10
STOPPED_THEN_RAN_SESSIONS = 5
POST_EXIT_HIGH_SESSIONS = 10               # the tail's "what the chart did after our exit"
BREAKEVEN_TOL_R = 0.05                     # |stop fill − entry| <= 0.05 R = "at breakeven" (hard-stop frame)
RECORDER_GAP_SESSIONS = GAP_RETRY_SESSIONS  # a closed fill older than this with no recorder rows (or no settled
#                                             control pair) = a recorder gap, named on the page (finding 10, re-challenge)
BREAKOUT_ERA = "bp1"                       # the pp exit as deployed 2026-10-31
# #718 flipped ON 2026-11-03 15:05:28 UTC (after the ORB) -> first acting session 2026-11-04 (D5) — read from the
# module's one dated record (the ADMISSION_SWITCHES row named open_below_floor), never re-typed here
OPEN_FLOOR_FIRST_SESSION: date = next(fs for fs, name, *_ in ADMISSION_SWITCHES if name == "open_below_floor")
PRE_1104, POST_1104 = "pre-11-04", "post-11-04"   # the second half of every admission-cell key (finding 3)

# the recorder's own nightly audit rows (live_fill_counterfactuals.py, one `_recorded` row per run, `_error` per
# failure) — captured so a month with no older closes can still show a dead recorder (finding 10)
RECORDER_RUN_EVENT = "live_fill_counterfactual_recorded"
RECORDER_ERROR_EVENT = "live_fill_counterfactual_error"
RECORDER_JOB_WEEKDAYS_ONLY = True          # scheduler: CronTrigger(hour=18, minute=4, day_of_week="mon-fri")
RECORDER_FIRST_SESSION = date(2026, 9, 3)  # the #482 job's first nightly run (rule_eras docstring, scheduler job list, the 482
#                                             YAML, commit history all date it 2026-09-03); it BACKFILLED fills from 08-16 that night,
#                                             so sessions 08-17..09-02 never had a run and are not "missing" (advisor, 2026-11-08)

# the full capture set = every capture/*.sql next to this file; build_report reports each one whose CSV is
# missing as NOT CAPTURED instead of reading an empty month (finding 2). Derived, never a typed list.
REQUIRED_CAPTURES: tuple[str, ...] = tuple(sorted(p.stem for p in (_HERE / "capture").glob("*.sql")))
NOT_CAPTURED = "n/a — not captured"

# runner_rule_sweep_recut's safeguard arm, VERBATIM from its predicate_sql (reused for the void check, §7)
SAFEGUARD_VOID_EXCLUDED = ("drawdown_breaker", "kill_scale_band", "manual_trading_halt", "breakout_v1_paper")
SAFEGUARD_ANSWERED_THROUGH = "2026-11-03 15:05:29+00"   # the #718 flip was answered the same day (the YAML's words)

CONTROLS = ("live_actual", "live_replay")
STOP_ARMS = ("stop_orb_low", "stop_adr_050", "stop_adr_075", "stop_orb_3r", "stop_low_of_day")
ENTRY_ARMS = ("entry_first_hour_bar", "book_first_hour_low_of_day")
HARVEST_ARMS = ("harvest_no_breakeven", "harvest_trail_only", "harvest_t3", "harvest_legacy_2r")
TRAIL_ARMS = ("trail_pivot_swing", "trail_character_ma")
LENS_ARMS = {"buy_point": ENTRY_ARMS, "stop": STOP_ARMS, "partials": HARVEST_ARMS, "exits": TRAIL_ARMS}
ALL_ARMS = STOP_ARMS + HARVEST_ARMS + TRAIL_ARMS + ENTRY_ARMS
FILL_FACTS = "fill_facts"

# the exit-leg vocabulary, from the FIVE writers (order_manager.py 1318 / 4928 / 6389 / 6551 / 6626): the two
# stop finalizers write stop_hit, the partial finalizer partial_profit, and the two full-exit finalizers write the
# `exit_reason` of the full_exit order row (`_record_full_exit_order`): sma_trail_stop (the trail AND the depth
# next-open sale, `execute_depth_open_sale`'s default), breakout_stall_cut, the breakout width sale (a sentence
# starting setup:stop_too_wide_after_fill) and the fallback 'exit'. gap_through / intraday_stop are NEVER legs.
REASON_STOP = "stop_hit"
REASON_PARTIAL = "partial_profit"
REASON_TRAIL = "sma_trail_stop"
REASON_STALL = "breakout_stall_cut"
REASON_WIDE_AFTER_FILL = "setup:stop_too_wide_after_fill"
REASON_FALLBACK = "exit"
EXIT_REASONS = (REASON_STOP, REASON_PARTIAL, REASON_TRAIL, REASON_STALL, REASON_WIDE_AFTER_FILL, REASON_FALLBACK)
DEPTH_RULE = "depth"

MISSED_EVENT = "breakout_v1_missed_by_slots"
HOLD_EVENT = "breakout_v1_entry_hold"
FILL_STOP_EVENT = "breakout_v1_fill_stop_checked"
UNREADABLE_EVENT = "breakout_v1_missed_unreadable"
ENTRY_DAY_EVENT = "breakout_v1_entry_day"

FOLDED_REVIEWS = ("bracket_geometry_variants_parked", "live_fill_counterfactuals_first_read_482",
                  "exit_tune_cohort_review", "runner_rule_sweep_recut", "stop_too_wide_outcome_cohort")

VERDICTS = ("CAN'T TELL", "NOTHING", "WATCH", "PROPOSE")
GRADE_LOW, GRADE_HIGH = "no", "good"       # his chart-sheet vocabulary (tests/fixtures/breakout_list_grades.py; D4)


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# helpers
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def f(x: Any) -> Optional[float]:
    if x is None or x == "":
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def d(x: Any) -> Optional[date]:
    if x is None or x == "":
        return None
    if isinstance(x, datetime):
        return x.date()
    if isinstance(x, date):
        return x
    return date.fromisoformat(str(x)[:10])


def _et(ts: Any) -> Optional[datetime]:
    if ts is None or ts == "":
        return None
    if isinstance(ts, datetime):
        dt = ts if ts.tzinfo else ts.replace(tzinfo=_UTC)
        return dt.astimezone(_ET)
    s = str(ts).strip().replace(" ", "T", 1)
    if s.endswith("+00"):
        s = s[:-3] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_UTC)
    return dt.astimezone(_ET)


def et_date(ts: Any) -> Optional[date]:
    """The ET date of a TIMESTAMPTZ as psql prints it ('2026-10-07 13:31:05.123+00' or ISO)."""
    dt = _et(ts)
    return None if dt is None else dt.date()


def et_minute(ts: Any) -> Optional[str]:
    dt = _et(ts)
    return None if dt is None else dt.strftime("%H:%M")


def truthy(x: Any) -> bool:
    return str(x).strip().lower() in ("t", "true", "1", "yes")


def median(vals: Iterable[Optional[float]]) -> Optional[float]:
    vals = [v for v in vals if v is not None]
    return statistics.median(vals) if vals else None


def fmt(v: Optional[float], p: int = 2) -> str:
    return "n/a" if v is None else f"{v:+.{p}f}"


def read_csv(path: Path) -> list[dict]:
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh))


def sessions_after(a: date, b: date) -> int:
    """Trading sessions strictly after `a` up to and including `b` (the recorder's own calendar)."""
    n, cur = 0, a + timedelta(days=1)
    while cur <= b:
        n += is_trading_day(cur)
        cur += timedelta(days=1)
    return n


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# §1 population
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def lane_of(trade: dict) -> str:
    mode, st = (trade.get("account_mode") or ""), (trade.get("signal_type") or "")
    if mode == "live" and st == "magna53":
        return "L1"
    if mode == "paper" and st == "magna53_smallcap":
        return "L2"
    if mode == "paper" and st == "breakout_v1":
        return "L3"
    return "L4"


def era_of(trade: dict) -> str:
    """The exit era from the ROW. breakout_v1 rows get BREAKOUT_ERA and are REFUSED by the magna53 function
    (it would read era_c); anything else goes through rule_eras.exit_era_label with the row's exit_rule."""
    st = trade.get("signal_type") or None
    rule = trade.get("exit_rule") or None
    if st == "breakout_v1" or rule == "breakout_pp":
        if st != "breakout_v1" or rule != "breakout_pp":
            raise ValueError(f"trade {trade.get('id')}: breakout_pp / breakout_v1 stamp mismatch ({st}, {rule})")
        return BREAKOUT_ERA
    return exit_era_label(d(trade["alert_date"]), st, exit_rule=rule)


def admission_era_of(trade: dict, stamp_row: Optional[dict] = None) -> tuple[Optional[str], str]:
    """-> (label, source). The recorder's `admission_era` stamp when a row exists; else derived from the alert
    date through rule_eras.admission_era_as_of and SAID SO ('derived'). Breakout rows: n/a (no magna53 admission)."""
    if lane_of(trade) == "L3":
        return None, "n/a"
    if stamp_row and stamp_row.get("admission_era"):
        return str(stamp_row["admission_era"]), "recorder"
    ad = d(trade.get("alert_date"))
    return (admission_era_as_of(ad) if ad else None), "derived"


def post_open_floor(trade: dict) -> bool:
    """D5: alerted on/after the #718 open-below-floor rule's first acting session. rule_eras.ADMISSION_SWITCHES
    carries the row since 2026-11-08, but the recorder rows written 11-04..11-07 were stamped BEFORE it existed
    (the 08-31 label), so the stamp alone cannot split era E — this flag does, on every lens line."""
    ad = d(trade.get("alert_date"))
    return bool(ad and ad >= OPEN_FLOOR_FIRST_SESSION)


def admission_cell_key(trade: dict, stamp_row: Optional[dict] = None) -> tuple[str, str]:
    """The admission cell a fill belongs to: (admission-era label, pre/post 11-04) — finding 3 of the re-challenge.
    I16: a fill alerted on/after 2026-11-04 takes the DERIVED label (rule_eras.admission_era_as_of), because the
    recorder stamped the 11-04..11-07 rows before the #718 row existed; the stamp still prints beside it (I12) and
    the disagreement is listed in review.out. Before 11-04 the stamp wins (the recorder saw the trade)."""
    if lane_of(trade) == "L3":
        return "n/a", PRE_1104
    post = post_open_floor(trade)
    if post:
        ad = d(trade.get("alert_date"))
        return (admission_era_as_of(ad) if ad else "unknown"), POST_1104
    label, _src = admission_era_of(trade, stamp_row)
    return (label or "unknown"), PRE_1104


def _cell_key_of(fl: dict) -> tuple[str, str]:
    """A fill dict's admission cell (`admission_cell` when build_report set it; else from its label + flag)."""
    key = fl.get("admission_cell")
    if key:
        return tuple(key)  # type: ignore[return-value]
    return str(fl.get("admission_era") or "unknown"), (POST_1104 if fl.get("post_1104") else PRE_1104)


def in_window(trade: dict, start: date, end: date) -> bool:
    """Closed, with closed_at's ET date in [start, end]. Open rows are never in a window."""
    if (trade.get("status") or "") != "closed":
        return False
    cd = et_date(trade.get("closed_at"))
    return cd is not None and start <= cd <= end


def population(trades: list[dict], start: date, end: date, read_1106_ids: Iterable[Any] = ()) -> dict:
    """Every row -> lane, era, in_window, excluded class; eras cumulative per lane. Never pooled."""
    read_1106 = {str(x) for x in read_1106_ids}
    out = {"rows": [], "by_lane_era": defaultdict(lambda: {"window": 0, "carried": 0, "open": 0,
                                                            "excluded": [], "no_r": [], "flagged": []})}
    for t in trades:
        lane, era = lane_of(t), era_of(t)
        win = in_window(t, start, end)
        closed = (t.get("status") or "") == "closed"
        excl = "pnl_attribution" if (t.get("pnl_attribution") or "") else None
        r = trade_realized_r(t) if closed else None
        row = {"id": str(t.get("id")), "ticker": t.get("ticker"), "lane": lane, "era": era, "in_window": win,
               "closed": closed, "excluded": excl, "realized_r": r,
               "no_r": closed and excl is None and trade_risk_per_share(t) is None,
               "reentry": str(t.get("entry_attempt") or "1") == "2", "read_1106": str(t.get("id")) in read_1106}
        out["rows"].append(row)
        cell = out["by_lane_era"][(lane, era)]
        if not closed:
            cell["open"] += 1
        elif win:
            cell["window"] += 1
        else:
            cell["carried"] += 1
        if excl:
            cell["excluded"].append(t.get("ticker"))
        if row["no_r"]:
            cell["no_r"].append(t.get("ticker"))
        if row["reentry"]:
            cell["flagged"].append(t.get("ticker"))
    return out


def era_mismatches(trades: list[dict], cf_rows: list[dict]) -> list[str]:
    """L1 cross-check: the derived era must equal the recorder's exit_era on every fill. Non-empty = STOP."""
    stamped = {}
    for r in cf_rows:
        stamped.setdefault(str(r["trade_id"]), r.get("exit_era"))
    bad = []
    for t in trades:
        if lane_of(t) != "L1":
            continue
        rec = stamped.get(str(t.get("id")))
        if rec is not None and rec != era_of(t):
            bad.append(f"{t.get('ticker')} trade {t.get('id')}: derived {era_of(t)} vs recorder {rec}")
    return bad


def recorder_gaps(trades: list[dict], cf_rows: list[dict], run_date: date) -> dict:
    """A dead recorder must not read as a thin era. Per era (L1): fills / fills with any recorder row / settled
    control pairs, the NAME of every closed fill older than RECORDER_GAP_SESSIONS sessions with no rows (`gaps`),
    and the NAME of every closed fill that old WITH rows but no settled control pair (`unsettled` — the recorder
    wrote something and never settled live_actual + live_replay; finding 10 of the re-challenge)."""
    rows_by_tid: dict[str, list[dict]] = defaultdict(list)
    for r in cf_rows:
        rows_by_tid[str(r["trade_id"])].append(r)
    out: dict[str, dict] = {}
    for t in trades:
        if lane_of(t) != "L1":
            continue
        era = era_of(t)
        cell = out.setdefault(era, {"fills": 0, "with_rows": 0, "settled_pairs": 0, "gaps": [], "unsettled": []})
        cell["fills"] += 1
        rows = rows_by_tid.get(str(t["id"]), [])
        cd = et_date(t.get("closed_at"))
        old_close = (t.get("status") or "") == "closed" and cd is not None and sessions_after(cd, run_date) > RECORDER_GAP_SESSIONS
        name = f"{t.get('ticker')} (trade {t.get('id')}, closed {cd})"
        if rows:
            cell["with_rows"] += 1
            if all(any(r["arm"] == c and r.get("outcome") == "settled" for r in rows) for c in CONTROLS):
                cell["settled_pairs"] += 1
            elif old_close:
                cell["unsettled"].append(name)
        elif old_close:
            cell["gaps"].append(name)
    return out


def recorder_gap_count(gaps: dict) -> int:
    """Every named fill the recorder owes us: no rows, or rows but no settled control pair, past the retry window."""
    return sum(len(c.get("gaps", [])) + len(c.get("unsettled", [])) for c in gaps.values())


def recorder_runs(audit_rows: list[dict], start: date, end: date) -> dict:
    """The recorder's own heartbeat (finding 10): the sessions in [max(start, RECORDER_FIRST_SESSION), end] the
    18:04 ET job should have run (weekdays that are trading days), the ET dates with a `_recorded` row, the sessions
    with none (NAMED), the `_error` rows (count + the first few summaries). `ran 0 of N` is a dead recorder even in
    a month with no older closes; the sessions before the job existed are not counted as missing."""
    ran_days = {et_date(r.get("created_at")) for r in audit_rows if r.get("event_type") == RECORDER_RUN_EVENT}
    ran_days.discard(None)
    errors = [r for r in audit_rows if r.get("event_type") == RECORDER_ERROR_EVENT]
    start = max(start, RECORDER_FIRST_SESSION)
    sessions, cur = [], start
    while cur <= end:
        if is_trading_day(cur) and (cur.weekday() < 5 or not RECORDER_JOB_WEEKDAYS_ONLY):
            sessions.append(cur)
        cur += timedelta(days=1)
    missing = [s for s in sessions if s not in ran_days]
    return {"sessions": len(sessions), "ran": len([s for s in sessions if s in ran_days]), "missing": missing, "from": start,
            "last_run": max(ran_days) if ran_days else None, "error_rows": len(errors),
            "error_samples": [str(r.get("summary") or "")[:120] for r in errors[:3]]}


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# exits legs — the vocabulary the five writers produce
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def exits_legs(trade: dict) -> list[dict]:
    raw = trade.get("exits")
    if not raw:
        return []
    legs = raw if isinstance(raw, list) else json.loads(raw)
    return [lg for lg in legs if isinstance(lg, dict)]


def reason_bucket(reason: Any) -> str:
    """A leg's reason -> one of EXIT_REASONS, or 'other:<reason>'. The width sale writes a SENTENCE that starts
    with its skip constant, so it is bucketed by prefix."""
    r = str(reason or "").strip()
    if not r:
        return "other:none"
    if r in EXIT_REASONS:
        return r
    if r.startswith(REASON_WIDE_AFTER_FILL):
        return REASON_WIDE_AFTER_FILL
    return f"other:{r}"


def final_reason(trade: dict) -> str:
    legs = exits_legs(trade)
    if not legs:
        return "other:none"
    return reason_bucket(legs[-1].get("reason"))


def is_depth_sale(trade: dict) -> bool:
    """Era E's depth sale books its leg as sma_trail_stop (`execute_depth_open_sale`'s default), so the ONLY
    row-level signature is exit_rule='depth' + a final sma_trail_stop leg."""
    return (trade.get("exit_rule") or "") == DEPTH_RULE and final_reason(trade) == REASON_TRAIL


def partial_fraction(trade: dict) -> float:
    """The fraction of the position the LIVE profit-take actually sold: Σ partial_profit leg shares ÷ entry_shares
    (0 when no partial leg — a 1-share position, or no partial at all)."""
    shares = f(trade.get("entry_shares"))
    if not shares or shares <= 0:
        return 0.0
    sold = sum((f(lg.get("shares")) or 0.0) for lg in exits_legs(trade) if lg.get("reason") == REASON_PARTIAL)
    return max(0.0, min(1.0, sold / shares))


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# §5 fidelity — the fairer test (re-weight the replay's partial to the live fraction; one bar)
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def reweight_replay_r(live_replay: dict, live_fraction: float) -> Optional[float]:
    """The stored live_replay walked one fractional share and sold 1/3 at the partial. Re-weight ITS legs so the
    partial leg carries `live_fraction` of the position and the remaining legs carry the rest, in the row's own R
    frame (entry − stop_price, the live stop). None when the legs cannot be read. A replay with no partial leg is
    returned as stored (nothing to re-weight)."""
    legs = exits_legs(live_replay)
    entry = f(live_replay.get("entry_price"))
    stop = f(live_replay.get("stop_price")) if live_replay.get("stop_price") not in (None, "") else f(live_replay.get("live_stop"))
    if not legs or entry is None or stop is None or entry - stop <= 0:
        return None
    risk = entry - stop
    part = [lg for lg in legs if lg.get("reason") == REASON_PARTIAL]
    rest = [lg for lg in legs if lg.get("reason") != REASON_PARTIAL]
    if not part:
        return f(live_replay.get("realized_r"))
    wp = sum((f(lg.get("shares")) or 0.0) for lg in part)
    wr = sum((f(lg.get("shares")) or 0.0) for lg in rest)
    if wp <= 0 or (wr <= 0 and live_fraction < 1.0):
        return None
    pnl = 0.0
    for lg in part:
        px = f(lg.get("price"))
        if px is None:
            return None
        pnl += (px - entry) * (f(lg.get("shares")) or 0.0) / wp * live_fraction
    for lg in rest:
        px = f(lg.get("price"))
        if px is None:
            return None
        pnl += (px - entry) * (f(lg.get("shares")) or 0.0) / wr * (1.0 - live_fraction)
    return pnl / risk


def classify_fidelity_miss(trade: dict, live_actual: dict, live_replay: dict) -> str:
    """Session / reason difference FIRST (a different exit path is never a sizing artefact), then the whole-share
    class (<= 3 shares and the replay's partial fired), else other."""
    if (str(live_actual.get("exit_session")) != str(live_replay.get("exit_session"))
            or reason_bucket(live_actual.get("final_reason")) != reason_bucket(live_replay.get("final_reason"))):
        return "exit_session_differs"
    shares = f(trade.get("entry_shares"))
    if shares is not None and shares <= SMALL_POSITION_SHARES and truthy(live_replay.get("partial_fired")):
        return "whole_share"
    return "other"


def fidelity(trade: dict, live_actual: Optional[dict], live_replay: Optional[dict]) -> dict:
    """-> {pass, via, baseline, diff, diff_reweighted, tol, tol_old_pass, cls, live_fraction}.
    tol = max(0.25, 0.10 x |live R|). A fill passes on the stored replay ('stored', arms compared with live_actual)
    or only after re-weighting the replay's partial to the live fraction ('reweighted', arms compared with the
    stored live_replay — the same 1/3 weighting the arms carry). The old 0.25R result rides beside it once."""
    base = {"pass": False, "via": None, "baseline": None, "diff": None, "diff_reweighted": None, "tol": None,
            "tol_old_pass": False, "cls": "controls_unsettled", "live_fraction": None}
    if (live_actual is None or live_replay is None or live_actual.get("outcome") != "settled"
            or live_replay.get("outcome") != "settled"):
        return base
    ra, rr = f(live_actual.get("realized_r")), f(live_replay.get("realized_r"))
    if ra is None or rr is None:
        return base
    diff = rr - ra
    tol = max(FIDELITY_ABS, FIDELITY_REL * abs(ra))
    out = dict(base, diff=diff, tol=tol, tol_old_pass=abs(diff) <= FIDELITY_ABS + 1e-9, live_fraction=partial_fraction(trade))
    if abs(diff) <= tol + 1e-9:
        out.update(**{"pass": True, "via": "stored", "baseline": "live_actual", "cls": None})
        return out
    cls = classify_fidelity_miss(trade, live_actual, live_replay)
    out["cls"] = cls
    if cls == "exit_session_differs":
        return out          # a different exit PATH is never a sizing artefact; re-weighting models share count only
    rr2 = reweight_replay_r(live_replay, out["live_fraction"])
    if rr2 is not None:
        out["diff_reweighted"] = rr2 - ra
        if abs(rr2 - ra) <= tol + 1e-9:
            out.update(**{"pass": True, "via": "reweighted", "baseline": "live_replay", "cls": None})
    return out


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# §2 / §3 arm lenses — the six conditions and the ladder
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def classify_arm_row(row: Optional[dict], arm: str) -> tuple[str, Optional[float], Optional[float]]:
    """-> (class, r_own, r_cap): settled / horizon / no_entry / abstain / unscoreable / pending / rcap_uncomputable.
    Stored realized_r_capped is used where present, recomputed where NULL (I3 / I4 of 11-06 carried over)."""
    if row is None:
        return "pending", None, None
    out = row.get("outcome")
    if out == "settled":
        rcap = f(row.get("realized_r_capped"))
        if rcap is None:
            rr = dict(row)
            if not rr.get("stop_price") and arm in CONTROLS:
                rr["stop_price"] = rr.get("live_stop")
            rcap = capped_dollar_r(rr)
        return ("settled" if rcap is not None else "rcap_uncomputable"), f(row.get("realized_r")), rcap
    if out == "horizon":
        return "horizon", f(row.get("mark_r")), None
    if out == "unscoreable" and arm in ENTRY_ARMS and (row.get("final_reason") or "").startswith("no_entry:"):
        return "no_entry", None, 0.0
    if out == "abstain":
        return "abstain", None, None
    return "unscoreable", None, None


@dataclass
class EraCell:
    arm: str
    era: str
    n: int = 0
    n_pre_1104: int = 0
    n_post_1104: int = 0
    excluded: Counter = field(default_factory=Counter)
    rcap_delta_sum: float = 0.0
    rown_delta_sum: float = 0.0
    rcap_deltas: list = field(default_factory=list)
    better: int = 0
    worse: int = 0
    tie: int = 0
    arm_ge2: int = 0
    arm_ge4: int = 0
    live_ge2: int = 0
    live_ge4: int = 0
    arm_le_m15: int = 0
    tail_clip: int = 0
    rescues: int = 0
    baseline_replay: int = 0
    engine_sum: Optional[float] = None
    engine_n: int = 0

    @property
    def readable(self) -> bool:
        return self.n >= READABLE_MIN

    @property
    def drop_best(self) -> Optional[float]:
        return None if not self.rcap_deltas else self.rcap_delta_sum - max(self.rcap_deltas)

    @property
    def engine_agrees(self) -> bool:
        if self.engine_sum is None:
            return False
        return (self.engine_sum > 0) == (self.rcap_delta_sum > 0)

    @property
    def won(self) -> Optional[bool]:
        """The 11-06 six conditions; None when the era is not readable."""
        if not self.readable:
            return None
        return (self.rcap_delta_sum > 0 and self.rown_delta_sum > 0 and (self.drop_best or 0) > 0
                and self.engine_agrees and self.tail_clip == 0 and self.arm_ge4 >= self.live_ge4)


def era_cell(arm: str, era: str, fills: list[dict]) -> EraCell:
    """fills: one dict per fill in the era with keys trade_id, fidelity_pass, live_actual, live_replay, arm_row and
    optionally baseline ('live_actual' | 'live_replay'; §5: a fill that passed only re-weighted is compared with
    the stored live_replay on EVERY condition) and post_1104. A paired fill = the baseline settled + fidelity pass +
    the arm scoreable (settled or no_entry)."""
    c = EraCell(arm=arm, era=era)
    eng: list[float] = []
    for fl in fills:
        base_name = fl.get("baseline") or "live_actual"
        base_row = fl.get(base_name)
        la_cls, la_own, la_cap = classify_arm_row(base_row, base_name)
        if la_cls != "settled":
            c.excluded["live_unsettled"] += 1
            continue
        if not fl.get("fidelity_pass"):
            c.excluded["fidelity_fail"] += 1
            continue
        a_cls, a_own, a_cap = classify_arm_row(fl.get("arm_row"), arm)
        if a_cls not in ("settled", "no_entry"):
            c.excluded[a_cls] += 1
            continue
        c.n += 1
        if fl.get("post_1104"):
            c.n_post_1104 += 1
        else:
            c.n_pre_1104 += 1
        c.baseline_replay += base_name == "live_replay"
        dcap = (a_cap or 0.0) - la_cap
        c.rcap_deltas.append(dcap)
        c.rcap_delta_sum += dcap
        if a_cls == "settled":
            c.rown_delta_sum += a_own - la_own
        a_own0 = a_own if a_cls == "settled" else 0.0
        c.arm_ge2 += a_own0 >= 2.0
        c.arm_ge4 += a_own0 >= TAIL_WIN_R
        c.live_ge2 += la_own >= 2.0
        c.live_ge4 += la_own >= TAIL_WIN_R
        c.arm_le_m15 += a_own0 <= TAIL_LOSS_R
        if abs(dcap) <= TIE:
            c.tie += 1
        elif dcap > 0:
            c.better += 1
        else:
            c.worse += 1
        if la_own >= 2.0 and (a_cap or 0.0) < la_cap - 0.5:
            c.tail_clip += 1
        if la_own <= -0.9 and a_own0 > 0:
            c.rescues += 1
        lr_cls, _, lr_cap = classify_arm_row(fl.get("live_replay"), "live_replay")
        if lr_cls == "settled" and a_cls == "settled":
            eng.append(a_cap - lr_cap)
    if eng:
        c.engine_sum, c.engine_n = sum(eng), len(eng)
    return c


def era_context(cells_by_era: dict[str, EraCell], current_era: str) -> str:
    parts = [f"{e} {'won' if c.won else 'lost'} (n {c.n})" for e, c in sorted(cells_by_era.items())
             if e != current_era and c.readable]
    return "; ".join(parts) if parts else "no other readable era"


def verdict(cells_by_era: dict[str, EraCell], current_era: str) -> tuple[str, str]:
    """The ladder (§2, D1): judged on the CURRENT era only — older eras are closed baselines, printed as context,
    never a veto. -> (verdict, reason). Current not readable -> CAN'T TELL; current LOST -> NOTHING; WON on 3-9 ->
    WATCH; on >= 10 -> PROPOSE."""
    cur = cells_by_era.get(current_era)
    ctx = era_context(cells_by_era, current_era)
    if cur is None or not cur.readable:
        return "CAN'T TELL", f"{current_era}: n {0 if cur is None else cur.n} < {READABLE_MIN}; context: {ctx}"
    if cur.won is False:
        return "NOTHING", f"{current_era} lost on n {cur.n}; context: {ctx}"
    if cur.n >= PROPOSE_MIN:
        return "PROPOSE", f"{current_era} WON on n {cur.n}; context: {ctx}"
    return "WATCH", f"{current_era} WON on n {cur.n} (< {PROPOSE_MIN}); context: {ctx}"


def count_verdict(current_n: int, test_met: bool) -> str:
    """The same ladder for count-based lenses (selection, slippage, missed-by-slots, stop-too-wide); current era
    only (D1)."""
    if current_n < READABLE_MIN:
        return "CAN'T TELL"
    if not test_met:
        return "NOTHING"
    return "PROPOSE" if current_n >= PROPOSE_MIN else "WATCH"


def arm_lens(lens: str, fills_by_era: dict[str, list[dict]], arm_rows: dict[tuple[str, str], dict],
             current_era: str) -> dict:
    """fills_by_era: era -> [ {trade_id, fidelity_pass, live_actual, live_replay, baseline, post_1104} ];
    arm_rows: (trade_id, arm) -> row."""
    out = {}
    for arm in LENS_ARMS[lens]:
        cells = {}
        for era, fills in fills_by_era.items():
            per = [dict(fl, arm_row=arm_rows.get((str(fl["trade_id"]), arm))) for fl in fills]
            cells[era] = era_cell(arm, era, per)
        v, why = verdict(cells, current_era)
        if v == "PROPOSE":
            # §1.3 / D5: a PROPOSE is quoted only when ONE admission cell — (admission era, pre/post 11-04), the
            # #718 change being an admission change (finding 3) — carries n >= 10 and WON on its own; the exit-era
            # cell pools them, and the 482 YAML says never pool to reach a number.
            by_adm: dict[tuple[str, str], list[dict]] = defaultdict(list)
            for fl in fills_by_era.get(current_era, []):
                by_adm[_cell_key_of(fl)].append(fl)
            adm_cells = {key: era_cell(arm, current_era, [dict(fl, arm_row=arm_rows.get((str(fl["trade_id"]), arm))) for fl in fls])
                         for key, fls in by_adm.items()}
            if not any(c.n >= PROPOSE_MIN and c.won for c in adm_cells.values()):
                v = "WATCH"
                why += "; demoted: no one admission cell (admission era x pre/post 11-04) holds " + str(PROPOSE_MIN) + " and wins (" + ", ".join(
                    f"{adm} {side} n {c.n} {'won' if c.won else 'lost' if c.won is False else 'unreadable'}"
                    for (adm, side), c in sorted(adm_cells.items())) + ")"
        out[arm] = {"cells": cells, "verdict": v, "why": why}
    return out


def admission_cells(lens: str, fills_by_era: dict[str, list[dict]], arm_rows: dict[tuple[str, str], dict]) -> list[dict]:
    """D5 / the 482 YAML: SEGMENT FIRST by admission era, never pooled — every (arm, exit era, admission era,
    pre/post 11-04) cell with its n and result, for review.out. The ladder reads the exit-era cell; these say
    whether one admission cell carries it (finding 3: the two sides of #718 are two admission populations)."""
    out = []
    for arm in LENS_ARMS[lens]:
        for era, fills in sorted(fills_by_era.items()):
            by_adm: dict[tuple[str, str], list[dict]] = defaultdict(list)
            for fl in fills:
                by_adm[_cell_key_of(fl)].append(fl)
            for (adm, side), fls in sorted(by_adm.items()):
                c = era_cell(arm, era, [dict(fl, arm_row=arm_rows.get((str(fl["trade_id"]), arm))) for fl in fls])
                out.append({"arm": arm, "era": era, "admission_era": adm, "side": side, "n": c.n, "won": c.won,
                            "rcap_delta_sum": c.rcap_delta_sum, "pre_1104": c.n_pre_1104, "post_1104": c.n_post_1104})
    return out


def regime_table(fills_by_era: dict[str, list[dict]], arm_rows: dict[tuple[str, str], dict]) -> list[dict]:
    """The 482 review's §5: every arm x entry-stamped regime x era with n; cells under 10 named thin; never pooled."""
    out = []
    for arm in ALL_ARMS:
        for era, fills in sorted(fills_by_era.items()):
            by_reg: dict[str, list[dict]] = defaultdict(list)
            for fl in fills:
                reg = (fl.get("live_actual") or {}).get("regime") or fl.get("regime") or "unknown"
                by_reg[str(reg)].append(fl)
            for reg, fls in sorted(by_reg.items()):
                c = era_cell(arm, era, [dict(fl, arm_row=arm_rows.get((str(fl["trade_id"]), arm))) for fl in fls])
                out.append({"arm": arm, "era": era, "regime": reg, "n": c.n, "rcap_delta_sum": c.rcap_delta_sum,
                            "won": c.won, "thin": c.n < PROPOSE_MIN})
    return out


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# §3 descriptives: partials / exits / buy point
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def breakeven_stop_leg(trade: dict) -> bool:
    """The position's FINAL leg is a stop fill within BREAKEVEN_TOL_R of entry (both sides — a stop filled at +5R
    is a trailed winner, not a give-back)."""
    legs = exits_legs(trade)
    risk, entry = trade_risk_per_share(trade), f(trade.get("entry_price"))
    if not legs or risk is None or entry is None:
        return False
    last = legs[-1]
    px = f(last.get("price"))
    return reason_bucket(last.get("reason")) == REASON_STOP and px is not None and abs(px - entry) <= BREAKEVEN_TOL_R * risk


def breakeven_arm_for(trade: dict) -> Optional[float]:
    """The price-armed breakeven multiple the ROW's own era ran: rule_eras.exit_rules_as_of(alert_date,
    signal_type, exit_rule=row)['breakeven_at_r'] — 3.0 for magna53 / magna53_smallcap from the 09-06 flip, None
    in era C and for every strategy the flip never touched (breakout rows). None = the armed shape does not apply
    (finding 4: the old 3R fallback counted an era-C trade as both shapes)."""
    ad = d(trade.get("alert_date"))
    if ad is None:
        return None
    rules = exit_rules_as_of(ad, trade.get("signal_type") or None, exit_rule=(trade.get("exit_rule") or None))
    return f(rules.get("breakeven_at_r"))


def runner_shapes(trade: dict, sd_rec: Optional[dict] = None, live_actual_row: Optional[dict] = None) -> dict:
    """The two give-back shapes behind `runner_rule_sweep_recut`, counted APART:
    partial_breakeven (era C): a partial_profit leg, then the rest stopped at breakeven.
    armed_breakeven (eras D/E): the peak reached the breakeven arm — peak_price >= entry + arm_r x (entry − ORB low),
    the ORB frame the arm is set in (sell_discipline's peak_r is in the hard-stop frame, 2x wider under the entry−2R
    stop, so it is NOT compared with 3) — and the position then stopped at breakeven, partial or not.
    arm_r = the recorder row's own `breakeven_arm_r` stamp where present, else the row's era through
    rule_eras.exit_rules_as_of; None (era C, breakout) = the armed shape does not apply (`arm_r` None, never 3)."""
    be = breakeven_stop_leg(trade)
    legs = exits_legs(trade)
    saw_partial = any(lg.get("reason") == REASON_PARTIAL for lg in legs[:-1]) if legs else False
    out = {"partial_breakeven": be and saw_partial, "armed_breakeven": False, "arm_price": None, "arm_r": None}
    entry, orb_low = f(trade.get("entry_price")), f(trade.get("orb_low"))
    peak = f((sd_rec or {}).get("peak_price"))
    arm_r = f((live_actual_row or {}).get("breakeven_arm_r"))
    if arm_r is None:
        arm_r = breakeven_arm_for(trade)
    out["arm_r"] = arm_r
    if arm_r is not None and entry is not None and orb_low is not None and entry > orb_low:
        out["arm_price"] = entry + arm_r * (entry - orb_low)
        out["armed_breakeven"] = be and peak is not None and peak >= out["arm_price"]
    return out


def stopped_then_ran(trade: dict, daily: dict[str, list[dict]], sessions: int = STOPPED_THEN_RAN_SESSIONS) -> Optional[bool]:
    """Stopped out (a final stop_hit leg — the only stop reason the writers produce), then a daily high >= entry
    + 2R within `sessions` sessions after the close day. None when not a stop-out or bars are missing."""
    if final_reason(trade) != REASON_STOP:
        return None
    risk, entry = trade_risk_per_share(trade), f(trade.get("entry_price"))
    cd = et_date(trade.get("closed_at"))
    if risk is None or entry is None or cd is None:
        return None
    bars = [b for b in daily.get(trade.get("ticker"), []) if d(b["trade_date"]) > cd][:sessions]
    if len(bars) < sessions:
        return None
    return any((f(b.get("high_price")) or -1) >= entry + 2 * risk for b in bars)


def post_exit_high_r(trade: dict, daily: dict[str, list[dict]], sessions: int = POST_EXIT_HIGH_SESSIONS) -> Optional[float]:
    """The tail's 'what the chart did after our exit': the max daily high over the `sessions` sessions after the
    close day, as R from ENTRY (hard-stop frame). None when fewer sessions are stored."""
    risk, entry = trade_risk_per_share(trade), f(trade.get("entry_price"))
    cd = et_date(trade.get("closed_at"))
    if risk is None or entry is None or cd is None:
        return None
    bars = [b for b in daily.get(trade.get("ticker"), []) if d(b["trade_date"]) > cd][:sessions]
    if len(bars) < sessions:
        return None
    highs = [f(b.get("high_price")) for b in bars]
    if any(h is None for h in highs):
        return None
    return (max(highs) - entry) / risk


def depth_sale_cost_r(trade: dict, daily: dict[str, list[dict]]) -> Optional[float]:
    """Era E / L2 depth sale: the next-open sale price vs the signal close (the prior session's close), in R
    (hard-stop frame). Negative = selling at the open cost that much. None when not a depth sale or bars missing."""
    if not is_depth_sale(trade):
        return None
    legs = exits_legs(trade)
    px, risk = f(legs[-1].get("price")), trade_risk_per_share(trade)
    sale_day = et_date(legs[-1].get("time")) or et_date(trade.get("closed_at"))
    if px is None or risk is None or sale_day is None:
        return None
    prior = [b for b in daily.get(trade.get("ticker"), []) if d(b["trade_date"]) < sale_day]
    if not prior:
        return None
    sig_close = f(prior[-1].get("close"))
    return None if sig_close is None else (px - sig_close) / risk


def partial_descriptives(trades: list[dict], sd: dict[str, dict], la_rows: Optional[dict[str, dict]] = None) -> dict:
    """Per lane/era group: partial fired rate, median capture, median giveback, BOTH runner shapes, tiny positions."""
    la_rows = la_rows or {}
    n = len(trades)
    fired = sum(truthy(t.get("partial_taken")) for t in trades)
    recs = [sd[str(t["id"])] for t in trades if str(t["id"]) in sd]
    shapes = [runner_shapes(t, sd.get(str(t["id"])), la_rows.get(str(t["id"]))) for t in trades]
    return {"n": n, "partial_fired": fired, "no_record": n - len(recs),
            "capture_pct_median": median(f(r.get("capture_pct")) for r in recs),
            "giveback_r_median": median(f(r.get("giveback_r")) for r in recs),
            "runner_shape_partial": sum(s["partial_breakeven"] for s in shapes),
            "runner_shape_armed": sum(s["armed_breakeven"] for s in shapes),
            "armed_na": sum(s["arm_r"] is None for s in shapes),          # no price-armed breakeven in this row's era
            "shares_le_2": sum((f(t.get("entry_shares")) or 0) <= 2 for t in trades)}


def exit_descriptives(trades: list[dict], sd: dict[str, dict], daily: Optional[dict[str, list[dict]]] = None,
                      la_rows: Optional[dict[str, dict]] = None) -> dict:
    """Final reason mix (the writers' vocabulary), hold / peak medians, stop-width medians, depth sales + their cost,
    and 'disappoints' on live_actual R_cap (None = no recorder for the lane)."""
    daily, la_rows = daily or {}, la_rows or {}
    recs = [sd[str(t["id"])] for t in trades if str(t["id"]) in sd]
    rs = [r for r in (trade_realized_r(t) for t in trades) if r is not None]
    costs = [c for c in (depth_sale_cost_r(t, daily) for t in trades) if c is not None]
    rcaps = []
    for t in trades:
        row = la_rows.get(str(t["id"]))
        cls, _, rcap = classify_arm_row(row, "live_actual")
        if cls == "settled":
            rcaps.append(rcap)
    return {"n": len(trades), "reasons": Counter(final_reason(t) for t in trades),
            "hold_days_median": median(f(r.get("hold_trading_days")) for r in recs),
            "peak_r_median": median(f(r.get("peak_r")) for r in recs),
            "realized_r_median": median(rs),
            "stop_pct_median": median(f(r.get("stop_pct")) for r in recs),
            "stop_per_adr_median": median(f(r.get("stop_per_adr")) for r in recs),
            "depth_sales": sum(is_depth_sale(t) for t in trades),
            "depth_cost_r_median": median(costs), "depth_cost_n": len(costs),
            "rcap_n": len(rcaps), "rcap_sum": sum(rcaps) if rcaps else None,
            "disappoints": (sum(rcaps) < 0 and not any(r >= TAIL_WIN_R for r in rs)) if rcaps else None}


def slippage_test(fills: list[dict]) -> dict:
    """§3 buy point (a): fills > +1% over the trigger (n >= 3) have an R_cap sum < 0 while the <= +1% fills' sum
    is > 0. fills: {fill_vs_trigger_pct, live_rcap, real_risk_vs_trigger_risk}. A NULL fill_vs_trigger_pct is its
    own count, never a <= 1% fill."""
    known = [fl for fl in fills if f(fl.get("fill_vs_trigger_pct")) is not None and f(fl.get("live_rcap")) is not None]
    null_n = sum(1 for fl in fills if f(fl.get("fill_vs_trigger_pct")) is None)
    hi = [fl for fl in known if f(fl["fill_vs_trigger_pct"]) > 1.0]
    lo = [fl for fl in known if f(fl["fill_vs_trigger_pct"]) <= 1.0]
    hi_sum, lo_sum = sum(f(x["live_rcap"]) for x in hi), sum(f(x["live_rcap"]) for x in lo)
    met = len(hi) >= READABLE_MIN and hi_sum < 0 and lo_sum > 0
    pcts = [f(x.get("fill_vs_trigger_pct")) for x in known]
    rr = [f(x.get("real_risk_vs_trigger_risk")) for x in fills if f(x.get("real_risk_vs_trigger_risk")) is not None]
    return {"n": len(known), "null_n": null_n, "over_1pct": len(hi), "over_sum": hi_sum, "under_sum": lo_sum,
            "median_pct": median(pcts), "max_pct": max(pcts) if pcts else None,
            "real_risk_median": median(rr), "real_risk_max": max(rr) if rr else None,
            "verdict": count_verdict(len(known), met) if len(hi) >= READABLE_MIN else "CAN'T TELL"}


def fill_minute_histogram(trades: list[dict]) -> Counter:
    """ET fill minute per trade ('09:31' ...); 'unknown' when filled_at is empty."""
    return Counter(et_minute(t.get("filled_at")) or "unknown" for t in trades)


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# §4 the tail + the per-trade window list
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def trade_row(t: dict, sd: dict[str, dict], fid: dict[str, dict], arm_rows: dict[tuple[str, str], dict],
              daily: dict[str, list[dict]], labels: dict[tuple[str, str], str],
              best_worst_arm: Optional[Callable[[str], tuple[Optional[str], Optional[str]]]] = None) -> dict:
    """One trade, every field the tail and the window list print (§4 / exit_tune's forensic on every trade)."""
    tid = str(t["id"])
    rec = sd.get(tid, {})
    fd = fid.get(tid, {})
    la = arm_rows.get((tid, "live_actual"))
    ff = arm_rows.get((tid, FILL_FACTS)) or {}
    risk, entry = trade_risk_per_share(t), f(t.get("entry_price"))
    legs = []
    for lg in exits_legs(t):
        px = f(lg.get("price"))
        legs.append({"reason": reason_bucket(lg.get("reason")), "day": et_date(lg.get("time")),
                     "price_r": ((px - entry) / risk) if (px is not None and entry is not None and risk) else None,
                     "shares": f(lg.get("shares"))})
    best, worst = best_worst_arm(tid) if best_worst_arm else (None, None)
    adm, adm_src = admission_era_of(t, la)
    return {"id": tid, "ticker": t.get("ticker"), "lane": lane_of(t), "era": era_of(t), "alert_date": str(t.get("alert_date")),
            "fill_minute": et_minute(t.get("filled_at")), "entry_shares": f(t.get("entry_shares")),
            "fill_vs_trigger_pct": f(ff.get("fill_vs_trigger_pct")), "real_risk_vs_trigger_risk": f(ff.get("real_risk_vs_trigger_risk")),
            "stop_pct": f(rec.get("stop_pct")), "stop_per_adr": f(rec.get("stop_per_adr")),
            "peak_r": f(rec.get("peak_r")), "peak_session": f(rec.get("peak_hold_day")),
            "realized_r": trade_realized_r(t) if (t.get("status") or "") == "closed" else None,
            "capture_pct": f(rec.get("capture_pct")), "giveback_r": f(rec.get("giveback_r")),
            "exit_legs": legs, "exit_reason": final_reason(t), "depth_sale": is_depth_sale(t),
            "hold_days": f(rec.get("hold_trading_days")), "regime": t.get("regime"),
            "admission_era": adm, "admission_era_source": adm_src, "post_1104": post_open_floor(t),
            "label": labels.get((t.get("ticker"), str(t.get("alert_date")))),
            "reentry": str(t.get("entry_attempt") or "1") == "2", "excluded": bool(t.get("pnl_attribution")),
            "fidelity": fd.get("pass"), "fidelity_via": fd.get("via"), "fidelity_cls": fd.get("cls"),
            "best_arm": best, "worst_arm": worst, "post_exit_high_r": post_exit_high_r(t, daily),
            "stopped_then_ran": stopped_then_ran(t, daily), "forensic_class": None}


def tails(trades: list[dict], sd: dict[str, dict], fidelity_by_id: dict[str, dict],
          best_worst_arm: Optional[Callable[[str], tuple[Optional[str], Optional[str]]]] = None,
          arm_rows: Optional[dict[tuple[str, str], dict]] = None, daily: Optional[dict[str, list[dict]]] = None,
          labels: Optional[dict[tuple[str, str], str]] = None) -> dict:
    """>= +4R winners and <= -1.5R losers on the REAL trade (never fidelity-gated), one full row each."""
    out = {"winners": [], "losers": []}
    for t in trades:
        if (t.get("status") or "") != "closed" or (t.get("pnl_attribution") or ""):
            continue
        r = trade_realized_r(t)
        if r is None:
            continue
        bucket = "winners" if r >= TAIL_WIN_R else ("losers" if r <= TAIL_LOSS_R else None)
        if bucket is None:
            continue
        out[bucket].append(trade_row(t, sd, fidelity_by_id, arm_rows or {}, daily or {}, labels or {}, best_worst_arm))
    return out


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# §6 breakout missed-by-slots + the L3 buy point
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def missed_records(audit_rows: list[dict]) -> tuple[list[dict], int]:
    """-> (records, bad_json_count). A row whose detail is not JSON is COUNTED, never dropped silently."""
    recs, bad = [], 0
    for r in audit_rows:
        if r.get("event_type") != MISSED_EVENT:
            continue
        try:
            rec = json.loads(r.get("detail") or "{}")
        except json.JSONDecodeError:
            bad += 1
            continue
        if not isinstance(rec, dict):
            bad += 1
            continue
        rec["_audit_id"] = r.get("id")
        recs.append(rec)
    return recs, bad


def width_ok(rec: dict) -> Optional[bool]:
    """The entry's own skip rule from the record's fields. `width` is a FRACTION, (level − stop) ÷ level
    (breakout_v1_entry.py:530), and `adr20` is a fraction too: keep width <= adr20. None when an input is missing."""
    w, adr = f(rec.get("width")), f(rec.get("adr20"))
    if w is None or adr is None:
        return None
    return w <= adr


def missed_proxy_walk(entry: float, stop: float, day: date, bars: list[dict],
                      sessions: int = MISSED_WALK_SESSIONS) -> dict:
    """Daily-bar PROXY for the pp walk over the `sessions` sessions after `day`: +2R before the stop (a session
    with both counts as stopped), MFE in R, maturity."""
    width = entry - stop
    if width <= 0:
        return {"mature": False, "plus2r_before_stop": None, "mfe_r": None, "reason": "no_width"}
    fwd = [b for b in sorted(bars, key=lambda b: d(b["trade_date"])) if d(b["trade_date"]) > day][:sessions]
    if len(fwd) < sessions:
        return {"mature": False, "plus2r_before_stop": None, "mfe_r": None, "reason": f"{len(fwd)} of {sessions} sessions"}
    target = entry + 2 * width
    plus2r, stopped, max_high = False, False, entry
    for b in fwd:
        hi, lo = f(b.get("high_price")), f(b.get("low_price"))
        if hi is None or lo is None:
            return {"mature": False, "plus2r_before_stop": None, "mfe_r": None, "reason": "bar_missing_high_low"}
        max_high = max(max_high, hi)
        if lo <= stop:
            stopped = True
            break
        if hi >= target:
            plus2r = True
            break
    return {"mature": True, "plus2r_before_stop": plus2r and not stopped, "mfe_r": (max_high - entry) / width,
            "reason": None}


def missed_vs_seated(missed: list[dict], seated: list[dict]) -> dict:
    """missed / seated: dicts with a 'walk' (missed_proxy_walk result) and, for seated, 'realized_r'.
    Test: missed +2R share >= seated share AND median MFE_10 missed >= seated."""
    mm = [m for m in missed if m["walk"]["mature"]]
    ss = [s for s in seated if s["walk"]["mature"]]
    share = lambda xs: (sum(bool(x["walk"]["plus2r_before_stop"]) for x in xs) / len(xs)) if xs else None  # noqa: E731
    m_share, s_share = share(mm), share(ss)
    m_med, s_med = median(x["walk"]["mfe_r"] for x in mm), median(x["walk"]["mfe_r"] for x in ss)
    met = (len(ss) >= READABLE_MIN and m_share is not None and s_share is not None
           and m_share >= s_share and m_med is not None and s_med is not None and m_med >= s_med)
    v = count_verdict(len(mm), met) if len(ss) >= READABLE_MIN or len(mm) < READABLE_MIN else "CAN'T TELL"
    return {"missed_n": len(missed), "missed_mature": len(mm), "seated_n": len(seated), "seated_mature": len(ss),
            "missed_plus2r_share": m_share, "seated_plus2r_share": s_share,
            "missed_mfe_median": m_med, "seated_mfe_median": s_med, "verdict": v}


def _detail(r: dict) -> dict:
    try:
        v = json.loads(r.get("detail") or "{}")
        return v if isinstance(v, dict) else {}
    except json.JSONDecodeError:
        return {}


def absence_observables(audit_rows: list[dict], seated_n: int, list_nights: int, toggle_state: Optional[str],
                        strategy_row: Optional[dict] = None) -> dict:
    """The positive observables beside a missed count of 0: hold rows, slots_full holds, the 15:55 step's own
    entry_day rows (its proof of running), the unreadable rows (a 15:55 that could not judge), the seated trades,
    the list nights, the runtime switch AND the strategy row (`mi_strategies.enabled` / `phase`). The env default
    (a third on/off source) is not in any table and is NOT captured — stated here, not assumed."""
    holds = [r for r in audit_rows if r.get("event_type") == HOLD_EVENT]
    slots_full = sum(1 for r in holds if _detail(r).get("state") == "slots_full")
    return {"hold_rows": len(holds), "slots_full_holds": slots_full, "seated_trades": seated_n,
            "list_nights": list_nights, "toggle": toggle_state,
            "entry_day_rows": sum(1 for r in audit_rows if r.get("event_type") == ENTRY_DAY_EVENT),
            "unreadable_rows": sum(1 for r in audit_rows if r.get("event_type") == UNREADABLE_EVENT),
            "strategy_enabled": (truthy(strategy_row.get("enabled")) if strategy_row else None),
            "strategy_phase": (strategy_row.get("phase") if strategy_row else None),
            "env_default": "not captured"}


ABSENCE_CAPTURES = ("audit_breakout", "breakout_list", "strategy_toggles", "strategies")   # what the sentence reads


def absence_sentence(obs: dict, missed_n: int, raw_n: Optional[int] = None, width_dropped: int = 0, malformed: int = 0,
                     bad_json: int = 0, not_captured: Iterable[str] = ()) -> str:
    """The sentence beside a missed count. `missed_n` is the READABLE count (width kept, day / price / stop present);
    `raw_n` is every missed-by-slots row written. Finding 5: when rows were written and none is readable, the page
    says what dropped them — never 'none broke out while held'. Finding 2: a missing capture file is NOT an empty
    month — the sentence names it and makes no claim."""
    missing = [n for n in not_captured if n in ABSENCE_CAPTURES]
    if missing:
        return "NOT CAPTURED: " + ", ".join(f"{n}.csv" for n in missing) + " — the absence check cannot be made (not 'nothing missed')"
    if raw_n is None:
        raw_n = missed_n
    drops = []
    if width_dropped:
        drops.append(f"{width_dropped} dropped by the width rule")
    if malformed:
        drops.append(f"{malformed} malformed (no day / break price / stop)")
    if bad_json:
        drops.append(f"{bad_json} unreadable JSON")
    drop_s = ("; " + ", ".join(drops)) if drops else ""
    if obs["list_nights"] == 0 or (obs["toggle"] not in (None, "on") and obs["seated_trades"] == 0 and obs["hold_rows"] == 0):
        return "the breakout paper lane did not run in this window" + drop_s
    if obs.get("entry_day_rows", 0) == 0 and raw_n == 0:
        return "the 15:55 missed-by-slots step left no entry_day row — the recorder did not run (not 'nothing missed')"
    if raw_n > 0 and missed_n == 0:
        return (f"{raw_n} missed-by-slots record(s) written, none readable — " + ", ".join(drops)
                + " (not 'none broke out while held')")
    if obs["slots_full_holds"] == 0:
        return "no name was ever held for a full paper book" + drop_s
    if missed_n == 0:
        return f"{obs['slots_full_holds']} hold rows, none broke out while held" + (
            f" ({obs['unreadable_rows']} unreadable row(s) — some names were never judged)" if obs.get("unreadable_rows") else "") + drop_s
    return f"missed {missed_n} of {obs['slots_full_holds']} held rows" + drop_s


def breakout_buy_point(l3_trades: list[dict], blist: list[dict], audit_rows: list[dict]) -> dict:
    """L3 buy point: fill vs the list `level` (%), the fill-stop decision mix (keep / lower / sell_all / unchecked
    = I10), and the thirds mix (a partial_profit leg at >= ~+2R = the +2R third; below it = the session-3 third;
    none)."""
    level_by = {}
    for r in blist:
        sd_, tk = d(r.get("scan_date")), r.get("ticker")
        if sd_ and tk:
            level_by.setdefault(tk, []).append((sd_, f(r.get("level"))))
    decisions = {}
    for r in audit_rows:
        if r.get("event_type") == FILL_STOP_EVENT:
            dt = _detail(r)
            if dt.get("trade_id") is not None:
                decisions[str(dt["trade_id"])] = dt.get("decision") or "unknown"
    fill_vs_level, dec_mix, thirds = [], Counter(), Counter()
    for t in l3_trades:
        ad, entry = d(t.get("alert_date")), f(t.get("entry_price"))
        cands = [lv for (sd_, lv) in level_by.get(t.get("ticker"), []) if sd_ is not None and ad and sd_ < ad and lv]
        if cands and entry:
            lv = cands[-1]
            fill_vs_level.append((entry / lv - 1.0) * 100.0)
        dec_mix[decisions.get(str(t["id"]), "unchecked")] += 1
        risk = trade_risk_per_share(t)
        parts = [lg for lg in exits_legs(t) if lg.get("reason") == REASON_PARTIAL]
        if not parts:
            thirds["none"] += 1
        elif risk and entry and f(parts[0].get("price")) is not None and f(parts[0]["price"]) >= entry + 1.9 * risk:
            thirds["+2R"] += 1
        else:
            thirds["session_3"] += 1
    return {"n": len(l3_trades), "fill_vs_level_median": median(fill_vs_level),
            "fill_vs_level_max": max(fill_vs_level) if fill_vs_level else None, "fill_vs_level_n": len(fill_vs_level),
            "decisions": dec_mix, "thirds": thirds}


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# §3 stop (c): the stop-too-wide matrix (verbatim from the YAML; two-sided Fisher as the YAML read it)
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def _hyper_p(k: int, row1: int, col1: int, n: int) -> float:
    return comb(row1, k) * comb(n - row1, col1 - k) / comb(n, col1)


def fisher_exact_two_sided(a: int, b: int, c: int, dd: int) -> float:
    """Two-sided Fisher exact p (the sum of every table at least as extreme as the observed, by probability) —
    the test the YAML's 09-16 reading used (4 of 11 vs 17 of 25 -> 0.141, CANNOT TELL). a = rejected hits,
    b = rejected misses, c = admitted hits, dd = admitted misses."""
    n = a + b + c + dd
    row1, col1 = a + b, a + c
    if n == 0 or comb(n, col1) == 0:
        return 1.0
    po = _hyper_p(a, row1, col1, n)
    lo, hi = max(0, col1 - (n - row1)), min(row1, col1)
    return min(1.0, sum(_hyper_p(k, row1, col1, n) for k in range(lo, hi + 1) if _hyper_p(k, row1, col1, n) <= po * (1 + 1e-9)))


def stop_too_wide_matrix(rejected_mfe: list[float], admitted_mfe: list[float]) -> dict:
    """MFE over d+1..d+5 from the gap-day open, in %, both cohorts. REVISIT / KEEP / CANNOT TELL as the YAML has it."""
    rn, an = len(rejected_mfe), len(admitted_mfe)
    r_hit = sum(x >= 10.0 for x in rejected_mfe)
    a_hit = sum(x >= 10.0 for x in admitted_mfe)
    r_rate = r_hit / rn if rn else None
    a_rate = a_hit / an if an else None
    r_med, a_med = median(rejected_mfe), median(admitted_mfe)
    if rn < READABLE_MIN or an < READABLE_MIN:
        return {"rejected_n": rn, "admitted_n": an, "matrix": "CANNOT TELL", "p": None,
                "rejected_rate": r_rate, "admitted_rate": a_rate, "rejected_median": r_med, "admitted_median": a_med,
                "verdict": "CAN'T TELL"}
    p = fisher_exact_two_sided(r_hit, rn - r_hit, a_hit, an - a_hit)
    if r_rate >= a_rate and r_med >= a_med:
        matrix = "REVISIT"
    elif r_rate < a_rate and r_med < a_med and p < 0.10:
        matrix = "KEEP"
    else:
        matrix = "CANNOT TELL"
    # the YAML's three answers map one-to-one onto the ladder: REVISIT -> WATCH / PROPOSE, KEEP -> NOTHING (the
    # current filter is right), CANNOT TELL -> CAN'T TELL — never NOTHING (finding 6: the 09-16 reading said it
    # could not tell, and "nothing" would read as "the current rule is best")
    v = ("PROPOSE" if (matrix == "REVISIT" and rn >= PROPOSE_MIN and an >= PROPOSE_MIN)
         else "WATCH" if matrix == "REVISIT" else "NOTHING" if matrix == "KEEP" else "CAN'T TELL")
    return {"rejected_n": rn, "admitted_n": an, "matrix": matrix, "p": p, "rejected_rate": r_rate,
            "admitted_rate": a_rate, "rejected_median": r_med, "admitted_median": a_med, "verdict": v}


def mfe_5d_pct(ticker: str, alert_date: date, daily: dict[str, list[dict]]) -> Optional[float]:
    """MFE over d+1..d+5 from the gap-day open, in %, on raw daily bars (the YAML's measure, both cohorts).
    None when the gap-day open or five forward sessions are missing. NEVER mi_ep_missed_outcomes.max_high_5d
    (a fraction whose window includes the gap day itself)."""
    bars = sorted(daily.get(ticker, []), key=lambda b: d(b["trade_date"]))
    day0 = [b for b in bars if d(b["trade_date"]) == alert_date]
    open_d0 = f(day0[0].get("open_price")) if day0 else None
    if not open_d0 or open_d0 <= 0:
        return None
    fwd = [b for b in bars if d(b["trade_date"]) > alert_date][:5]
    if len(fwd) < 5:
        return None
    highs = [f(b.get("high_price")) for b in fwd]
    if any(h is None for h in highs):
        return None
    return (max(highs) / open_d0 - 1.0) * 100.0


def stop_too_wide_section(skips: list[dict], admitted: list[dict], daily: dict[str, list[dict]]) -> dict:
    """Rejected (skip rows) vs ADMITTED (entered magna53 rows since 05-05 — the YAML's control, captured by
    admitted_magna53.sql), both scored by mfe_5d_pct on the same raw bars; the admitted cohort's account-mode and
    admission-era split stated beside the rate (the YAML's era_scoped note)."""
    rej = [m for m in (mfe_5d_pct(s.get("ticker"), d(s["alert_date"]), daily) for s in skips) if m is not None]
    adm = [m for m in (mfe_5d_pct(t.get("ticker"), d(t["alert_date"]), daily) for t in admitted) if m is not None]
    res = stop_too_wide_matrix(rej, adm)
    res["rejected_rows"], res["admitted_rows"] = len(skips), len(admitted)
    res["rejected_unscored"], res["admitted_unscored"] = len(skips) - len(rej), len(admitted) - len(adm)
    res["admitted_modes"] = Counter((t.get("account_mode") or "unknown") for t in admitted)
    res["admitted_admission_eras"] = Counter(admission_era_as_of(d(t["alert_date"])) for t in admitted if d(t.get("alert_date")))
    return res


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# §3 selection — his labels, his chart-sheet grades, the declared abstentions
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def _load_by_path(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, _REPO / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(name, mod)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def declared_abstentions() -> set[tuple[str, str]]:
    """Operator-labelled names the fixture declares EXCLUDED (a documented abstention — CHPT 09-03, ABNB 08-07 —
    not a selection miss this review re-raises every month). Read from tests/fixtures/must_not_miss_eps.py."""
    mod = _load_by_path("must_not_miss_eps_720", "tests/fixtures/must_not_miss_eps.py")
    return {(m.ticker, m.alert_date) for m in mod.MUST_NOT_MISS if m.excluded and m.label_source == "operator"}


def operator_labels() -> list[tuple[str, str]]:
    from shared.operator_labelled_eps import OPERATOR_LABELLED_EPS
    return [(e.ticker, e.alert_date) for e in OPERATOR_LABELLED_EPS]


def breakout_grades_fixture() -> list[dict]:
    """His chart-sheet grades (ruling 2026-11-05; D4) — tests/fixtures/breakout_list_grades.py, never
    mi_breakout_v1_grades (empty since that ruling)."""
    mod = _load_by_path("breakout_list_grades_720", "tests/fixtures/breakout_list_grades.py")
    return [{"ticker": g.ticker, "list_date": g.list_date, "grade": g.grade, "words": g.operator_words}
            for g in mod.BREAKOUT_LIST_GRADES]


def selection_labels(trades: list[dict], skips: list[dict], labelled: Iterable[tuple[str, str]],
                     alerts: Iterable[dict] = (), abstentions: Iterable[tuple[str, str]] = ()) -> list[dict]:
    """What we did with HIS labels: for each (ticker, alert_date) -> traded / skipped (reason) / alerted, no trade
    row (mi_ep_alerts has it) / never alerted. Declared abstentions are listed as 'abstention' and never a miss."""
    by_key_t = {(t.get("ticker"), str(t.get("alert_date"))): t for t in trades}
    by_key_s = {(s.get("ticker"), str(s.get("alert_date"))): s for s in skips}
    alerted = {(a.get("ticker"), str(a.get("alert_date"))) for a in alerts}
    abst = set(abstentions)
    out = []
    for ticker, ad in labelled:
        key = (ticker, ad)
        if key in abst:
            out.append({"ticker": ticker, "alert_date": ad, "did": "abstention", "detail": "declared in must_not_miss_eps.py"})
        elif key in by_key_t:
            t = by_key_t[key]
            out.append({"ticker": ticker, "alert_date": ad, "did": "traded", "detail": f"R {fmt(trade_realized_r(t))}"
                        if (t.get("status") or "") == "closed" else "open"})
        elif key in by_key_s:
            out.append({"ticker": ticker, "alert_date": ad, "did": "skipped", "detail": by_key_s[key].get("skip_reason") or ""})
        elif key in alerted:
            out.append({"ticker": ticker, "alert_date": ad, "did": "alerted, no trade row", "detail": "mi_ep_alerts"})
        else:
            out.append({"ticker": ticker, "alert_date": ad, "did": "never alerted", "detail": "no mi_ep_alerts row"})
    return out


SELECTION_MISS = ("skipped", "alerted, no trade row", "never alerted")


def selection_verdict(rows: list[dict]) -> tuple[str, int]:
    """-> (verdict, missed_n). Under 3 missed labelled names = CAN'T TELL (§2's under-3 rule; the rows are still
    listed); 3+ = WATCH (labels carry no returns test, so never PROPOSE); none missed = NOTHING; no label = CAN'T TELL."""
    judged = [r for r in rows if r["did"] != "abstention"]
    missed = sum(r["did"] in SELECTION_MISS for r in judged)
    if not judged:
        return "CAN'T TELL", 0
    if missed == 0:
        return "NOTHING", 0
    return ("WATCH" if missed >= READABLE_MIN else "CAN'T TELL"), missed


def breakout_grade_for(ticker: str, alert_date: date, grades: list[dict]) -> Optional[str]:
    """His grade on the latest list night strictly before the breakout day; None = ungraded."""
    cands = [g for g in grades if g.get("ticker") == ticker and d(g.get("list_date")) is not None and d(g["list_date"]) < alert_date]
    if not cands:
        return None
    return max(cands, key=lambda g: d(g["list_date"])).get("grade")


def breakout_selection(l3_trades: list[dict], grades: list[dict]) -> dict:
    """'his NO names lose, his GOOD names carry the winners': every graded `no` trade <= 0R AND >= 1 `good` trade
    >= +2R. CAN'T TELL under 3 graded `no` trades; met -> WATCH (NEVER PROPOSE: charts support, never decide — a
    grade filter is the one thing the standing rule rules out, and his EP labels are capped the same way; finding
    7); not met -> NOTHING."""
    rows = []
    for t in l3_trades:
        if (t.get("status") or "") != "closed" or (t.get("pnl_attribution") or ""):
            continue
        rows.append({"ticker": t.get("ticker"), "grade": breakout_grade_for(t.get("ticker"), d(t["alert_date"]), grades),
                     "r": trade_realized_r(t)})
    graded = [x for x in rows if x["grade"] is not None and x["r"] is not None]
    low = [x for x in graded if x["grade"] == GRADE_LOW]
    high = [x for x in graded if x["grade"] == GRADE_HIGH]
    met = len(low) >= READABLE_MIN and all(x["r"] <= 0 for x in low) and any(x["r"] >= 2.0 for x in high)
    v = ("WATCH" if met else "NOTHING") if len(low) >= READABLE_MIN else "CAN'T TELL"
    return {"n": len(rows), "graded": len(graded), "ungraded": len(rows) - len(graded), "low_n": len(low), "high_n": len(high),
            "by_grade": Counter(x["grade"] or "ungraded" for x in rows), "verdict": v, "rows": rows}


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# §7 safeguard transitions (runner_rule_sweep_recut's void arm) + the predicates copied from the YAML
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def era_start_for(label: str, fallback: date) -> date:
    """The current exit era's first date from rule_eras' dated record (`exit_era_start`) — never re-typed here, so
    the next exit flip moves the safeguard-void window with it; `fallback` for a label the record does not date."""
    return exit_era_start(label) or fallback


def safeguard_transitions_check(rows: list[dict], era_start: date) -> list[str]:
    """LIVE / global transitions since the current era start, excluding the YAML's own list and anything at or
    before its ANSWERED-THROUGH stamp. Each one printed = 'the 08-29 runner read is void'."""
    answered = _et(SAFEGUARD_ANSWERED_THROUGH)
    out = []
    for r in rows:
        if (r.get("account_mode") or "") not in ("live", "global"):
            continue
        if (r.get("safeguard") or "") in SAFEGUARD_VOID_EXCLUDED:
            continue
        at = _et(r.get("last_transition_at"))
        if at is None or at.date() < era_start or at <= answered:
            continue
        out.append(f"{r.get('safeguard')}|{r.get('account_mode')} -> {r.get('state')} at {at.isoformat()}")
    return out


def predicate_bodies_from_yaml(yaml_path: Path) -> dict[str, str]:
    """review_id -> predicate_sql with ONLY the trailing semicolon (and anything after it) removed. The `--`
    comments stay in: they are part of the YAML text and the server reads past them inside COPY (...)."""
    import yaml
    reg = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    entries = reg["reviews"] if isinstance(reg, dict) else reg
    out = {}
    for e in entries:
        rid = e.get("review_id")
        if rid in FOLDED_REVIEWS:
            out[rid] = strip_trailing_semicolon(e.get("predicate_sql") or "")
    return out


def strip_trailing_semicolon(sql: str) -> str:
    """Drop the LAST statement-level `;` of a predicate and whatever follows it (a trailing comment); nothing else
    is touched. A `;` inside a `--` comment is text, not a terminator (the 482 predicate's comment has one)."""
    lines = sql.rstrip().splitlines()
    cut = None
    for i, line in enumerate(lines):
        code = line.split("--", 1)[0]
        if ";" in code:
            cut = (i, code.rfind(";"))
    if cut is None:
        return "\n".join(lines)
    i, j = cut
    kept = lines[:i] + [lines[i][:j]]
    return "\n".join(kept).rstrip()


def emit_predicates_sql(yaml_path: Path) -> str:
    """capture/predicates.sql: ONE server-side COPY (a `\\copy` is one line and a `--` comment would swallow the
    rest of it) whose SELECT carries each review's predicate_sql VERBATIM as a scalar subquery."""
    bodies = predicate_bodies_from_yaml(yaml_path)
    parts = []
    for rid in FOLDED_REVIEWS:
        body = bodies.get(rid)
        if body is None:
            raise SystemExit(f"predicate for {rid} not found in {yaml_path}")
        parts.append(f"SELECT '{rid}' AS review, (\n{body}\n) AS n")
    return ("SET default_transaction_read_only = on;\n"
            "-- #720 §7: the five folded reviews' predicate_sql, copied VERBATIM from data_gated_reviews.yaml by\n"
            "-- `run_review.py --emit-predicates` (tests pin this file to the YAML). Server-side COPY: multi-line, comments kept.\n"
            "COPY (\n" + "\nUNION ALL\n".join(parts) + "\n) TO STDOUT WITH CSV HEADER;\n")


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# §9 render
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def _legs_str(legs: list[dict]) -> str:
    return "; ".join(f"{lg['reason']}@{fmt(lg['price_r'])}R" + (f" {lg['day']}" if lg.get("day") else "") for lg in legs) or "—"


def render(report: dict) -> str:
    """The one page: line 1 = the answer; population, lens, tail, missed, folded, action; then the per-trade list."""
    lines = [f"# #720 monthly trade review — {report['run_date']}", "",
             f"**{report['answer']}**", ""]
    for name in report.get("not_captured", []):
        lines.append(f"**NOT CAPTURED: {name}.csv** — every number that reads it is n/a on this page.")
    if report.get("not_captured"):
        lines.append("")
    lines += [f"Window: trades closed {report['window_start']} to {report['window_end']} (ET). "
              f"Eras are cumulative from each era's start; nothing is pooled across eras or lanes.", ""]
    lines += ["## Population", "", "| Lane | Era | closed in window | carried from era start | still open | excluded | no R frame | re-entries |",
              "|---|---|---|---|---|---|---|---|"]
    for (lane, era), c in sorted(report["population"].items()):
        lines.append(f"| {lane} | {era} | {c['window']} | {c['carried']} | {c['open']} | "
                     f"{', '.join(c['excluded']) or '—'} | {', '.join(c['no_r']) or '—'} | {', '.join(c['flagged']) or '—'} |")
    if report.get("pre_window_closes"):
        lines.append("\nTrades filled before the first window start and closed inside a window (era-B stop; not in the capture): "
                     + ", ".join(f"{k} {v}" for k, v in report["pre_window_closes"].items()) + ".")
    if report.get("legacy_paper_count") is not None:
        lines.append(f"\nLegacy `mi_paper_trades` rows closed in the window: {report['legacy_paper_count']} (expected 0).")
    if report.get("recorder_gaps"):
        lines += ["", "Recorder coverage (L1): " + "; ".join(
            f"{era}: {c['fills']} fills, {c['with_rows']} with recorder rows, {c['settled_pairs']} settled control pairs"
            + (f", GAP (no rows past the retry window): {', '.join(c['gaps'])}" if c["gaps"] else "")
            + (f", UNSETTLED (rows but no settled control pair past the retry window): {', '.join(c.get('unsettled', []))}" if c.get("unsettled") else "")
            for era, c in sorted(report["recorder_gaps"].items())) + "."]
    rr_ = report.get("recorder_runs")
    if rr_ is not None:
        if rr_ == NOT_CAPTURED:
            lines.append(f"Recorder heartbeat: {NOT_CAPTURED} (audit_recorder.csv).")
        else:
            miss = [s.isoformat() for s in rr_["missing"]]
            lines.append(f"Recorder heartbeat: the 18:04 ET job wrote its nightly row on {rr_['ran']} of {rr_['sessions']} sessions since {rr_['from']}"
                         + (f" (the job's first session; the window starts earlier)" if rr_['from'] == RECORDER_FIRST_SESSION else "")
                         + (f" (last {rr_['last_run']})" if rr_["last_run"] else " (never)")
                         + (f"; sessions with no row: {', '.join(miss[:10])}{' …' if len(miss) > 10 else ''}" if miss else "")
                         + f"; error rows {rr_['error_rows']}" + (f" ({'; '.join(rr_['error_samples'])})" if rr_["error_samples"] else "") + ".")
    if report.get("fidelity"):
        fd = report["fidelity"]
        lines += ["", f"Replay fidelity (§5: within max(0.25R, 10% of the real R); the replay's partial re-weighted to the shares the "
                      f"live sizer sold): {fd['pass']} of {fd['n']} fills pass — {fd['stored']} on the stored replay, {fd['reweighted']} "
                      f"only after re-weighting (their arms are compared with the replay) — {fd['old_pass']} under the old 0.25R bar; "
                      f"failures by class: " + (", ".join(f"{k} {v}" for k, v in fd["classes"].items()) or "none") + "."]
    lines += ["", "## Lenses", "", "| Lens | Lane / era | n | reading | verdict |", "|---|---|---|---|---|"]
    for row in report["lens_rows"]:
        lines.append(f"| {row['lens']} | {row['where']} | {row['n']} | {row['reading']} | {row['verdict']} |")
    lines += ["", "## The tail (the real trades; never gated by fidelity)", ""]
    for bucket, title in (("winners", f"≥ +{TAIL_WIN_R:.0f}R winners"), ("losers", f"≤ {TAIL_LOSS_R}R losers")):
        rows = report["tails"].get(bucket, [])
        lines.append(f"**{title}: {len(rows)}**")
        if rows:
            lines += ["", "| Ticker | Lane | Era | alert | fill min | shares | fill vs trigger | stop % / ADR | peak R (session) | R | capture | "
                           "exit legs | hold | regime | admission era | label | best / worst arm | fidelity | 10-session high after exit (R) |",
                      "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
            for r in rows:
                fidelity_s = ("pass" + (f" ({r['fidelity_via']})" if r.get("fidelity_via") else "") if r["fidelity"]
                              else ("fail: " + str(r["fidelity_cls"]) if r["fidelity"] is not None else "n/a"))
                lines.append(f"| {r['ticker']} | {r['lane']} | {r['era']} | {r['alert_date']} | {r['fill_minute'] or 'n/a'} | "
                             f"{r['entry_shares'] if r['entry_shares'] is not None else 'n/a'} | {fmt(r['fill_vs_trigger_pct'])}% | "
                             f"{fmt(r['stop_pct'])} / {fmt(r['stop_per_adr'])} | {fmt(r['peak_r'])} ({r['peak_session'] if r['peak_session'] is not None else 'n/a'}) | "
                             f"{fmt(r['realized_r'])} | {fmt(r['capture_pct'])} | {_legs_str(r['exit_legs'])} | "
                             f"{r['hold_days'] if r['hold_days'] is not None else 'n/a'} | {r['regime'] or 'n/a'} | "
                             f"{r['admission_era'] or 'n/a'}{' (derived)' if r['admission_era_source'] == 'derived' else ''} | "
                             f"{r['label'] or '—'} | {r['best_arm'] or 'n/a'} / {r['worst_arm'] or 'n/a'} | {fidelity_s} | {fmt(r['post_exit_high_r'])} |")
        lines.append("")
    m = report.get("missed", {})
    lines += ["## Breakout: names that broke out but never got a paper slot", "",
              f"Missed records {m.get('missed_n', 0)} (mature {m.get('missed_mature', 0)}; {m.get('width_dropped', 0)} dropped by the width rule, "
              f"{m.get('bad_json', 0)} unreadable JSON), seated trades the same days {m.get('seated_n', 0)} (mature {m.get('seated_mature', 0)}; "
              f"all seated breakout trades {m.get('seated_all', 0)}); +2R-before-stop share missed "
              f"{fmt(m.get('missed_plus2r_share'))} vs seated {fmt(m.get('seated_plus2r_share'))}; median MFE (R) missed "
              f"{fmt(m.get('missed_mfe_median'))} vs seated {fmt(m.get('seated_mfe_median'))}. Verdict: {m.get('verdict', 'CAN\'T TELL')}.",
              f"Absence check: {report.get('missed_absence', 'n/a')}.", ""]
    lines += ["## The five folded reviews", "", "| Review | predicate count (its own bar) | verdict here |", "|---|---|---|"]
    for row in report.get("folded", []):
        lines.append(f"| {row['review']} | {row['n']} | {row['verdict']} |")
    if report.get("safeguard_voids") is not None:
        sv = report["safeguard_voids"]
        lines.append("\nLive/global safeguard transitions since the current era start (each one = the 08-29 runner read is void): "
                     + ("; ".join(sv) if sv else "none") + ".")
    elif "safeguard_transitions" in report.get("not_captured", []):
        lines.append(f"\nLive/global safeguard transitions since the current era start: {NOT_CAPTURED}.")
    lines += ["", f"**Action: {report['action']}**", ""]
    wl = report.get("window_trades", [])
    lines += ["## Every closed trade in the window (the forensic fields; the classification is written by inspection on run day)", "",
              f"{len(wl)} trade(s).", "",
              "| id | Ticker | Lane | Era | alert | fill min | shares | fill vs trigger | stop % / ADR | peak R | R | exit | legs | hold | regime | "
              "admission era | post-11-04 | label | read 11-06 | fidelity | 10-session high after (R) | class |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in wl:
        lines.append(f"| {r['id']} | {r['ticker']} | {r['lane']} | {r['era']} | {r['alert_date']} | {r['fill_minute'] or 'n/a'} | "
                     f"{r['entry_shares'] if r['entry_shares'] is not None else 'n/a'} | {fmt(r['fill_vs_trigger_pct'])}% | "
                     f"{fmt(r['stop_pct'])} / {fmt(r['stop_per_adr'])} | {fmt(r['peak_r'])} | {fmt(r['realized_r'])} | {r['exit_reason']}"
                     f"{' (depth sale)' if r['depth_sale'] else ''} | {_legs_str(r['exit_legs'])} | "
                     f"{r['hold_days'] if r['hold_days'] is not None else 'n/a'} | {r['regime'] or 'n/a'} | {r['admission_era'] or 'n/a'} | "
                     f"{'yes' if r['post_1104'] else 'no'} | {r['label'] or '—'} | {'yes' if r.get('read_1106') else 'no'} | "
                     f"{'pass' if r['fidelity'] else ('fail: ' + str(r['fidelity_cls']) if r['fidelity'] is not None else 'n/a')} | "
                     f"{fmt(r['post_exit_high_r'])} | {r['forensic_class'] or '(by inspection)'} |")
    lines.append("")
    return "\n".join(lines)


# §7: which lens verdicts each folded review's row reads (finding 8). 482 asked stop + harvest + trail; the parked
# geometry review asked stop level + entry; exit_tune's sweep is the partial; runner_rule's fact is the two runner
# shapes (descriptive — no arm answers it); stop_too_wide has its own matrix verdict.
FOLD_MAP: dict[str, Any] = {"bracket_geometry_variants_parked": ("stop", "buy_point"),
                            "live_fill_counterfactuals_first_read_482": ("stop", "partials", "exits"),
                            "exit_tune_cohort_review": ("partials",),
                            "runner_rule_sweep_recut": "descriptive",
                            "stop_too_wide_outcome_cohort": "stop_too_wide"}
_LADDER_RANK = {v: i for i, v in enumerate(VERDICTS)}


def folded_rows(predicates: list[dict], arm_results: dict[str, dict], stw_verdict: str) -> list[dict]:
    """ALWAYS the five rows in FOLDED_REVIEWS order (finding 2): a review missing from predicates.csv — or a
    missing file — prints its count as NOT CAPTURED instead of vanishing. Verdict = the highest ladder rung any
    mapped arm reached (an arm on WATCH in the stop lens shows on the 482 row even when the trail arms are
    unreadable)."""
    counts = {p.get("review"): p.get("n") for p in predicates}
    out = []
    for rid in FOLDED_REVIEWS:
        spec = FOLD_MAP[rid]
        if spec == "descriptive":
            v = "descriptive"
        elif spec == "stop_too_wide":
            v = stw_verdict
        else:
            vs = [r["verdict"] for lens in spec for r in arm_results.get(lens, {}).values()]
            v = max(vs, key=lambda x: _LADDER_RANK.get(x, -1)) if vs else "CAN'T TELL"
        out.append({"review": rid, "n": counts.get(rid, NOT_CAPTURED) if counts.get(rid) not in (None, "") else NOT_CAPTURED,
                    "verdict": v})
    return out


def action_line(lens_rows: list[dict]) -> str:
    props = [r for r in lens_rows if r["verdict"] == "PROPOSE"]
    if not props:
        return "none"
    return "; ".join(f"{r['lens']} ({r['where']}): write the CHANGE_PROCESS proposal — needs an N ≥ 10 backtest "
                     f"and your sign-off" for r in props)


def _is_arm_row(row: dict) -> bool:
    """An arm-vs-live lens row (not a count lens, not a descriptive): build_report tags them; a bare row is read
    from its name ('<lens>: <arm>')."""
    if "kind" in row:
        return row["kind"] == "arm"
    name = row.get("lens", "")
    return ": " in name and name.split(": ", 1)[1] in ALL_ARMS


def answer_line(lens_rows: list[dict], tails_: dict, recorder_gaps_: Optional[dict] = None, fidelity_: Optional[dict] = None,
                not_captured: Iterable[str] = ()) -> str:
    """Line 1 (finding 1). In order: a capture that is not whole; a PROPOSE; a recorder that owes fills; then — ONLY
    when an arm lens on the current era actually read NOTHING — 'Nothing beats what we run'. Arms that only WATCH
    say so; no readable arm lens says 'too few trades to read yet'. The old line printed 'Nothing beats' on an empty
    capture and on three fills with no recorder rows."""
    nc = list(not_captured)
    props = [r for r in lens_rows if r["verdict"] == "PROPOSE"]
    arm_rows_ = [r for r in lens_rows if _is_arm_row(r)]
    nothings = [r for r in arm_rows_ if r["verdict"] == "NOTHING"]
    watches = [r for r in arm_rows_ if r["verdict"] == "WATCH"]
    gap_n = recorder_gap_count(recorder_gaps_ or {})
    if nc:
        head = f"capture incomplete — {len(nc)} file(s) NOT CAPTURED ({', '.join(nc)}); nothing on this page is a verdict"
    elif props:
        head = f"{len(props)} lens(es) worth a CHANGE_PROCESS proposal"
    elif gap_n:
        head = f"recorder gap on {gap_n} fill(s) — the arm lenses cannot be read until the recorder catches up"
    elif nothings:
        head = "Nothing beats what we run" + (f"; {len(watches)} arm(s) on watch" if watches else "")
    elif watches:
        head = f"{len(watches)} arm(s) on watch (won on under {PROPOSE_MIN} trades); nothing proposed, nothing read as beaten"
    else:
        fid_s = ""
        if fidelity_ and fidelity_.get("n"):
            fid_s = f" ({fidelity_['n']} closed live fill(s), {fidelity_.get('pass', 0)} with a settled replay pair that passes)"
        head = "too few trades to read yet" + fid_s
    return (f"{head}; big winners {len(tails_.get('winners', []))}, bad losers {len(tails_.get('losers', []))}; "
            f"action: {'see below' if props and not nc else 'none'}.")


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# manifest + the report driver (reads CSVs only)
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def missing_captures(data: Path) -> list[str]:
    """Every capture/*.sql whose CSV is absent from the run's data dir (finding 2: a failed capture must never read
    as an empty month)."""
    return [name for name in REQUIRED_CAPTURES if not (data / f"{name}.csv").exists()]


def write_manifest(run_dir: Path, captured_at: str) -> str:
    data = run_dir / "data"
    lines = [f"captured_at: {captured_at}"]
    for p in sorted(data.glob("*.csv")):
        rows = max(0, sum(1 for _ in open(p, "rb")) - 1)
        lines.append(f"{p.name}: rows {rows} md5 {hashlib.md5(p.read_bytes()).hexdigest()}")
    for name in missing_captures(data):
        lines.append(f"{name}.csv: NOT CAPTURED")
    (run_dir / "MANIFEST.txt").write_text("\n".join(lines) + "\n")
    return "\n".join(lines)


def _csv(data: Path, name: str) -> list[dict]:
    """[] for a missing file — build_report has already recorded the miss in `not_captured` (finding 2); nothing
    downstream may read [] as 'nothing happened' without checking that list."""
    p = data / name
    return read_csv(p) if p.exists() else []


def _daily_by_ticker(rows: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        out[r["ticker"]].append(r)
    for k in out:
        out[k].sort(key=lambda b: d(b["trade_date"]))
    return out


def read_1106_ids_from(path: Optional[Path]) -> set[str]:
    """The 20 fills the 11-06 read scored: ONLY the id column of its capture is read (no outcome column)."""
    if path is None or not path.exists():
        return set()
    with open(path, newline="") as fh:
        return {row["id"] for row in csv.DictReader(fh) if row.get("id")}


def build_report(run_dir: Path, run_date: date, window_start: date, prev_capture: Optional[date] = None,
                 read_1106_csv: Optional[Path] = None, labelled: Optional[list[tuple[str, str]]] = None,
                 abstentions: Optional[set[tuple[str, str]]] = None, grades: Optional[list[dict]] = None) -> dict:
    """Assemble the report dict from the captured CSVs. Every number comes from the functions above; every lens of
    the plan reaches the page. `labelled` / `abstentions` / `grades` default to the repo's own lists (tests inject)."""
    data = run_dir / "data"
    not_captured = missing_captures(data)           # finding 2: named, never read as an empty month
    if "trades" in not_captured:
        raise SystemExit("trades.csv NOT CAPTURED — nothing to read")
    trades = read_csv(data / "trades.csv")
    cf = _csv(data, "cf_arms.csv")
    audit_rec = _csv(data, "audit_recorder.csv")
    sd = {str(r["trade_id"]): r for r in _csv(data, "sell_discipline.csv")}
    audit = _csv(data, "audit_breakout.csv")
    daily = _daily_by_ticker(_csv(data, "daily_bars.csv"))
    skips_stw = _csv(data, "skips_stop_too_wide.csv")
    admitted = _csv(data, "admitted_magna53.csv")
    skips_all = _csv(data, "skips_window.csv")
    alerts = _csv(data, "ep_alerts.csv")
    blist = _csv(data, "breakout_list.csv")
    toggles = _csv(data, "strategy_toggles.csv")
    strategies = _csv(data, "strategies.csv")
    transitions = _csv(data, "safeguard_transitions.csv")
    predicates = _csv(data, "predicates.csv")
    legacy = _csv(data, "legacy_paper_count.csv")
    pre_window = _csv(data, "pre_window_closes.csv")
    start = (prev_capture + timedelta(days=1)) if prev_capture else window_start
    out_lines = [f"calendar: {CALENDAR}"]

    mism = era_mismatches(trades, cf)
    if mism:
        raise SystemExit("ERA MISMATCH — the read stops:\n  " + "\n  ".join(mism))
    read_ids = read_1106_ids_from(read_1106_csv)
    pop = population(trades, start, run_date, read_1106_ids=read_ids)
    arm_rows = {(str(r["trade_id"]), r["arm"]): r for r in cf}
    la_rows = {tid: row for (tid, arm), row in arm_rows.items() if arm == "live_actual"}
    by_id = {str(t["id"]): t for t in trades}
    closed = [t for t in trades if (t.get("status") or "") == "closed" and not (t.get("pnl_attribution") or "")]
    lane_era: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for t in closed:
        lane_era[(lane_of(t), era_of(t))].append(t)
    gaps = recorder_gaps(trades, cf, run_date) if "cf_arms" not in not_captured else {}
    rec_runs = recorder_runs(audit_rec, start, run_date) if "audit_recorder" not in not_captured else NOT_CAPTURED

    # fidelity (L1) + the arm lenses
    fid = {}
    for tid, t in by_id.items():
        if lane_of(t) == "L1" and (t.get("status") or "") == "closed":
            fid[tid] = fidelity(t, arm_rows.get((tid, "live_actual")), arm_rows.get((tid, "live_replay")))
    fills_by_era: dict[str, list[dict]] = defaultdict(list)
    for tid, fdct in fid.items():
        t = by_id[tid]
        if t.get("pnl_attribution"):
            continue
        adm, _src = admission_era_of(t, la_rows.get(tid))
        fills_by_era[era_of(t)].append({"trade_id": tid, "fidelity_pass": fdct["pass"], "baseline": fdct.get("baseline") or "live_actual",
                                        "live_actual": arm_rows.get((tid, "live_actual")),
                                        "live_replay": arm_rows.get((tid, "live_replay")),
                                        "admission_era": adm, "post_1104": post_open_floor(t), "regime": t.get("regime"),
                                        "admission_cell": admission_cell_key(t, la_rows.get(tid))})
    current_era = exit_era_label(run_date, "magna53")
    lens_rows = []
    arm_results = {}
    for lens in ("buy_point", "stop", "partials", "exits"):
        res_by_arm = arm_lens(lens, fills_by_era, arm_rows, current_era)
        arm_results[lens] = res_by_arm
        for arm, res in res_by_arm.items():
            cur = res["cells"].get(current_era)
            split = f"; pre-11-04 {cur.n_pre_1104} / post {cur.n_post_1104}" if cur and current_era == "era_e" else ""
            lens_rows.append({"lens": f"{lens}: {arm}", "where": f"L1 / {current_era}", "n": cur.n if cur else 0,
                              "reading": res["why"] + split, "verdict": res["verdict"], "kind": "arm"})
            for era, c in sorted(res["cells"].items()):
                out_lines.append(f"{lens:9s} {arm:28s} {era}: n {c.n} (pre-11-04 {c.n_pre_1104} / post {c.n_post_1104}; baseline=replay on {c.baseline_replay}) "
                                 f"R_cap Δ {fmt(c.rcap_delta_sum)} drop-best {fmt(c.drop_best)} R_own Δ {fmt(c.rown_delta_sum)} tail-clip {c.tail_clip} "
                                 f"arm≥4R {c.arm_ge4} live≥4R {c.live_ge4} engine {'agrees' if c.engine_agrees else 'disagrees'} won {c.won} excluded {dict(c.excluded)}")
        for cell in admission_cells(lens, fills_by_era, arm_rows):
            out_lines.append(f"admission {lens:9s} {cell['arm']:28s} {cell['era']} {cell['admission_era']} {cell['side']}: n {cell['n']} "
                             f"R_cap Δ {fmt(cell['rcap_delta_sum'])} won {cell['won']}")
    for cell in regime_table(fills_by_era, arm_rows):
        out_lines.append(f"regime {cell['arm']:28s} {cell['era']} {cell['regime']:10s}: n {cell['n']}{' THIN' if cell['thin'] else ''} "
                         f"R_cap Δ {fmt(cell['rcap_delta_sum'])} won {cell['won']}")

    # recorder check: stop_low_of_day vs stop_orb_low identical rows (one confirmation, not two)
    same = total = 0
    for tid in fid:
        a, b = arm_rows.get((tid, "stop_low_of_day")), arm_rows.get((tid, "stop_orb_low"))
        if a and b and a.get("outcome") == "settled" and b.get("outcome") == "settled":
            total += 1
            same += abs((f(a.get("realized_r")) or 0) - (f(b.get("realized_r")) or 0)) < 1e-9
    out_lines.append(f"recorder check: stop_low_of_day = stop_orb_low on {same} of {total} settled fills")

    # admission-era mix per lane/era (the recorder stamp; derived where no row) + I12/I16: every stamp that
    # disagrees with the derived label is listed (the 11-04..11-07 rows were stamped before the #718 row existed)
    for (lane, era), ts in sorted(lane_era.items()):
        mix = Counter()
        for t in ts:
            adm, src = admission_era_of(t, la_rows.get(str(t["id"])))
            mix[f"{adm}{' (derived)' if src == 'derived' else ''}"] += 1
        out_lines.append(f"admission mix {lane} {era}: " + ", ".join(f"{k} {v}" for k, v in sorted(mix.items()))
                         + f"; post-11-04 {sum(post_open_floor(t) for t in ts)} of {len(ts)}")
    for t in closed:
        if lane_of(t) == "L3":
            continue
        row = la_rows.get(str(t["id"]))
        ad = d(t.get("alert_date"))
        if row and row.get("admission_era") and ad and str(row["admission_era"]) != admission_era_as_of(ad):
            out_lines.append(f"admission stamp vs derived: {t.get('ticker')} trade {t.get('id')} (alert {ad}): stamp {row['admission_era']} "
                             f"vs derived {admission_era_as_of(ad)} — cell key uses {'derived (I16)' if post_open_floor(t) else 'the stamp (I12)'}")

    # selection (L1 labels; L3 grades)
    labelled_all = labelled if labelled is not None else operator_labels()
    abst = abstentions if abstentions is not None else declared_abstentions()
    labelled_in = [(tk, ad) for tk, ad in labelled_all
                   if start <= date.fromisoformat(ad) <= run_date or any(
                       t.get("ticker") == tk and str(t.get("alert_date")) == ad for t in trades)]
    labels_map = {(tk, ad): "his EP" for tk, ad in labelled_all}
    sel = selection_labels(trades, skips_all, labelled_in, alerts, abst)
    sel_v, sel_missed = selection_verdict(sel)
    lens_rows.append({"lens": "selection: his EP labels", "where": "L1", "n": len([s for s in sel if s["did"] != "abstention"]),
                      "reading": (", ".join(f"{s['ticker']} {s['did']}" for s in sel) or "no labelled name in the window")
                      + (f"; {sel_missed} missed (under 3 trades)" if 0 < sel_missed < READABLE_MIN else ""),
                      "verdict": sel_v})
    l3 = [t for t in trades if lane_of(t) == "L3"]
    grades_ = grades if grades is not None else breakout_grades_fixture()
    bsel = breakout_selection(l3, grades_)
    lens_rows.append({"lens": "selection: his breakout grades (chart sheets)", "where": f"L3 / {BREAKOUT_ERA}", "n": bsel["graded"],
                      "reading": f"graded {bsel['graded']} of {bsel['n']} (" + ", ".join(f"{k} {v}" for k, v in sorted(bsel["by_grade"].items())) + ")",
                      "verdict": bsel["verdict"]})

    # buy point (a): slippage per era on L1 fill_facts (verdict on the current era; the others are context, D1)
    for era in sorted(fills_by_era):
        fills = []
        for fl in fills_by_era[era]:
            ff = arm_rows.get((fl["trade_id"], FILL_FACTS))
            la_cls, _, la_cap = classify_arm_row(fl["live_actual"], "live_actual")
            if la_cls == "settled":
                fills.append({"fill_vs_trigger_pct": (ff or {}).get("fill_vs_trigger_pct"), "live_rcap": la_cap,
                              "real_risk_vs_trigger_risk": (ff or {}).get("real_risk_vs_trigger_risk")})
        st = slippage_test(fills)
        hist = fill_minute_histogram([by_id[fl["trade_id"]] for fl in fills_by_era[era]])
        lens_rows.append({"lens": "buy point: fill vs trigger", "where": f"L1 / {era}", "n": st["n"],
                          "reading": f"median {fmt(st['median_pct'])}% max {fmt(st['max_pct'])}% over +1%: {st['over_1pct']} "
                                     f"(R_cap sum {fmt(st['over_sum'])} vs {fmt(st['under_sum'])}); fill vs trigger unknown on {st['null_n']}; "
                                     f"real risk ÷ trigger risk median {fmt(st['real_risk_median'], 3)} max {fmt(st['real_risk_max'], 3)}; "
                                     f"fill minutes " + ", ".join(f"{k} {v}" for k, v in sorted(hist.items())),
                          "verdict": st["verdict"] if era == current_era else f"context ({st['verdict']})"})

    # stop (b)/(c), partials (b), exits (b)-(d): descriptives per lane/era
    for (lane, era), ts in sorted(lane_era.items()):
        if lane == "L4":
            continue
        pdsc, edsc = partial_descriptives(ts, sd, la_rows), exit_descriptives(ts, sd, daily, la_rows)
        ran = [stopped_then_ran(t, daily) for t in ts]
        split = f"; pre-11-04 {sum(not post_open_floor(t) for t in ts)} / post {sum(post_open_floor(t) for t in ts)}" if era == "era_e" else ""
        lens_rows.append({"lens": "stop: stopped out, then ran", "where": f"{lane} / {era}", "n": sum(x is not None for x in ran),
                          "reading": f"{sum(bool(x) for x in ran)} of {sum(x is not None for x in ran)} stop-outs printed +2R within 5 sessions "
                                     f"({sum(x is None for x in ran)} not judgeable); stop width median {fmt(edsc['stop_pct_median'])}% / "
                                     f"{fmt(edsc['stop_per_adr_median'])} ADR{split}", "verdict": "descriptive"})
        lens_rows.append({"lens": "partials: fired / kept", "where": f"{lane} / {era}", "n": pdsc["n"],
                          "reading": f"partial fired {pdsc['partial_fired']}; median capture {fmt(pdsc['capture_pct_median'])}; median giveback "
                                     f"{fmt(pdsc['giveback_r_median'])}R; runner shape — partial then breakeven {pdsc['runner_shape_partial']} (era C's), "
                                     f"armed then breakeven {pdsc['runner_shape_armed']} (eras D/E's, the row's own arm; n/a on {pdsc['armed_na']} with no price-armed breakeven); "
                                     f"≤2-share positions {pdsc['shares_le_2']}; no record {pdsc['no_record']}{split}", "verdict": "descriptive"})
        dis = edsc["disappoints"]
        lens_rows.append({"lens": "exits: how trades ended", "where": f"{lane} / {era}", "n": edsc["n"],
                          "reading": ", ".join(f"{k} {v}" for k, v in edsc["reasons"].most_common()) + f"; depth sales {edsc['depth_sales']}"
                                     + (f" (next-open sale vs signal close median {fmt(edsc['depth_cost_r_median'])}R on {edsc['depth_cost_n']})" if edsc["depth_cost_n"] else "")
                                     + f"; median hold {edsc['hold_days_median']} days; median peak {fmt(edsc['peak_r_median'])}R vs kept {fmt(edsc['realized_r_median'])}R; "
                                     f"disappoints (live R_cap sum {fmt(edsc['rcap_sum'])} on {edsc['rcap_n']}): "
                                     f"{'yes' if dis else ('no' if dis is False else 'n/a (no recorder)')}{split}", "verdict": "descriptive"})
    stw = stop_too_wide_section(skips_stw, admitted, daily)
    lens_rows.append({"lens": "stop: the stop-too-wide filter", "where": "magna53 skips vs admitted (both modes, since 05-05)", "n": stw["rejected_n"],
                      "reading": f"rejected {stw['rejected_n']} hit {fmt(stw['rejected_rate'])} median MFE {fmt(stw['rejected_median'])}% vs admitted "
                                 f"{stw['admitted_n']} hit {fmt(stw['admitted_rate'])} median {fmt(stw['admitted_median'])}%; {stw['matrix']}"
                                 + (f" (two-sided p {stw['p']:.3f})" if stw['p'] is not None else "")
                                 + f"; unscored {stw['rejected_unscored']} / {stw['admitted_unscored']}; admitted modes "
                                 + ", ".join(f"{k} {v}" for k, v in sorted(stw["admitted_modes"].items())) + "; admitted admission eras "
                                 + ", ".join(f"{k} {v}" for k, v in sorted(stw["admitted_admission_eras"].items())), "verdict": stw["verdict"]})

    # L3 buy point
    bbp = breakout_buy_point(l3, blist, audit)
    lens_rows.append({"lens": "buy point: fill vs list level / fill-stop decision / thirds", "where": f"L3 / {BREAKOUT_ERA}", "n": bbp["n"],
                      "reading": f"fill vs level median {fmt(bbp['fill_vs_level_median'])}% max {fmt(bbp['fill_vs_level_max'])}% on {bbp['fill_vs_level_n']}; "
                                 f"fill-stop decisions " + ", ".join(f"{k} {v}" for k, v in sorted(bbp["decisions"].items()))
                                 + "; thirds " + ", ".join(f"{k} {v}" for k, v in sorted(bbp["thirds"].items())), "verdict": "descriptive"})

    # the tail (real trades) + the per-trade window list
    def best_worst(tid: str):
        vals = [(f(arm_rows[(tid, a)].get("realized_r")), a) for a in ALL_ARMS
                if (tid, a) in arm_rows and arm_rows[(tid, a)].get("outcome") == "settled" and f(arm_rows[(tid, a)].get("realized_r")) is not None]
        if not vals:
            return None, None
        return f"{max(vals)[1]} {fmt(max(vals)[0])}", f"{min(vals)[1]} {fmt(min(vals)[0])}"
    tl = tails(trades, sd, fid, best_worst, arm_rows, daily, labels_map)
    window_trades = []
    for t in trades:
        if in_window(t, start, run_date):
            row = trade_row(t, sd, fid, arm_rows, daily, labels_map, best_worst)
            row["read_1106"] = str(t["id"]) in read_ids
            window_trades.append(row)

    # missed-by-slots + absence observables
    recs_all, bad_json = missed_records(audit)
    recs = [r for r in recs_all if width_ok(r)]
    missed, malformed = [], 0
    for r in recs:
        day, px, stop = d(r.get("day")), f(r.get("break_price")), f(r.get("stop"))
        if day is None or px is None or stop is None:
            malformed += 1          # finding 5: counted and named, never a silent skip
            continue
        missed.append({"ticker": r.get("ticker"), "day": day, "walk": missed_proxy_walk(px, stop, day, daily.get(r.get("ticker"), []))})
    missed_days = {m["day"] for m in missed}
    seated_all, seated = [], []
    for t in l3:
        fday, px, stop = et_date(t.get("filled_at")), f(t.get("entry_price")), f(t.get("hard_stop"))
        if fday is None or px is None or stop is None:
            continue
        s = {"ticker": t.get("ticker"), "day": fday, "realized_r": trade_realized_r(t),
             "walk": missed_proxy_walk(px, stop, fday, daily.get(t.get("ticker"), []))}
        seated_all.append(s)
        if fday in missed_days:
            seated.append(s)
    mvs = missed_vs_seated(missed, seated)
    mvs["width_dropped"] = len(recs_all) - len(recs)
    mvs["bad_json"] = bad_json
    mvs["malformed"] = malformed
    mvs["raw_n"] = len(recs_all) + bad_json          # every missed-by-slots row written, readable or not
    mvs["seated_all"] = len(seated_all)
    toggle = next((r.get("state") or r.get("status") or r.get("value") for r in toggles if r.get("safeguard") == "breakout_v1_paper"), None)
    strat = next((r for r in strategies if r.get("strategy_id") == "breakout_v1"), None)
    obs = absence_observables(audit, len(l3), len({r.get("scan_date") for r in blist}), toggle, strat)
    lens_rows.append({"lens": "breakout: missed by slots vs seated", "where": f"L3 / {BREAKOUT_ERA}", "n": mvs["missed_mature"],
                      "reading": f"+2R-before-stop share missed {fmt(mvs['missed_plus2r_share'])} vs seated {fmt(mvs['seated_plus2r_share'])}; "
                                 f"median MFE missed {fmt(mvs['missed_mfe_median'])}R vs seated {fmt(mvs['seated_mfe_median'])}R", "verdict": mvs["verdict"]})

    # folded reviews: ALWAYS the five rows (finding 2) — the predicate counts (verbatim SQL) beside the lens
    # verdicts each one maps to (FOLD_MAP, finding 8)
    folded = folded_rows(predicates, arm_results, stw["verdict"])
    voids = safeguard_transitions_check(transitions, era_start_for(current_era, window_start)) if "safeguard_transitions" not in not_captured else None

    report = {"run_date": run_date.isoformat(), "window_start": start.isoformat(), "window_end": run_date.isoformat(),
              "population": dict(pop["by_lane_era"]), "lens_rows": lens_rows, "tails": tl, "window_trades": window_trades,
              "fidelity": {"n": len(fid), "pass": sum(v["pass"] for v in fid.values()),
                           "stored": sum(v["via"] == "stored" for v in fid.values()),
                           "reweighted": sum(v["via"] == "reweighted" for v in fid.values()),
                           "old_pass": sum(v["tol_old_pass"] for v in fid.values()),
                           "classes": Counter(v["cls"] for v in fid.values() if not v["pass"])},
              "recorder_gaps": gaps, "recorder_runs": rec_runs, "not_captured": not_captured, "missed": mvs,
              "missed_absence": absence_sentence(obs, mvs["missed_n"], raw_n=mvs["raw_n"], width_dropped=mvs["width_dropped"],
                                                 malformed=malformed, bad_json=bad_json, not_captured=not_captured) + f" (observables: {obs})",
              "folded": folded, "safeguard_voids": voids,
              "legacy_paper_count": (f(legacy[0].get("legacy_paper_closed_in_window")) if legacy else None),
              "pre_window_closes": {f"{r.get('account_mode')}/{r.get('signal_type')}": r.get("n") for r in pre_window},
              "selection": sel, "breakout_selection": bsel, "breakout_buy_point": bbp, "stop_too_wide": stw}
    report["action"] = action_line(lens_rows) if not not_captured else "none — re-capture the missing file(s) and re-run"
    report["answer"] = answer_line(lens_rows, tl, gaps, report["fidelity"], not_captured)
    if not_captured:
        out_lines.insert(0, "NOT CAPTURED: " + ", ".join(f"{n}.csv" for n in not_captured))
    if rec_runs != NOT_CAPTURED:
        out_lines.append(f"recorder heartbeat: ran {rec_runs['ran']} of {rec_runs['sessions']} sessions; missing "
                         + (", ".join(s.isoformat() for s in rec_runs["missing"]) or "none") + f"; error rows {rec_runs['error_rows']}")
    out_lines.append("fidelity per fill: " + "; ".join(
        f"{by_id[t].get('ticker')} {('pass ' + str(v['via'])) if v['pass'] else 'FAIL ' + str(v['cls'])} Δ {fmt(v['diff'])}"
        + (f" (re-weighted Δ {fmt(v['diff_reweighted'])}, live fraction {fmt(v['live_fraction'])})" if v.get("diff_reweighted") is not None else "")
        + f" tol {fmt(v['tol'])}" for t, v in fid.items()))
    out_lines.append("safeguard voids: " + ("; ".join(voids) if voids else "none"))
    report["out"] = "\n".join(out_lines)
    return report


def main(argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--manifest", metavar="RUN_DIR")
    ap.add_argument("--report", metavar="RUN_DIR")
    ap.add_argument("--emit-predicates", metavar="OUT_SQL", help="write capture/predicates.sql from data_gated_reviews.yaml")
    ap.add_argument("--run-date", default=None)
    ap.add_argument("--prev-capture", default=None, help="ET date of the previous run's capture (window lower bound)")
    ap.add_argument("--read-1106", default=str(_REPO / "scripts/probes/_482_read_1106/data/live_all.csv"),
                    help="the 11-06 read's trade capture; ONLY its id column is read, to flag those fills")
    a = ap.parse_args(argv)
    if a.emit_predicates:
        Path(a.emit_predicates).write_text(emit_predicates_sql(_REPO / "data_gated_reviews.yaml"))
        print(f"wrote {a.emit_predicates}")
        return 0
    if a.manifest:
        print(write_manifest(Path(a.manifest), datetime.now(_ET).isoformat()))
        return 0
    if a.report:
        run_dir = Path(a.report)
        run_date = d(a.run_date) or datetime.now(_ET).date()
        rep = build_report(run_dir, run_date, FIRST_WINDOW_START, d(a.prev_capture), Path(a.read_1106))
        md = render(rep)
        (run_dir / "review.md").write_text(md)
        (run_dir / "review.out").write_text(rep["out"] + "\n")
        print(md)
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
