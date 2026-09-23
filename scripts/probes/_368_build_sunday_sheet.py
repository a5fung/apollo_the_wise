#!/usr/bin/env python3
"""#368 — build the 44-row labelling sheet for the operator's Sunday sitting.

He set the labelling for this weekend (*"let's do it this weekend"*, 2026-09-10). His time should
go on JUDGEMENT, not on assembling rows, so this puts them in front of him in the SAME column shape
as the sheet he already completed in one go on 2026-08-03 — `docs/analysis/368_labeling_sheet.tsv`.

POPULATION: the 44 THEMED rows in `mi_theme_relevance_cohort` with no `operator_label`, alerts
2026-08-04 → 2026-09-08, enrolled under the CURRENT engine. The 136 unlabelled themeless winners
are deliberately NOT here: they guard the asymmetry (a direction, already supported at n=36), not
the magnitude, and including them would nearly double the sitting for no gain on the D2 question.

Read-only. Writes one TSV. The ingest side is `scripts/_368_ingest_labels.py --sheet <path>`.
"""
import asyncio
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agents.market_intelligence.db import get_pool   # noqa: E402

OUT = Path("docs/analysis/368_labeling_sheet_2026-09-13.tsv")

_SQL = """
    SELECT c.ticker, c.alert_date, c.stratum, c.enrol_fwd_5d_pct,
           a.judge_grade, a.catalyst_quality, a.catalyst_type,
           left(coalesce(a.catalyst, ''), 160) AS catalyst,
           t.theme_name
      FROM mi_theme_relevance_cohort c
      LEFT JOIN LATERAL (
          SELECT judge_grade, catalyst_quality, catalyst_type, catalyst
            FROM mi_ep_alerts e
           WHERE e.ticker = c.ticker AND e.alert_date = c.alert_date
           ORDER BY e.id DESC LIMIT 1
      ) a ON TRUE
      -- ⚠ READ THE THEME FROM THE SHADOW, NOT FROM mi_themes. The cohort's `stratum` was set at
      -- enrolment from `mi_theme_axis_shadow.themeless_flag`, so `mi_theme_axis_shadow.theme_name`
      -- IS the theme the engine credited on that alert. My first version re-derived it from
      -- mi_themes with a 7-day window and left 15 of the 44 rows showing "(no theme row within
      -- 7d)" — a third of the sheet asking him to judge a theme it did not show him. The source of
      -- the label must be the source of the stratum.
      LEFT JOIN LATERAL (
          SELECT s.theme_name, s.theme_name_7d
            FROM mi_theme_axis_shadow s
           WHERE s.ticker = c.ticker AND s.alert_date = c.alert_date
           ORDER BY s.id DESC LIMIT 1
      ) t ON TRUE
     WHERE c.operator_label IS NULL AND c.stratum = 'themed'
     ORDER BY c.alert_date, c.ticker
"""


async def main() -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(_SQL)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as fh:
        w = csv.writer(fh, delimiter="\t")
        w.writerow(["row", "stratum", "date", "ticker", "grade", "theme",
                    "fwd_5d_pct", "catalyst_type", "catalyst", "LABEL", "NOTE"])
        for i, r in enumerate(rows, 1):
            grade = r["judge_grade"] or r["catalyst_quality"] or "-"
            fwd = "" if r["enrol_fwd_5d_pct"] is None else f"{r['enrol_fwd_5d_pct']:.1f}"
            w.writerow([i, r["stratum"], r["alert_date"].isoformat(), r["ticker"], grade,
                        r["theme_name"] or r["theme_name_7d"] or "(engine credited no theme)", fwd,
                        r["catalyst_type"] or "-",
                        (r["catalyst"] or "(no catalyst on record)").replace("\t", " "),
                        "", ""])
    print(f"wrote {len(rows)} rows -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
