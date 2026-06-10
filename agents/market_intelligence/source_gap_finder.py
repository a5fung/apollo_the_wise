"""#235 (Wave E) — the gap-discovery loop: unknown movers → where WAS it reported?

Closes the #210/#211 loop. The /unknownrate KPI counts real movers whose
catalyst we could NOT confirm from direct feeds; this pass takes that cohort
and asks ONE bounded Perplexity question per name: where was the cause first
published? The answer is a SOURCE-ONBOARDING recommendation for the operator
(press wire we don't ingest, SEC form type we skip, IR page, niche outlet) —
NEVER a grade input. This respects the LLM-judge-not-discoverer line: the
discovery here is about OUR FEED COVERAGE, and its output is telemetry + an
operator queue (memory feedback_catalyst_sourcing_direct_over_llm prescribes
exactly this: LLM finds WHERE it was reported → onboard that direct source).

Cadence: weekly (Sun 08:45 ET job), cap 8 names — bounded cost, and feeds the
Sunday review window. Audit: one `source_gap_candidate` row per finding
(dedup: a ticker+date already audited is not re-asked). Telegram digest only
when ≥1 actionable (non-covered, non-none) recommendation exists.
"""
from __future__ import annotations

import json
import logging
import re

logger = logging.getLogger(__name__)

_CAP = 8

# Feeds we already ingest — a gap-finder answer naming these is an
# extraction/timing gap (interesting, different fix), not a missing source.
_COVERED_FEEDS = ("benzinga", "sec ", "sec.gov", "edgar", "8-k", "6-k", "alpaca")

_GAP_PROMPT = (
    "On {date}, the stock {ticker} gapped {gap:+.1f}% on heavy volume. "
    "Identify the SPECIFIC news event that caused that move and WHERE it was "
    "FIRST published. Answer in EXACTLY this format (one line each):\n"
    "EVENT: <one sentence>\n"
    "FIRST_REPORTED: <newswire/publication/feed name, SEC form type, or company IR page>\n"
    "SOURCE_CLASS: <press_wire|sec_filing|ir_page|media_outlet|analyst_note|social|none_found>\n"
    "If you cannot identify a causal event, use SOURCE_CLASS: none_found."
)

_FIELD_RE = re.compile(
    r"EVENT:\s*(?P<event>.+?)\s*FIRST_REPORTED:\s*(?P<reported>.+?)\s*SOURCE_CLASS:\s*(?P<cls>[a-z_]+)",
    re.S | re.I,
)


def parse_gap_answer(text: str) -> dict | None:
    """Tolerant parse of the structured gap answer. None when unparseable or
    explicitly none_found — both are non-actionable. `covered` marks feeds we
    already ingest (extraction/timing gap, not a missing source)."""
    if not text:
        return None
    m = _FIELD_RE.search(text)
    if not m:
        return None
    cls = m.group("cls").strip().lower()
    if cls == "none_found":
        return None
    reported = m.group("reported").strip()[:120]
    return {
        "event": m.group("event").strip()[:200],
        "first_reported": reported,
        "source_class": cls,
        "covered": any(f in reported.lower() for f in _COVERED_FEEDS),
    }


async def run_source_gap_finder(days: int = 7) -> dict:
    """Weekly pass over the window's unknown cohort (the /unknownrate
    predicates). Returns {n_cohort, n_asked, n_found, findings}."""
    from agents.market_intelligence.collector import search_news_perplexity
    from agents.market_intelligence.db import get_pool, log_audit_event

    pool = await get_pool()
    async with pool.acquire() as conn:
        # Same two-era unknown predicates as /unknownrate (#211/#249), minus
        # rows a prior run already adjudicated (dedup via audit detail JSON).
        rows = await conn.fetch("""
            SELECT a.ticker, a.alert_date, a.gap_pct
            FROM mi_ep_alerts a
            WHERE a.alert_date >= current_date - ($1)::int
              AND (a.catalyst_type = 'unknown'
                   OR a.fire_status IN ('unknown','pre_catalyst_anticipation',
                                        'no_fire_confirmed','real_unknown')
                   OR a.fire_axes = '{}'
                   OR a.catalyst ILIKE '%no clear%catalyst%'
                   OR a.catalyst ILIKE '%no specific news%')
              AND NOT EXISTS (
                  SELECT 1 FROM mi_audit_log g
                  WHERE g.event_type = 'source_gap_candidate'
                    AND g.detail LIKE '%"' || a.ticker || '"%'
                    AND g.detail LIKE '%"' || a.alert_date::text || '"%'
              )
            ORDER BY a.alert_date DESC
            LIMIT $2
        """, days, _CAP)

    findings = []
    n_asked = 0
    for r in rows:
        n_asked += 1
        answer = await search_news_perplexity(
            _GAP_PROMPT.format(date=r["alert_date"], ticker=r["ticker"],
                               gap=float(r["gap_pct"] or 0)),
            recency="month",
        )
        parsed = parse_gap_answer(answer)
        payload = {
            "ticker": r["ticker"], "alert_date": str(r["alert_date"]),
            "gap_pct": float(r["gap_pct"] or 0),
            "finding": parsed,  # None = adjudicated, nothing found
            # feedback_silent_failures: keep the raw head so a persistent
            # parse failure (vs a real none_found) is diagnosable from audit.
            "raw_head": (answer or "")[:300],
        }
        await log_audit_event(
            "source_gap_candidate",
            (f"{r['ticker']} {r['alert_date']}: "
             + (f"{parsed['source_class']} — {parsed['first_reported']}"
                if parsed else "none_found")),
            json.dumps(payload),
        )
        if parsed:
            findings.append({**payload, **parsed})

    actionable = [f for f in findings if not f["covered"]]
    if actionable:
        from agents.market_intelligence.briefing import send_telegram_message
        lines = ["🧭 *Source-gap finder* (weekly — #235/#211)",
                 "_Real movers we couldn't source from direct feeds; where they WERE reported:_"]
        for f in actionable:
            lines.append(
                f"\n`{f['ticker']}` {f['alert_date']} ({f['gap_pct']:+.1f}%)\n"
                f"  {f['source_class']}: *{f['first_reported']}*\n"
                f"  _{f['event']}_"
            )
        covered_n = len(findings) - len(actionable)
        if covered_n:
            lines.append(f"\n_+{covered_n} covered-feed finding(s) (extraction/timing gap) — audit only._")
        lines.append("\n_Onboard-or-skip is your call (#210: direct sources > LLM discovery). Telemetry only — grades untouched._")
        await send_telegram_message("\n".join(lines))

    return {"n_cohort": len(rows), "n_asked": n_asked,
            "n_found": len(findings), "findings": findings}
