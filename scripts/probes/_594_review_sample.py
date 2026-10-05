"""#594 — build the next chart REVIEW SAMPLE for the operator to rule on.

His loop (2026-08-25): *"chart read is WIP so we'll keep reviewing, feeding in charts, label,
evaluate, etc. until we find an edge in it."* I surface a sample, he rules, the rulings land in
`tests/fixtures/must_not_trade_charts.py` keyed on (ticker, DATE).

⚠ BALANCED BOTH WAYS, NEVER A LIST OF FAILURES. Sample #1's whole finding — *"looks like our
chart vision is spotting the opposite thing"* — was visible ONLY because both directions were
shown. A file that can only record rejections trains a filter that only knows how to reject.
  A. we said HIGH and it collapsed
  B. we scored it BELOW the bar and it ran

⚠ OUTCOMES COME FROM `mi_daily_closes`, NOT `mi_ep_missed_outcomes`. That table holds only
alerts we did NOT buy (its own docstring), so arm A — which is by definition alerts — is
partly invisible in it. Reading arm A there is what made three runs of the ranking review
report "zero big winners" on 2026-09-21. [[check-what-the-system-already-did]]

⚠ EVERY DATE MUST BE SETTLED at 20 sessions, so nothing shown is still open, and the gap on the
named date must be REAL. `NO_SETUP_ON_THIS_DATE` exists in the fixture because VEEE 2026-07-08
was shown as a "+354% we rejected" when it gapped 4.1% and closed DOWN 21% — the +354% belonged
to an unrelated event five sessions later. A forward return measured from a date's open will
happily attribute a later move to a date that had no setup.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Runs either from the repo or piped into the container over stdin, where __file__ is
# "<stdin>" and has no parents — hence the fallback rather than an IndexError.
try:
    _REPO = Path(__file__).resolve().parents[2]
except (NameError, IndexError):
    _REPO = Path("/app")
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from datetime import date
# The previous sample's window end (exclusive lower bound). Sample #1 ended 2026-08-08; sample #2
# (built 2026-09-21) ended 2026-08-22. Override: python _594_review_sample.py YYYY-MM-DD
SINCE = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1][:2] == "20" else date(2026, 8, 8)
SETTLE_SESSIONS = 20

# ⚠ A REAL EP DAY, checked on the DAILY BARS (2026-10-05, his "I want real potential EPs, not garbage to
# grade"): sample #3's first build showed CHRN 08-27 / AGX 09-03 / DG 08-27 as gap days because the ALERT's
# gap_pct is the price at scan time (pre-market or 09:50) vs the prior close — at the 09:30 open they were up
# only 4-6% and faded. Rule, stated before the run: OPEN >= GAP_MIN% above the prior session's close (the live
# MIN_GAP_PCT, 9) AND that day's volume >= VOL_MULT x the prior 20-session average.
GAP_MIN = 9.0
VOL_MULT = 3.0

_FWD = """
WITH src AS ({src}),
px AS (
    SELECT c.ticker, c.trade_date, c.open_price, c.close, c.volume,
           LAG(c.close) OVER w AS prev_close,
           AVG(c.volume) OVER (PARTITION BY c.ticker ORDER BY c.trade_date
                               ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING) AS avg_vol20,
           ROW_NUMBER() OVER w AS rn
      FROM mi_daily_closes c
     WHERE c.ticker IN (SELECT ticker FROM src)
    WINDOW w AS (PARTITION BY c.ticker ORDER BY c.trade_date)
),
base AS (
    SELECT s.ticker, s.d AS the_date, s.ep_score, s.cat, p.open_price AS day_open, p.rn,
           (p.open_price / p.prev_close - 1) * 100 AS open_gap, p.volume / NULLIF(p.avg_vol20, 0) AS vol_x
      FROM src s
      JOIN px p ON p.ticker = s.ticker AND p.trade_date = s.d
     WHERE p.open_price > 0 AND p.prev_close > 0
       AND (p.open_price / p.prev_close - 1) * 100 >= {gap_min}
       AND p.volume >= {vol_mult} * p.avg_vol20
)
SELECT b.ticker, b.the_date, ROUND(b.open_gap::numeric,1) AS gap, ROUND(b.vol_x::numeric,1) AS vol_x,
       ROUND(b.ep_score::numeric,1) AS score, b.cat,
       ROUND(((MAX(f.close) FILTER (WHERE f.rn = b.rn + {n}) / b.day_open) - 1) * 100) AS pct_20d
  FROM base b
  JOIN px f ON f.ticker = b.ticker AND f.rn BETWEEN b.rn + 1 AND b.rn + {n}
 GROUP BY b.ticker, b.the_date, b.open_gap, b.vol_x, b.ep_score, b.cat, b.day_open, b.rn
