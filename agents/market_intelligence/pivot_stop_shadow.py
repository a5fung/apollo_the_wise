"""ADR 0031 C3 — the pivot-stop SHADOW on the live book (log-only; THE LINE intact).

For each CLOSED live trade, replay the exit ladder three ways over the trade's own daily bars —
identical prefix (partial/breakeven), only the TRAIL differing — and log the counterfactual:

  baseline — trail_mode='sma' (the live global trail)
  P1       — trail_mode='pivot_swing' (ratcheting CONFIRMED swing-low, bar-annotated by
             pivot_analysis.annotate_pivot_stops; close-below semantics — recorded deviation)
  P2       — trail_mode='character_ma' (home_MA × (1 − undercut_p80) from the per-ticker
             character profile) — SKIPPED when the profile ABSTAINS (first-class outcome)

All three replays ride the #445 driver (iter_exit_ladder) — no fifth loop copy (register R4).
Per-arm columns, never blended (ADR 0013 discipline). The profile snapshot is stored IN the row
(auditable/replayable; no standalone character table until a 2nd consumer — ADR 0031 §2).
mi_pivot_stop_shadow is seeded by db.initialize_schema. Gated review:
pivot_stop_shadow_review (≥10 settled non-abstained; the can't-0-row rule).

Sequencing gate (ADR 0031 §0, operator-signed F3): this shadow COEXISTS with the giveback
shadow (disjoint tables, both read-only counterfactuals); any LIVE flip queues strictly BEHIND
the giveback F1 resolution + N≥10 + the §5 tail-clip test + CHANGE_PROCESS.
"""
from __future__ import annotations

import json
import logging
from datetime import date

from agents.market_intelligence.db import get_pool, log_audit_event
from agents.market_intelligence.broker.exit_logic import iter_exit_ladder, seed_exit_state  # exec-boundary-ok: exit_logic is PURE exit-ladder math (no Alpaca client, no trade-state I/O) — the ADR 0031 shadow reuses the tested ladder + the #445 driver for its counterfactuals (same F11 pattern as the giveback shadow); pure compute, no live execution
from agents.market_intelligence.pivot_analysis import annotate_pivot_stops, character_profile

logger = logging.getLogger(__name__)

# #310 catch-up (fixes the silent same-day-round-trip drop): forward bars for a trade
# closed on day D don't exist until D+1's close is ingested (mi_daily_closes refreshes at
# 17:00 ET; this job runs at 17:42 ET) — the old exact `closed_at::date = today` WHERE meant
# a trade with zero forward bars on its own close day was looked at exactly ONCE, silently
# `continue`d, and NEVER revisited (measured: 7/7 same-day live closes since 2026-07-06, 0
# shadow rows; 2/2 overnight holds shadowed fine). This window instead re-scans recently
# -closed, not-yet-shadowed trades every run so they're picked up once bars accumulate. 45d
# is ~8x the 40-bar fwd-fetch cap in calendar days — comfortable headroom past weekends/
# holidays for any actively-listed ticker to clear _MIN_FWD_BARS.
_CATCHUP_LOOKBACK_DAYS = 45

# annotate_pivot_stops (pivot_analysis.py) drives confirmed_swing_lows(bars, k=2) by default:
# a fractal-low CANDIDATE only exists at index i where `k <= i < len(bars) - k`
# (pivot_analysis.py confirmed_swing_lows) — that range is EMPTY for len(bars) < 2k+1 = 5.
# Below 5 forward bars a confirmed P1 pivot stop is PROVABLY impossible (not just unlikely):
# pivot_stops is guaranteed all-None and the P1 arm degenerates to hard-stop-only,
# indistinguishable from baseline by construction — not a real counterfactual. 5 is the floor
# below which a replay is DEFERRED (left for a later run once more bars exist) rather than
# logged with a partial/garbage row. (A naive `trade_date >= alert_date` fetch — including
# the alert-day bar itself — would let a same-day trade "pass" this guard with exactly one
# bar; the ladder skips any day `<= alert_date` (exit_logic.apply_daily_exit_step), so that
# one bar never runs a real step and the replay mark-to-closes on it as if the trade "held to
# end" — do NOT do that. Forward bars stay strictly `trade_date > alert_date`.)
_MIN_FWD_BARS = 5

# Skip-reason enum for the `pivot_stop_shadow_skipped` audit event (#310 — replaces the old
# silent `continue`, the reason other tooling/telegram can filter the audit log on).
_SKIP_BAD_INPUTS = "bad_inputs"
_SKIP_INSUFFICIENT_BARS = "insufficient_forward_bars"


