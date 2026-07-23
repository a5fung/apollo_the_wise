"""Tape Quality Score (TQS) — Stage-1 SHADOW annotation (#498, operator-authorized 2026-07-21).

FULL SSoT: `docs/design/tape_quality_score.md` (the metric, verdict rule R1, validation 6/6 on the
operator-labelled cases, rollout stages + guardrails). The math here is a FAITHFUL PORT of the
VALIDATED probe `scripts/probes/_tape_quality_step0.py::tape_quality` — do not "improve" it without
re-running the labelled-6 + cohort validation (tests/test_tape_quality.py pins probe↔module parity).

WHAT IT MEASURES (operator definition — quality = TIGHT, not trend direction): over the 20 sessions
STRICTLY BEFORE the alert (the EP/gap day is excluded by construction — a name is never penalised
for its own thrust), per-bar NTR (intraday range % = (high-low)/close*100, deliberately NOT gap-aware
TR) feeds spike/held/reversal counts + the 2nd-largest-bar ratio (bmr2). The discriminator is the
REVERSAL count, not bar size — a big bar that HOLDS is a legit thrust; big bars that reverse and
repeat = wide-and-loose "gap-and-crap" junk. Verdict rule R1:

    junk  = spike_rev >= 2 OR spike_ct >= 4 OR bmr2 >= 3.0
    watch = (not junk) AND (spike_rev == 1 OR spike_ct in {2,3} OR bmr2 >= 2.5)
    clean = otherwise ; unknown = < 15 live bars (NEVER junk — no penalty for missing data)

TELEMETRY-ONLY — THE HARD STAGE-1 CONSTRAINT (design §4, non-negotiable). TQS is a pure READ-ONLY
annotation computed AFTER the alert is fully graded: it MUST NOT block/skip an order, alter sizing,
demote/upgrade ep_score, change score_tier, or feed the grade/detection in ANY way. Mechanically:
  • `annotate_ep_alerts_tape_quality` is called as the LAST post-scan block in
    ep_detector.run_ep_scan — downstream of the floor score, the judge override, the composite
    authority, and _emit_grade_decision; every decision has settled before it runs.
  • It writes ONLY the mi_ep_alerts tape_* columns (db.update_ep_alert_tape_quality — the SET
    clause is pinned to tape_* by test) + the display-only `r["tape_quality"]` key, which only
    briefing.send_ep_alert reads (the TAPE line render). Nothing in grading/entry/sizing reads it.
  • Junk is a soft CHARACTER filter, never a trade signal (design §4a-C: the junk barbell's 78%
    fwd-5d win rate is untradeable with real stops — never chase junk, never gate on it here).
Any hard-gate/demote decision is Stage 4 = THE LINE (operator sign-off + Stage-3 backtest +
CHANGE_PROCESS) — never this module's authority.

Adopted guardrails (design §4a):
  • A. `unknown` (<15 live bars) renders "unseasoned", NOT "clean" — TQS never upgrades a raw
    IPO/SPAC; the existing base-age gates own the trade decision.
  • B. No lookahead: the spike-held give-back look stays WITHIN the pre-alert window (a spike on
    the last in-window bar falls back to close-position only); the score never reads the alert
    day or beyond.
  • UNIVERSAL: annotates every scored EP alert (all tiers), not just #331 — wide-and-loose is bad
    across ALL EP charts.

Distinct from `tape_features.py` (#299 — INTRADAY judge-payload features: OR÷ATR, premarket volume
curve, spread). This module is the DAILY-bar structure-tightness read; no overlap, no shared code.
"""
from __future__ import annotations

import logging
import statistics
from typing import Any

from agents.market_intelligence.db import (
    get_pool,
    get_tape_bars_asof,
    log_audit_event,
    update_ep_alert_tape_quality,
)

logger = logging.getLogger(__name__)

# ── Constants — VERBATIM from the validated probe (_tape_quality_step0.py) ────────────────
_WIN = 20               # sessions strictly BEFORE the alert (the EP/gap day never scores itself)
_SPIKE_K = 2.0          # a "spike" bar = NTR > K * median NTR
_HELD_CLOSE = 0.70      # close in outer 30% of its own range (in the bar's direction)
_GIVEBACK = 0.60        # a HELD bar keeps >= 40% of its range over the next 2 closes
_MIN_LIVE_BARS = 15     # < this -> 'unknown' (NEVER junk — no penalty for missing data)