HAVING COUNT(*) = {n}
"""

# "We said HIGH" = a HIGH-tier alert row (MODERATE alerts are not the claim this arm tests), one row per
# (ticker, day) at the day's best score — a name can carry two alert rows (MRLN/NVTS/RUM did).
ARM_A = """SELECT a.ticker, a.alert_date AS d, MAX(a.gap_pct) AS gap_pct, MAX(a.ep_score) AS ep_score,
                  NULL::numeric AS ep_bar, MAX(COALESCE(a.catalyst_quality,'?')) AS cat
             FROM mi_ep_alerts a
            WHERE a.alert_date > $1::date AND a.alert_date <= CURRENT_DATE - 30
              AND a.score_tier = 'HIGH'
            GROUP BY a.ticker, a.alert_date"""

# ⚠ "BELOW THE BAR" = below the SKIP FLOOR of 50, not below the regime HIGH bar. Two reasons,
# both checked: (1) `ep_bar` is NULL on all 3,020 scan-log rows in the settled window — the
# column only starts being written later, so a `< ep_bar` filter silently returns NOTHING, which
# is how the first run of this probe produced an empty arm B; (2) the HIGH bar is
# regime-dependent (65-80, `ep_detector.py:3207`) while 50 is the fixed line under which a name
# is SKIPPED outright ("<50 = skip", ep_detector.py:32). Sample #1's arm B was built on exactly
# this line — its rows read "score 38 < 50", "score 43 < 50" — so the two samples stay
# comparable. Using a regime bar here would mix eras across the cohort.
ARM_B = """SELECT l.ticker, l.scan_date AS d, MAX(l.gap_pct) AS gap_pct,
                  MAX(l.ep_score) AS ep_score, NULL::numeric AS ep_bar,
                  MAX(COALESCE(l.catalyst_quality,'?')) AS cat
             FROM mi_ep_scan_log l
            WHERE l.scan_date > $1::date AND l.scan_date <= CURRENT_DATE - 30
              AND l.ep_score IS NOT NULL AND l.gap_pct >= 9
              -- ⚠ NEVER SHOW HIM A NAME WE ACTUALLY TOOK. Excluding alerts is not tidiness:
              -- the first run of this probe put MRNA 2026-08-19 in arm B as "we scored it below
              -- the bar and it ran +36%". We ALERTED it at 115.2 and BOUGHT it (trade 374). It
              -- had 37 ticks that day scoring 21.6 to 115.2, and `ORDER BY scan_time_et DESC`
              -- took the LAST one. [[check-what-the-system-already-did]]
              AND NOT EXISTS (SELECT 1 FROM mi_ep_alerts a
                               WHERE a.ticker = l.ticker AND a.alert_date = l.scan_date)
            GROUP BY l.ticker, l.scan_date
              -- The BEST score of the whole day, not a single tick. "We scored it below the bar"
              -- has to mean we never got it above — a name that peaked at 96 and drifted to 21
              -- was not rejected, it was taken.
            HAVING MAX(l.ep_score) < 50"""


async def main() -> None:
    from agents.market_intelligence.db import get_pool
    pool = await get_pool()
    async with pool.acquire() as c:
        a = await c.fetch(_FWD.format(src=ARM_A, n=SETTLE_SESSIONS, gap_min=GAP_MIN, vol_mult=VOL_MULT), SINCE)
        b = await c.fetch(_FWD.format(src=ARM_B, n=SETTLE_SESSIONS, gap_min=GAP_MIN, vol_mult=VOL_MULT), SINCE)

    # Top 15 per arm: the caller drops (ticker, date) pairs he has already ruled on, then shows five.
    a = sorted([r for r in a if r["pct_20d"] is not None], key=lambda r: r["pct_20d"])[:15]
    b = sorted([r for r in b if r["pct_20d"] is not None], key=lambda r: -r["pct_20d"])[:15]

    print(f"==== A. WE SAID HIGH AND IT FAILED — worst 15 (settled {SETTLE_SESSIONS} sessions) ====")
    print("ticker|alert_date|open_gap|vol_x|ep_score|cat|pct_20d")
    for r in a:
        print(f"{r['ticker']}|{r['the_date']}|{r['gap']}|{r['vol_x']}|{r['score']}|{r['cat']}|{r['pct_20d']}")
    print(f"\n==== B. WE SCORED IT BELOW THE BAR AND IT RAN — best 15 ====")
    print("ticker|scan_date|open_gap|vol_x|ep_score|cat|pct_20d")
    for r in b:
        print(f"{r['ticker']}|{r['the_date']}|{r['gap']}|{r['vol_x']}|{r['score']}|{r['cat']}|{r['pct_20d']}")

asyncio.run(main())