async def _log_skip(ticker: str, trade_id: int, reason: str, detail: str) -> None:
    """Audit a skipped trade instead of the old silent `continue` (#310). No row is written —
    the trade stays un-shadowed and is re-tried on the next run once the underlying condition
    (more forward bars) resolves. `reason` is one of the `_SKIP_*` enum tags above."""
    try:
        await log_audit_event(
            "pivot_stop_shadow_skipped",
            summary=f"{reason}: {ticker} trade {trade_id}",
            detail=detail)
    except Exception as _e:  # loud-ok: telemetry-of-telemetry, same as the error/logged emitters below
        logger.warning("pivot_stop_shadow skip-audit emit failed (non-fatal): %s", _e)


def _arm_replay(bars: list[dict], *, alert_date, entry_price, hard_stop, shares,
                trail_mode: str, profile: dict | None = None,
                pivot_stops: list | None = None) -> dict | None:
    """One counterfactual replay over the trade's own daily bars (post-alert-date bars only —
    the driver's alert_date semantics skip today<=alert_date). Returns exit R/date/MFE-capture."""
    risk = entry_price - hard_stop
    if risk <= 0 or shares <= 0 or not bars:
        return None
    state = seed_exit_state(alert_date=alert_date, entry_price=entry_price,
                            hard_stop=hard_stop, remaining_shares=shares)
    kw = {"trail_mode": trail_mode}
    if trail_mode == "character_ma":
        kw.update(character_ma_window=profile["home_window"],
                  character_ma_kind=profile["home_kind"],
                  character_undercut=profile["undercut_p80"])
    feed = []
    for i, b in enumerate(bars):
        bar = {"l": float(b["low_price"]), "c": float(b["close"])}
        if trail_mode == "pivot_swing" and pivot_stops is not None:
            bar["pivot_stop"] = pivot_stops[i]
        feed.append((b["trade_date"], bar))

    exit_date, exit_reason, last_step = None, "held_to_end", None
    for _i, day, step in iter_exit_ladder(state, feed):
        last_step = step
        if step.closed:
            exit_date, exit_reason = day, step.close_reason
            break
    if last_step is None:
        return None
    if exit_date is None:  # rode to the end of available bars — mark-to-last-close
        remaining = state["remaining_shares"]
        pnl = sum(e.get("pnl", 0) for e in state["exits"]) + \
            (float(bars[-1]["close"]) - entry_price) * remaining
    else:
        pnl = last_step.new_total_pnl
    risk_dollars = risk * shares
    mfe = max((float(b["high_price"]) - entry_price) for b in bars) * shares
    return {
        "exit_r": round(pnl / risk_dollars, 4),
        "exit_date": exit_date,
        "exit_reason": exit_reason,
        "capture_pct": round(pnl / mfe, 4) if mfe > 0 else None,
        "mfe_r": round(mfe / risk_dollars, 4),
    }


