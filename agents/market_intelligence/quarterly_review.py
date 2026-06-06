"""Monthly methodology backward-check sweep (#62 + #77 regime-monitor).

2026-05-20 originally shipped as quarterly. 2026-05-22 converted to
monthly cadence after the Pradeep-quote backward check (#77) made the
regime-change framing explicit: backward checks are regime-shift
monitors, NOT methodology-tuning loops. Monthly gives faster signal
without inviting frequent tuning (sample-size discipline still applies
before any methodology ship).

Per user_quarterly_rule_review.md: rules-as-SSoT, anti-overfit; batch
N≥30 evidence, not single-case reactions. Monthly cadence + per-band
WR drift is the right "regime check" granularity.

Module name retained as `quarterly_review` for caller-compat; the
cadence moved monthly per the 2026-05-22 ship.

Scripts run: see `QUARTERLY_BACKWARD_CHECK_SCRIPTS` below — that list is
the SSoT (don't maintain a duplicate roster in this docstring; it drifts).

Add scripts there as new backward checks / methodology findings ship —
EVERY load-bearing finding gets an entry or it silently goes stale
unmeasured (feedback_methodology_insights_need_periodic_revalidation).
Each registered script MUST be re-runnable via `python -m <module>` with
no required args, output to stdout, and return a clean exit code.
"""
from __future__ import annotations

import asyncio
import logging
import subprocess
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


