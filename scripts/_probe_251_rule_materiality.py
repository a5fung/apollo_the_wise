"""#251 verify (READ-ONLY): old-vs-new extract_deal_value on real mi_ep_alerts rows.

Confirms the deal-context gates change behavior the right way on the live corpus:
earnings-name rows (KSS/PGY class) where the OLD logic grabbed a revenue figure
should now ABSTAIN (None -> judge owns materiality); genuine deal rows keep firing.

Run: docker exec apollo-market python /app/scripts/_probe_251_rule_materiality.py
No writes, no LLM calls, no trade state.
"""
import asyncio

from agents.market_intelligence.catalyst_materiality import (
    _DEAL_RE, _MULT, extract_deal_value,
)
from agents.market_intelligence.db import get_pool

HIGHLIGHT = {"KSS", "PGY"}  # the #251 observed false-'transformative' names


def _old_extract(text):
    """Pre-#251 behavior: bare MAX dollar figure, no context gates."""
    if not text:
        return None
    best = None
    for m in _DEAL_RE.finditer(text):
        raw = m.group(1).replace(",", "")
        try:
            val = float(raw)
        except ValueError:
            continue
        unit = (m.group(2) or "").lower()
        val *= _MULT.get(unit, 1.0)
        if not unit and val < 1000:
            continue
        if best is None or val > best:
            best = val
    return best


def _fmt(v):
    if v is None:
        return "abstain"
    return f"${v/1e9:.2f}B" if v >= 1e9 else f"${v/1e6:.1f}M"


async def main():
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT ticker, alert_date, catalyst, claude_analysis FROM mi_ep_alerts "
            "WHERE alert_date >= CURRENT_DATE - 45 AND catalyst IS NOT NULL "
            "ORDER BY alert_date, ticker"
        )
    n = changed = old_fired = new_fired = 0
    for r in rows:
        text = f"{r['catalyst'] or ''} {r['claude_analysis'] or ''}"
        old, new = _old_extract(text), extract_deal_value(text)
        n += 1
        old_fired += old is not None
        new_fired += new is not None
        mark = " <-- #251 target" if r["ticker"] in HIGHLIGHT else ""
        if old != new:
            changed += 1
            print(f"CHANGED {r['ticker']:6s} {r['alert_date']}  "
                  f"old={_fmt(old):>9s} -> new={_fmt(new):>9s}{mark}")
            print(f"        catalyst: {(r['catalyst'] or '')[:140]!r}")
        elif mark:
            print(f"same    {r['ticker']:6s} {r['alert_date']}  "
                  f"old={_fmt(old):>9s} -> new={_fmt(new):>9s}{mark}")
    print(f"\n{n} rows (45d) | deal-value fired: old {old_fired} -> new {new_fired} "
          f"| changed {changed}")
    print("PASS criterion: KSS/PGY rows show old=$X -> new=abstain; "
          "real deal rows (contract/acquisition language) unchanged.")


asyncio.run(main())
