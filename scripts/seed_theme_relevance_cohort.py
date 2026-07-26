#!/usr/bin/env python3
"""#329 STEP-0 part 3 — seed the themeless-winner-INCLUSIVE theme-relevance label cohort
(mi_theme_relevance_cohort) for the operator's #368 ground-truth labeling.

WHY THIS COHORT SHAPE (operator 6/24, restated 7/26): the theme axis is ASYMMETRIC — boost
theme-as-driver, never penalize themeless — so its correctness has two failure sides, and the
label cohort must cover BOTH:
  • 'themed'           — every themed shadow row (the boost's only acting population): the
                         false-POSITIVE side ("we credited the theme but it wasn't the driver").
  • 'themeless_winner' — themeless rows whose SETTLED fwd_5d cleared the established +5% win
                         bar: the false-NEGATIVE / undiscovered-theme blind-spot side ("not
                         seeing a theme ≠ no theme exists — that is why the EP can feed back
                         into themes"). A themed-only cohort would be structurally blind to it.
Themeless NON-winners are deliberately not auto-enrolled (review-load — the operator feels the
COUNT; a control stratum is an operator add at #368 if wanted). The enrolment rule is the ONE
shared classify_label_stratum in theme_axis_shadow.py — deterministic + auditable, and the
numbers that justified each enrolment are persisted on the row (enrol_fwd_5d_pct /
enrol_n_sessions_5d) so the selection can be re-checked later.

LOOKAHEAD NOTE: forward outcomes select WHICH themeless rows get labeled — they are the
DEFINITION of this stratum ("winner"), not a feature of any attribution signal. The signals
themselves (mi_theme_axis_shadow) stay as-of-alert-date; labels/outcomes join at eval time.

IDEMPOTENT + LABEL-SAFE: upserts on (ticker, alert_date); the ON CONFLICT update is guarded by
`operator_label IS NULL`, so re-running (to top up as new rows accrue / outcomes settle) can
NEVER overwrite a row the operator has already labeled. Touches ONLY mi_theme_relevance_cohort
— never mi_ep_alerts / mi_themes / any grade or trade table (SHADOW).

Per THE LINE: committed RUNNABLE but NOT run against prod by the agent that wrote it — the
parent session runs it (needs the live DB pool, same runtime as the market agent).

Usage (inside apollo-market, which has the modules + DB):
  python scripts/seed_theme_relevance_cohort.py [--since-days N]            # DRY-RUN
  python scripts/seed_theme_relevance_cohort.py [--since-days N] --commit   # write
"""
from __future__ import annotations

import asyncio
import sys
from collections import Counter

from agents.market_intelligence.db import get_pool
from agents.market_intelligence.theme_axis_shadow import classify_label_stratum

# Shadow rows LEFT-joined to outcomes: themed rows enrol regardless of outcome (o.* may be
# NULL); themeless rows need a settled winning outcome to enrol (classify_label_stratum).
_SELECT_SQL = """
SELECT s.ticker, s.alert_date, s.themeless_flag, s.theme_name, s.grade,
       o.fwd_5d_pct, o.n_sessions_5d
FROM mi_theme_axis_shadow s
LEFT JOIN mi_ep_scan_outcomes o
       ON o.ticker = s.ticker AND o.scan_date = s.alert_date
WHERE s.alert_date >= CURRENT_DATE - $1::int
ORDER BY s.alert_date, s.ticker
"""

_UPSERT_SQL = """
INSERT INTO mi_theme_relevance_cohort
    (ticker, alert_date, stratum, enrol_fwd_5d_pct, enrol_n_sessions_5d)
VALUES ($1, $2, $3, $4, $5)
ON CONFLICT (ticker, alert_date) DO UPDATE SET
    stratum = EXCLUDED.stratum,
    enrol_fwd_5d_pct = EXCLUDED.enrol_fwd_5d_pct,
    enrol_n_sessions_5d = EXCLUDED.enrol_n_sessions_5d
WHERE mi_theme_relevance_cohort.operator_label IS NULL
"""


async def main() -> None:
    args = sys.argv[1:]
    since_days = 365  # the shadow table only reaches back to the #369 backfill (~May 2026)
    if "--since-days" in args:
        since_days = int(args[args.index("--since-days") + 1])
    commit = "--commit" in args

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(_SELECT_SQL, since_days)

        enrolments = []
        for r in rows:
            stratum = classify_label_stratum(
                r["themeless_flag"], r["fwd_5d_pct"], r["n_sessions_5d"])
            if stratum is None:
                continue
            enrolments.append((r, stratum))

        counts = Counter(stratum for _r, stratum in enrolments)
        print(f"{len(rows)} mi_theme_axis_shadow rows (last {since_days}d) -> "
              f"{len(enrolments)} enrolments: "
              f"{counts.get('themed', 0)} themed, "
              f"{counts.get('themeless_winner', 0)} themeless_winner "
              f"({len(rows) - len(enrolments)} not enrolled)")

        if not commit:
            print("\n--- DRY-RUN sample (first 10 per stratum; NO writes) ---")
            for want in ("themed", "themeless_winner"):
                shown = 0
                for r, stratum in enrolments:
                    if stratum != want or shown >= 10:
                        continue
                    fwd = (f"{r['fwd_5d_pct']:+.1f}%" if r["fwd_5d_pct"] is not None
                           else "unsettled")
                    print(f"  {r['alert_date']} {r['ticker']:6} {stratum:16} "
                          f"grade={r['grade'] or '-':8} "
                          f"theme={(r['theme_name'] or '-')[:22]:22} fwd_5d={fwd}")
                    shown += 1
            print(f"\n(total {len(enrolments)} rows would be upserted with --commit; "
                  "labeled rows are never overwritten)")
            return

        n = 0
        for r, stratum in enrolments:
            await conn.execute(
                _UPSERT_SQL,
                r["ticker"], r["alert_date"], stratum,
                r["fwd_5d_pct"], r["n_sessions_5d"],
            )
            n += 1
        print(f"\nseeded {n} rows into mi_theme_relevance_cohort "
              f"({counts.get('themed', 0)} themed / "
              f"{counts.get('themeless_winner', 0)} themeless_winner). "
              "Re-run any time to top up — operator-labeled rows are never overwritten.")


if __name__ == "__main__":
    asyncio.run(main())