# Each entry: (display_label, module, extra_args).
# extra_args is appended to `python -m <module>` invocation.
# Monthly cadence as regime-check; methodology ship still requires
# per-script backward-check + sample-size discipline.
QUARTERLY_BACKWARD_CHECK_SCRIPTS = [
    ("Revenue-stage threshold (#50)",
     "scripts._b50_revenue_stage_threshold_backward_check", []),
    ("ATR-normalized gap scoring (#53)",
     "scripts._b53_atr_normalized_gap_backward_check", []),
    ("9M Day 2 stop/ATR distribution (#54)",
     "scripts._b54_9m_day2_stop_atr_distribution", []),
    # Pradeep "rallying-into-catalyst" bands (#77, added 2026-05-22).
    # Regime-shift monitor: which pre-20d-return bands have highest WR?
    # Pradeep claims sideways-into-catalyst (RKLB-class) is highest WR;
    # our 60d cohort shows the OPPOSITE for late-cycle bull regime.
    # Monthly cadence will catch the inversion if regime shifts.
    ("Pradeep rally bands (#77)",
     "scripts._b77_pradeep_neglect_backward_check", []),
    # Flag detector graduation evidence (#92, added 2026-05-23).
    # First evaluation 2026-05-23 showed inverted forward returns by
    # stage — WATCH < TIGHTENING < COILED < TRIGGERED with returns
    # DECREASING as stage advances. TRIGGERED N=5 settled 10d showed
    # 0% WR, -4.51% avg. Anti-graduation evidence; continue shadow.
    # Monthly re-run tracks evolution toward N>=30 settled TRIGGERED.
    # TIGHTENING bright-spot (+1.14% 10d / 24.4% WR) flagged for
    # separate alert-class surface consideration if cohort grows.
    ("Flag detector graduation (#92)",
     "scripts._b92_flag_detector_graduation_evidence", []),
    # M&A filter Path B FP-rate drift detection (#88, added 2026-05-23).
    # 2026-05-23 ship validated 2/2 TPs kept, 8/10 FPs blocked vs 13
    # historical cases. Monthly re-evaluation classifies post-ship
    # events to detect TP regression (Polygon insights API changes)
    # or new FP patterns (sympathy-merger reasoning bleed, direction-
    # blindness via descriptions per #90).
    ("M&A filter Path B FP-rate (#88)",
     "scripts._b88_mna_filter_path_b_fp_rate", []),
    # Intraday flag-break detector evidence (#94, added 2026-05-23).
    # Shadow-phase monthly re-evaluation. Tracks signal sustainment for
    # decision-gate at N>=10 settled breaks. Graduation to Phase 2
    # (operator-confirm entry) requires N>=10 + avg ret_10d >+3% +
    # WR>=35%. Per feedback_methodology_insights_need_periodic_revalidation.
    ("Intraday flag-break evidence (#94)",
     "scripts._b94_intraday_flag_break_evidence", []),
    # Decliner-band bounce signal deep-dive (#78, added 2026-05-23).
    # Sub-band analysis (-5/-10/-20 splits) + catalyst-quality breakdown.
    # 2026-05-23 first run: -10 to -20% sub-band is sweet spot (83% WR
    # N=6, +12.42% avg); deep -20%+ band is capitulation regime (no
    # bounce). Auto-refresh tracks signal strength as cohort grows
    # toward the N≥30 settled decision gate.
    ("Decliner band bounce signal (#78)",
     "scripts._b78_decliner_band_bounce_signal", []),
    # News source quality (2026-05-21 #71/#72 trigger) — 90d view of
    # per-source coverage/density/attribution + drift detection. Surfaces
    # silent degradation in news sources (Polygon, Alpaca, yfinance,
    # Perplexity, Claude analysis). Loud-not-silent discipline.
    ("News source quality (90d)",
     "agents.market_intelligence.news_source_quality", ["quarterly"]),
    # SIP-replay R cohort (#223, added 2026-06-06) — Gate-3 cutover
    # evidence. Re-runs the same-exit cross-check (synth-FILLED vs
    # synth-CANCELLED) so the IEX adverse-selection finding is re-measured
    # as the cohort grows / regime shifts, NOT a one-time 6/6 snapshot.
    # The TL;DR leads the stdout so the sweep summary carries the SELECTION
    # delta. Per feedback_methodology_insights_need_periodic_revalidation
    # (every methodology finding gets a script in this sweep or it goes stale).
    # Finding doc: docs/analysis/sip_replay_gate3_2026-06-06.md.
    ("SIP-replay R cohort / Gate-3 selection (#223)",
     "scripts.sip_replay_r_cohort", []),
    # ORB bar-1 wick-outlier backward check (#122, registered 2026-06-06).
    # Was orphaned — a load-bearing backward check that prints N + a
    # ship/insufficient verdict, accruing toward the N>=10 ship gate
    # (data-gated review orb_bar1_wick_outlier_persistence_filter, earliest
    # 2026-08-15). Monthly re-run tracks the cohort toward that gate so the
    # finding doesn't go stale unmeasured (same discipline as the rest).
    ("ORB bar-1 wick-outlier (#122)",
     "scripts.orb_wick_outlier_backwardcheck", []),
    # #197 cap+1 (game_changer) slot-admission SHADOW (registered 2026-06-06).
    # Observe-only tracker of policy (a): would a cap+1 admission of a
    # game_changer blocked by max_positions have paid? Accrues toward the N>=30
    # promotion gate. Read-only; live cap+1 needs sign-off + CHANGE_PROCESS.
    ("#197 cap+1 game_changer slot shadow",
     "scripts.shadow_cap_plus_one_197", []),
]


def _extract_summary_section(stdout: str, max_lines: int = 25) -> str:
    """Pull the band-level summary table out of a backward-check stdout.

    Each script prints a banner table around line ~50 with the per-band
    counts + win rates. We extract the table region by looking for
    'BAND' header or 'win rate' / 'WR' keywords and grab the surrounding
    block.
    """
    lines = stdout.splitlines()
    # Find the start of any 'BAND' table
    band_idx = None
    for i, line in enumerate(lines):
        if "BAND" in line and ("avg_5d" in line or "win" in line.lower()):
            band_idx = i
            break
    if band_idx is None:
        # Fallback: return first 25 non-empty lines
        out = [ln for ln in lines if ln.strip()][:max_lines]
        return "\n".join(out)
    # Grab from header + max_lines after
    end = min(band_idx + max_lines, len(lines))
    return "\n".join(lines[band_idx - 1 : end])


