"""Volume-profile alert context — Slice 1 SHADOW annotation (operator-ruled 2026-07-24).

FULL SSoT: `docs/analysis/volume_profile_alert_context_2026-07-27.md` (the measured
distributions, metric definitions V1–V4, the render mocks, the noise budgets, the cost
analysis). The math here is a FAITHFUL PORT of the measured session probes (vp_measure.py /
vp_render.py — the cohort numbers and the doc's QBTS/ABSI mocks were computed with exactly
these definitions; QBTS 7/27 reproduces the operator's hand-read to the day and the ratio).
Do not "improve" the definitions without re-running the 221-alert cohort measurement.

WHAT IT SHOWS (the operator's 50d volume-profile frame — participation, a separate axis from
the TAPE/NTR range structure; QBTS 7/27 read *tape_clean* while volume said the crowd left a
month ago):
  • r5_50 (V1) — mean volume of the last 5 pre-alert sessions ÷ the 50d SMA ("5d avg 0.46×
    of 50d"). Orthogonal to the alert's existing numbers (corr vs gap −0.01, vs ep_score +0.02).
  • LAB50 (V2) — sessions since volume last closed ≥ its as-of-that-day 50d SMA, + that day's
    ratio ("last ≥avg vol day 22 sess ago (1.3×)"). Renders only at ≥3 sessions (18% of
    alerts — the doc's noise budget; 83% of alerts have one within 2 sessions).
  • VOL sparkline (V3) — last 20 pre-alert sessions' vol ÷ as-of-day 50d SMA on a FIXED
    0→2× scale (▁=0 · ~▄=1.0× · █=≥2×) — cross-stock comparable BY DESIGN, deliberately NOT
    min-max normalised like the NTR spark. Same window-selection code as the NTR spark so
    the two labeled rows column-align per session (the QBTS divergence read needs the pair).
  • Alert-day landmark (V4) — alert-day EOD volume ÷ max pre-alert volume over min(252,
    available) sessions; renders in the EOD EP recap, NOT the alert (doc §4: 128/196 alerts
    fire pre-9:45 where an "on pace" claim is premarket noise).

DEPTH HONESTY (non-negotiable — the store is ~13 months): every "highest in N" label states
the ACTUAL verified depth — "1y" ONLY at ≥252 pre-alert live sessions, else "#1 vol day in
Xmo"; below 50 live sessions everything renders `unseasoned` (no 50d base). NEVER a phrase
that implies all-time — "HVE"/"highest ever" is Slice 2's Polygon-verified claim, not ours.

TELEMETRY-ONLY — THE LINE (operator 7/24: "even if this doesn't affect how we trade (yet) it
gives me a view and allow us to collect this data"). This module is a pure READ-ONLY
annotation computed AFTER the alert is fully graded: it MUST NOT block/skip an order, alter
sizing, demote/upgrade ep_score, change score_tier, or feed the grade/detection in ANY way.
Mechanically:
  • `annotate_one_vol_profile` is driven per-candidate from the LAST post-scan block
    (tape_quality.annotate_ep_alerts_tape_quality's loop) on the SAME already-fetched bars —
    zero extra queries, and downstream of every settled decision, exactly like TQS.
  • It writes ONLY the mi_ep_alerts vol_* columns (db.update_ep_alert_vol_profile /
    update_ep_alert_vol_landmark — SET clauses pinned to vol_* by test) + the display-only
    `r["vol_profile"]` key, which only briefing.send_ep_alert reads (the VOL line + spark).
  • Any read of vol_* by grading/entry/sizing is out of scope and requires CHANGE_PROCESS +
    operator sign-off + backtest (doc §7 Q4: the hot-tape finding is nominal p≈0.03 at N≈210
    — telemetry-grade direction, NOT gate-grade evidence).

Failure discipline (the TQS contract, verbatim): never raises; per-candidate failures are
isolated (one bad ticker can't suppress the rest) and counted via `vol_profile_shadow_failed`
/ `vol_landmark_eod_failed` audit events; DB-first, so the alert never renders a line the
row lacks.

⚠ `_VOL_SPARK_WIN` is a SEPARATE display constant from the tape module's shared 20-session
window constant — equal (20) so the NTR/VOL rows column-align, but DECOUPLED: the tape
thresholds were validated at 20 and neither constant may silently move the other. This
module never references the tape constant (mechanically pinned in tests/test_vol_profile.py).
"""
from __future__ import annotations

import logging
from typing import Any

from agents.market_intelligence.db import (
    get_pool,
    get_tape_bars_asof,
    log_audit_event,
    update_ep_alert_vol_landmark,
    update_ep_alert_vol_profile,
)
# Shared glyphs + the NTR spark's liveness predicate — the VOL spark must select the
# IDENTICAL window (same slots, same live filter) or the two rows stop column-aligning.
from agents.market_intelligence.tape_quality import _SPARK_BLOCKS, _live