_SPARK_BLOCKS = "▁▂▃▄▅▆▇█"  # 20-day NTR sparkline glyphs (min→▁ … max→█ within the window)


def _live(b: dict) -> bool:
    """A tradeable bar: positive volume, both extremes present, high > low, positive close.
    VERBATIM port of the probe's `_live` — liveness is filtered INSIDE the 20-session window
    (dead/NULL rows still occupy window slots, exactly as the cohort validation computed it)."""
    return (b["volume"] or 0) > 0 and b["high_price"] is not None and b["low_price"] is not None \
        and b["close"] and float(b["high_price"]) > float(b["low_price"]) and float(b["close"]) > 0


def tape_quality(bars: list[dict], alert_date: Any) -> dict[str, Any]:
    """Return the TQS dict for the 20 live sessions strictly before alert_date, or
    {'tier': 'unknown'}. VERBATIM port of the validated probe (see module docstring) —
    `bars` are mi_daily_closes-shaped dicts (trade_date, open_price, high_price, low_price,
    close, volume), ascending. Pure function — no I/O.

    Returned keys (computed tiers): tier ('tape_clean'|'tape_watch'|'tape_junk'), n, ntr_med,
    spike_ct, held, rev, bmr2, adr, whip. 'unknown' returns only {tier, n}."""
    pre = [b for b in bars if b["trade_date"] < alert_date]
    win = [b for b in pre[-_WIN:] if _live(b)]
    if len(win) < _MIN_LIVE_BARS:
        return {"tier": "unknown", "n": len(win)}
    ntr = [(float(b["high_price"]) - float(b["low_price"])) / float(b["close"]) * 100 for b in win]
    med = statistics.median(ntr)
    if med <= 0:
        return {"tier": "unknown", "n": len(win)}
    spike_idx = [i for i, v in enumerate(ntr) if v > _SPIKE_K * med]
    held = rev = 0
    for i in spike_idx:
        b = win[i]
        h, l, c, o = float(b["high_price"]), float(b["low_price"]), float(b["close"]), \
            (float(b["open_price"]) if b["open_price"] else float(b["close"]))
        rng = h - l
        up = c >= o
        close_pos = (c - l) / rng if up else (h - c) / rng      # near-extreme in the bar's direction
        # give-back over the next 2 closes (last-bar spike: close-position only) — the look stays
        # WITHIN the pre-alert window: no lookahead onto the alert day (design guardrail B).
        giveback = 0.0
        nxt = [float(win[j]["close"]) for j in (i + 1, i + 2) if j < len(win)]
        if nxt:
            adverse = min(nxt) if up else max(nxt)
            giveback = (c - adverse) / rng if up else (adverse - c) / rng
        if close_pos >= _HELD_CLOSE and giveback < _GIVEBACK:
            held += 1
        else:
            rev += 1
    srt = sorted(ntr, reverse=True)
    bmr2 = (srt[1] / med) if len(srt) > 1 else (srt[0] / med)
    junk = rev >= 2 or len(spike_idx) >= 4 or bmr2 >= 3.0
    watch = (not junk) and (rev == 1 or len(spike_idx) in (2, 3) or bmr2 >= 2.5)
    tier = "tape_junk" if junk else "tape_watch" if watch else "tape_clean"
    whip = 2 * rev + 0.5 * held + max(0.0, bmr2 - 1.5)
    return {"tier": tier, "n": len(win), "ntr_med": med, "spike_ct": len(spike_idx),
            "held": held, "rev": rev, "bmr2": bmr2, "adr": statistics.mean(ntr), "whip": whip}