async def run_quarterly_sweep() -> dict:
    """Execute every registered backward-check script. Returns a dict
    with per-script outcome + an aggregated message ready for Telegram.

    Each script runs in a subprocess so a single failure doesn't abort
    the whole sweep. Output captured + truncated.
    """
    started_at = datetime.now(timezone.utc)
    results: list[dict] = []

    for entry in QUARTERLY_BACKWARD_CHECK_SCRIPTS:
        # Tuple shape: (label, module, extra_args). Pre-2026-05-21 entries
        # were 2-tuples; back-compat to 3rd element default to empty list.
        if len(entry) == 3:
            label, module, extra_args = entry
        else:
            label, module = entry
            extra_args = []
        logger.info(f"Quarterly sweep: running {module} {extra_args} ({label})")
        try:
            proc = await asyncio.to_thread(
                subprocess.run,
                ["python", "-m", module, *extra_args],
                capture_output=True,
                text=True,
                timeout=600,  # 10 min per script
            )
            results.append({
                "label": label,
                "module": module,
                "exit_code": proc.returncode,
                "stdout_summary": _extract_summary_section(proc.stdout),
                "stderr_tail": proc.stderr[-500:] if proc.stderr else "",
            })
        except Exception as e:
            results.append({
                "label": label,
                "module": module,
                "exit_code": -1,
                "stdout_summary": "",
                "stderr_tail": f"FAILED: {type(e).__name__}: {str(e)[:300]}",
            })

    # Aggregate into one Telegram digest
    elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
    lines = [
        f"📊 *Monthly backward-check sweep* — regime-shift monitor",
        f"_{started_at.strftime('%Y-%m-%d %H:%M')} UTC · "
        f"{len(results)} scripts · {elapsed:.0f}s_",
        "_Watch for band-level WR shifts vs prior month — that's the regime signal._",
        "",
    ]
    for r in results:
        ok = "✅" if r["exit_code"] == 0 else "🔴"
        lines.append(f"{ok} *{r['label']}*")
        if r["stdout_summary"]:
            # Wrap in code block for monospace rendering
            lines.append("```")
            lines.append(r["stdout_summary"][:1500])
            lines.append("```")
        if r["exit_code"] != 0 and r["stderr_tail"]:
            lines.append(f"_error: {r['stderr_tail'][:200]}_")
        lines.append("")

    lines.append("_Re-runnable on demand via `docker exec apollo-market "
                 "python -m agents.market_intelligence.quarterly_review`. "
                 "Re-calibration decisions still require backward-check "
                 "evidence + advisor review per quarterly-rule discipline._")

    return {
        "started_at": started_at.isoformat(),
        "elapsed_sec": elapsed,
        "results": results,
        "digest_message": "\n".join(lines),
    }


async def quarterly_backward_check_sweep_job():
    """Scheduler entry point — quarterly cron. Runs the sweep + sends
    digest. Wired in scheduler.py at quarter boundaries (1st of Feb,
    May, Aug, Nov, 8:00 AM ET).
    """
    from agents.market_intelligence.briefing import send_telegram_message
    from agents.market_intelligence.db import log_audit_event

    logger.info("Quarterly backward-check sweep starting...")
    try:
        result = await run_quarterly_sweep()
        await log_audit_event(
            "quarterly_backward_check_sweep",
            f"Completed in {result['elapsed_sec']:.0f}s · "
            f"{len(result['results'])} scripts",
        )
        await send_telegram_message(result["digest_message"])
        logger.info("Quarterly sweep digest sent")
    except Exception as e:
        logger.exception(f"Quarterly sweep failed: {e}")
        from core.notifications import notify_job_failure
        await notify_job_failure("quarterly_backward_check_sweep", str(e))


if __name__ == "__main__":
    # Direct invocation: run + print digest. Doesn't Telegram.
    result = asyncio.run(run_quarterly_sweep())
    print(result["digest_message"])
