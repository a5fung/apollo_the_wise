"""#302 — P6 replay-regression report (v0): the accruing LIVE R-distribution beside the
#268b calibration envelope.

WHAT THIS IS (and is NOT). `data_gated_reviews.yaml::kill_scale_bands_quarterly_review`
input (b) asks for "the P6 replay-regression weekly reports (divergence between accruing
replay and the calibration)" — it wants the comparison **data surfaced** for the operator's
quarterly judgment, NOT an automated divergence alert. So v0 SURFACES the live fingerprint
next to the calibration card and persists a snapshot; it does **not** verdict and does **not**
Telegram.

WHY NO AUTOMATED VERDICT (advisor 2026-06-19, `feedback_validate_metric_before_decision`):
comparing a small accruing live cohort to the #268b *full-year n=399* envelope dimension-by-
dimension is statistically invalid — the path stats (maxDD −24.1R, worst-streak 15) are
properties of a 399-trade path a short live cohort cannot reach for months (false comfort),
and per-trade expectancy at N≈20 has a huge CI given the 62%-stop / 13%-≥+3R shape (a
divergence flag would fire on noise). So we surface sample-size-invariant per-trade stats
(expectancy, win-rate, avg-win/avg-loss-R) with N shown, display maxDD/streak as raw running
counters (NOT "vs calibration"), and let the operator judge at the quarterly review once N
supports a valid statistic.

LIVE ONLY: paper's R-distribution IS the IEX selection artifact (the GATE-3 finding — paper
drops the fast clean-breakout winners), so comparing paper to the SIP-calibrated envelope
would surface large FALSE divergence that is just feed bias. Pre-launch the section honestly
reads "comparison begins at cutover" and shows the envelope as a reference card.

Reuses `kill_scale_bands.assemble_band_inputs` (the SAME live realized-R cohort the bands
read) + `current_losing_streak` + `CALIBRATION_ENVELOPE`. Folds into the Sunday weekly review
as a SECTION (consolidate-not-proliferate); on-demand via `scripts/replay_regression.py`.
"""
from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)


def compute_fingerprint(realized_rs) -> dict:
    """Per-trade stats + raw running path counters for a chronological (oldest→newest)
    realized-R list. Per-trade stats (expectancy, win-rate, avg-win/avg-loss-R) are
    sample-size-invariant → comparable to the calibration at any N. max_dd_r / worst_streak
    are PATH stats surfaced as raw counters only — a short cohort cannot reach a full-year
    path extreme, so they are never framed as 'vs calibration'."""
    from agents.market_intelligence.kill_scale_bands import current_losing_streak
    rs = [float(r) for r in realized_rs if r is not None]
    n = len(rs)
    if n == 0:
        return {"n": 0}
    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r <= 0]
    cum = peak = max_dd = 0.0
    worst_streak = run = 0
    for r in rs:
        cum += r
        peak = max(peak, cum)
        max_dd = max(max_dd, peak - cum)
        run = run + 1 if r <= 0 else 0
        worst_streak = max(worst_streak, run)
    return {
        "n": n,
        "expectancy_r": sum(rs) / n,
        "win_rate": len(wins) / n,
        "avg_win_r": sum(wins) / len(wins) if wins else 0.0,
        "avg_loss_r": sum(losses) / len(losses) if losses else 0.0,
        "max_dd_r": -max_dd,                       # expressed as a negative drawdown
        "worst_streak": worst_streak,
        "cur_streak": current_losing_streak(rs),   # published convention (r ≤ 0 = loss)
    }


_PERSISTED_KEYS = ("n", "expectancy_r", "win_rate", "avg_win_r", "avg_loss_r",
                   "max_dd_r", "worst_streak", "cur_streak")


def render_section(account_mode: str, fp: dict) -> list[str]:
    """Side-by-side digest lines: live fingerprint vs the #268b calibration card + caveats.
    SURFACES only — no verdict (pure: fingerprint dict → lines)."""
    from agents.market_intelligence.kill_scale_bands import CALIBRATION_ENVELOPE as env
    out = ["", f"*🔁 Replay-regression* ({account_mode} R-dist vs #268b calibration):"]
    if fp.get("n", 0) == 0:
        out.append(f"  live: comparison begins at cutover (0 {account_mode} closed trades)")
    else:
        out.append(
            f"  live (n={fp['n']}): exp {fp['expectancy_r']:+.2f}R · "
            f"win {fp['win_rate']*100:.0f}% · avgW {fp['avg_win_r']:+.2f}R · "
            f"avgL {fp['avg_loss_r']:+.2f}R · "
            f"[running maxDD {fp['max_dd_r']:.1f}R · streak {fp['cur_streak']}/{fp['worst_streak']}]")
    out.append(
        f"  calibration ({env['source']}): exp {env['expectancy_r']:+.2f}R · "
        f"win {env['win_rate']*100:.0f}% · "
        f"[path: maxDD {env['max_dd_r']:.1f}R · streak {env['worst_streak']} — full-year, "
        f"not comparable at low N]")
    out.append(
        "  ⓘ exp/win are per-trade (comparable); maxDD/streak are full-year PATH stats. "
        "live≠calibration can be STRUCTURAL (47% recall · IEX-1min-ORB · Lane-2 dark pre-6/26 "
        "· live fills SIP not IEX) — investigate, don't assume decay.")
    return out


async def assess_regression(account_mode: str = "live") -> dict:
    """One DB read → the live realized-R fingerprint (the SAME cohort the bands read)."""
    from agents.market_intelligence.kill_scale_bands import assemble_band_inputs
    inputs = await assemble_band_inputs(account_mode)
    return compute_fingerprint(inputs["realized_rs"])


async def regression_digest_section(account_mode: str = "live") -> list[str]:
    """Render-only section for the on-demand script / any caller that just wants the lines."""
    try:
        return render_section(account_mode, await assess_regression(account_mode))
    except Exception as e:  # noqa: BLE001
        return ["", f"_replay-regression unavailable: {e}_"]


async def run_replay_regression(account_mode: str = "live", *, persist: bool = True) -> dict:
    """Compute the fingerprint, render the section, and (only once LIVE trades exist) persist
    ONE `replay_regression_snapshot` audit row so the quarterly band review reads the accruing
    distribution over time. SURFACES only — no divergence verdict, no Telegram (the statistic
    isn't valid at low N; the operator judges at the quarterly review). Error-wrapped so it
    never breaks the Sunday digest chain. Returns {lines, fingerprint}."""
    try:
        fp = await assess_regression(account_mode)
        lines = render_section(account_mode, fp)
        if persist and fp.get("n", 0) > 0:
            from agents.market_intelligence.db import log_audit_event
            from agents.market_intelligence.kill_scale_bands import CALIBRATION_ENVELOPE
            await log_audit_event(
                "replay_regression_snapshot",
                f"{account_mode} live R-dist n={fp['n']} exp={fp['expectancy_r']:+.2f}R",
                json.dumps({"account_mode": account_mode,
                            **{k: fp[k] for k in _PERSISTED_KEYS},
                            "calibration_source": CALIBRATION_ENVELOPE["source"]}))
        return {"lines": lines, "fingerprint": fp}
    except Exception as e:  # noqa: BLE001 — telemetry must never break the Sunday digest
        logger.warning(f"run_replay_regression({account_mode}) skipped: {e}")
        return {"lines": ["", f"_replay-regression unavailable: {e}_"], "error": str(e)}
