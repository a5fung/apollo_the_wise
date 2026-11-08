"""#720 — the monthly comprehensive trade review: RUNNER SKELETON.

Plan: docs/analysis/720_monthly_review_plan_2026-11-08.md (pre-registered 2026-11-08, before any outcome
row of the first window was read). This file holds the queries (capture/*.sql, read-only) and every
computation as a pure function over CSV dicts, so the review can be unit-tested on INVENTED fixtures
(tests/test_720_monthly_review.py) and run on 11-29 with no new code.

CAPTURE ONCE, READ MANY. Run day:
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
import json
import statistics
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterable, Optional
from zoneinfo import ZoneInfo

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from agents.market_intelligence.book_geometry_arms import capped_dollar_r  # noqa: E402
from agents.market_intelligence.broker.order_manager import plus8r_partial_shares  # noqa: E402
from agents.market_intelligence.rule_eras import exit_era_label  # noqa: E402
from agents.market_intelligence.sell_discipline import trade_realized_r, trade_risk_per_share  # noqa: E402


def _replay_constant(name: str):
    """Read ONE constant from scripts/ep_replay.py without re-typing it (the date the whole-share partial sizer
    changed lives only there, by that module's own design)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("ep_replay_for_720", _REPO / "scripts" / "ep_replay.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("ep_replay_for_720", mod)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return getattr(mod, name)


PARTIAL_MIN_ONE_SHARE_FROM: date = _replay_constant("PARTIAL_MIN_ONE_SHARE_FROM")

_ET = ZoneInfo("America/New_York")
_UTC = ZoneInfo("UTC")

# ── pinned constants (the plan, §1 / §2 / §5 / §6) ──────────────────────────────────────────────
FIRST_WINDOW_START = date(2026, 8, 16)     # era C start = the recorder's BACKFILL_FROM
READABLE_MIN = 3                           # fewer paired / readable trades -> CAN'T TELL
PROPOSE_MIN = 10                           # the CHANGE_PROCESS N
TIE = 0.05
FIDELITY_ABS = 0.25
FIDELITY_REL = 0.10
SMALL_POSITION_SHARES = 3
TAIL_WIN_R = 4.0
TAIL_LOSS_R = -1.5
MISSED_WALK_SESSIONS = 10
STOPPED_THEN_RAN_SESSIONS = 5
BREAKOUT_ERA = "bp1"                       # the pp exit as deployed 2026-10-31

CONTROLS = ("live_actual", "live_replay")
STOP_ARMS = ("stop_orb_low", "stop_adr_050", "stop_adr_075", "stop_orb_3r", "stop_low_of_day")
ENTRY_ARMS = ("entry_first_hour_bar", "book_first_hour_low_of_day")
HARVEST_ARMS = ("harvest_no_breakeven", "harvest_trail_only", "harvest_t3", "harvest_legacy_2r")
TRAIL_ARMS = ("trail_pivot_swing", "trail_character_ma")
LENS_ARMS = {"buy_point": ENTRY_ARMS, "stop": STOP_ARMS, "partials": HARVEST_ARMS, "exits": TRAIL_ARMS}
FILL_FACTS = "fill_facts"

MISSED_EVENT = "breakout_v1_missed_by_slots"
HOLD_EVENT = "breakout_v1_entry_hold"
FILL_STOP_EVENT = "breakout_v1_fill_stop_checked"

VERDICTS = ("CAN'T TELL", "NOTHING", "WATCH", "PROPOSE")


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
    if isinstance(x, date):
        return x
    return date.fromisoformat(str(x)[:10])


def et_date(ts: Any) -> Optional[date]:
    """The ET date of a TIMESTAMPTZ as psql prints it ('2026-10-07 13:31:05.123+00' or ISO)."""
    if ts is None or ts == "":
        return None
    if isinstance(ts, datetime):
        dt = ts if ts.tzinfo else ts.replace(tzinfo=_UTC)
        return dt.astimezone(_ET).date()
    s = str(ts).strip().replace(" ", "T", 1)
    if s.endswith("+00"):
        s = s[:-3] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_UTC)
    return dt.astimezone(_ET).date()


def truthy(x: Any) -> bool:
    return str(x).strip().lower() in ("t", "true", "1", "yes")


def median(vals: Iterable[float]) -> Optional[float]:
    vals = [v for v in vals if v is not None]
    return statistics.median(vals) if vals else None


def fmt(v: Optional[float], p: int = 2) -> str:
    return "n/a" if v is None else f"{v:+.{p}f}"


def read_csv(path: Path) -> list[dict]:
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh))


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