def format_tape_line(tqs: "dict[str, Any] | None") -> str:
    """The `TAPE:` alert line — display-only. `unknown` renders "unseasoned", NEVER "clean"
    (design guardrail A: TQS must not upgrade a raw IPO; base-age gates own the trade) and
    never "junk" (no penalty for missing data). Empty string when there is nothing to show."""
    if not tqs or not tqs.get("tier"):
        return ""
    tier = tqs["tier"]
    if tier == "unknown":
        return (f"TAPE: *unseasoned* ({tqs.get('n', 0)} live bars < {_MIN_LIVE_BARS} — "
                "no tape read; base-age/IPO gates own the trade)")
    label = tier.replace("tape_", "")
    spike_ct = tqs.get("spike_ct", 0)
    return (
        f"TAPE: *{label}* · {spike_ct} spike{'' if spike_ct == 1 else 's'}"
        f" ({tqs.get('held', 0)}H/{tqs.get('rev', 0)}R)"
        f" · bmr2 {tqs.get('bmr2', 0.0):.1f} · ADR {tqs.get('adr', 0.0):.1f}%"
    )


def tape_sparkline(bars: list[dict], alert_date: Any) -> str:
    """20-day NTR sparkline over the SAME window selection as `tape_quality` (last 20 pre-alert
    slots, live bars only) — one block glyph per live bar, min-max normalised within the window
    (min NTR → ▁, max NTR → █; flat window → all ▁). Display-only context; the TAPE line carries
    the absolute numbers (bmr2 / ADR). Empty string when no live bars."""
    pre = [b for b in bars if b["trade_date"] < alert_date]
    win = [b for b in pre[-_WIN:] if _live(b)]
    if not win:
        return ""
    ntr = [(float(b["high_price"]) - float(b["low_price"])) / float(b["close"]) * 100 for b in win]
    lo, hi = min(ntr), max(ntr)
    span = hi - lo
    if span <= 1e-12:
        return _SPARK_BLOCKS[0] * len(ntr)
    top = len(_SPARK_BLOCKS) - 1
    return "".join(
        _SPARK_BLOCKS[min(top, int((v - lo) / span * len(_SPARK_BLOCKS)))] for v in ntr
    )


async def annotate_ep_alerts_tape_quality(results: list[dict]) -> None:
    """#498 Stage-1 SHADOW annotator — called as the LAST post-scan block in
    ep_detector.run_ep_scan, AFTER every grade decision has fully settled (floor → judge
    override → composite authority → _emit_grade_decision). UNIVERSAL: every scored alert row,
    all tiers (not #331- or HIGH-gated).

    TELEMETRY-ONLY (THE LINE — see module docstring): reads mi_daily_closes (strictly
    pre-alert bars, no lookahead), writes ONLY the mi_ep_alerts tape_* columns
    (db.update_ep_alert_tape_quality) + the display-only `r["tape_quality"]` key that
    briefing.send_ep_alert renders. It never reads or writes score_tier / ep_score / any
    grading, sizing, entry, or safeguard state. DB-first (the fire_axes discipline): `r` is
    only annotated after the row write succeeds, so the alert never renders a TAPE line the
    row lacks.

    NEVER raises; per-candidate failures are isolated (one bad ticker can't suppress the
    rest) and counted via a `tape_quality_shadow_failed` audit event."""
    if not results:
        return
    pool = await get_pool()
    async with pool.acquire() as conn:
        for r in results:
            try:
                ticker, alert_date = r.get("ticker"), r.get("alert_date")
                if not ticker or not alert_date:
                    continue
                bars = await get_tape_bars_asof(conn, ticker, alert_date)
                tqs = tape_quality(bars, alert_date)
                tqs["sparkline"] = tape_sparkline(bars, alert_date)
                # DB first, then the display mirror — the alert never shows what the row lacks.
                await update_ep_alert_tape_quality(conn, ticker, alert_date, tqs)
                r["tape_quality"] = tqs  # display-only key; nothing in grading/entry reads it
            except Exception as _e:
                logger.warning(f"tape-quality annotation failed for {r.get('ticker')}: {_e}")
                try:
                    await log_audit_event(
                        "tape_quality_shadow_failed",
                        f"{r.get('ticker')} {r.get('alert_date')}: {type(_e).__name__}: {_e}",
                    )
                except Exception:  # loud-ok: fallback-of-the-fallback — the audit call may
                    pass            # share the same DB outage; already logger.warning'd and
                                     # the scan must still proceed (SHADOW contract; mirrors
                                     # structure_axis_shadow's identical inner guard).