logger = logging.getLogger(__name__)

# ── Constants — the doc's measured definitions (§3) ───────────────────────────────────────
_VOL_SPARK_WIN = 20     # display-only; equals the tape window (20) so rows align — DECOUPLED name
_MIN_BASE_BARS = 50     # < this → 'unseasoned' — no 50d base (doc §2; 3/224 cohort alerts)
_R5_WIN = 5             # V1 numerator window
_LAB50_LOOKBACK = 260   # LAB50 walks back at most this many sessions (the measured probe's bound)
_LAB50_MIN_RENDER = 3   # segment renders only at ≥3 sessions (18% of alerts — noise budget)
_SPARK_CEIL = 2.0       # V3 fixed scale 0→2× (▁=0 · ~▄=1.0× · █=≥2×) — cross-stock comparable
_FULL_YEAR_BARS = 252   # a "1y" label requires ≥ this many pre-alert live sessions (doc §2)
_SESS_PER_MONTH = 21    # depth-honest label arithmetic ("#1 vol day in Xmo" = depth // 21)


def _vol_live(b: dict) -> bool:
    """A live session for the VOLUME series: positive volume + positive close — the doc §3
    convention the cohort was measured with. Deliberately looser than tape_quality._live
    (no high/low requirement): a volume print with missing extremes is still a
    participation data point."""
    return (b["volume"] or 0) > 0 and b["close"] and float(b["close"]) > 0


def vol_profile(bars: list[dict], alert_date: Any) -> dict[str, Any]:
    """Alert-time metrics V1 (r5_50) + V2 (LAB50) over the live sessions STRICTLY before
    alert_date (the alert day never scores itself — the TQS no-lookahead rule). FAITHFUL
    PORT of the measured probe (vp_measure.py::metrics — see module docstring). Pure
    function, no I/O. `bars` are mi_daily_closes-shaped dicts, ascending.

    Returns {hist_n} alone when <50 live pre-alert sessions ('unseasoned' — no 50d base),
    else {hist_n, r5_50, lab50, lab50_ratio}. lab50 is 0-based sessions since the last
    volume close ≥ its as-of-that-day trailing-50-INCLUSIVE SMA (the chart-overlay
    convention, stated once in the doc's appendix; 0 = the last pre-alert session itself);
    lab50 None with hist_n ≥ 50 = none found in the ~260-session lookback (a real extreme,
    not a failure)."""
    pre_live = [b for b in bars if b["trade_date"] < alert_date and _vol_live(b)]
    n = len(pre_live)
    out: dict[str, Any] = {"hist_n": n}
    if n < _MIN_BASE_BARS:
        return out
    vols = [float(b["volume"]) for b in pre_live]
    sma50_now = sum(vols[-_MIN_BASE_BARS:]) / float(_MIN_BASE_BARS)
    out["r5_50"] = (sum(vols[-_R5_WIN:]) / float(_R5_WIN)) / sma50_now
    lab = ratio = None
    for k in range(n - 1, max(_MIN_BASE_BARS - 2, n - _LAB50_LOOKBACK) - 1, -1):
        if k + 1 < _MIN_BASE_BARS:
            break  # no full 50-session base as of day k — stop, don't degrade the definition
        s = sum(vols[k - (_MIN_BASE_BARS - 1):k + 1]) / float(_MIN_BASE_BARS)
        if s and vols[k] >= s:
            lab = n - 1 - k          # 0 = the last pre-alert session itself
            ratio = vols[k] / s
            break
    out["lab50"] = lab
    out["lab50_ratio"] = ratio
    return out


def format_vol_line(vp: "dict[str, Any] | None") -> str:
    """The `VOL:` alert line — display-only, plain words (the 7/24 TAPE-line readability
    ruling). <50 live sessions renders "unseasoned" — never a silent junk value. The LAB50
    segment appears only at ≥3 sessions (noise budget) or, rarer still, when NO ≥avg volume
    day exists in the checkable lookback (stated with its honest depth). Empty string when
    there is nothing to show."""
    if not vp:
        return ""
    n = vp.get("hist_n", 0)
    if "r5_50" not in vp:
        return f"VOL: *unseasoned* ({n} sessions < {_MIN_BASE_BARS} — no 50d base)"
    line = f"VOL: 5d avg {vp['r5_50']:.2f}× of 50d"
    lab = vp.get("lab50")
    if lab is None:
        checkable = min(n - (_MIN_BASE_BARS - 1), _LAB50_LOOKBACK)
        line += f" · no ≥avg vol day in last {checkable} sess"
    elif lab >= _LAB50_MIN_RENDER:
        line += f" · last ≥avg vol day {lab} sess ago ({vp['lab50_ratio']:.1f}×)"
    return line


