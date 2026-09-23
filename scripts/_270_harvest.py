#!/usr/bin/env python3
"""#270 shared HARVEST evaluator — the SINGLE realized-exit simulator + rule set, used by
BOTH `_270_exit_replay.py` (FIRST5 entry; day-0 MINUTE + daily path, opt/pess bounds) and
`_270_anticipation_replay.py` (coiled-close entry; daily-only path, pess). Extracted 2026-06-14
(/simplify): the two scripts previously carried hand-synced copies of this loop + rule dict, so
a fill-honesty change in one silently skipped the other — exactly the MFE-vs-realized
silent-divergence class the #270 analysis exists to close. One implementation, no drift.

A `path` is a list of bars: {o, h, l, c, kind:"min"|"day", prior_low, day_idx}. The caller owns
path construction (entry-specific); this module owns the harvest math only.
"""

# Each rule: partials [(R_multiple, fraction)], breakeven_after_first, trail_prior_low,
# time_stop_days (force-exit remaining at that daily bar's close), hold (exit at end),
# perfect_mfe (ceiling anchor). The full speed spectrum; callers pick the subset they need.
RULES = {
    "MFE_ceiling":   dict(perfect_mfe=True),
    "all_out_+1R":   dict(partials=[(1.0, 1.0)]),
    "time_stop_2d":  dict(time_stop_days=2),
    "half_1R_trail": dict(partials=[(1.0, 0.5)], breakeven_after_first=True,
                          trail_prior_low=True),
    # tail-capture variants — bank the bulk fast (protect the median) but keep a
    # runner tranche for the fat tail (the setup's reason-for-being).
    "bank_1R_3R":    dict(partials=[(1.0, 0.5), (3.0, 0.5)]),                 # 1/2@+1R, 1/2@+3R
    "bank2_1R_run":  dict(partials=[(1.0, 0.667)], breakeven_after_first=True,
                          trail_prior_low=True),                              # 2/3@+1R, 1/3 trail
    "hold_10d":      dict(hold=True),
    # Pradeep TWO-PHASE / character-based exit (operator 2026-06-15, from his anticipation
    # tweets): day-0 AGGRESSIVE intraday giveback trail ("move stops aggressively if it
    # gaps/breaks out fast — it fades you out WITH profit") → survivors held on the prior-low
    # trail to a day-5 time stop ("genuine breakouts don't fade — hold 3-5 days"). Tests
    # CONDITIONAL hold (hold only what survives day-0) — the path fixed targets CAP and
    # unconditional hold_10d LOSES. day0_giveback = max fraction of the gain-from-running-high
    # surrendered on day-0 before the trail fires (0.50 = give back half; 0.33 = tighter).
    "twophase_g50":  dict(day0_giveback=0.50, trail_prior_low=True, time_stop_days=5),
    "twophase_g33":  dict(day0_giveback=0.33, trail_prior_low=True, time_stop_days=5),
}


def simulate(entry, init_stop, path, rule, bound):
    """Realized R under one intrabar `bound` ('opt' target-first / 'pess' stop-first).
    risk = entry - init_stop. Returns (realized_R, captured_pct_of_mfe, fills) where
    `fills` is a list of (day_idx, fraction) for every exit slice — the raw material
    for the fill-day distribution that VALIDATES (vs assumes) the 'same-day harvest'
    claim (day_idx 0 == trigger day). Returns None if risk <= 0."""
    risk = entry - init_stop
    if risk <= 0:
        return None
    if rule.get("perfect_mfe"):
        mfe_px = max(b["h"] for b in path)
        return (mfe_px - entry) / risk, 1.0, []          # ceiling anchor: no real fills

    partials = list(rule.get("partials", []))           # (R_mult, frac) queue
    stop = init_stop
    pos = 1.0
    realized = 0.0                                       # in R units
    day_count = 0
    mfe_px = entry
    fills = []                                           # (day_idx, fraction) per slice

    for b in path:
        mfe_px = max(mfe_px, b["h"])
        # Phase 1 — day-0 aggressive intraday GIVEBACK trail (Pradeep): it only activates
        # ONCE THERE IS PROFIT TO PROTECT (gain >= +1R — "protect profit if it gaps/breaks
        # out fast"); before that the structural stop holds, so intraday noise
        # near entry can't stop you. After activation, never surrender more than `day0_giveback`
        # of the gain from the running intraday high → a fast spike-and-fade exits WITH profit;
        # a steady grinder never trips it (survives to phase 2). Only raises the stop.
        gb = rule.get("day0_giveback")
        if (gb is not None and b["kind"] == "min" and b["day_idx"] == 0
                and (mfe_px - entry) >= risk):                  # activate only once up >= +1R
            stop = max(stop, mfe_px - gb * (mfe_px - entry))
        if b["kind"] == "day":
            day_count += 1
            if rule.get("trail_prior_low") and b["prior_low"] is not None:
                stop = max(stop, b["prior_low"])
        # next partial target price (if any)
        tgt_px = entry + partials[0][0] * risk if partials else None
        hit_tgt = tgt_px is not None and b["h"] >= tgt_px
        hit_stop = b["l"] <= stop

        def take_partial():
            nonlocal pos, realized, partials, stop
            r_mult, frac = partials.pop(0)
            f = min(frac, pos)
            realized += f * r_mult                       # target fills AT target price
            pos -= f
            fills.append((b["day_idx"], f))
            if rule.get("breakeven_after_first"):
                stop = max(stop, entry)

        def take_stop():
            nonlocal pos, realized
            fill = min(stop, b["o"])                     # gap-through honesty
            realized += pos * (fill - entry) / risk
            fills.append((b["day_idx"], pos))
            pos = 0.0

        if hit_tgt and hit_stop:
            if bound == "opt":
                take_partial()
                if pos > 0 and b["l"] <= stop:           # stop may still hit after
                    take_stop()
            else:                                        # pessimistic: stop first
                take_stop()
        elif hit_tgt:
            take_partial()
        elif hit_stop:
            take_stop()

        if pos <= 0:
            break
        if rule.get("time_stop_days") and b["kind"] == "day" and day_count >= rule["time_stop_days"]:
            realized += pos * (b["c"] - entry) / risk    # force-exit at close
            fills.append((b["day_idx"], pos))
            pos = 0.0
            break

    if pos > 0:                                          # survived: exit at last close
        realized += pos * (path[-1]["c"] - entry) / risk
        fills.append((path[-1]["day_idx"], pos))
    captured = realized / ((mfe_px - entry) / risk) if mfe_px > entry else float("nan")
    return realized, captured, fills


def daily_path(bars, entry_idx, end_idx):
    """Build a daily-only `path` over (entry_idx, end_idx] for a close-entry harvest (the
    anticipation case — no day-0 minute resolution). `prior_low` seeds from the entry day's
    low and trails the previous completed daily bar; `day_idx` counts from 1."""
    path, prior_low = [], bars[entry_idx]["l"]
    for di, b in enumerate(bars[entry_idx + 1: end_idx + 1], start=1):
        path.append({"o": b["o"], "h": b["h"], "l": b["l"], "c": b["c"],
                     "kind": "day", "prior_low": prior_low, "day_idx": di})
        prior_low = b["l"]
    return path
