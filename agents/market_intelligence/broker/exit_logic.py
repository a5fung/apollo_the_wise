"""Pure daily-exit-step decision logic — single source of truth for the
SMA10/20 trail + Day 3-5 partial profit + hard-stop ladder used by both
the backtester and the live tracker.

No DB, Alpaca, or Telegram side effects: callers wrap this with their
own persistence and broker calls. Backtest semantics are the default —
hard_stop fires deterministically when bar_low <= hard_stop. The live
tracker re-calls with state['hard_stop']=None when Alpaca confirms the
position is still held (stop didn't actually trigger), and re-calls
with skip_partial_decision=True if the partial-exit helper failed and
the trade should fall through to SMA logic with the original remaining.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Any


@dataclass
class ExitStep:
    action: str
    """One of: 'skip_pre_alert', 'no_data', 'stopped_out', 'sma_stopped',
    'partial_only', 'updated'.  'partial_only' means partial fired and
    position remains open; 'sma_stopped' may fire alongside a partial
    in the same step (caller checks partial_fired in addition to action)."""

    closed: bool
    close_reason: str | None
    close_price: float | None
    close_shares: float | None
    close_pnl: float | None

    partial_fired: bool
    partial_shares: float
    partial_price: float | None
    partial_pnl: float | None

    effective_stop: float
    active_sma: float | None
    """The active trailing indicator value — SMA10/20 by default, or the 10/20 EMA when
    `trail_mode='ema_10_20'` (#396 HTF Phase 4). Field name kept as `active_sma` for callers
    already reading it; the VALUE's source depends on the trail_mode the caller requested."""
    bar_low: float | None
    bar_close: float | None
    hold_days: int

    # Updated state fields for caller persistence
    new_remaining: float
    new_partial_taken: bool
    new_breakeven_active: bool
    new_running_closes: list[float]
    new_exits: list[dict]
    new_total_pnl: float

    stop_source: str = "hard_stop"
    """TELEMETRY ONLY — which input actually SET `effective_stop` (#560, 2026-08-12).
    One of 'hard_stop' / 'trail' (the active_sma value) / 'breakeven' (entry_price) /
    'giveback_floor'. Presentation layers (operator-facing Telegram) use this to say
    WHICH rule moved the stop instead of leaving the operator to guess. Purely a label
    on a value already computed by the existing max()-composition below — it does NOT
    feed back into the computation, so effective_stop is byte-identical to before this
    field existed. Default 'hard_stop' only matters for hand-built ExitStep() in tests
    that don't set it; every real code path below sets it explicitly."""


def ema(closes: list[float], window: int) -> float | None:
    """Standard EMA of `closes`, seeded with the SMA of the first `window` values then
    recursively updated (smoothing factor 2/(window+1)) through the remaining closes. Returns
    the EMA value AS OF THE LAST element in `closes`. None when len(closes) < window —
    mirrors the None-on-insufficient-data contract the inline SMA10/20 trail already uses
    below. Pure function, no side effects. #396 HTF Phase 4 (management SHADOW) — the 10/20
    EMA trail input; also usable anywhere an EMA (vs SMA) trail is wanted.

    NB (7/3 review): near-duplicate of regime._ema — kept SEPARATE deliberately:
    exit_logic is pure broker-side math with zero heavy imports; importing regime
    (which pulls collector/db) would break that. The EMA definition is frozen
    textbook math; if it ever changes, change BOTH (regime.py ~line 41)."""
    if len(closes) < window:
        return None
    multiplier = 2.0 / (window + 1)
    value = sum(closes[:window]) / window
    for c in closes[window:]:
        value = (c - value) * multiplier + value
    return value


def giveback_floor(
    running_closes: list[float],
    entry_price: float | None,
    *,
    arm_gain: float | None = None,
    arm_r: float | None = None,
    floor_frac: float | None = None,
    risk_per_share: float | None = None,
) -> float | None:
    """Peak-lock giveback floor price, or None when disarmed / not configured.

    ADR 0023 Card 1 (A3) — the ONE new exit hook, pure + opt-in + DEFAULT-OFF. When a
    trade has run up past an ARM threshold, lock in a FLOOR at a fraction of the peak
    gain so a round-tripper (SMCI +11.7%→−$639, PURR +13.4%→$3) can't give the whole
    move back. Returns a price to feed the EXISTING `effective_stop = max(...)`
    composition — it is one more max() input, so it can only RAISE the stop, never lower it.

    Contract:
      - `floor_frac is None` → hook OFF: return None immediately (the default; keeps every
        existing caller byte-identical, nothing computed).
      - Exactly one of `arm_gain` (peak_gain fraction, e.g. 0.08 = +8%) / `arm_r` (peak gain
        in R-multiples, e.g. 2.0 = +2R — REQUIRES `risk_per_share`) sets WHEN the lock arms.
      - Armed when `peak_close >= arm_price` (>=, inclusive boundary). peak_close =
        max(running_closes) — derivable from state, no schema change; live wiring later would
        use `mi_live_trades.highest_price_seen`.
      - Floor = `entry + floor_frac × (peak_close − entry)`. Since arming needs peak > entry
        (arm_gain/arm_r > 0), the floor is always above entry when armed.
      - `entry_price` falsy or `running_closes` empty → None (data gap, graceful — not a
        config error). Inconsistent CONFIG (both/neither arm, non-positive arm, arm_r without
        a positive risk_per_share, floor_frac outside (0, 1]) → ValueError (fail loud, mirrors
        the `trail_mode` guard in apply_daily_exit_step).
    """
    if floor_frac is None:
        return None
    # --- config validation (fail loud, only reachable once the hook is opted-in) ---
    if not (0.0 < floor_frac <= 1.0):
        raise ValueError(f"giveback_floor: floor_frac must be in (0, 1], got {floor_frac!r}")
    if (arm_gain is None) == (arm_r is None):
        raise ValueError("giveback_floor: pass EXACTLY one of arm_gain / arm_r")
    if arm_gain is not None and arm_gain <= 0:
        raise ValueError(f"giveback_floor: arm_gain must be > 0, got {arm_gain!r}")
    if arm_r is not None:
        if arm_r <= 0:
            raise ValueError(f"giveback_floor: arm_r must be > 0, got {arm_r!r}")
        if risk_per_share is None or risk_per_share <= 0:
            raise ValueError("giveback_floor: arm_r requires a positive risk_per_share")
    # --- data guards (graceful None, not a config error) ---
    if not entry_price or not running_closes:
        return None
    peak_close = max(running_closes)
    if arm_gain is not None:
        arm_price = entry_price * (1.0 + arm_gain)
    else:
        arm_price = entry_price + arm_r * risk_per_share
    if peak_close < arm_price:
        return None
    return entry_price + floor_frac * (peak_close - entry_price)


def apply_daily_exit_step(
    state: dict[str, Any],
    daily_bar: dict[str, Any] | None,
    today: date,
    *,
    integer_partial_shares: bool = False,
    skip_partial_decision: bool = False,
    skip_hard_stop_close: bool = False,
    trail_mode: str = "sma",
    scale_fraction: float | None = None,
    giveback_arm_gain: float | None = None,
    giveback_arm_r: float | None = None,
    giveback_floor_frac: float | None = None,
    giveback_risk_per_share: float | None = None,
    character_ma_window: int = 20,
    character_ma_kind: str = "sma",
    character_undercut: float = 0.0,
    trail_undercut: float = 0.0,
    prior_closes: list[float] | None = None,
) -> ExitStep:
    """Compute one daily exit step.

    state must contain:
      alert_date, remaining_shares, entry_price, hard_stop,
      partial_taken, breakeven_active, exits, running_closes

    daily_bar (None if no bar available) provides 'l' and 'c'.

    integer_partial_shares: True for live (Alpaca needs whole shares),
      False for backtest (fractional sim).
    skip_partial_decision: True to bypass the partial-profit branch
      entirely (used by live wrapper after partial helper fails).

    trail_mode: 'sma' (DEFAULT, byte-identical to pre-#396 behavior) uses the
      max(SMA10, SMA20) trail. 'ema_10_20' (#396 HTF Phase 4 management SHADOW,
      OPT-IN — no existing caller passes this) uses the max(EMA10, EMA20) trail
      instead via the `ema()` helper above — same downstream branch (close below
      the trail -> close), just a different indicator source. 'sma_10_20_handoff'
      (ADR 0023 Card 2 sweep, OPT-IN — evidence-only, no live caller) trails a
      SINGLE SMA10 until a partial is taken, then hands off to SMA20 (tighter early,
      looser once de-risked). Any other value raises ValueError (fail loud).

    scale_fraction: None (DEFAULT) preserves the EXACT original partial-sizing
      arithmetic (`remaining // 3` / `remaining / 3` — the untouched behavior
      every existing caller depends on). A float (e.g. 0.40, within the sourced
      0.33-0.50 HTF range — docs/setups/htf.md) OPTS IN to a variable scale-out
      fraction instead of the hardcoded 1/3 (#396 HTF Phase 4).

    giveback_arm_gain / giveback_arm_r / giveback_floor_frac / giveback_risk_per_share:
      ADR 0023 Card 1 (A3) peak-lock, DEFAULT-OFF. `giveback_floor_frac is None`
      (default) → NO effect, byte-identical to every existing caller. When set (with
      exactly one of giveback_arm_gain / giveback_arm_r, the latter needing
      giveback_risk_per_share), computes the `giveback_floor()` price and feeds it as one
      more max() input into the step-4 effective_stop composition — it can only RAISE the
      stop. The close-below-effective-stop branch (step 5) is UNCHANGED (the giveback lock
      surfaces as an `sma_trail_stop` close; the ExitStep.effective_stop value reveals which
      input bound). See `giveback_floor` above for arm/floor semantics + fail-loud config
      validation. Opt-in for the #306 harvest sweep harness (Card 2); no live caller passes it.

    prior_closes: the STOCK's daily closes from BEFORE entry, oldest-first (#548,
      2026-08-08). The trail is *the stock's* 10/20-day moving average — a standard
      indicator that exists every day, with or without our position
      (`EP_TRADING_RULES.md` §B4: "Trail your stop with the 10- or 20-day moving
      average… Exit on first daily close below the active MA"). Without this the trail
      averaged `running_closes`, which starts EMPTY at fill and holds only the closes
      observed while WE held — i.e. the mean of our holding period. It therefore could
      not exist until ~10 trading days held, and on live money (max hold 2 days) it was
      structurally dead: 0 fires in 17 trades, 2 fires ever, both paper, both at exactly
      10 closes. The operator caught it: *"10d MA exists regardless of how long we
      traded it."*

      ⚠ Feeds the TRAIL INDICATORS ONLY. `giveback_floor` and the peak it derives from
      `max(running_closes)` deliberately still see the HELD period alone — a pre-entry
      high is not a gain we ever had, and folding it in would arm the giveback floor
      against a peak the position never reached.

      None (DEFAULT) = byte-identical to every existing caller.

    """
    if trail_mode not in ("sma", "ema_10_20", "sma_10_20_handoff", "pivot_swing",
                          "character_ma", "sma10", "sma20", "sma50", "none"):
        raise ValueError(f"apply_daily_exit_step: unknown trail_mode {trail_mode!r}")
    remaining = float(state.get("remaining_shares") or 0)
    alert_date = state["alert_date"]
    entry_price = state.get("entry_price")
    hard_stop = state.get("hard_stop")
    partial_taken = bool(state.get("partial_taken", False))
    breakeven_active = bool(state.get("breakeven_active", False))
    exits = list(state.get("exits") or [])
    running_closes = list(state.get("running_closes") or [])

    if remaining <= 0 or today <= alert_date:
        return _skip(remaining, partial_taken, breakeven_active,
                     running_closes, exits, today, alert_date,
                     "skip_pre_alert")

    if not daily_bar:
        return _skip(remaining, partial_taken, breakeven_active,
                     running_closes, exits, today, alert_date,
                     "no_data")

    bar_low = float(daily_bar.get("l", 0))
    bar_close = float(daily_bar.get("c", 0))
    hold_days = (today - alert_date).days
    running_closes = running_closes + [bar_close]

    # 1. Hard stop — backtest-pure semantics. Live wrapper passes
    # skip_hard_stop_close=True after Alpaca verifies the position is
    # still held, so the close branch is bypassed but hard_stop still
    # contributes to effective_stop below.
    if hard_stop and bar_low <= hard_stop and not skip_hard_stop_close:
        pnl = (hard_stop - entry_price) * remaining if entry_price else 0
        new_exits = exits + [{
            "time": datetime.combine(today, time(16, 0)).isoformat(),
            "price": hard_stop,
            "reason": "stop_hit",
            "shares": remaining,
            "pnl": pnl,
        }]
        total_pnl = sum(e.get("pnl", 0) for e in new_exits)
        return ExitStep(
            action="stopped_out", closed=True,
            close_reason="stop_hit", close_price=hard_stop,
            close_shares=remaining, close_pnl=pnl,
            partial_fired=False, partial_shares=0,
            partial_price=None, partial_pnl=None,
            effective_stop=float(hard_stop), active_sma=None,
            bar_low=bar_low, bar_close=bar_close, hold_days=hold_days,
            new_remaining=0, new_partial_taken=partial_taken,
            new_breakeven_active=breakeven_active,
            new_running_closes=running_closes, new_exits=new_exits,
            new_total_pnl=total_pnl, stop_source="hard_stop",
        )

    # 2. Trail indicator — SMA10/20 (default, UNCHANGED), the 10/20 EMA (opt-in, #396),
    # or the SMA10→SMA20 handoff (opt-in, ADR 0023 Card 2 sweep — Axis B).
    # THE TRAIL SEES THE STOCK'S HISTORY, the peak/giveback logic below does not (#548).
    # `running_closes` is our HELD period; `trail_closes` prepends the stock's prior closes so
    # SMA10/20 is the real 10/20-day moving average from day one instead of the mean of however
    # long we happen to have been in. Empty/None prior_closes -> identical to the old behavior.
    trail_closes = list(prior_closes or []) + running_closes
    active_sma = None
    if trail_mode == "none":
        # 2026-09-06 (#545 trail sweep, OPT-IN, evidence-only — no live caller passes this):
        # NO trail line at all, so the effective stop is the hard stop and the breakeven floor
        # alone. The control arm: without it, "the trail earns its keep" is unfalsifiable.
        active_sma = None
    elif trail_mode in ("sma10", "sma20", "sma50"):
        # A SINGLE moving average, not the max() of two. The live "sma" mode takes
        # max(SMA10, SMA20), which is the TIGHTER of the pair — and when a stock rolls over
        # and SMA20 rises above SMA10, that max() hands the position a stop ABOVE the recent
        # price. These arms isolate one line so that effect is measurable rather than assumed.
        _w = int(trail_mode[3:])
        active_sma = (sum(trail_closes[-_w:]) / _w) if len(trail_closes) >= _w else None
    elif trail_mode == "ema_10_20":
        ema_10 = ema(trail_closes, 10)
        ema_20 = ema(trail_closes, 20)
        if ema_20 is not None:
            active_sma = ema_10 if (ema_10 is not None and ema_10 > ema_20) else ema_20
        elif ema_10 is not None:
            active_sma = ema_10
    elif trail_mode == "pivot_swing":
        # ADR 0031 P1 (SHADOW-ONLY, 2026-07-12): the trail line is the caller-annotated
        # ratcheting CONFIRMED swing low, carried on the bar itself (extra bar keys pass
        # through the #445 driver untouched). Recorded deviation: exits fire on the ladder's
        # uniform CLOSE-below semantics, not intraday touch — conservative for the arm.
        _ps = daily_bar.get("pivot_stop")
        active_sma = float(_ps) if _ps is not None else None
    elif trail_mode == "character_ma":
        # ADR 0031 P2 (SHADOW-ONLY): the stock's own respected MA with ITS OWN habitual
        # undercut tolerance — home_MA × (1 − undercut_p80), both from the per-ticker
        # character profile (pivot_analysis.character_profile). <window closes → no line
        # yet (no exit — mirrors the existing None-guard behavior).
        if character_ma_kind == "ema":
            _line = ema(trail_closes, character_ma_window)
        else:
            _line = (sum(trail_closes[-character_ma_window:]) / character_ma_window
                     if len(trail_closes) >= character_ma_window else None)
        active_sma = _line * (1.0 - character_undercut) if _line is not None else None
    else:
        sma_10 = sum(trail_closes[-10:]) / 10 if len(trail_closes) >= 10 else None
        sma_20 = sum(trail_closes[-20:]) / 20 if len(trail_closes) >= 20 else None
        if trail_mode == "sma_10_20_handoff":
            # SMA10 until a partial is taken, then SMA20 (a SINGLE sma, not the max()).
            # partial_taken here is the PRIOR-day state (step 3 flips it AFTER this), so the
            # switch to SMA20 takes effect the day AFTER the partial. Post-partial but <20
            # closes → fall back to SMA10 so a trail stays live (never drops protection).
            if partial_taken:
                active_sma = sma_20 if sma_20 is not None else sma_10
            else:
                active_sma = sma_10
        else:
            # "sma" — max(SMA10, SMA20), byte-identical to pre-#396 (both call sites).
            if sma_20 is not None:
                active_sma = sma_10 if sma_10 > sma_20 else sma_20
            elif sma_10 is not None:
                active_sma = sma_10

    # 3. Partial profit Day 3-5
    partial_fired = False
    partial_shares = 0.0
    partial_pnl = None
    partial_price = None
    if not skip_partial_decision and hold_days >= 3 and not partial_taken and entry_price:
        take_partial = (
            (hold_days <= 4 and bar_close > entry_price)
            or hold_days >= 5
        )
        if take_partial:
            if scale_fraction is None:
                # UNCHANGED — the original hardcoded 1/3 arithmetic every existing caller depends on.
                if integer_partial_shares:
                    partial_shares = float(int(remaining) // 3)
                else:
                    partial_shares = remaining / 3
            else:
                # #396 opt-in variable scale (0.33-0.50, sourced — docs/setups/htf.md).
                if integer_partial_shares:
                    partial_shares = float(int(remaining * scale_fraction))
                else:
                    partial_shares = remaining * scale_fraction
            if partial_shares > 0:
                partial_fired = True
                partial_price = bar_close
                partial_pnl = (bar_close - entry_price) * partial_shares
                remaining -= partial_shares
                exits = exits + [{
                    "time": datetime.combine(today, time(16, 0)).isoformat(),
                    "price": bar_close,
                    "reason": "partial_profit",
                    "shares": partial_shares,
                    "pnl": partial_pnl,
                }]
                partial_taken = True
                breakeven_active = True

    # 2b. Trail undercut (2026-09-06, #545, OPT-IN default 0.0 = byte-identical).
    # Operator: "price still below by a margin vs stop immediately". Requires the close to
    # clear the line by a margin before it counts as a break, so a marginal poke through the
    # average is not an exit. Applies to whichever line mode 2 produced; with "character_ma"
    # it STACKS on that mode's own per-ticker undercut (both are deliberate tolerances).
    if trail_undercut and active_sma is not None:
        if not 0.0 <= trail_undercut < 1.0:
            raise ValueError(f"trail_undercut must be in [0, 1), got {trail_undercut!r}")
        active_sma = active_sma * (1.0 - trail_undercut)

    # 4. Effective stop
    # stop_source is a pure LABEL tracking which branch last raised effective_stop —
    # every condition/value below is byte-identical to before this label existed
    # (#560); it only records which one fired, never changes what fires.
    effective_stop = float(hard_stop or 0)
    stop_source = "hard_stop"
    if active_sma and active_sma > effective_stop:
        effective_stop = active_sma
        stop_source = "trail"
    if breakeven_active and entry_price and entry_price > effective_stop:
        effective_stop = float(entry_price)
        stop_source = "breakeven"
    # 4b. Peak-lock giveback floor (ADR 0023 Card 1, A3) — DEFAULT-OFF. One more max()
    # input: raises effective_stop to lock in a fraction of the peak gain once armed,
    # never lowers it. running_closes already includes today's close (line above).
    gb_floor = giveback_floor(
        running_closes, entry_price,
        arm_gain=giveback_arm_gain, arm_r=giveback_arm_r,
        floor_frac=giveback_floor_frac, risk_per_share=giveback_risk_per_share,
    )
    if gb_floor is not None and gb_floor > effective_stop:
        effective_stop = gb_floor
        stop_source = "giveback_floor"

    # 5. SMA trail close
    if bar_close < effective_stop and remaining > 0:
        pnl = (bar_close - entry_price) * remaining if entry_price else 0
        new_exits = exits + [{
            "time": datetime.combine(today, time(16, 0)).isoformat(),
            "price": bar_close,
            "reason": "sma_trail_stop",
            "shares": remaining,
            "pnl": pnl,
        }]
        total_pnl = sum(e.get("pnl", 0) for e in new_exits)
        return ExitStep(
            action="sma_stopped", closed=True,
            close_reason="sma_trail_stop", close_price=bar_close,
            close_shares=remaining, close_pnl=pnl,
            partial_fired=partial_fired, partial_shares=partial_shares,
            partial_price=partial_price, partial_pnl=partial_pnl,
            effective_stop=effective_stop, active_sma=active_sma,
            bar_low=bar_low, bar_close=bar_close, hold_days=hold_days,
            new_remaining=0, new_partial_taken=partial_taken,
            new_breakeven_active=breakeven_active,
            new_running_closes=running_closes, new_exits=new_exits,
            new_total_pnl=total_pnl, stop_source=stop_source,
        )

    # 6. Still open
    total_pnl = sum(e.get("pnl", 0) for e in exits)
    action = "partial_only" if partial_fired else "updated"
    return ExitStep(
        action=action, closed=False,
        close_reason=None, close_price=None, close_shares=None, close_pnl=None,
        partial_fired=partial_fired, partial_shares=partial_shares,
        partial_price=partial_price, partial_pnl=partial_pnl,
        effective_stop=effective_stop, active_sma=active_sma,
        bar_low=bar_low, bar_close=bar_close, hold_days=hold_days,
        new_remaining=remaining, new_partial_taken=partial_taken,
        new_breakeven_active=breakeven_active,
        new_running_closes=running_closes, new_exits=exits,
        new_total_pnl=total_pnl, stop_source=stop_source,
    )


def _skip(remaining, partial_taken, breakeven_active,
          running_closes, exits, today, alert_date, action) -> ExitStep:
    hold_days = (today - alert_date).days if alert_date else 0
    total_pnl = sum(e.get("pnl", 0) for e in exits)
    return ExitStep(
        action=action, closed=False,
        close_reason=None, close_price=None, close_shares=None, close_pnl=None,
        partial_fired=False, partial_shares=0,
        partial_price=None, partial_pnl=None,
        effective_stop=0, active_sma=None,
        bar_low=None, bar_close=None, hold_days=hold_days,
        new_remaining=remaining, new_partial_taken=partial_taken,
        new_breakeven_active=breakeven_active,
        new_running_closes=running_closes, new_exits=exits,
        new_total_pnl=total_pnl, stop_source="none",
    )


# ── #445: THE canonical replay driver (one copy of the seed→step→carry loop) ─
# The "seed 8-field state → loop apply_daily_exit_step → carry state forward →
# detect .closed" pattern was copy-pasted 4× (giveback_shadow._replay ·
# _306_harvest_sweep.replay · flag_detector._htf_management_replay ·
# orb_extension_shadow settle) and register R4 (moneypath audit 7/12) requires
# every NEW shadow (0026-C3 / 0027-C3 / 0031-C3) to ride ONE driver instead of
# a fifth copy. The driver owns ONLY the fragile duplicated part (seed shape +
# carry-forward); fold/termination semantics stay with each consumer.

def seed_exit_state(*, alert_date, entry_price, hard_stop, remaining_shares,
                    partial_taken=False, breakeven_active=False,
                    exits=None, running_closes=None) -> dict:
    """The canonical 8-field exit-ladder state. Persisted-state consumers
    (orb_extension resume) may pass their stored values for the mutable five."""
    return {
        "alert_date": alert_date,
        "entry_price": entry_price,
        "hard_stop": hard_stop,
        "remaining_shares": remaining_shares,
        "partial_taken": partial_taken,
        "breakeven_active": breakeven_active,
        "exits": list(exits) if exits else [],
        "running_closes": list(running_closes) if running_closes else [],
    }


def iter_exit_ladder(state: dict, bars, *, integer_partial_shares: bool = True,
                     **step_kwargs):
    """Drive `apply_daily_exit_step` over `bars`, carrying state forward IN PLACE.

    `bars`: iterable of `(day, bar_dict)` — bar_dict needs at least {"l","c"}
    (extra keys pass through untouched). `step_kwargs` are forwarded verbatim to
    every step (trail_mode / scale_fraction / giveback_* — constant per replay,
    matching all four migrated call sites).

    Yields `(i, day, step)` AFTER the carry, so `state` already reflects the
    step when the consumer sees it (the caller's dict is updated in place — the
    persisted-state consumers write `state` straight back to their tables).
    Stops after yielding a closed step; a caller that needs pre-step values
    (e.g. HTF's was_breakeven) snapshots them before consuming the next item.
    """
    for i, (day, bar) in enumerate(bars):
        step = apply_daily_exit_step(
            state, bar, day, integer_partial_shares=integer_partial_shares,
            **step_kwargs)
        state.update(
            remaining_shares=step.new_remaining,
            partial_taken=step.new_partial_taken,
            breakeven_active=step.new_breakeven_active,
            exits=step.new_exits,
            running_closes=step.new_running_closes,
        )
        yield i, day, step
        if step.closed:
            return
