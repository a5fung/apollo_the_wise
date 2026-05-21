"""Quarterly methodology backward-check sweep (#62, 2026-05-20).

Per user_quarterly_rule_review.md discipline: rules-as-SSoT + quarterly
review (NOT frequent tuning). Anti-overfit; batch N≥30 evidence, not
single-case reactions.

The quarterly sweep re-runs all backward-check scripts shipped by
backward-check work, captures their stdout, aggregates findings, and
sends one Telegram digest. Operator reviews the digest to spot drift
between quarters.

Cadence: every 90 days. Compatible with the existing data_gated_reviews
mechanism — that handles per-question specific-trigger reviews
(predicate_sql), this handles the systematic baseline sweep.

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


QUARTERLY_BACKWARD_CHECK_SCRIPTS = [
    ("Revenue-stage threshold (#50)",
     "scripts._b50_revenue_stage_threshold_backward_check"),
    ("ATR-normalized gap scoring (#53)",
     "scripts._b53_atr_normalized_gap_backward_check"),
    ("9M Day 2 stop/ATR distribution (#54)",
     "scripts._b54_9m_day2_stop_atr_distribution"),
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

    for label, module in QUARTERLY_BACKWARD_CHECK_SCRIPTS:
        logger.info(f"Quarterly sweep: running {module} ({label})")
        try:
            proc = await asyncio.to_thread(
                subprocess.run,
                ["python", "-m", module],
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
        f"📊 *Quarterly methodology backward-check sweep*",
        f"_{started_at.strftime('%Y-%m-%d %H:%M')} UTC · "
        f"{len(results)} scripts · {elapsed:.0f}s_",
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
