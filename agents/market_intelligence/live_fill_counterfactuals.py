"""2026-09-03 — #482 LIVE-FILL COUNTERFACTUAL RECORDER.

WHY (operator, 2026-09-03): *"After every analysis you just give the opposite rec, I don't
trust any of this."* Four stop findings in three days each reversed the last, and each ran
on a different re-slice of history. This module ends the re-slicing: for EVERY MAGNA53 fill
in `mi_live_trades` it records, beside the real outcome and never replacing it, what each
counterfactual stop and harvest rule would have produced ON THE SAME RECORDED BARS, settled
through the SAME exit ladder the live tracker calls. The next stop conclusion comes from
accrual on the population we actually trade, forward, not from another re-slice.

THE ERA STAMP — the operator's design constraint, in his words: *"even if we stop looking
explicitly at entries with the counterfactual, there's still possibility that we'll be
updating our filters, etc. as we observe live EPs, i.e. if I see we miss one I'd suggest it
so we can update to catch it."* The admitted population WILL move under this recorder — that
is correct behaviour (P1: a real EP must never be missed). So every row carries which
admission regime and which exit rule-set produced the trade (`rule_eras.py` + the alert
row's own admission-time stamps), and a later reader SEGMENTS instead of pooling. The
failure this prevents is the exact one that produced the flip-flop: Phase 3's answer
differed from the 08-16 read because the populations differed and nothing said so.

THE ARMS (one row each, per fill — `ARMS` below):
  live_actual           what the real trade did (mi_live_trades.total_pnl / placed risk).
  live_replay           the LIVE rule (entry−2R stop, +2R partial, breakeven, SMA trail)
                        walked on the same bars — the per-trade FIDELITY CHECK. A
                        counterfactual number is quotable only where live_replay agrees
                        with live_actual (scripts/ep_replay.py validate, made forward).
  stop_orb_low          the stop retired 2026-08-16 (ORB low), live ladder, target pinned.
  stop_adr_050          entry − 0.5 × ADR20$, live ladder, target pinned.
  stop_adr_075          entry − 0.75 × ADR20$, live ladder, target pinned.
  harvest_no_breakeven  live stop; 1/3 off at +2R; the stop does NOT move to entry after
                        the partial (the trail still applies). Tests the +0.33R "unit
                        effect": 26 of 54 partial-takers end at exactly +0.33R because the
                        breakeven stop turns the remaining 2/3 into a scratch.
  harvest_trail_only    live stop; NO partial ever; hard stop + SMA trail on the whole
                        position. Tests whether the partial itself caps the winners (0 of
                        26 closed live trades has ever reached 4R).
  harvest_t3            live stop; 1/3 off at +2R; the remaining 2/3 sold at the close of
                        the 3rd session after the partial (hard stop stays, no breakeven,
                        no trail post-partial — the #2 lineage's rule, mirrored exactly).
                        Phase 3's one direction-only runner (+16R on 55 takers, three
                        names carrying 80%) — the cheap forward test of that claim.
  Why these: stop arms vary ONE thing (where the stop sits) against the live ladder; harvest
  arms vary ONE thing each against the live stop. The +2R target is PINNED to the ORB R in
  every stop arm (entry + 2·(entry − orb_low)) because Phase 3 §6 showed the pin is what
  makes any stop tolerable; "own-unit" targets are a mechanism check, not a candidate.
  Each rule is one plain sentence (P15-A). R is reported in each arm's OWN units
  (pnl ÷ (entry − its stop)) so a wider stop is not flattered; realized_pct and pnl_adr
  are size-free.

WHAT IT MIRRORS. The walk (`walk_arm`) re-implements `scripts/ep_replay._walk_leg` — the
only mechanics validated per-trade against real fills (stop 44/44 · entered 33/33 ·
exit-class 29/30 · R within 0.25R on 25/30; current-era 4/4 within 0.16R) — because that
harness cannot be imported here (it imports broker/order_manager, and walks to a capture-
bound horizon). Parity is pinned by `tests/test_live_fill_counterfactuals.py` on identical
bars, the `exit_path_shadow._sma_trail` precedent. Day 0: stop-first within a minute bar;
stop AND target in one bar → abstain (order unknowable at 1-min grain); the fill bar
straddling the stop → abstain; a resting stop fills at the OPEN when the open gaps
through it. Sessions after day 0: the live ladder (`exit_logic.apply_daily_exit_step`)
with the broker's raise-only resting-stop overlay; the ladder's day-3/5 partial stood down
(era C); the trail sees the stock's own 40-calendar-day pre-entry closes (#548).
DELIBERATE DEVIATIONS from `_walk_leg`, each stated: (1) a HORIZON of 40 forward sessions
— an arm still open then is written `outcome='horizon'` with a MARK (`mark_r`), never a
return; (2) a missing session BLOCKS the walk (pending, retried nightly through the stored
row then the single-day fallback) instead of being leapt — the #616 lane's abstain rule;
after 5 further sessions with the gap still open the arm is written `abstain` with the gap
named; (3) walked arms use one fractional share (1/3 partials) rather than the row's
integer share count — R and pct are size-free by construction.

THE LINE — read this before touching anything here. This module is a passive OBSERVER:
  - It has EXACTLY ONE write target: `mi_live_fill_counterfactuals` (plus `mi_audit_log`
    via the shared `log_audit_event` helper — never a trade-state table).
  - It NEVER writes to `mi_live_trades`, `mi_live_orders`, or any column any live decision
    reads. It never calls the Alpaca client, `order_manager`, or `live_tracker`; the only
    broker import is `exit_logic` — pure ladder math (the giveback / pivot-stop precedent).
  - It reads `mi_live_trades`, `mi_ep_alerts`, `mi_intraday_bars`, `mi_daily_closes` (+ the
    single-day Polygon daily fallback already used by exit_path_shadow) — all read-only.
    No new per-fill market-data fetch: day-0 minutes come from what the trade lifecycle
    already stored (stream write-through + the 16:22 ET back-fill); ADR from stored daily
    rows; if either is missing the arm records NULL and is COUNTED, never substituted.
  - It is read by NO grading / entry / sizing / ordering / safeguard path — comparison
    telemetry only. The recorder can be completely broken and the live trade is unaffected:
    every arm and every write is wrapped; a failure degrades to a counted error + an
    `mi_audit_log` row, `run_live_fill_counterfactuals` never raises.
  - SILENT. No Telegram, ever, while evidence accrues (operator ruling 2026-08-30 for the
    sibling lane: an unproven signal in his notifications becomes a de-facto trade signal).
  - Write-once: UNIQUE (trade_id, arm) + ON CONFLICT DO NOTHING. A settled arm is never
    rewritten; `SETTLE_VERSION` says which recorder wrote it.

SCOPE. `signal_type = 'magna53'` (the ORB-R target frame is MAGNA53's; 9m_day2 is retired
and must never be cited — operator 2026-08-29), `filled_at` on/after `BACKFILL_FROM` =
2026-08-16, the day the current entry−2R stop went live: era C is the current stop's OWN
population, and anything earlier is the re-slice this task exists to end. Both account
modes are recorded and stamped (`account_mode`); the gated review counts live only.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from typing import Any, Optional

from shared.dates import _ET

from agents.market_intelligence.broker.exit_logic import apply_daily_exit_step, seed_exit_state  # exec-boundary-ok: exit_logic is PURE exit-ladder math (no Alpaca client, no trade-state I/O) — the #482 recorder settles every counterfactual through the SAME ladder the live tracker calls instead of re-implementing it (the giveback / pivot-stop shadow precedent); pure compute, no live execution
from agents.market_intelligence.db import (
    _f,
    get_counterfactual_arms_written,
    get_counterfactual_fills,
    get_daily_bar_with_fallback,
    get_daily_ohlc_range,
    get_ep_alert_admission_stamp,
    get_intraday_bars_window,
    get_pool,
    insert_live_fill_counterfactual,
    log_audit_event,
)
from agents.market_intelligence.rule_eras import (
    admission_era_as_of,
    exit_era_label,
    exit_rules_as_of,
)
from agents.market_intelligence.trading_calendar import get_market_status

logger = logging.getLogger(__name__)

SETTLE_VERSION = "cf_v1"
HORIZON_SESSIONS = 40          # forward sessions after the fill day; open beyond → 'horizon' + mark
GAP_RETRY_SESSIONS = 5         # a data gap older than this many sessions is written 'abstain'
BACKFILL_FROM = date(2026, 8, 16)   # era C: the day the live entry−2R stop went live
TARGET_R = 2.0                 # the +2R partial level, fixed (exit_path_shadow's convention:
                               # this records the rule as SIGNED, not whatever the constant is today)
ADR_WINDOW = 20                # sessions in the ADR mean
ADR_MIN_SESSIONS = 10          # below this ADR is NULL (ep_replay.adr20_pct's floor)
ADR_LOOKBACK_CAL_DAYS = 60     # calendar days read to cover the ADR window
PRIOR_CLOSES_CAL_DAYS = 40     # live_tracker._load_exit_state's trail window (#548)
SETTLED_AFTER_ET = time(16, 30)  # today's daily bar is settled only after the close

# (arm, kind, stop_rule, harvest_rule)
ARMS: tuple[tuple[str, str, str, str], ...] = (
    ("live_actual", "control", "live", "live_ladder"),
    ("live_replay", "control", "live", "live_ladder"),
    ("stop_orb_low", "stop", "orb_low", "live_ladder"),
    ("stop_adr_050", "stop", "adr_050", "live_ladder"),
    ("stop_adr_075", "stop", "adr_075", "live_ladder"),
    ("harvest_no_breakeven", "harvest", "live", "no_breakeven"),
    ("harvest_trail_only", "harvest", "live", "trail_only"),
    ("harvest_t3", "harvest", "live", "t3"),
)
ARM_NAMES: tuple[str, ...] = tuple(a[0] for a in ARMS)
HARVEST_RULES = ("live_ladder", "no_breakeven", "trail_only", "t3")
STOP_RULES = ("live", "orb_low", "adr_050", "adr_075")


# ── Pure compute (fixture-testable, no IO) ─────────────────────────────────────────────


def compute_adr20_pct(pre_bars: list[dict]) -> tuple[Optional[float], int]:
    """(mean (high−low)/close × 100 over the last ≤ADR_WINDOW bars, n used). Bars ascending
    with high_price/low_price/close; incomplete bars skipped. Below ADR_MIN_SESSIONS →
    (None, n): NULL and counted, never a substitute (ep_replay.adr20_pct's rule)."""
    vals = []
    for b in pre_bars[-ADR_WINDOW:]:
        h, l, c = _f(b.get("high_price")), _f(b.get("low_price")), _f(b.get("close"))
        if h is None or l is None or not c:
            continue
        vals.append((h - l) / c * 100.0)
    if len(vals) < ADR_MIN_SESSIONS:
        return None, len(vals)
    return sum(vals) / len(vals), len(vals)


def pinned_target(entry: Optional[float], orb_low: Optional[float],
                  target_r: float = TARGET_R) -> Optional[float]:
    """entry + target_r × (entry − orb_low): the ORB-R frame `order_manager.
    profit_target_r_per_share` pins for MAGNA53 (R = entry − orb_low, NOT the placed stop).
    None when no valid frame exists — the ADR 0014 rule: skip, never fabricate."""
    if entry is None or entry <= 0 or orb_low is None or orb_low >= entry:
        return None
    return entry + target_r * (entry - orb_low)


def arm_stop_price(stop_rule: str, *, entry: Optional[float], orb_low: Optional[float],
                   live_stop: Optional[float], adr_dollar: Optional[float]) -> Optional[float]:
    """This arm's initial protective stop. None = unscoreable (missing input), never a guess."""
    if stop_rule == "live":
        return live_stop
    if stop_rule == "orb_low":
        return orb_low
    if stop_rule in ("adr_050", "adr_075"):
        if not entry or entry <= 0 or adr_dollar is None or adr_dollar <= 0:
            return None
        return entry - (0.5 if stop_rule == "adr_050" else 0.75) * adr_dollar
    raise ValueError(f"unknown stop_rule {stop_rule!r}")


def _fresh_walk() -> dict[str, Any]:
    return {"status": None, "reason": None, "exits": [], "final_reason": None,
            "partial_fired": False, "gap_through": False, "exit_session": None,
            "sessions_walked": 0, "pnl_per_share": None, "mark_pnl_per_share": None,
            "pending_at": None, "remaining": 1.0}


def walk_arm(*, entry: float, stop: float, target: Optional[float],
             day0_bars: Optional[list[dict]], fill_idx: int,
             sessions: list[tuple[date, Optional[dict]]], prior_closes: list[float],
             harvest: str, fill_day: date,
             breakeven_at_partial: bool = True, trail_prior_closes: bool = True,
             ladder_partial: bool = False, horizon: int = HORIZON_SESSIONS) -> dict:
    """Walk ONE arm from the fill bar to settlement, on one fractional share.

    `day0_bars`: the fill day's 1-min bars {m,o,h,l,c}, `fill_idx` = the fill minute's
    index (None = minutes unavailable → pending). `sessions`: [(date, bar|None)] for the
    trading sessions AFTER the fill day, oldest first, already capped at `horizon`; a None
    bar is a gap and BLOCKS the walk (pending at that date). Mirrors
    scripts/ep_replay._walk_leg for the live rule and the #2 lineage's t3 (module docstring
    lists the three deliberate deviations).

    status: settled | abstain | horizon | pending. R is left to the caller (pnl_per_share /
    (entry − stop)); `mark_pnl_per_share` is set only at the horizon."""
    if harvest not in HARVEST_RULES:
        raise ValueError(f"unknown harvest rule {harvest!r}")
    out = _fresh_walk()
    if stop is None or entry is None or entry - stop <= 0:
        out.update(status="abstain", reason="nonpositive_risk_per_share")
        return out
    if day0_bars is None or fill_idx is None or fill_idx < 0 or fill_idx >= len(day0_bars):
        out.update(status="pending", reason="no_day0_minute_bars", pending_at=fill_day)
        return out

    remaining = 1.0
    partial_taken = False
    exits: list[dict] = []
    # The live ladder is the only harvest that raises the resting stop to entry after the
    # partial (breakeven). no_breakeven / t3 keep the hard stop; trail_only never partials.
    be_floor = harvest == "live_ladder" and breakeven_at_partial
    use_target = target is not None and harvest != "trail_only"

    def book(px: float, qty: float, reason: str, when: Any) -> None:
        exits.append({"time": str(when), "price": px, "reason": reason, "shares": qty,
                      "pnl": (px - entry) * qty})

    def take_partial(px: float, when: Any) -> float:
        nonlocal remaining, partial_taken
        qty = remaining / 3
        if qty <= 0:
            return 0.0
        book(px, qty, "partial_profit", when)
        remaining -= qty
        partial_taken = True
        out["partial_fired"] = True
        return qty

    def stopped(px: float, when: Any) -> None:
        nonlocal remaining
        book(px, remaining, "stop_hit", when)
        remaining = 0.0
        out["final_reason"] = "stop_hit"

    # ── Day 0: the minute walk from the fill bar (stop-first; same-bar → abstain) ──
    cur_stop = float(stop)
    closed = False
    fb = day0_bars[fill_idx]
    if fb["l"] <= stop:
        if use_target and fb["h"] >= target:
            out.update(status="abstain", reason="day0_fill_bar_stop_and_target")
            return out
        # The fill is the first touch of the trigger; a close BELOW the stop proves the path
        # descended through it after that touch. A close at/above the stop leaves the order
        # unknowable at 1-min grain → abstain (never guess).
        if fb["c"] < stop:
            stopped(stop, fb["m"])
            closed = True
        else:
            out.update(status="abstain", reason="day0_fill_bar_straddles_stop")
            return out
    if not closed and use_target and fb["h"] >= target and fb["c"] >= stop:
        # target > entry ≥ the trigger, so a target touch inside the fill bar post-dates the
        # fill — orderable (the _walk_leg argument).
        if take_partial(target, fb["m"]) and be_floor:
            cur_stop = max(cur_stop, entry)
    for b in day0_bars[fill_idx + 1:]:
        if closed:
            break
        hit_stop = b["l"] <= cur_stop
        hit_tgt = use_target and not partial_taken and b["h"] >= target
        if hit_stop and hit_tgt:
            out.update(status="abstain", reason="day0_stop_and_target_same_bar")
            return out
        if hit_stop:
            px = b["o"] if (b["o"] is not None and b["o"] < cur_stop) else cur_stop
            if px != cur_stop:
                out["gap_through"] = True
            stopped(px, b["m"])
            closed = True
        elif hit_tgt:
            if take_partial(target, b["m"]) and be_floor:
                cur_stop = max(cur_stop, entry)
    if closed:
        out["exit_session"] = 0

    # ── Sessions after day 0: the live ladder + the broker's raise-only resting stop ──
    last_close = day0_bars[-1]["c"] if day0_bars else entry
    if not closed:
        state = seed_exit_state(
            alert_date=fill_day, entry_price=entry, hard_stop=stop,
            remaining_shares=remaining, partial_taken=partial_taken,
            breakeven_active=partial_taken and be_floor, exits=list(exits))
        resting = cur_stop
        post_sessions = 0
        for idx, (d, b) in enumerate(sessions, start=1):
            if closed:
                break
            if b is None or b.get("c") is None or b.get("l") is None or b.get("h") is None:
                out.update(status="pending", reason=f"missing_session:{d.isoformat()}",
                           pending_at=d)
                out["exits"] = exits
                out["remaining"] = state["remaining_shares"]
                return out
            out["sessions_walked"] = idx
            last_close = b["c"]
            hit_tgt = (use_target and not state["partial_taken"] and b["h"] >= target)
            if hit_tgt and b["l"] <= resting:
                out.update(status="abstain", reason=f"fwd_stop_and_target_same_day:{d.isoformat()}")
                return out
            if hit_tgt:
                remaining = state["remaining_shares"]
                partial_taken = state["partial_taken"]
                if take_partial(target, d) and be_floor:
                    resting = max(resting, entry)
                state["remaining_shares"] = remaining
                state["partial_taken"] = True
                state["breakeven_active"] = be_floor
                state["exits"] = list(exits)
                post_sessions = 0
            if harvest == "t3" and state["partial_taken"]:
                # ── the #2 lineage's post-partial walk (_walk_leg runner branch, mirrored):
                # hard stop stays, no breakeven, no trail; sell the runner at the 3rd close
                # after the partial session (the partial session itself is session 0).
                if hit_tgt:
                    continue
                post_sessions += 1
                remaining = state["remaining_shares"]
                if b["l"] <= stop:
                    px = b["o"] if (b["o"] is not None and b["o"] < stop) else stop
                    if px != stop:
                        out["gap_through"] = True
                    stopped(px, d)
                    closed = True
                    out["exit_session"] = idx
                    break
                if post_sessions >= 3:
                    book(b["c"], remaining, "time_close", d)
                    remaining = 0.0
                    out["final_reason"] = "time_close"
                    closed = True
                    out["exit_session"] = idx
                    break
                continue
            state["hard_stop"] = resting
            step = apply_daily_exit_step(
                state, {"l": b["l"], "c": b["c"]}, d,
                integer_partial_shares=False,
                skip_partial_decision=not ladder_partial,
                prior_closes=(list(prior_closes) if trail_prior_closes else None))
            state.update(remaining_shares=step.new_remaining,
                         partial_taken=step.new_partial_taken,
                         breakeven_active=step.new_breakeven_active,
                         exits=step.new_exits,
                         running_closes=step.new_running_closes)
            if step.closed:
                px, reason = step.close_price, step.close_reason
                if reason == "stop_hit" and b["o"] is not None and b["o"] < px:
                    px = b["o"]           # gap-through honesty: the resting stop fills at the open
                    out["gap_through"] = True
                exits = [dict(e) for e in step.new_exits]
                exits[-1] = {**exits[-1], "price": px,
                             "pnl": (px - entry) * exits[-1]["shares"]}
                out["final_reason"] = reason
                out["exit_session"] = idx
                remaining = 0.0
                closed = True
            else:
                exits = [dict(e) for e in step.new_exits]
                remaining = step.new_remaining
                resting = max(resting, step.effective_stop)
        out["partial_fired"] = any(e["reason"] == "partial_profit" for e in exits)

    out["exits"] = exits
    out["remaining"] = remaining
    pnl = sum(e["pnl"] for e in exits)
    if closed:
        out.update(status="settled", pnl_per_share=pnl)
    elif out["sessions_walked"] >= horizon:
        out.update(status="horizon", reason="open_at_horizon", final_reason="horizon",
                   mark_pnl_per_share=pnl + (last_close - entry) * remaining)
    else:
        out.update(status="pending", reason="open_walk_not_definitive")
    return out


def live_actual_outcome(trade: dict, *, fill_day: date, entry: float, live_stop: float) -> dict:
    """The `live_actual` arm from the trade row itself — no walk. status: settled |
    pending (still open) | unscoreable. R in the placed stop's units: total_pnl /
    (entry_shares × (entry − hard_stop)) — sell_discipline.trade_risk_per_share's frame."""
    out = _fresh_walk()
    if (trade.get("status") or "") != "closed" or trade.get("total_pnl") is None:
        out.update(status="pending", reason="live_trade_open")
        return out
    shares = _f(trade.get("entry_shares"))
    risk = entry - live_stop
    if not shares or shares <= 0 or risk <= 0:
        out.update(status="unscoreable",
                   reason=f"live_actual_inputs:shares={shares},risk={risk}")
        return out
    total_pnl = float(trade["total_pnl"])
    exits = trade.get("exits")
    if isinstance(exits, str):
        import json
        try:
            exits = json.loads(exits or "[]")
        except Exception:  # loud-ok: the row's legs are display-only here; R comes from total_pnl
            exits = []
    exits = list(exits or [])
    closed_at = trade.get("closed_at")
    closed_day = closed_at.astimezone(_ET).date() if isinstance(closed_at, datetime) else None
    out.update(
        status="settled", exits=exits, pnl_per_share=total_pnl / shares,
        final_reason=(exits[-1].get("reason") if exits and isinstance(exits[-1], dict) else None),
        partial_fired=bool(trade.get("partial_taken")) or any(
            isinstance(e, dict) and e.get("reason") == "partial_profit" for e in exits),
        exit_session=(len(_trading_days(fill_day + timedelta(days=1), closed_day))
                      if closed_day and closed_day > fill_day else 0),
        remaining=0.0,
    )
    return out


def _trading_days(start: date, end: date) -> list[date]:
    out = []
    d = start
    while d <= end:
        if get_market_status(d).is_trading_day:
            out.append(d)
        d += timedelta(days=1)
    return out


def last_settled_session(today: date, now_et: datetime) -> date:
    """The last trading session whose daily bar is SETTLED: today only after the close
    (SETTLED_AFTER_ET), else the previous trading day. A partial day must never settle an
    exit (ep_replay's LAST_SETTLED rule)."""
    d = today
    if now_et.date() == today and now_et.timetz().replace(tzinfo=None) < SETTLED_AFTER_ET:
        d = today - timedelta(days=1)
    while not get_market_status(d).is_trading_day:
        d -= timedelta(days=1)
    return d


# ── Orchestration (DB reads; writes only mi_live_fill_counterfactuals + audit) ─────────


async def _assemble_sessions(conn, ticker: str, fill_day: date,
                             last_session: date) -> list[tuple[date, Optional[dict]]]:
    """[(date, bar|None)] for the trading sessions after `fill_day` through
    `last_session`, capped at HORIZON_SESSIONS. Stored rows first (one ranged read); a
    session missing from the store goes through the single-day fallback; still missing →
    None (the walk blocks there — never leaps a gap, never fabricates)."""
    days = _trading_days(fill_day + timedelta(days=1), last_session)[:HORIZON_SESSIONS]
    if not days:
        return []
    rows = await get_daily_ohlc_range(conn, ticker, days[0], days[-1])
    by = {r["trade_date"]: r for r in rows}
    out: list[tuple[date, Optional[dict]]] = []
    for d in days:
        r = by.get(d)
        bar = None
        if r is not None and r.get("close") is not None:
            bar = {"o": _f(r.get("open_price")), "h": _f(r.get("high_price")),
                   "l": _f(r.get("low_price")), "c": _f(r.get("close"))}
        if bar is None or bar["h"] is None or bar["l"] is None or bar["c"] is None:
            o, h, l, c, _src = await get_daily_bar_with_fallback(conn, ticker, d)
            bar = None if (c is None or h is None or l is None) else {"o": o, "h": h, "l": l, "c": c}
        out.append((d, bar))
    return out


async def _day0_bars(conn, ticker: str, fill_day: date,
                     filled_at: datetime) -> tuple[Optional[list[dict]], Optional[int]]:
    """The fill day's stored 1-min RTH bars + the fill minute's index. (None, None) when
    the fill minute is not stored — pending, then abstain after GAP_RETRY_SESSIONS."""
    start = datetime.combine(fill_day, time(9, 30), tzinfo=_ET)
    end = datetime.combine(fill_day, time(16, 0), tzinfo=_ET)
    bars = await get_intraday_bars_window(conn, ticker, start, end)
    bars = [b for b in bars if b["o"] is not None and b["h"] is not None
            and b["l"] is not None and b["c"] is not None]
    if not bars:
        return None, None
    fill_minute = filled_at.astimezone(_ET).replace(second=0, microsecond=0)
    for i, b in enumerate(bars):
        bm = b["m"].astimezone(_ET) if isinstance(b["m"], datetime) else b["m"]
        if bm == fill_minute:
            return bars, i
    return None, None


def _base_fields(trade: dict, arm: tuple[str, str, str, str], *, fill_day: date,
                 inputs: dict, era: dict, stamp: Optional[dict], settled_session: date) -> dict:
    name, kind, stop_rule, harvest_rule = arm
    stamp = stamp or {}
    return {
        "settled_session": settled_session,
        "trade_id": int(trade["id"]), "ticker": trade["ticker"],
        "account_mode": trade.get("account_mode") or "paper",
        "signal_type": trade.get("signal_type"), "entry_attempt": trade.get("entry_attempt"),
        "alert_date": trade["alert_date"], "fill_day": fill_day,
        "arm": name, "arm_kind": kind, "stop_rule": stop_rule, "harvest_rule": harvest_rule,
        "entry_price": inputs["entry"], "orb_high": inputs["orb_high"],
        "orb_low": inputs["orb_low"], "live_stop": inputs["live_stop"],
        "target_price": inputs["target"], "target_r": TARGET_R,
        "adr20_pct": inputs["adr20_pct"], "adr20_n": inputs["adr20_n"],
        "adr_dollar": inputs["adr_dollar"],
        "pnl_attribution": trade.get("pnl_attribution"), "regime": trade.get("regime"),
        "exit_era": era["exit_era"], "exit_rules": era["exit_rules"],
        "admission_era": era["admission_era"],
        "rubric_version": stamp.get("rubric_version"), "score_tier": stamp.get("score_tier"),
        "ep_score": _f(stamp.get("ep_score")), "judge_grade": stamp.get("judge_grade"),
        "judge_tier": stamp.get("judge_tier"),
        "grade_engine_authority": stamp.get("grade_engine_authority"),
        "setup_class": stamp.get("setup_class"),
        "baseline_floor_tier": stamp.get("baseline_floor_tier"),
        "alert_source": stamp.get("alert_source"),
        "settle_version": SETTLE_VERSION,
    }


def _outcome_fields(res: dict, *, entry: float, stop: Optional[float],
                    adr_dollar: Optional[float], outcome: str,
                    day0_bar_count: Optional[int]) -> dict:
    risk = (entry - stop) if (stop is not None and entry) else None
    f: dict[str, Any] = {
        "stop_price": stop, "risk_per_share": risk,
        "stop_width_pct": (risk / entry * 100.0) if (risk and entry) else None,
        "stop_width_adr": (risk / adr_dollar) if (risk and adr_dollar) else None,
        "outcome": outcome, "final_reason": res.get("final_reason") or res.get("reason"),
        "realized_r": None, "realized_pct": None, "pnl_adr": None, "mark_r": None,
        "partial_fired": res.get("partial_fired"), "gap_through": res.get("gap_through"),
        "exit_session": res.get("exit_session"), "sessions_walked": res.get("sessions_walked"),
        "day0_bar_count": day0_bar_count, "exits": list(res.get("exits") or []),
    }
    pnl = res.get("pnl_per_share")
    if outcome == "settled" and pnl is not None and risk:
        f["realized_r"] = pnl / risk
        f["realized_pct"] = pnl / entry * 100.0
        f["pnl_adr"] = (pnl / adr_dollar) if adr_dollar else None
    mark = res.get("mark_pnl_per_share")
    if outcome == "horizon" and mark is not None and risk:
        f["mark_r"] = mark / risk
    return f


async def _write(fields: dict, out: dict, label: str) -> bool:
    try:
        inserted = await insert_live_fill_counterfactual(fields)
    except Exception as e:  # loud-ok: counted + audited; the live trade is untouched either way
        out["errors"] += 1
        await log_audit_event("live_fill_counterfactual_error", f"{label}: write failed: {e}")
        return False
    if inserted:
        out["written"] += 1
        out[{"settled": "settled", "abstain": "abstained", "unscoreable": "unscoreable",
             "horizon": "horizon"}[fields["outcome"]]] += 1
    return inserted


async def _record_one_fill(conn, trade: dict, last_session: date, out: dict) -> None:
    trade_id = int(trade["id"])
    ticker = trade["ticker"]
    label = f"{ticker} trade {trade_id}"
    written = await get_counterfactual_arms_written(conn, trade_id)
    todo = [a for a in ARMS if a[0] not in written]
    if not todo:
        return
    out["fills_considered"] += 1
    out["arms_considered"] += len(todo)

    filled_at = trade.get("filled_at")
    if not isinstance(filled_at, datetime):
        raise ValueError("filled_at missing on a filled row")
    fill_day = filled_at.astimezone(_ET).date()
    alert_date = trade["alert_date"]
    entry = _f(trade.get("entry_price"))
    orb_high = _f(trade.get("orb_high"))
    orb_low = _f(trade.get("orb_low"))
    live_stop = _f(trade.get("hard_stop"))          # read ONCE; stored on every row

    era = {"exit_era": exit_era_label(alert_date),
           "exit_rules": exit_rules_as_of(alert_date),
           "admission_era": admission_era_as_of(alert_date)}
    rules = era["exit_rules"]
    stamp = await get_ep_alert_admission_stamp(conn, ticker, alert_date)

    # Pre-alert daily rows: ADR (last ≤20 sessions) + the trail's prior closes (40 cal days).
    pre = await get_daily_ohlc_range(conn, ticker, alert_date - timedelta(days=ADR_LOOKBACK_CAL_DAYS),
                                     alert_date - timedelta(days=1))
    adr20_pct, adr20_n = compute_adr20_pct(pre)
    adr_dollar = (adr20_pct / 100.0 * entry) if (adr20_pct is not None and entry) else None
    prior_cut = alert_date - timedelta(days=PRIOR_CLOSES_CAL_DAYS)
    prior_closes = [float(r["close"]) for r in pre
                    if r.get("close") is not None and r["trade_date"] >= prior_cut]
    target = pinned_target(entry, orb_low)
    inputs = {"entry": entry, "orb_high": orb_high, "orb_low": orb_low, "live_stop": live_stop,
              "target": target, "adr20_pct": adr20_pct, "adr20_n": adr20_n,
              "adr_dollar": adr_dollar}

    missing = [k for k in ("entry", "orb_high", "orb_low", "live_stop") if inputs[k] is None]
    if missing or target is None or live_stop >= entry:
        reason = f"missing_inputs:{','.join(missing) or 'invalid_frame'}"
        for arm in todo:
            fields = _base_fields(trade, arm, fill_day=fill_day, inputs=inputs, era=era, stamp=stamp,
                                 settled_session=last_session)
            fields.update(_outcome_fields({"reason": reason}, entry=entry or 0.0, stop=None,
                                          adr_dollar=adr_dollar, outcome="unscoreable",
                                          day0_bar_count=None))
            await _write(fields, out, f"{label} {arm[0]}")
        return

    day0_bars = fill_idx = None
    sessions: Optional[list] = None
    for arm in todo:
        name, _kind, stop_rule, harvest = arm
        try:
            fields = _base_fields(trade, arm, fill_day=fill_day, inputs=inputs, era=era, stamp=stamp,
                                 settled_session=last_session)
            if name == "live_actual":
                res = live_actual_outcome(trade, fill_day=fill_day, entry=entry, live_stop=live_stop)
                if res["status"] == "pending":
                    out["pending"] += 1
                    continue
                fields.update(_outcome_fields(res, entry=entry, stop=live_stop, adr_dollar=adr_dollar,
                                              outcome=res["status"], day0_bar_count=None))
                await _write(fields, out, f"{label} {name}")
                continue

            stop = arm_stop_price(stop_rule, entry=entry, orb_low=orb_low,
                                  live_stop=live_stop, adr_dollar=adr_dollar)
            if stop is None:
                res = {"reason": f"no_adr20:{adr20_n}_sessions"}
                fields.update(_outcome_fields(res, entry=entry, stop=None, adr_dollar=adr_dollar,
                                              outcome="unscoreable", day0_bar_count=None))
                await _write(fields, out, f"{label} {name}")
                continue

            if day0_bars is None:
                day0_bars, fill_idx = await _day0_bars(conn, ticker, fill_day, filled_at)
            if sessions is None:
                sessions = await _assemble_sessions(conn, ticker, fill_day, last_session)
            day0_count = (len(day0_bars) - fill_idx) if (day0_bars and fill_idx is not None) else 0

            res = walk_arm(entry=entry, stop=stop, target=target, day0_bars=day0_bars,
                           fill_idx=fill_idx, sessions=sessions, prior_closes=prior_closes,
                           harvest=harvest, fill_day=fill_day,
                           breakeven_at_partial=bool(rules["breakeven_at_partial"]),
                           trail_prior_closes=bool(rules["trail_prior_closes"]),
                           ladder_partial=bool(rules["ladder_partial"]))
            status = res["status"]
            if status == "pending":
                gap = res.get("pending_at")
                stale = (gap is not None
                         and len(_trading_days(gap + timedelta(days=1), last_session)) >= GAP_RETRY_SESSIONS)
                if not stale:
                    out["pending"] += 1
                    continue
                status = "abstain"          # the gap never closed: recorded, counted, never leapt
            fields.update(_outcome_fields(res, entry=entry, stop=stop, adr_dollar=adr_dollar,
                                          outcome=status, day0_bar_count=day0_count))
            await _write(fields, out, f"{label} {name}")
        except Exception as e:  # loud-ok: one arm's failure is counted; the others and the live trade proceed
            out["errors"] += 1
            await log_audit_event("live_fill_counterfactual_error",
                                  f"{label} arm {name}: {type(e).__name__}: {e}")


async def run_live_fill_counterfactuals(today: Optional[date] = None, *,
                                        now_et: Optional[datetime] = None) -> dict[str, int]:
    """Nightly entry point (scheduler `live_fill_counterfactuals`, 18:04 ET). NEVER raises:
    every failure is a counted error + an mi_audit_log row. Returns the run's counters."""
    now = now_et or datetime.now(_ET)
    today = today or now.date()
    out: dict[str, int] = {"population": 0, "fills_considered": 0, "arms_considered": 0,
                           "written": 0, "settled": 0, "abstained": 0, "unscoreable": 0,
                           "horizon": 0, "pending": 0, "errors": 0}
    try:
        last_session = last_settled_session(today, now)
        fills = await get_counterfactual_fills(BACKFILL_FROM, len(ARMS))
    except Exception as e:  # loud-ok: the run reports and ends; nothing live depends on it
        out["errors"] += 1
        await log_audit_event("live_fill_counterfactual_error", f"fill query failed: {e}")
        return out
    out["population"] = len(fills)
    if fills:
        try:
            pool = await get_pool()
            async with pool.acquire() as conn:
                for trade in fills:
                    try:
                        await _record_one_fill(conn, trade, last_session, out)
                    except Exception as e:  # loud-ok: per-fill isolation; counted + audited
                        out["errors"] += 1
                        await log_audit_event(
                            "live_fill_counterfactual_error",
                            f"{trade.get('ticker')} trade {trade.get('id')}: {type(e).__name__}: {e}")
        except Exception as e:  # loud-ok: pool-level failure; counted + audited
            out["errors"] += 1
            await log_audit_event("live_fill_counterfactual_error", f"run failed: {e}")
    await log_audit_event(
        "live_fill_counterfactual_recorded",
        f"{out['population']} fill(s) with arms to settle, {out['arms_considered']} arm(s) "
        f"considered: {out['written']} written ({out['settled']} settled, "
        f"{out['abstained']} abstained, {out['unscoreable']} unscoreable, "
        f"{out['horizon']} at horizon), {out['pending']} pending, {out['errors']} error(s)")
    return out