def vol_sparkline(bars: list[dict], alert_date: Any) -> str:
    """V3 — 20-day volume sparkline on a FIXED 0→2× scale: each session plots its volume ÷
    its as-of-that-day trailing-50-inclusive SMA (▁=0 · ~▄=1.0× · █=≥2×). Fixed scale is
    the point — the SAME ratio renders the SAME glyph on every stock (cross-stock
    comparable), unlike the min-max-normalised NTR spark (which stays exactly as validated).
    Window selection is IDENTICAL to tape_sparkline (last 20 pre-alert slots, tape-_live
    bars) so the labeled NTR/VOL rows column-align per session. Renders for whatever live
    bars exist (same as the NTR spark); empty string when none."""
    pre = [b for b in bars if b["trade_date"] < alert_date]
    win = [b for b in pre[-_VOL_SPARK_WIN:] if _live(b)]
    if not win:
        return ""
    pre_live = [b for b in pre if _vol_live(b)]
    vols = [float(b["volume"]) for b in pre_live]
    idx = {b["trade_date"]: i for i, b in enumerate(pre_live)}
    top = len(_SPARK_BLOCKS) - 1
    out = []
    for b in win:
        k = idx[b["trade_date"]]  # _live ⊆ _vol_live, so every window bar is in the series
        base = vols[max(0, k - (_MIN_BASE_BARS - 1)):k + 1]
        s = sum(base) / len(base)
        r = (float(b["volume"]) / s) if s else 0.0
        out.append(_SPARK_BLOCKS[min(top, int(r / _SPARK_CEIL * len(_SPARK_BLOCKS)))])
    return "".join(out)


def vol_landmark(bars: list[dict], alert_date: Any, alert_vol: "float | None") -> "dict[str, Any] | None":
    """V4 — the alert-day landmark, EOD truth: alert-day EOD volume ÷ max pre-alert volume
    over the last min(252, available) live sessions. Pure function; the caller supplies the
    EOD volume (snapshot) because mi_daily_closes gets today's row only in the nightly pull.
    Returns None when there is no alert-day volume or no pre-alert history."""
    if not alert_vol or float(alert_vol) <= 0:
        return None
    pre_live = [b for b in bars if b["trade_date"] < alert_date and _vol_live(b)]
    n = len(pre_live)
    if n == 0:
        return None
    vols = [float(b["volume"]) for b in pre_live]
    mx = max(vols[-_FULL_YEAR_BARS:])
    lm: dict[str, Any] = {
        "hist_n": n,
        "depth": min(n, _FULL_YEAR_BARS),
        "alert_vol": float(alert_vol),
        "vs_max": float(alert_vol) / mx if mx else None,
    }
    if n >= _MIN_BASE_BARS:
        lm["alert_r50"] = float(alert_vol) / (sum(vols[-_MIN_BASE_BARS:]) / float(_MIN_BASE_BARS))
    return lm


def _fmt_shares(v: float) -> str:
    if v >= 1e9:
        return f"{v / 1e9:.1f}B"
    if v >= 1e6:
        return f"{v / 1e6:.1f}M"
    return f"{v / 1e3:.0f}K"


def format_vol_landmark_line(ticker: str, lm: "dict[str, Any] | None") -> str:
    """The EOD-recap landmark line — fires only at ≥1.0× the pre-alert max (23% of alerts).
    DEPTH-HONEST BY CONSTRUCTION: "1y" only at ≥252 pre-alert live sessions, else the actual
    depth ("#1 vol day in 10mo"); <50 sessions renders "unseasoned" with NO superlative
    claim at all. NEVER any phrase implying all-time — "HVE"/"highest ever" is Slice 2's
    Polygon-verified label, not computable from a 13-month store (doc §2 verdict)."""
    if not lm or lm.get("vs_max") is None or lm["vs_max"] < 1.0:
        return ""
    vol_s = _fmt_shares(lm["alert_vol"])
    if lm["hist_n"] < _MIN_BASE_BARS:
        return (f"`{ticker}` vol {vol_s} — *unseasoned* ({lm['hist_n']} sessions < "
                f"{_MIN_BASE_BARS} — no landmark read)")
    depth = lm["depth"]
    span = "1y" if depth >= _FULL_YEAR_BARS else f"{depth // _SESS_PER_MONTH}mo"
    r50 = lm.get("alert_r50")
    r50_s = f", {r50:.1f}× 50d avg" if r50 else ""
    return (f"`{ticker}` vol {vol_s} — #1 vol day in {span} "
            f"({lm['vs_max']:.1f}× prior max{r50_s})")


