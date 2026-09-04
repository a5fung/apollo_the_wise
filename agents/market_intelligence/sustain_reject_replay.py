"""2026-09-03 — #593 SUSTAIN-REJECT BRACKET REPLAY.

WHY (operator, 2026-09-03): the #490/#559 real-time sustain rule turns some gapping names
away. A watchdog exists to say whether it is turning away names that would have made money.
The rule as signed tests whether the PRICE moved >=20% above the declined level — and a
price move is not a trade outcome. Two of the four names the current test flags — IPST
($9.25 -> $4.71 over five sessions) and WETO ($22.74 -> $11.50) — spiked for minutes and
closed ~49% below the level they were declined at. They would have been STOPPED OUT by our
own bracket. Turning them away was correct, and the price-move test counts them as mistakes.
His own words: *"the two key things to know is 1) did it turn away real EPs, those that
would've made us 4R+ or 2) to a lesser extent those that would've made us positive return
at all."*

THE BUILD. Replace the price-move test with what our OWN bracket would have realized:
  1. For every net-declined ep_rt_sustain_reject ticker-day (the SAME funnel the #593 signed
     predicate already reads — kept unchanged; only the breach test moves), reconstruct the
     CURRENT-ERA MAGNA53 entry: ORB (the 9:30 minute bar), the admission ATR gate
     (`validate_orb_entry`), the stop-limit buy trigger in the submission window (`entry_walk`
     below, MIRRORING scripts/ep_replay.entry_walk's exact mechanics rather than a fifth copy
     — see WHAT IT MIRRORS).
  2. If it would have filled, walk the SAME live exit ladder
     (`live_fill_counterfactuals.walk_arm` — REUSED, not reimplemented; that module already
     is "the freshest example of this shape" and its walk was parity-tested against real
     fills the same day this task was written) under CURRENT-ERA rules (`rule_eras.
     exit_rules_as_of`), and store `realized_r` / `meets_4r` (>=4R, the P1 real-EP measure)
     / `meets_positive` (>0R, the lesser measure).
  3. `data_gated_reviews.yaml`'s standing predicate then reads the stored columns — it stays
     SQL and cheap; the replay is what changed, not the predicate's shape.

SUBMIT TIME IS THE REJECT'S OWN TICK, NOT A FIXED 09:31. A name declined at 09:41 could
never have been admitted before then — an ORB cross at 09:33 is a fill our bracket could
not have taken. `submit` is the earliest reject's own ET tick, floored to the minute and
floored UP to 09:31 (an order cannot submit before the open); a tick at/after 09:45 is
`window_out_of_orb` (CLAUDE.md's own ORB submission rule) — never simulated.

SURVIVORSHIP — the operator's own design constraint for #482, restated here because it bites
harder on THIS population: a name declined 3 sessions ago that is STILL RUNNING under the
live ladder is not a miss the recorder can drop just because it has not settled. Under the
live ladder winners run (trailing) and losers settle in minutes — a write-once-on-terminal
design (like #482's per-arm rows) would systematically keep the loser-heavy settled slice and
starve the trigger of exactly the evidence (a real runner still open) it exists to catch.
FIX: every row is written on the FIRST pass, terminal or not. A non-terminal walk (still
running, not a data gap) writes `outcome='open'` with `mark_r` — a MARK-TO-MARKET at the last
available close, never a return — and `mark_meets_4r`. The SAME guarded UPSERT
(`db.upsert_sustain_reject_replay`, WHERE the EXISTING row's outcome = 'open') refreshes it
on every later run until it actually settles, then never touches it again. A genuine DATA GAP
(a past session whose bar never arrived) is DIFFERENT from "still open" and is retried for
GAP_RETRY_SESSIONS nights (reusing `live_fill_counterfactuals.GAP_RETRY_SESSIONS`) before
being written `unscoreable` — it is never silently dropped either.

THE ERA STAMP — same reasoning as #482 ("we'll be updating our filters ... as we observe
live EPs"): `admission_era` records which admission stack REJECTED this name
(`rule_eras.admission_era_as_of(decline_date)`), so a later reader can segment if the
funnel's own floors (9% gap, $50M dollar volume) ever move. The WALK itself deliberately
does NOT use the era at decline_date — it always uses `rule_eras.exit_rules_as_of(today)`,
i.e. the bracket AS IT EXISTS NOW, because the question this task answers is "does the
CURRENT sustain rule cost the CURRENT bracket real EPs," not archaeology. `replay_exit_era`
/ `replay_exit_rules` / `replay_asof_date` record which "current" a settled row used, so a
future rule change is visible rather than silently reinterpreting old rows.

WHAT IT MIRRORS. `entry_walk` below is scripts/ep_replay.entry_walk's exact logic (broker
microstructure: stop-limit-buy trigger, gap-through, the limit-armed fallback) — mirrored,
not imported, because production code does not import from scripts/ (the offline-capture
harness; see its own module docstring). `_stop_limit_buy_price` mirrors
broker.order_manager.stop_limit_buy_price's two-floor buffer formula, exactly like
live_fill_counterfactuals.py inlines its own stop/target math rather than importing
order_manager (order_manager pulls in the Alpaca/execution stack; a shadow recorder must
not). The post-entry walk is NOT re-implemented a fourth time: it calls
`live_fill_counterfactuals.walk_arm` and `_assemble_sessions` directly — the SAME day-0
stop-first / same-bar-abstain / forward-ladder mechanics `walk_arm`'s own docstring already
validates against `_walk_leg` and real fills.

THE LINE — read this before touching anything here. This module is a passive OBSERVER:
  - ONE write target: `mi_sustain_reject_replays` (plus `mi_audit_log` via `log_audit_event`
    — never a trade-state table).
  - It NEVER writes to `mi_live_trades`, `mi_live_orders`, `mi_ep_alerts`, or any column any
    live decision reads. It calls no broker module and no Alpaca client — its only imports
    beyond agents.market_intelligence are `backtester.filters.validate_orb_entry` (the
    shared, non-broker admission rule scripts/ep_replay.py also calls) and
    `alert_rank_shadow.compute_atr14_prior` (pure, already used by a sibling shadow lane).
  - It is read by NO grading / entry / sizing / ordering / safeguard path — comparison
    telemetry only, feeding the #593 data_gated_reviews.yaml predicate alone. The recorder
    can be completely broken and the live trade path is unaffected: every reject's walk is
    wrapped; a failure degrades to a counted error + an `mi_audit_log` row,
    `run_sustain_reject_replay` never raises.
  - SILENT. No Telegram, ever, while evidence accrues (same posture as #482's sibling lane).
  - NOTHING ABOUT LIVE ADMISSION CHANGES. This watches the #490/#559 sustain gate; it never
    touches `ep_rt_sustain_enabled`, `_sustain_ok`, `EP_RT_SUSTAIN_BARS`, or the gate itself.

SCOPE. The SAME net-declined `ep_rt_sustain_reject` population the #593 signed predicate
reads, over a WIDER trailing window (`WINDOW_TRADING_DAYS`, deliberately wider than the
predicate's own 30-day trigger window) so a lagging write never leaves the predicate short.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from typing import Any, Optional

from shared.dates import _ET

from agents.market_intelligence import live_fill_counterfactuals as lfc
from agents.market_intelligence import rule_eras
from agents.market_intelligence.alert_rank_shadow import compute_atr14_prior
from agents.market_intelligence.backtester.filters import validate_orb_entry
from agents.market_intelligence.db import (
    _f,
    get_daily_ohlc_range,
    get_intraday_bars_window,
    get_pool,
    get_sustain_reject_population,
    get_sustain_replay_existing,
    log_audit_event,
    upsert_sustain_reject_replay,
)
from agents.market_intelligence.live_fill_counterfactuals import (
    n_trading_days_back,
    pinned_target,
    walk_arm,
)

logger = logging.getLogger(__name__)

SETTLE_VERSION = "srr_v1"
TARGET_R = 2.0                    # the +2R partial level, matching live_fill_counterfactuals.TARGET_R
GAP_FLOOR_PCT = 0.09              # MIN_GAP_PCT (ep_detector.py) — the 9% floor the signed funnel holds
DOLLAR_VOL_FLOOR = 50_000_000.0   # the $50M d0 dollar-volume floor the signed funnel holds
BREACH_MULT = 1.20                # the OLD +20%-price-move test — stored beside the new measure only
ATR_LOOKBACK_CAL_DAYS = 40        # calendar days read for prev_close + the ATR-14-prior window
PRIOR_CLOSES_CAL_DAYS = 40        # live_fill_counterfactuals convention — the trail's window (#548)
WINDOW_TRADING_DAYS = 40          # wider than the #593 predicate's 30-trading-day trigger window,
                                   # so a slow-to-settle row is never missing when the predicate reads it


# ── Pure compute (fixture-testable, no IO) ─────────────────────────────────────────────


def _stop_limit_buy_price(stop_price: float) -> float:
    """The LIMIT price for a stop-limit BUY parent order — mirrors
    broker.order_manager.stop_limit_buy_price's two-floor buffer (0.5% or $0.02, whichever
    is larger) EXACTLY. Inlined rather than imported: order_manager pulls in the
    Alpaca/execution stack, which a shadow recorder must never import (the
    live_fill_counterfactuals precedent — see that module's own inlined pinned_target)."""
    return round(max(stop_price * 1.005, stop_price + 0.02), 2)


def entry_walk(bars: list[dict], orb_high: float, submit: time,
               cancel: Optional[time]) -> dict:
    """Reconstruct the MAGNA53 stop-limit buy (stop = orb_high, limit =
    `_stop_limit_buy_price`): scan minute bars in [submit, cancel); the order triggers when
    a bar trades >= orb_high.
      bar opens < orb_high, high >= orb_high  -> intra-bar cross, fill AT orb_high
      bar opens in [orb_high, limit]          -> fill at the open
      bar opens above the limit               -> limit-armed; fills at the LIMIT on the
                                                 first later bar with low <= limit
    No cross by cancel: 'no_entry' only when the window has full minute coverage, else
    ABSTAIN — a gap could hide the cross. MIRRORS scripts/ep_replay.entry_walk's exact
    broker-microstructure logic (see the module docstring's WHAT IT MIRRORS: production code
    does not import scripts/, the offline-capture-only harness)."""
    limit = _stop_limit_buy_price(orb_high)
    limit_armed = False
    window = [b for b in bars
              if b["m"].time() >= submit and (cancel is None or b["m"].time() < cancel)]
    for b in window:
        if limit_armed:
            if b["l"] <= limit:
                return {"status": "filled", "px": limit, "minute": b["m"]}
            continue
        if b["o"] >= orb_high:
            if b["o"] <= limit:
                return {"status": "filled", "px": b["o"], "minute": b["m"]}
            limit_armed = True
            if b["l"] <= limit:
                return {"status": "filled", "px": limit, "minute": b["m"]}
        elif b["h"] >= orb_high:
            return {"status": "filled", "px": orb_high, "minute": b["m"]}
    if limit_armed:
        return {"status": "no_entry", "reason": "triggered_above_limit_never_filled"}
    end = cancel if cancel is not None else time(16, 0)
    expected = int((datetime.combine(date.min, end) -
                    datetime.combine(date.min, max(submit, time(9, 30)))).total_seconds() // 60)
    if len(window) < expected:
        return {"status": "abstain",
                "reason": f"entry_window_gaps:{expected - len(window)}_of_{expected}"}
    return {"status": "no_entry", "reason": "never_crossed_orb_high"}


def submit_time_and_window(decline_ts_et: datetime) -> tuple[Optional[time], bool]:
    """(submit_time, window_out_of_orb) from the earliest reject's own ET timestamp. Floored
    to the minute; floored UP to 09:31 (an order cannot submit before the open — pre-market
    ticks submit at the open like every other MAGNA53 admission). A tick at/after 09:45 is
    WINDOW_OUT_OF_ORB (CLAUDE.md's own ORB submission rule) and is never simulated —
    (None, True)."""
    t = decline_ts_et.time().replace(second=0, microsecond=0)
    if t >= time(9, 45):
        return None, True
    return max(t, time(9, 31)), False


def entry_cancel_asof(d: date) -> Optional[time]:
    """The unfilled-entry cancel time live on date d — 10:00 ET since the +2R partial went
    live (rule_eras.PARTIAL_LIVE_DATE), None before (CLAUDE.md ORB window; era-A fills as
    late as 11:35 prove no cancel then). `rule_eras.exit_rules_as_of` does not carry this
    switch (scripts/ep_replay.RuleSet does) — reused here rather than adding a field neither
    of this module's two other consumers of exit_rules_as_of would need."""
    return time(10, 0) if d >= rule_eras.PARTIAL_LIVE_DATE else None


def current_era_stop(stop_mode: str, orb_high: float, orb_low: float) -> float:
    """The protective stop CURRENT-era rules would place. orb_low pre-2026-08-16;
    2*orb_low-orb_high (order_manager ~L498: R = the ORB range) since — the SAME two formulas
    scripts/ep_replay.RuleSet.stop_price uses for stop_mode 'orb_low' / 'entry_minus_2r'."""
    if stop_mode == "orb_low":
        return orb_low
    return 2 * orb_low - orb_high


def old_basis_breaches(d0_high: Optional[float], sessions: list[tuple[date, Optional[dict]]],
                       declined_level: Optional[float]) -> tuple[Optional[bool], Optional[bool]]:
    """(breach_mfe_20, breach_settled_20) — the TWO price-move bases this task replaces as
    the TRIGGER, computed for EVERY row with a known declined_level (independent of whether
    OUR bracket's ORB/ATR/window rules would also have taken the trade — the retired funnel
    never simulated an entry), stored beside the new measure for a side-by-side report,
    never re-derived twice. `d0_high` is d0's own DAILY high (mi_daily_closes.high_price,
    the retired predicate's OWN basis) — never a minute-bar high, which the retired funnel
    never used either. MFE = peak HIGH over d0..d0+5 (d0_high plus up to 5 forward daily
    highs); SETTLED = the close on the d0+5 session specifically (None if that session has
    not happened yet — genuinely unknown, not a non-breach). Both None when declined_level
    is unknown (no valid prev_close)."""
    if declined_level is None:
        return None, None
    fwd = sessions[:5]
    highs = [d0_high] if d0_high is not None else []
    highs += [bar["h"] for _, bar in fwd if bar and bar.get("h") is not None]
    mfe_high = max(highs) if highs else None
    breach_mfe = (mfe_high >= declined_level * BREACH_MULT) if mfe_high is not None else None
    settled_close = None
    if len(fwd) >= 5 and fwd[4][1] is not None and fwd[4][1].get("c") is not None:
        settled_close = fwd[4][1]["c"]
    breach_settled = (settled_close >= declined_level * BREACH_MULT) if settled_close is not None else None
    return breach_mfe, breach_settled


def mark_pnl_per_share(res: dict, day0_bars: list[dict],
                       sessions: list[tuple[date, Optional[dict]]], entry: float) -> Optional[float]:
    """A MARK-TO-MARKET pnl/share for a walk that is still genuinely OPEN (walk_arm's
    'pending' / 'open_walk_not_definitive' case) — walk_arm itself only computes a mark at
    the 40-session HORIZON; this applies the SAME formula
    (pnl_from_exits + (last_close - entry) x remaining) to the open case, using the last
    close `walk_arm` actually walked through. Mirrors walk_arm's own horizon-case arithmetic
    verbatim rather than a second copy of the ladder itself."""
    exits = res.get("exits") or []
    remaining = res.get("remaining")
    if remaining is None:
        return None
    pnl = sum(e["pnl"] for e in exits)
    last_close = None
    for _, bar in reversed(sessions):
        if bar is not None and bar.get("c") is not None:
            last_close = bar["c"]
            break
    if last_close is None and day0_bars:
        last_close = day0_bars[-1].get("c")
    if last_close is None:
        return None
    return pnl + (last_close - entry) * remaining


# ── Orchestration (DB reads; writes only mi_sustain_reject_replays + audit) ────────────


def _fresh_fields(ticker: str, decline_date: date, rt_gap: Optional[float],
                  admission_era: str, replay_exit_era: str, replay_exit_rules: dict,
                  replay_asof_date: date, settled_session: date) -> dict[str, Any]:
    return {
        "ticker": ticker, "decline_date": decline_date, "rt_gap": rt_gap,
        "declined_level": None, "prev_close": None, "close_d0": None, "volume_d0": None,
        "held_floor_d0": None, "cleared_dollar_vol": None, "entry_reachable": None,
        "orb_high": None, "orb_low": None, "atr14_prior": None, "atr14_prior_n": None,
        "orb_valid": None, "orb_skip_reason": None,
        "submit_time_et": None, "entry_status": None, "entry_reason": None,
        "entry_price": None, "entry_minute": None,
        "stop_price": None, "target_price": None, "target_r": TARGET_R,
        "outcome": None, "final_reason": None, "realized_r": None, "realized_pct": None,
        "mark_r": None, "meets_4r": None, "meets_positive": None, "mark_meets_4r": None,
        "mark_meets_positive": None,
        "partial_fired": None, "gap_through": None, "exit_session": None,
        "sessions_walked": None, "exits": [],
        "breach_mfe_20": None, "breach_settled_20": None,
        "admission_era": admission_era, "replay_exit_era": replay_exit_era,
        "replay_exit_rules": replay_exit_rules, "replay_asof_date": replay_asof_date,
        "settle_version": SETTLE_VERSION, "settled_session": settled_session,
    }


async def _write(fields: dict, out: dict, label: str) -> bool:
    return await lfc.write_replay_row(
        fields, out, label,
        upsert=upsert_sustain_reject_replay,
        error_event="sustain_reject_replay_error",
    )


async def _record_one_reject(conn, row: dict, last_session: date, run_date: date,
                             out: dict) -> None:
    ticker, decline_date = row["ticker"], row["decline_date"]
    rt_gap = _f(row.get("rt_gap"))
    label = f"{ticker} {decline_date.isoformat()}"
    out["candidates"] += 1

    admission_era = rule_eras.admission_era_as_of(decline_date)
    replay_exit_rules = rule_eras.exit_rules_as_of(run_date)
    replay_exit_era = rule_eras.exit_era_label(run_date)
    fields = _fresh_fields(ticker, decline_date, rt_gap, admission_era, replay_exit_era,
                           replay_exit_rules, run_date, last_session)

    try:
        # ── prior + d0 daily bars: prev_close, close_d0, volume_d0, ATR-14-prior ──
        daily = await get_daily_ohlc_range(
            conn, ticker, decline_date - timedelta(days=ATR_LOOKBACK_CAL_DAYS), decline_date)
        d0_row = next((r for r in daily if r["trade_date"] == decline_date), None)
        prior_rows = [r for r in daily if r["trade_date"] < decline_date]
        prev_row = prior_rows[-1] if prior_rows else None
        prev_close = _f(prev_row["close"]) if prev_row else None
        close_d0 = _f(d0_row["close"]) if d0_row else None
        volume_d0 = _f(d0_row["volume"]) if d0_row else None
        fields.update(prev_close=prev_close, close_d0=close_d0, volume_d0=volume_d0)
        if rt_gap is not None and prev_close:
            fields["declined_level"] = prev_close * (1 + rt_gap / 100.0)
        if prev_close and close_d0 is not None:
            fields["held_floor_d0"] = (close_d0 - prev_close) / prev_close >= GAP_FLOOR_PCT
        if volume_d0 is not None and close_d0 is not None:
            fields["cleared_dollar_vol"] = (volume_d0 * close_d0) >= DOLLAR_VOL_FLOOR
        d0_high = _f(d0_row.get("high_price")) if d0_row else None
        if d0_high is not None and fields["declined_level"] is not None:
            # OLD funnel leg (d): reproduced exactly, on the DAILY high — independent of
            # whether our own bracket's ORB/ATR/window rules would also take the trade.
            fields["entry_reachable"] = d0_high >= fields["declined_level"]

        # Forward sessions are fetched HERE, unconditionally — both the OLD-basis breach
        # test below and the post-fill exit-ladder walk need the SAME list, and the retired
        # funnel computed breach_mfe/breach_settled for EVERY scoreable row regardless of
        # whether an ORB entry would ever have been simulated (it never simulated one at
        # all). Computing this only after a fill would silently NULL every no_trade/
        # window_out_of_orb row and make the stored old-basis columns incomparable to the
        # 2026-09-01 historical read.
        sessions = await lfc._assemble_sessions(conn, ticker, decline_date, last_session)
        fields["breach_mfe_20"], fields["breach_settled_20"] = old_basis_breaches(
            d0_high, sessions, fields["declined_level"])

        prior_hlc = [(_f(r.get("high_price")), _f(r.get("low_price")), _f(r.get("close")))
                    for r in prior_rows]
        prior_hlc = [t for t in prior_hlc if all(v is not None for v in t)]
        # compute_atr14_prior returns a single Optional[float] (None below 10 rows) — the
        # row count is stored separately for diagnostics (how many usable prior daily rows
        # were actually available), not returned by the function itself.
        atr14 = compute_atr14_prior(prior_hlc)
        fields.update(atr14_prior=atr14, atr14_prior_n=len(prior_hlc))
        prior_cut = decline_date - timedelta(days=PRIOR_CLOSES_CAL_DAYS)
        prior_closes = [float(r["close"]) for r in prior_rows
                        if r.get("close") is not None and r["trade_date"] >= prior_cut]

        # ── submit / window (the reject's OWN tick, not a fixed 09:31) ──
        decline_ts_et = row["decline_ts_et"]
        submit, window_out = submit_time_and_window(decline_ts_et)
        fields["submit_time_et"] = submit or decline_ts_et.time().replace(second=0, microsecond=0)
        if window_out:
            fields.update(entry_status="window_out_of_orb", outcome="no_trade",
                         final_reason="window_out_of_orb")
            await _write(fields, out, label)
            return

        # ── day-0 minute bars + ORB (the 9:30 bar) ──
        start = datetime.combine(decline_date, time(9, 30), tzinfo=_ET)
        end = datetime.combine(decline_date, time(16, 0), tzinfo=_ET)
        bars0 = await get_intraday_bars_window(conn, ticker, start, end)
        # bar_time is TIMESTAMPTZ; asyncpg hands it back UTC-aware — normalize to ET BEFORE
        # any .time() comparison (entry_walk's submission window, the 9:30 ORB lookup) or
        # every one of them silently compares the wrong clock (the live_fill_counterfactuals
        # ._day0_bars precedent for exactly this).
        bars0 = [{**b, "m": b["m"].astimezone(_ET) if isinstance(b["m"], datetime) else b["m"]}
                for b in bars0 if None not in (b["o"], b["h"], b["l"], b["c"])]
        if not bars0:
            fields.update(entry_status="no_day0_minute_bars", outcome="unscoreable",
                         final_reason="no_day0_minute_bars")
            await _write(fields, out, label)
            return
        orb = next((b for b in bars0 if b["m"].time() == time(9, 30)), None)
        if orb is None:
            fields.update(entry_status="no_930_bar_for_orb", outcome="unscoreable",
                         final_reason="no_930_bar_for_orb")
            await _write(fields, out, label)
            return
        orb_high, orb_low = orb["h"], orb["l"]
        fields.update(orb_high=orb_high, orb_low=orb_low)

        ok, skip = validate_orb_entry(orb_high, orb_low, atr14)
        fields.update(orb_valid=ok, orb_skip_reason=skip)
        if not ok:
            fields.update(entry_status="orb_invalid", outcome="no_trade", final_reason=skip)
            await _write(fields, out, label)
            return

        cancel = entry_cancel_asof(run_date)
        fill = entry_walk(bars0, orb_high, submit, cancel)
        fields.update(entry_status=fill["status"], entry_reason=fill.get("reason"))
        if fill["status"] != "filled":
            fields.update(outcome="unscoreable" if fill["status"] == "abstain" else "no_trade",
                         final_reason=fill.get("reason"))
            await _write(fields, out, label)
            return

        entry_px = fill["px"]
        fields.update(entry_price=entry_px, entry_minute=fill["minute"])
        stop = current_era_stop(replay_exit_rules["stop_mode"], orb_high, orb_low)
        risk = entry_px - stop
        if risk <= 0:
            fields.update(outcome="unscoreable", final_reason="nonpositive_risk_per_share")
            await _write(fields, out, label)
            return
        fields["stop_price"] = stop
        target = (pinned_target(entry_px, orb_low, TARGET_R)
                 if replay_exit_rules["intraday_partial_r"] else None)
        fields["target_price"] = target

        fill_idx = next(i for i, b in enumerate(bars0) if b["m"] == fill["minute"])
        # `sessions` was already fetched above (before the window/day0 checks) — reused here
        # rather than a second round trip.

        res = walk_arm(entry=entry_px, stop=stop, target=target, day0_bars=bars0,
                       fill_idx=fill_idx, sessions=sessions, prior_closes=prior_closes,
                       harvest="live_ladder", fill_day=decline_date,
                       breakeven_at_partial=bool(replay_exit_rules["breakeven_at_partial"]),
                       trail_prior_closes=bool(replay_exit_rules["trail_prior_closes"]),
                       ladder_partial=bool(replay_exit_rules["ladder_partial"]))
        status = res["status"]

        if status == "pending":
            gap = res.get("pending_at")
            if gap is not None:
                # a genuine DATA GAP (a past session whose bar never arrived) — retried like
                # #482's own forward-session gap, never silently dropped.
                stale = len(lfc._trading_days(gap + timedelta(days=1), last_session)) >= lfc.GAP_RETRY_SESSIONS
                if not stale:
                    out["pending"] += 1
                    return
                fields.update(outcome="unscoreable", final_reason=res.get("reason"))
                await _write(fields, out, label)
                return
            # genuinely still OPEN — not a data gap. Written now (the survivorship fix), and
            # refreshed by later runs via the guarded UPSERT until it actually settles.
            mark = mark_pnl_per_share(res, bars0, sessions, entry_px)
            fields.update(
                outcome="open", final_reason=res.get("reason"),
                partial_fired=res.get("partial_fired"), gap_through=res.get("gap_through"),
                sessions_walked=res.get("sessions_walked"), exits=res.get("exits") or [])
            if mark is not None:
                fields["mark_r"] = mark / risk
                fields["mark_meets_4r"] = fields["mark_r"] >= 4.0
                fields["mark_meets_positive"] = fields["mark_r"] > 0
            await _write(fields, out, label)
            return

        fields.update(
            partial_fired=res.get("partial_fired"), gap_through=res.get("gap_through"),
            exit_session=res.get("exit_session"), sessions_walked=res.get("sessions_walked"),
            exits=res.get("exits") or [], final_reason=res.get("final_reason") or res.get("reason"))
        if status == "settled":
            pnl = res.get("pnl_per_share")
            fields["outcome"] = "settled"
            if pnl is not None:
                fields["realized_r"] = pnl / risk
                fields["realized_pct"] = pnl / entry_px * 100.0
                fields["meets_4r"] = fields["realized_r"] >= 4.0
                fields["meets_positive"] = fields["realized_r"] > 0
        elif status == "horizon":
            fields["outcome"] = "horizon"
            mark = res.get("mark_pnl_per_share")
            if mark is not None:
                fields["mark_r"] = mark / risk
                fields["mark_meets_4r"] = fields["mark_r"] >= 4.0
                fields["mark_meets_positive"] = fields["mark_r"] > 0
        else:  # abstain — a genuine day-0 order-ambiguity (same-bar stop+target, etc.)
            fields["outcome"] = "unscoreable"
        await _write(fields, out, label)
    except Exception as e:  # loud-ok: one reject's failure is counted; the others proceed
        out["errors"] += 1
        await log_audit_event("sustain_reject_replay_error", f"{label}: {type(e).__name__}: {e}")


async def run_sustain_reject_replay(today: Optional[date] = None, *,
                                    now_et: Optional[datetime] = None) -> dict[str, int]:
    """Nightly entry point. NEVER raises: every failure is a counted error + an
    mi_audit_log row. Returns the run's counters."""
    now = now_et or datetime.now(_ET)
    today = today or now.date()
    out: dict[str, int] = {"population": 0, "candidates": 0, "written": 0, "settled": 0,
                           "no_trade": 0, "unscoreable": 0, "open": 0, "horizon": 0,
                           "pending": 0, "errors": 0}
    try:
        last_session = lfc.last_settled_session(today, now)
        window_start = n_trading_days_back(last_session, WINDOW_TRADING_DAYS)
        rows = await get_sustain_reject_population(window_start)
        existing = await get_sustain_replay_existing(window_start)
    except Exception as e:  # loud-ok: the run reports and ends; nothing live depends on it
        out["errors"] += 1
        await log_audit_event("sustain_reject_replay_error", f"population query failed: {e}")
        return out
    out["population"] = len(rows)
    todo = [r for r in rows
           if existing.get((r["ticker"], r["decline_date"])) in (None, "open")]
    if todo:
        try:
            pool = await get_pool()
            async with pool.acquire() as conn:
                for row in todo:
                    try:
                        await _record_one_reject(conn, row, last_session, today, out)
                    except Exception as e:  # loud-ok: per-name isolation; counted + audited
                        out["errors"] += 1
                        await log_audit_event(
                            "sustain_reject_replay_error",
                            f"{row.get('ticker')} {row.get('decline_date')}: "
                            f"{type(e).__name__}: {e}")
        except Exception as e:  # loud-ok: pool-level failure; counted + audited
            out["errors"] += 1
            await log_audit_event("sustain_reject_replay_error", f"run failed: {e}")
    await log_audit_event(
        "sustain_reject_replay_recorded",
        f"{out['population']} net-declined ticker-day(s) in window, {len(todo)} candidate(s) "
        f"processed: {out['written']} written ({out['settled']} settled, "
        f"{out['no_trade']} no_trade, {out['unscoreable']} unscoreable, {out['open']} open, "
        f"{out['horizon']} at horizon), {out['pending']} pending, {out['errors']} error(s)")
    return out
