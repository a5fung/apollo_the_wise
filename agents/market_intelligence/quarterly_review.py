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

Scripts run:
  - _b50_revenue_stage_threshold_backward_check.py
    (#50 — pre-revenue gate threshold; rolled back from $5M → $0.01)
  - _b53_atr_normalized_gap_backward_check.py
    (#53 — ATR-normalized gap scoring; verdict no-ship)
  - _b54_9m_day2_stop_atr_distribution.py
    (#54 — 9M Day 2 stop/ATR distribution; verdict no-ship at N<30)

Add scripts here as new backward checks are shipped. Each script must
be re-runnable with no required args, output to stdout, return clean
exit code.
"""
from __future__ import annotations

import asyncio
import logging
import subprocess
from datetime import datetime

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
    # News source quality (2026-05-21 #71/#72 trigger) — 90d view of
    # per-source coverage/density/attribution + drift detection. Surfaces
    # silent degradation in news sources (Polygon, Alpaca, yfinance,
    # Perplexity, Claude analysis). Loud-not-silent discipline.
    ("News source quality (90d)",
     "agents.market_intelligence.news_source_quality", ["quarterly"]),
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
    started_at = datetime.utcnow()
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
    elapsed = (datetime.utcnow() - started_at).total_seconds()
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