async def annotate_one_vol_profile(conn: Any, r: dict, bars: list[dict]) -> None:
    """Per-candidate slice of the SHADOW annotation — driven from
    tape_quality.annotate_ep_alerts_tape_quality's loop on the bars it ALREADY fetched
    (zero extra queries; doc §6 Slice 1). TELEMETRY-ONLY (THE LINE — module docstring):
    writes ONLY the mi_ep_alerts vol_* columns + the display-only `r["vol_profile"]` key.
    DB-first: `r` is annotated only after the row write succeeds, so the alert never
    renders a VOL line the row lacks. NEVER raises — a failure here is isolated to this
    candidate and counted via a `vol_profile_shadow_failed` audit event."""
    try:
        ticker, alert_date = r.get("ticker"), r.get("alert_date")
        if not ticker or not alert_date or bars is None:
            return
        vp = vol_profile(bars, alert_date)
        vp["sparkline"] = vol_sparkline(bars, alert_date)
        # DB first, then the display mirror — the alert never shows what the row lacks.
        await update_ep_alert_vol_profile(conn, ticker, alert_date, vp)
        r["vol_profile"] = vp  # display-only key; nothing in grading/entry reads it
    except Exception as _e:
        logger.warning(f"vol-profile annotation failed for {r.get('ticker')}: {_e}")
        try:
            await log_audit_event(
                "vol_profile_shadow_failed",
                f"{r.get('ticker')} {r.get('alert_date')}: {type(_e).__name__}: {_e}",
            )
        except Exception:  # loud-ok: fallback-of-the-fallback — the audit call may share
            pass            # the same DB outage; already logger.warning'd and the scan
                            # must proceed (the tape_quality inner-guard contract).


async def eod_vol_landmark_pass(today: Any) -> list[str]:
    """V4 — the EOD landmark pass, called from the 16:10 EOD EP recap job (doc §4: 128/196
    alerts fire pre-9:45, where an "on pace for #1" claim would be premarket noise — the
    verdict belongs where EOD volume is exact). For each of today's live EP alerts (all
    tiers, deduped): alert-day EOD volume from the Polygon full-market snapshot
    (consolidated tape — ONE call for the whole batch; the IEX per-ticker feed undercounts
    and is never used here) ÷ max pre-alert volume from mi_daily_closes.

    Writes vol_alert_vs_max for EVERY computable alert (the telemetry accrual is the point
    — doc §6), DB-first, then returns the render lines for landmarks that fired (≥1.0×) for
    the recap to fold into the close digest. NEVER raises; [] on any failure, with
    `vol_landmark_eod_failed` audit events so an outage can't masquerade as a
    no-landmark day."""
    lines: list[str] = []
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            alerts = await conn.fetch(
                """SELECT DISTINCT ticker FROM mi_ep_alerts
                   WHERE alert_date = $1 AND COALESCE(source, 'live') = 'live'
                   ORDER BY ticker""",
                today,
            )
            if not alerts:
                return []
            from agents.market_intelligence.collector import get_snapshot_all
            snap = await get_snapshot_all()
            if not snap:
                await log_audit_event(
                    "vol_landmark_eod_failed",
                    f"{today}: snapshot fetch empty — landmark pass skipped for "
                    f"{len(alerts)} alert(s)",
                )
                return []
            for a in alerts:
                ticker = a["ticker"]
                try:
                    day = (snap.get(ticker) or {}).get("day") or {}
                    alert_vol = day.get("v")
                    if not alert_vol:
                        # Not in the snapshot (halted/delisted) — no claim, row stays NULL
                        # (honest "not computed"), and the batch continues.
                        continue
                    bars = await get_tape_bars_asof(conn, ticker, today)
                    lm = vol_landmark(bars, today, float(alert_vol))
                    if lm is None or lm.get("vs_max") is None:
                        continue
                    # DB first (the annotator discipline): telemetry row before any render.
                    await update_ep_alert_vol_landmark(conn, ticker, today, lm["vs_max"])
                    line = format_vol_landmark_line(ticker, lm)
                    if line:
                        lines.append(line)
                except Exception as _e:
                    logger.warning(f"vol-landmark EOD failed for {ticker}: {_e}")
                    try:
                        await log_audit_event(
                            "vol_landmark_eod_failed",
                            f"{ticker} {today}: {type(_e).__name__}: {_e}",
                        )
                    except Exception:  # loud-ok: fallback-of-the-fallback — same DB outage;
                        pass            # already logger.warning'd, the batch must continue.
    except Exception as _e:
        logger.warning(f"vol-landmark EOD pass failed: {_e}")
        try:
            await log_audit_event(
                "vol_landmark_eod_failed", f"{today}: {type(_e).__name__}: {_e}",
            )
        except Exception:  # loud-ok: fallback-of-the-fallback — the audit call may share
            pass            # the same outage; already logger.warning'd (recap must proceed).
    return lines