async def run_pivot_stop_shadow(today: date, *, signal_type: str = "magna53",
                                account_mode: str = "live") -> int:
    """Log the pivot-stop shadow for LIVE trades closed in the last _CATCHUP_LOOKBACK_DAYS
    days and not yet shadowed (#310 catch-up, not an exact `closed_at = today` match — a
    same-day round trip has zero forward bars on its own close day and must be revisited on
    a LATER run once bars accumulate). Idempotent: `mi_pivot_stop_shadow.trade_id` is the
    natural key (PRIMARY KEY) — the `NOT EXISTS` filter plus `ON CONFLICT (trade_id) DO
    NOTHING` on the insert together guarantee a re-run never double-inserts.
    Pure compute + DB/audit — no broker calls, no live-exit change. Returns rows logged."""
    pool = await get_pool()
    logged = 0
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT t.id, t.ticker, t.alert_date, t.account_mode, t.entry_price,
                   t.entry_shares, t.hard_stop
            FROM mi_live_trades t
            WHERE t.status = 'closed' AND t.signal_type = $1 AND t.account_mode = $2
              AND (t.closed_at AT TIME ZONE 'America/New_York')::date BETWEEN ($3::date - $4) AND $3
              AND NOT EXISTS (SELECT 1 FROM mi_pivot_stop_shadow p WHERE p.trade_id = t.id)
        """, signal_type, account_mode, today, _CATCHUP_LOOKBACK_DAYS)
        for r in rows:
            try:
                entry = float(r["entry_price"] or 0)
                hard_stop = float(r["hard_stop"] or 0)
                shares = float(r["entry_shares"] or 0)
                if entry <= 0 or hard_stop <= 0 or shares <= 0:
                    await _log_skip(r["ticker"], r["id"], _SKIP_BAD_INPUTS,
                                    f"entry={entry} hard_stop={hard_stop} shares={shares}")
                    continue
                # the trade's own forward bars (strictly AFTER alert_date — see _MIN_FWD_BARS
                # comment on why `>=` would be wrong here) — fetched first so an
                # insufficient-bars skip doesn't waste the 260-row history fetch below.
                fwd = [dict(b) for b in await conn.fetch("""
                    SELECT trade_date, high_price, low_price, close FROM mi_daily_closes
                    WHERE ticker=$1 AND trade_date > $2 ORDER BY trade_date LIMIT 40
                """, r["ticker"], r["alert_date"])]
                if len(fwd) < _MIN_FWD_BARS:
                    await _log_skip(r["ticker"], r["id"], _SKIP_INSUFFICIENT_BARS,
                                    f"{len(fwd)} fwd bar(s) since {r['alert_date']}, "
                                    f"need >={_MIN_FWD_BARS}")
                    continue
                hist = [dict(b) for b in await conn.fetch("""
                    SELECT trade_date, high_price, low_price, close FROM mi_daily_closes
                    WHERE ticker=$1 AND trade_date <= $2 ORDER BY trade_date DESC LIMIT 260
                """, r["ticker"], r["alert_date"])][::-1]

                profile = character_profile(hist)
                pivot_stops = annotate_pivot_stops(fwd)
                common = dict(alert_date=r["alert_date"], entry_price=entry,
                              hard_stop=hard_stop, shares=shares)
                base = _arm_replay(fwd, trail_mode="sma", **common)
                p1 = _arm_replay(fwd, trail_mode="pivot_swing", pivot_stops=pivot_stops, **common)
                p2 = (_arm_replay(fwd, trail_mode="character_ma", profile=profile, **common)
                      if profile else None)
                if base is None:
                    # only reachable via risk<=0 (hard_stop >= entry_price) — the earlier
                    # guard already ruled out empty bars / non-positive shares.
                    await _log_skip(r["ticker"], r["id"], _SKIP_BAD_INPUTS,
                                    f"non-positive risk: entry={entry} hard_stop={hard_stop}")
                    continue
                await conn.execute("""
                    INSERT INTO mi_pivot_stop_shadow
                        (trade_id, ticker, alert_date, account_mode,
                         baseline_exit_r, p1_exit_r, p1_exit_date, p2_exit_r, p2_exit_date,
                         mfe_r, baseline_capture_pct, p1_capture_pct, p2_capture_pct,
                         profile, abstained, abstain_reason)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14::jsonb,$15,$16)
                    ON CONFLICT (trade_id) DO NOTHING
                """, r["id"], r["ticker"], r["alert_date"], r["account_mode"],
                    base["exit_r"],
                    p1["exit_r"] if p1 else None, p1["exit_date"] if p1 else None,
                    p2["exit_r"] if p2 else None, p2["exit_date"] if p2 else None,
                    base["mfe_r"], base["capture_pct"],
                    p1["capture_pct"] if p1 else None,
                    p2["capture_pct"] if p2 else None,
                    profile,  # plain dict — the pool codec jsonb-encodes ONCE (#177/#287 class)
                    profile is None,
                    None if profile else "no_ma_cleared_respect_bar_or_lt_3_episodes")
                logged += 1
            except Exception as e:
                logger.error(f"pivot_stop_shadow: trade {r['id']} ({r['ticker']}) failed: {e}")
                try:
                    await log_audit_event(
                        "pivot_stop_shadow_error",
                        f"{r['ticker']} trade {r['id']}: {type(e).__name__}: {e}")
                except Exception:  # loud-ok: log_audit_event self-catches; logger.error above already fired
                    pass
    if logged:
        try:
            await log_audit_event(
                "pivot_stop_shadow_logged",
                summary=f"logged {logged} pivot-stop shadow row(s) for {today}")
        except Exception as _e:  # loud-ok: telemetry-of-telemetry; the shadow rows are already durable
            logger.warning("pivot_stop_shadow audit emit failed (non-fatal): %s", _e)
    return logged