def in_window(trade: dict, start: date, end: date) -> bool:
    """Closed, with closed_at's ET date in (start-1, end]. Open rows are never in a window."""
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


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# §5 fidelity — the fairer test
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def live_partial_shares(held: int, fill_day: Optional[date]) -> int:
    """Whole shares the LIVE profit-take sold on `fill_day`: `plus8r_partial_shares` (2 -> 1) from the 2026-10-12
    size rule (`scripts/ep_replay.PARTIAL_MIN_ONE_SHARE_FROM`, imported), `int(held // 3)` (2 -> 0) before it.
    An unknown fill day uses today's rule."""
    if fill_day is not None and fill_day < PARTIAL_MIN_ONE_SHARE_FROM:
        return int(held // 3)
    return plus8r_partial_shares(held)


def partial_size_bound(entry_shares: Optional[float], target_r: Optional[float], replay_partial_fired: bool,
                       fill_day: Optional[date] = None) -> float:
    """The whole-share allowance: |live_fraction - 1/3| x target_r, only when the replay's partial fired on a
    position of <= 3 shares. Under today's sizer: 1 share -> 0 sold -> 8/3; 2 -> 1/2 -> 4/3; 3 -> 1/3 -> 0.
    Before 2026-10-12 a 2-share position sold NOTHING, so its bound is 1/3 x target_r (8/3). Else 0."""
    if not replay_partial_fired or entry_shares is None or target_r is None:
        return 0.0
    held = int(entry_shares)
    if held <= 0 or held > SMALL_POSITION_SHARES:
        return 0.0
    live_fraction = live_partial_shares(held, fill_day) / held
    return abs(live_fraction - 1.0 / 3.0) * float(target_r)


def fidelity(trade: dict, live_actual: Optional[dict], live_replay: Optional[dict]) -> dict:
    """-> {pass, diff, tol, tol_old_pass, cls}. Quotable arm numbers need pass=True. The old 0.25R result rides
    beside it once for continuity. A missing / unsettled control -> pass False, cls 'controls_unsettled'."""
    if (live_actual is None or live_replay is None or live_actual.get("outcome") != "settled"
            or live_replay.get("outcome") != "settled"):
        return {"pass": False, "diff": None, "tol": None, "tol_old_pass": False, "cls": "controls_unsettled"}
    ra, rr = f(live_actual.get("realized_r")), f(live_replay.get("realized_r"))
    if ra is None or rr is None:
        return {"pass": False, "diff": None, "tol": None, "tol_old_pass": False, "cls": "controls_unsettled"}
    diff = rr - ra
    shares = f(trade.get("entry_shares"))
    fill_day = d(live_replay.get("fill_day")) or et_date(trade.get("filled_at"))
    bound = partial_size_bound(shares, f(live_replay.get("target_r")), truthy(live_replay.get("partial_fired")), fill_day)
    tol = max(FIDELITY_ABS, FIDELITY_REL * abs(ra)) + bound
    ok = abs(diff) <= tol + 1e-9
    return {"pass": ok, "diff": diff, "tol": tol, "tol_old_pass": abs(diff) <= FIDELITY_ABS + 1e-9,
            "cls": None if ok else classify_fidelity_miss(trade, live_actual, live_replay)}


def classify_fidelity_miss(trade: dict, live_actual: dict, live_replay: dict) -> str:
    shares = f(trade.get("entry_shares"))
    if shares is not None and shares <= SMALL_POSITION_SHARES and truthy(live_replay.get("partial_fired")):
        return "whole_share"
    if (str(live_actual.get("exit_session")) != str(live_replay.get("exit_session"))
            or (live_actual.get("final_reason") or "") != (live_replay.get("final_reason") or "")):
        return "exit_session_differs"
    return "other"


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
    """fills: one dict per fill in the era with keys trade_id, fidelity_pass, live_actual, live_replay, arm_row.
    A paired fill = live_actual settled + fidelity pass + the arm scoreable (settled or no_entry)."""
    c = EraCell(arm=arm, era=era)
    eng: list[float] = []
    for fl in fills:
        la_cls, la_own, la_cap = classify_arm_row(fl.get("live_actual"), "live_actual")
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


def verdict(cells_by_era: dict[str, EraCell], current_era: str) -> tuple[str, str]:
    """The ladder (§2). -> (verdict, reason). Current era not readable -> CAN'T TELL; any readable era LOST ->
    NOTHING; current WON on 3-9 -> WATCH; on >= 10 -> PROPOSE."""
    cur = cells_by_era.get(current_era)
    if cur is None or not cur.readable:
        return "CAN'T TELL", f"{current_era}: n {0 if cur is None else cur.n} < {READABLE_MIN}"
    lost = [e for e, c in cells_by_era.items() if c.readable and c.won is False]
    if lost:
        return "NOTHING", "lost " + ", ".join(sorted(lost))
    if cur.n >= PROPOSE_MIN:
        return "PROPOSE", f"{current_era} WON on n {cur.n}"
    return "WATCH", f"{current_era} WON on n {cur.n} (< {PROPOSE_MIN})"


def count_verdict(current_n: int, test_met: bool, other_eras_lost: bool = False) -> str:
    """The same ladder for count-based lenses (selection, slippage, missed-by-slots, stop-too-wide)."""
    if current_n < READABLE_MIN:
        return "CAN'T TELL"
    if not test_met or other_eras_lost:
        return "NOTHING"
    return "PROPOSE" if current_n >= PROPOSE_MIN else "WATCH"


def arm_lens(lens: str, fills_by_era: dict[str, list[dict]], arm_rows: dict[tuple[str, str], dict],
             current_era: str) -> dict:
    """fills_by_era: era -> [ {trade_id, fidelity_pass, live_actual, live_replay} ]; arm_rows: (trade_id, arm) -> row."""
    out = {}
    for arm in LENS_ARMS[lens]:
        cells = {}
        for era, fills in fills_by_era.items():
            per = [dict(fl, arm_row=arm_rows.get((str(fl["trade_id"]), arm))) for fl in fills]
            cells[era] = era_cell(arm, era, per)
        v, why = verdict(cells, current_era)
        out[arm] = {"cells": cells, "verdict": v, "why": why}
    return out


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# §3 descriptives: partials / exits / buy point
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def exits_legs(trade: dict) -> list[dict]:
    raw = trade.get("exits")
    if not raw:
        return []
    legs = raw if isinstance(raw, list) else json.loads(raw)
    return [lg for lg in legs if isinstance(lg, dict)]


def runner_shape(trade: dict) -> bool:
    """A partial fired AND the rest was stopped at (or within 0.05R of) breakeven — the fact behind the runner
    sweep: the winner gave the runner back."""
    legs = exits_legs(trade)
    risk = trade_risk_per_share(trade)
    entry = f(trade.get("entry_price"))
    if risk is None or entry is None:
        return False
    saw_partial = False
    for lg in legs:
        if lg.get("reason") == "partial_profit":
            saw_partial = True
        elif saw_partial and lg.get("reason") in ("stop_hit", "gap_through", "intraday_stop"):
            px = f(lg.get("price"))
            if px is not None and px >= entry - 0.05 * risk:
                return True
    return False


def final_reason(trade: dict) -> str:
    legs = exits_legs(trade)
    if not legs:
        return "unknown"
    return str(legs[-1].get("reason") or "unknown")


def stopped_then_ran(trade: dict, daily: dict[str, list[dict]], sessions: int = STOPPED_THEN_RAN_SESSIONS) -> Optional[bool]:
    """Stopped out, then a daily high >= entry + 2R within `sessions` sessions after the close day. None when
    not a stop-out or bars are missing (never an absence read as 'no')."""
    if final_reason(trade) not in ("stop_hit", "gap_through", "intraday_stop"):
        return None
    risk, entry = trade_risk_per_share(trade), f(trade.get("entry_price"))
    cd = et_date(trade.get("closed_at"))
    if risk is None or entry is None or cd is None:
        return None
    bars = [b for b in daily.get(trade.get("ticker"), []) if d(b["trade_date"]) > cd][:sessions]
    if len(bars) < sessions:
        return None
    return any((f(b.get("high_price")) or -1) >= entry + 2 * risk for b in bars)


def partial_descriptives(trades: list[dict], sd: dict[str, dict]) -> dict:
    """Per lane/era group: partial fired rate, median capture, median giveback, runner-shape count, tiny positions."""
    n = len(trades)
    fired = sum(truthy(t.get("partial_taken")) for t in trades)
    recs = [sd[str(t["id"])] for t in trades if str(t["id"]) in sd]
    return {"n": n, "partial_fired": fired, "no_record": n - len(recs),
            "capture_pct_median": median(f(r.get("capture_pct")) for r in recs),
            "giveback_r_median": median(f(r.get("giveback_r")) for r in recs),
            "runner_shape": sum(runner_shape(t) for t in trades),
            "shares_le_2": sum((f(t.get("entry_shares")) or 0) <= 2 for t in trades)}


def exit_descriptives(trades: list[dict], sd: dict[str, dict]) -> dict:
    recs = [sd[str(t["id"])] for t in trades if str(t["id"]) in sd]
    rs = [trade_realized_r(t) for t in trades]
    rs = [r for r in rs if r is not None]
    return {"n": len(trades), "reasons": Counter(final_reason(t) for t in trades),
            "hold_days_median": median(f(r.get("hold_trading_days")) for r in recs),
            "peak_r_median": median(f(r.get("peak_r")) for r in recs),
            "realized_r_median": median(rs),
            "disappoints": (sum(rs) < 0 and not any(r >= TAIL_WIN_R for r in rs)) if rs else None}


def slippage_test(fills: list[dict]) -> dict:
    """§3 buy point (a): fills > +1% over the trigger (n >= 3) have an R_cap sum < 0 while the <= +1% fills' sum
    is > 0. fills: {fill_vs_trigger_pct, live_rcap}."""
    hi = [fl for fl in fills if (f(fl.get("fill_vs_trigger_pct")) or 0) > 1.0 and f(fl.get("live_rcap")) is not None]
    lo = [fl for fl in fills if (f(fl.get("fill_vs_trigger_pct")) or 0) <= 1.0 and f(fl.get("live_rcap")) is not None]
    hi_sum, lo_sum = sum(f(x["live_rcap"]) for x in hi), sum(f(x["live_rcap"]) for x in lo)
    met = len(hi) >= READABLE_MIN and hi_sum < 0 and lo_sum > 0
    return {"n": len(hi) + len(lo), "over_1pct": len(hi), "over_sum": hi_sum, "under_sum": lo_sum,
            "median_pct": median(f(x.get("fill_vs_trigger_pct")) for x in fills),
            "max_pct": max((f(x.get("fill_vs_trigger_pct")) or 0) for x in fills) if fills else None,
            "verdict": count_verdict(len(hi) + len(lo), met) if len(hi) >= READABLE_MIN else "CAN'T TELL"}


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# §4 the tail
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def tails(trades: list[dict], sd: dict[str, dict], fidelity_by_id: dict[str, dict],
          best_worst_arm: Optional[Callable[[str], tuple[Optional[str], Optional[str]]]] = None) -> dict:
    """>= +4R winners and <= -1.5R losers on the REAL trade (never fidelity-gated), one row each."""
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
        rec = sd.get(str(t["id"]), {})
        fid = fidelity_by_id.get(str(t["id"]), {})
        best, worst = best_worst_arm(str(t["id"])) if best_worst_arm else (None, None)
        out[bucket].append({
            "ticker": t.get("ticker"), "lane": lane_of(t), "era": era_of(t), "alert_date": str(t.get("alert_date")),
            "entry_shares": f(t.get("entry_shares")), "realized_r": r, "peak_r": f(rec.get("peak_r")),
            "capture_pct": f(rec.get("capture_pct")), "hold_days": f(rec.get("hold_trading_days")),
            "stop_pct": f(rec.get("stop_pct")), "stop_per_adr": f(rec.get("stop_per_adr")),
            "exit_reason": final_reason(t), "regime": t.get("regime"), "reentry": str(t.get("entry_attempt") or "1") == "2",
            "fidelity": fid.get("pass"), "fidelity_cls": fid.get("cls"), "best_arm": best, "worst_arm": worst})
    return out


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# §6 breakout missed-by-slots
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def missed_records(audit_rows: list[dict]) -> list[dict]:
    recs = []
    for r in audit_rows:
        if r.get("event_type") != MISSED_EVENT:
            continue
        try:
            rec = json.loads(r.get("detail") or "{}")
        except json.JSONDecodeError:
            continue
        rec["_audit_id"] = r.get("id")
        recs.append(rec)
    return recs


def width_ok(rec: dict) -> Optional[bool]:
    """The entry's own skip rule from the record's fields: width <= adr20 x break_price. None when an input is missing."""
    w, adr, px = f(rec.get("width")), f(rec.get("adr20")), f(rec.get("break_price"))
    if w is None or adr is None or px is None:
        return None
    return w <= adr * px


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


def absence_observables(audit_rows: list[dict], seated_n: int, list_nights: int, toggle_state: Optional[str]) -> dict:
    holds = [r for r in audit_rows if r.get("event_type") == HOLD_EVENT]
    slots_full = 0
    for r in holds:
        try:
            if json.loads(r.get("detail") or "{}").get("state") == "slots_full":
                slots_full += 1
        except json.JSONDecodeError:
            pass
    return {"hold_rows": len(holds), "slots_full_holds": slots_full, "seated_trades": seated_n,
            "list_nights": list_nights, "toggle": toggle_state}


def absence_sentence(obs: dict, missed_n: int) -> str:
    if obs["list_nights"] == 0 or (obs["toggle"] not in (None, "on") and obs["seated_trades"] == 0 and obs["hold_rows"] == 0):
        return "the breakout paper lane did not run in this window"
    if obs["slots_full_holds"] == 0:
        return "no name was ever held for a full paper book"
    if missed_n == 0:
        return f"{obs['slots_full_holds']} hold rows, none broke out while held"
    return f"missed {missed_n} of {obs['slots_full_holds']} held rows"


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# §3 stop (c): the stop-too-wide matrix (verbatim from the YAML)
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def fisher_exact_one_sided_le(a: int, b: int, c: int, dd: int) -> float:
    """P(rejected hit-rate this low or lower | margins) — hypergeometric lower tail. a = rejected hits, b = rejected
    misses, c = admitted hits, dd = admitted misses."""
    from math import comb
    n = a + b + c + dd
    row1, col1 = a + b, a + c
    denom = comb(n, col1)
    return sum(comb(row1, k) * comb(n - row1, col1 - k) for k in range(0, a + 1)) / denom if denom else 1.0


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
    p = fisher_exact_one_sided_le(r_hit, rn - r_hit, a_hit, an - a_hit)
    if r_rate >= a_rate and r_med >= a_med:
        matrix = "REVISIT"
    elif r_rate < a_rate and r_med < a_med and p < 0.10:
        matrix = "KEEP"
    else:
        matrix = "CANNOT TELL"
    v = ("PROPOSE" if (matrix == "REVISIT" and rn >= PROPOSE_MIN and an >= PROPOSE_MIN)
         else "WATCH" if matrix == "REVISIT" else "NOTHING")
    return {"rejected_n": rn, "admitted_n": an, "matrix": matrix, "p": p, "rejected_rate": r_rate,
            "admitted_rate": a_rate, "rejected_median": r_med, "admitted_median": a_med, "verdict": v}


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# §9 render
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def render(report: dict) -> str:
    """The one page: line 1 = the answer; population, lens, tail, missed, folded, action."""
    lines = [f"# #720 monthly trade review — {report['run_date']}", "",
             f"**{report['answer']}**", "",
             f"Window: trades closed {report['window_start']} to {report['window_end']} (ET). "
             f"Eras are cumulative from each era's start; nothing is pooled across eras or lanes.", ""]
    lines += ["## Population", "", "| Lane | Era | closed in window | carried from era start | still open | excluded | no R frame | re-entries |",
              "|---|---|---|---|---|---|---|---|"]
    for (lane, era), c in sorted(report["population"].items()):
        lines.append(f"| {lane} | {era} | {c['window']} | {c['carried']} | {c['open']} | "
                     f"{', '.join(c['excluded']) or '—'} | {', '.join(c['no_r']) or '—'} | {', '.join(c['flagged']) or '—'} |")
    if report.get("legacy_paper_count") is not None:
        lines.append(f"\nLegacy `mi_paper_trades` rows closed in the window: {report['legacy_paper_count']} (expected 0).")
    if report.get("fidelity"):
        fd = report["fidelity"]
        lines += ["", f"Replay fidelity (the fairer test, §5 of the plan): {fd['pass']} of {fd['n']} fills pass "
                      f"({fd['old_pass']} under the old 0.25R bar); failures by class: "
                      + (", ".join(f"{k} {v}" for k, v in fd["classes"].items()) or "none") + "."]
    lines += ["", "## Lenses", "", "| Lens | Lane / era | n | reading | verdict |", "|---|---|---|---|---|"]
    for row in report["lens_rows"]:
        lines.append(f"| {row['lens']} | {row['where']} | {row['n']} | {row['reading']} | {row['verdict']} |")
    lines += ["", "## The tail (the real trades; never gated by fidelity)", ""]
    for bucket, title in (("winners", f"≥ +{TAIL_WIN_R:.0f}R winners"), ("losers", f"≤ {TAIL_LOSS_R}R losers")):
        rows = report["tails"].get(bucket, [])
        lines.append(f"**{title}: {len(rows)}**")
        if rows:
            lines += ["", "| Ticker | Lane | Era | R | peak R | capture | hold days | exit | shares | fidelity |", "|---|---|---|---|---|---|---|---|---|---|"]
            for r in rows:
                lines.append(f"| {r['ticker']} | {r['lane']} | {r['era']} | {fmt(r['realized_r'])} | {fmt(r['peak_r'])} | "
                             f"{fmt(r['capture_pct'])} | {r['hold_days'] if r['hold_days'] is not None else 'n/a'} | {r['exit_reason']} | "
                             f"{r['entry_shares'] if r['entry_shares'] is not None else 'n/a'} | "
                             f"{'pass' if r['fidelity'] else ('fail: ' + str(r['fidelity_cls']) if r['fidelity'] is not None else 'n/a')} |")
        lines.append("")
    m = report.get("missed", {})
    lines += ["## Breakout: names that broke out but never got a paper slot", "",
              f"Missed records {m.get('missed_n', 0)} (mature {m.get('missed_mature', 0)}), seated trades the same days "
              f"{m.get('seated_n', 0)} (mature {m.get('seated_mature', 0)}); +2R-before-stop share missed "
              f"{fmt(m.get('missed_plus2r_share'))} vs seated {fmt(m.get('seated_plus2r_share'))}; median MFE (R) missed "
              f"{fmt(m.get('missed_mfe_median'))} vs seated {fmt(m.get('seated_mfe_median'))}. Verdict: {m.get('verdict', 'CAN\'T TELL')}.",
              f"Absence check: {report.get('missed_absence', 'n/a')}.", ""]
    lines += ["## The five folded reviews", "", "| Review | this month's n | verdict |", "|---|---|---|"]
    for row in report.get("folded", []):
        lines.append(f"| {row['review']} | {row['n']} | {row['verdict']} |")
    lines += ["", f"**Action: {report['action']}**", ""]
    return "\n".join(lines)


def action_line(lens_rows: list[dict]) -> str:
    props = [r for r in lens_rows if r["verdict"] == "PROPOSE"]
    if not props:
        return "none"
    return "; ".join(f"{r['lens']} ({r['where']}): write the CHANGE_PROCESS proposal — needs an N ≥ 10 backtest "
                     f"and your sign-off" for r in props)


def answer_line(lens_rows: list[dict], tails_: dict) -> str:
    props = [r for r in lens_rows if r["verdict"] == "PROPOSE"]
    watches = [r for r in lens_rows if r["verdict"] == "WATCH"]
    head = (f"{len(props)} lens(es) worth a CHANGE_PROCESS proposal" if props
            else "Nothing beats what we run" + (f"; {len(watches)} on watch" if watches else ""))
    return (f"{head}; big winners {len(tails_.get('winners', []))}, bad losers {len(tails_.get('losers', []))}; "
            f"action: {'see below' if props else 'none'}.")


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# manifest + the report driver (reads CSVs only)
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def write_manifest(run_dir: Path, captured_at: str) -> str:
    data = run_dir / "data"
    lines = [f"captured_at: {captured_at}"]
    for p in sorted(data.glob("*.csv")):
        rows = max(0, sum(1 for _ in open(p, "rb")) - 1)
        lines.append(f"{p.name}: rows {rows} md5 {hashlib.md5(p.read_bytes()).hexdigest()}")
    (run_dir / "MANIFEST.txt").write_text("\n".join(lines) + "\n")
    return "\n".join(lines)




# ═══════════════════════════════════════════════════════════════════════════════════════════════
# §3 selection / §3 stop (c) helpers that join captured files
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def selection_labels(trades: list[dict], skips: list[dict], labelled: Iterable[tuple[str, str]]) -> list[dict]:
    """What we did with HIS labels: for each (ticker, alert_date) he named -> traded / skipped (reason) / never alerted."""
    by_key_t = {(t.get("ticker"), str(t.get("alert_date"))): t for t in trades}
    by_key_s = {(s.get("ticker"), str(s.get("alert_date"))): s for s in skips}
    out = []
    for ticker, ad in labelled:
        key = (ticker, ad)
        if key in by_key_t:
            t = by_key_t[key]
            out.append({"ticker": ticker, "alert_date": ad, "did": "traded", "detail": f"R {fmt(trade_realized_r(t))}"
                        if (t.get("status") or "") == "closed" else "open"})
        elif key in by_key_s:
            out.append({"ticker": ticker, "alert_date": ad, "did": "skipped", "detail": by_key_s[key].get("skip_reason") or ""})
        else:
            out.append({"ticker": ticker, "alert_date": ad, "did": "never alerted", "detail": ""})
    return out


def breakout_grade_for(ticker: str, alert_date: date, grades: list[dict]) -> Optional[str]:
    """His /bgrade grade on the latest list night strictly before the breakout day; None = ungraded."""
    cands = [g for g in grades if g.get("ticker") == ticker and d(g["scan_date"]) is not None and d(g["scan_date"]) < alert_date]
    if not cands:
        return None
    return max(cands, key=lambda g: d(g["scan_date"])).get("grade")


def breakout_selection(l3_trades: list[dict], grades: list[dict]) -> dict:
    """'his C/skip names lose, his A+/A names carry the winners': every graded C/skip trade <= 0R AND >= 1 A+/A trade >= +2R."""
    rows = []
    for t in l3_trades:
        if (t.get("status") or "") != "closed" or (t.get("pnl_attribution") or ""):
            continue
        r = trade_realized_r(t)
        rows.append({"ticker": t.get("ticker"), "grade": breakout_grade_for(t.get("ticker"), d(t["alert_date"]), grades), "r": r})
    graded = [x for x in rows if x["grade"] is not None and x["r"] is not None]
    low = [x for x in graded if x["grade"] in ("C", "skip")]
    high = [x for x in graded if x["grade"] in ("A+", "A")]
    met = len(low) >= READABLE_MIN and all(x["r"] <= 0 for x in low) and any(x["r"] >= 2.0 for x in high)
    v = count_verdict(len(graded), met) if len(low) >= READABLE_MIN else "CAN'T TELL"
    return {"n": len(rows), "graded": len(graded), "ungraded": len(rows) - len(graded), "low_n": len(low), "high_n": len(high),
            "by_grade": Counter(x["grade"] or "ungraded" for x in rows), "verdict": v, "rows": rows}


def mfe_5d_pct(ticker: str, alert_date: date, daily: dict[str, list[dict]], open_d0: Optional[float] = None) -> Optional[float]:
    """MFE over d+1..d+5 from the gap-day open, in %, on raw daily bars (the YAML's measure). None when bars are missing."""
    bars = sorted(daily.get(ticker, []), key=lambda b: d(b["trade_date"]))
    if open_d0 is None:
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
    rej = []
    for s in skips:
        m = None
        mh, o = f(s.get("max_high_5d")), f(s.get("open_d0"))
        if mh and o and o > 0:
            m = (mh / o - 1.0) * 100.0
        else:
            m = mfe_5d_pct(s.get("ticker"), d(s["alert_date"]), daily)
        if m is not None:
            rej.append(m)
    adm = [m for m in (mfe_5d_pct(t.get("ticker"), d(t["alert_date"]), daily) for t in admitted) if m is not None]
    res = stop_too_wide_matrix(rej, adm)
    res["rejected_rows"], res["admitted_rows"] = len(skips), len(admitted)
    return res


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# the report driver (reads CSVs only)
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def _csv(data: Path, name: str) -> list[dict]:
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
                 read_1106_csv: Optional[Path] = None) -> dict:
    """Assemble the report dict from the captured CSVs. Every number comes from the functions above; every
    lens of the plan reaches the page (arm lenses, descriptives, selection, slippage, stop-too-wide, the tail,
    missed-by-slots with its absence observables, the folded reviews)."""
    data = run_dir / "data"
    trades = read_csv(data / "trades.csv")
    cf = _csv(data, "cf_arms.csv")
    sd = {str(r["trade_id"]): r for r in _csv(data, "sell_discipline.csv")}
    audit = _csv(data, "audit_breakout.csv")
    daily = _daily_by_ticker(_csv(data, "daily_bars.csv"))
    skips_stw = _csv(data, "skips_stop_too_wide.csv")
    skips_all = _csv(data, "skips_window.csv")
    grades = _csv(data, "breakout_grades.csv")
    blist = _csv(data, "breakout_list.csv")
    toggles = _csv(data, "strategy_toggles.csv")
    predicates = _csv(data, "predicates.csv")
    legacy = _csv(data, "legacy_paper_count.csv")
    start = (prev_capture + timedelta(days=1)) if prev_capture else window_start

    mism = era_mismatches(trades, cf)
    if mism:
        raise SystemExit("ERA MISMATCH — the read stops:\n  " + "\n  ".join(mism))
    pop = population(trades, start, run_date, read_1106_ids=read_1106_ids_from(read_1106_csv))
    arm_rows = {(str(r["trade_id"]), r["arm"]): r for r in cf}
    by_id = {str(t["id"]): t for t in trades}
    closed = [t for t in trades if (t.get("status") or "") == "closed" and not (t.get("pnl_attribution") or "")]
    lane_era: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for t in closed:
        lane_era[(lane_of(t), era_of(t))].append(t)

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
        fills_by_era[era_of(t)].append({"trade_id": tid, "fidelity_pass": fdct["pass"],
                                        "live_actual": arm_rows.get((tid, "live_actual")),
                                        "live_replay": arm_rows.get((tid, "live_replay"))})
    current_era = exit_era_label(run_date, "magna53")
    lens_rows, out_lines = [], []
    arm_results = {}
    for lens in ("buy_point", "stop", "partials", "exits"):
        res_by_arm = arm_lens(lens, fills_by_era, arm_rows, current_era)
        arm_results[lens] = res_by_arm
        for arm, res in res_by_arm.items():
            cur = res["cells"].get(current_era)
            lens_rows.append({"lens": f"{lens}: {arm}", "where": f"L1 / {current_era}", "n": cur.n if cur else 0,
                              "reading": res["why"], "verdict": res["verdict"]})
            for era, c in sorted(res["cells"].items()):
                out_lines.append(f"{lens:9s} {arm:28s} {era}: n {c.n} R_cap Δ {fmt(c.rcap_delta_sum)} drop-best {fmt(c.drop_best)} "
                                 f"R_own Δ {fmt(c.rown_delta_sum)} tail-clip {c.tail_clip} arm≥4R {c.arm_ge4} live≥4R {c.live_ge4} "
                                 f"engine {'agrees' if c.engine_agrees else 'disagrees'} won {c.won} excluded {dict(c.excluded)}")

    # recorder check: stop_low_of_day vs stop_orb_low identical rows (one confirmation, not two)
    same = total = 0
    for tid in fid:
        a, b = arm_rows.get((tid, "stop_low_of_day")), arm_rows.get((tid, "stop_orb_low"))
        if a and b and a.get("outcome") == "settled" and b.get("outcome") == "settled":
            total += 1
            same += abs((f(a.get("realized_r")) or 0) - (f(b.get("realized_r")) or 0)) < 1e-9
    out_lines.append(f"recorder check: stop_low_of_day = stop_orb_low on {same} of {total} settled fills")

    # selection (L1 labels; L3 grades)
    labelled = []
    try:
        from shared.operator_labelled_eps import OPERATOR_LABELLED_EPS
        labelled = [(e.ticker, e.alert_date) for e in OPERATOR_LABELLED_EPS
                    if start <= date.fromisoformat(e.alert_date) <= run_date or any(
                        t.get("ticker") == e.ticker and str(t.get("alert_date")) == e.alert_date for t in trades)]
    except Exception:  # loud-ok: the list is optional context; the page says so
        out_lines.append("selection: operator label list not importable")
    sel = selection_labels(trades, skips_all, labelled)
    watch_rows = [s for s in sel if s["did"] != "traded"]
    lens_rows.append({"lens": "selection: his EP labels", "where": "L1", "n": len(sel),
                      "reading": ", ".join(f"{s['ticker']} {s['did']}" for s in sel) or "no labelled name in the window",
                      "verdict": "WATCH" if watch_rows else ("NOTHING" if sel else "CAN'T TELL")})
    l3 = [t for t in trades if lane_of(t) == "L3"]
    bsel = breakout_selection(l3, grades)
    lens_rows.append({"lens": "selection: his breakout grades", "where": f"L3 / {BREAKOUT_ERA}", "n": bsel["graded"],
                      "reading": f"graded {bsel['graded']} of {bsel['n']} (" + ", ".join(f"{k} {v}" for k, v in sorted(bsel["by_grade"].items())) + ")",
                      "verdict": bsel["verdict"]})

    # buy point (a): slippage, per era on L1 fill_facts
    for era in sorted(fills_by_era):
        fills = []
        for fl in fills_by_era[era]:
            ff = arm_rows.get((fl["trade_id"], FILL_FACTS))
            la_cls, _, la_cap = classify_arm_row(fl["live_actual"], "live_actual")
            if ff and la_cls == "settled":
                fills.append({"fill_vs_trigger_pct": ff.get("fill_vs_trigger_pct"), "live_rcap": la_cap})
        st = slippage_test(fills)
        lens_rows.append({"lens": "buy point: fill vs trigger", "where": f"L1 / {era}", "n": st["n"],
                          "reading": f"median {fmt(st['median_pct'])}% max {fmt(st['max_pct'])}% over +1%: {st['over_1pct']} "
                                     f"(R_cap sum {fmt(st['over_sum'])} vs {fmt(st['under_sum'])})",
                          "verdict": st["verdict"] if era == current_era else "descriptive"})

    # stop (b)/(c), partials (b), exits (b)-(d): descriptives per lane/era
    for (lane, era), ts in sorted(lane_era.items()):
        if lane == "L4":
            continue
        pdsc, edsc = partial_descriptives(ts, sd), exit_descriptives(ts, sd)
        ran = [stopped_then_ran(t, daily) for t in ts]
        lens_rows.append({"lens": "stop: stopped out, then ran", "where": f"{lane} / {era}", "n": sum(x is not None for x in ran),
                          "reading": f"{sum(bool(x) for x in ran)} of {sum(x is not None for x in ran)} stop-outs printed +2R within 5 sessions "
                                     f"({sum(x is None for x in ran)} not judgeable)", "verdict": "descriptive"})
        lens_rows.append({"lens": "partials: fired / kept", "where": f"{lane} / {era}", "n": pdsc["n"],
                          "reading": f"partial fired {pdsc['partial_fired']}; median capture {fmt(pdsc['capture_pct_median'])}; median giveback "
                                     f"{fmt(pdsc['giveback_r_median'])}R; runner shape {pdsc['runner_shape']}; ≤2-share positions {pdsc['shares_le_2']}; "
                                     f"no record {pdsc['no_record']}", "verdict": "descriptive"})
        dis = edsc["disappoints"]
        lens_rows.append({"lens": "exits: how trades ended", "where": f"{lane} / {era}", "n": edsc["n"],
                          "reading": ", ".join(f"{k} {v}" for k, v in edsc["reasons"].most_common()) + f"; median hold {edsc['hold_days_median']} days; "
                                     f"median peak {fmt(edsc['peak_r_median'])}R vs kept {fmt(edsc['realized_r_median'])}R; disappoints: "
                                     f"{'yes' if dis else ('no' if dis is False else 'n/a')}", "verdict": "descriptive"})
    stw = stop_too_wide_section(skips_stw, [t for t in closed if lane_of(t) == "L1"], daily)
    lens_rows.append({"lens": "stop: the stop-too-wide filter", "where": "magna53 skips vs admitted", "n": stw["rejected_n"],
                      "reading": f"rejected {stw['rejected_n']} hit {fmt(stw['rejected_rate'])} median MFE {fmt(stw['rejected_median'])}% vs admitted "
                                 f"{stw['admitted_n']} hit {fmt(stw['admitted_rate'])} median {fmt(stw['admitted_median'])}%; {stw['matrix']}"
                                 + (f" (p {stw['p']:.3f})" if stw['p'] is not None else ""), "verdict": stw["verdict"]})

    # the tail (real trades)
    def best_worst(tid: str):
        vals = [(f(arm_rows[(tid, a)].get("realized_r")), a) for a in STOP_ARMS + HARVEST_ARMS + TRAIL_ARMS + ENTRY_ARMS
                if (tid, a) in arm_rows and arm_rows[(tid, a)].get("outcome") == "settled" and f(arm_rows[(tid, a)].get("realized_r")) is not None]
        if not vals:
            return None, None
        return f"{max(vals)[1]} {fmt(max(vals)[0])}", f"{min(vals)[1]} {fmt(min(vals)[0])}"
    tl = tails(trades, sd, fid, best_worst)

    # missed-by-slots + absence observables
    recs_all = missed_records(audit)
    recs = [r for r in recs_all if width_ok(r)]
    missed = []
    for r in recs:
        day, px, stop = d(r.get("day")), f(r.get("break_price")), f(r.get("stop"))
        if day is None or px is None or stop is None:
            continue
        missed.append({"ticker": r.get("ticker"), "day": day, "walk": missed_proxy_walk(px, stop, day, daily.get(r.get("ticker"), []))})
    seated = []
    for t in l3:
        fday, px, stop = et_date(t.get("filled_at")), f(t.get("entry_price")), f(t.get("hard_stop"))
        if fday is None or px is None or stop is None:
            continue
        seated.append({"ticker": t.get("ticker"), "day": fday, "realized_r": trade_realized_r(t),
                       "walk": missed_proxy_walk(px, stop, fday, daily.get(t.get("ticker"), []))})
    mvs = missed_vs_seated(missed, seated)
    mvs["width_dropped"] = len(recs_all) - len(recs)
    toggle = next((r.get("state") or r.get("status") or r.get("value") for r in toggles if r.get("safeguard") == "breakout_v1_paper"), None)
    obs = absence_observables(audit, len(l3), len({r.get("scan_date") for r in blist}), toggle)
    lens_rows.append({"lens": "breakout: missed by slots vs seated", "where": f"L3 / {BREAKOUT_ERA}", "n": mvs["missed_mature"],
                      "reading": f"+2R-before-stop share missed {fmt(mvs['missed_plus2r_share'])} vs seated {fmt(mvs['seated_plus2r_share'])}; "
                                 f"median MFE missed {fmt(mvs['missed_mfe_median'])}R vs seated {fmt(mvs['seated_mfe_median'])}R", "verdict": mvs["verdict"]})

    # folded reviews: the predicate counts beside the lens verdict each one maps to
    fold_map = {"bracket_geometry_variants_parked": ("stop", None), "live_fill_counterfactuals_first_read_482": ("exits", None),
                "exit_tune_cohort_review (closes)": ("partials", None), "runner_rule_sweep_recut (trade arm)": ("partials", None),
                "stop_too_wide_outcome_cohort": (None, stw["verdict"])}
    folded = []
    for p in predicates:
        lens, fixed = fold_map.get(p.get("review"), (None, None))
        if fixed is not None:
            v = fixed
        elif lens:
            vs = [r["verdict"] for r in arm_results.get(lens, {}).values()]
            v = "PROPOSE" if "PROPOSE" in vs else "WATCH" if "WATCH" in vs else "NOTHING" if "NOTHING" in vs else "CAN'T TELL"
        else:
            v = "n/a"
        folded.append({"review": p.get("review"), "n": p.get("n"), "verdict": v})

    report = {"run_date": run_date.isoformat(), "window_start": start.isoformat(), "window_end": run_date.isoformat(),
              "population": dict(pop["by_lane_era"]), "lens_rows": lens_rows, "tails": tl,
              "fidelity": {"n": len(fid), "pass": sum(v["pass"] for v in fid.values()),
                           "old_pass": sum(v["tol_old_pass"] for v in fid.values()),
                           "classes": Counter(v["cls"] for v in fid.values() if not v["pass"])},
              "missed": mvs, "missed_absence": absence_sentence(obs, mvs["missed_n"]) + f" (observables: {obs})",
              "folded": folded, "legacy_paper_count": (f(legacy[0].get("legacy_paper_closed_in_window")) if legacy else None),
              "selection": sel, "breakout_selection": bsel, "stop_too_wide": stw}
    report["action"] = action_line(lens_rows)
    report["answer"] = answer_line(lens_rows, tl)
    out_lines.append("fidelity per fill: " + "; ".join(f"{by_id[t].get('ticker')} {'pass' if v['pass'] else 'FAIL ' + str(v['cls'])} "
                                                       f"Δ {fmt(v['diff'])} tol {fmt(v['tol'])}" for t, v in fid.items()))
    report["out"] = "\n".join(out_lines)
    return report


def main(argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--manifest", metavar="RUN_DIR")
    ap.add_argument("--report", metavar="RUN_DIR")
    ap.add_argument("--run-date", default=None)
    ap.add_argument("--prev-capture", default=None, help="ET date of the previous run's capture (window lower bound)")
    ap.add_argument("--read-1106", default=str(_REPO / "scripts/probes/_482_read_1106/data/live_all.csv"),
                    help="the 11-06 read's trade capture; ONLY its id column is read, to flag those fills")
    a = ap.parse_args(argv)
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
