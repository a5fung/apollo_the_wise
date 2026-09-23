# #594 step 0 — sample #2 scored: the run-up rule catches none of the four new bad charts

**MEASUREMENT ONLY. Nothing was changed, proposed or tuned.** Same code as the 2026-09-21 run
(`scripts/probes/_structure_read_v3.py::score_against_operator_rulings`, one pre-declared rule,
ANCHOR-75 = `runup_low_pct_20 >= 75.0`, his own signed number). His labels are ground truth here,
never scored themselves.

**The one-sentence change vs 09-21: coverage of his condemned charts fell again, 53% → 43%,
because all four of the new BAD_CHART rulings (RARE, BW, LPTH, FRMI) run through this rule
clean — their 20-session run-up sits between 9% and 41%, nowhere near the 75% cutline — while
every one of his six new approved charts also stays clean, so RULE 0 and the must-not-reject
column are still perfect.**

## Method and population

⚠ **Reconstructed, not reused.** The 09-21 session's own SQL/driver script was not committed to
the repo (it lived in that session's scratchpad, which this session does not have). The scored
CODE is unchanged — `_structure_read_v3.py` and `score_against_operator_rulings` are the exact
committed 09-21 functions (commit `ca57cb1a`), called with no new arguments. Only the bar-fetch
driver (`read_for`) was rebuilt here, following the 09-21 doc's own description: daily bars from
prod `mi_daily_closes`, prior bars + the alert-day open into `structure_read_v3`.

**Prod pull, once, to a file:** `SELECT ... FROM mi_daily_closes WHERE ticker IN (62 tickers) ORDER
BY ticker, trade_date` over SSH into `apollo-postgres`, saved to
`scratchpad/594rescore/bars.psv` (16,846 rows, Aug 2025 – Sep 2026, whatever the table holds for
each name). Everything below is computed locally from that one file — no second prod query.

**Populations, all derived from the fixtures, not hand-listed:**

| population | 09-21 n | 09-23 n | what grew it |
|---|---|---|---|
| real EPs (the RULE 0 bar) | 30 | **30** | unchanged — no new `must_not_miss_eps.py` members |
| his must-NOT-reject dates | 3 | **9** | +6: the six OK/GOOD rulings from sample #2 (WYFI, AVAH, NIQ, TBBB, MRVI, HAE) |
| dates he condemned (BAD_CHART) | 17 | **21** | +4: RARE, BW, LPTH, FRMI |
| dates he only POINTED AT | 3 | 3 | unchanged |
| distinct tickers named | 52 | **62** | +10, exactly the ten new rulings |

Every date read cleanly — **0 of 66 rows across all five populations (30 real EPs + 3 excluded +
9 must-not-reject + 21 condemned + 3 pointed-at) came back unreadable.**

⚠ **The bars only reach back to ~2025-08 — whatever `mi_daily_closes` currently holds for these
tickers, nothing further.** That does not touch the four-row table below: `runup_low_pct_20`
needs 20 prior sessions and `extension_live_pct` needs 10 calendar days, both comfortably inside
that window. It DOES mean the multi-year criteria he named on 09-06 — an Oct-2025 double top, a
2022 base — are outside every number this read produces, RARE's "stuck in multi year downtrend"
included. See the parity check below and "What this does not answer."

## The result

| direction | 2026-09-21 | 2026-09-23 |
|---|---|---|
| **real EPs wrongly rejected (RULE 0)** | 0 of 30 | **0 of 30** |
| **his must-NOT-reject dates lost** | 0 of 3 | **0 of 9** |
| dates he condemned, rejected | 9 of 17 (53%) | **9 of 21 (43%)** |
| pointed-at dates rejected (a flag, not a miss) | 1 of 3 — MXL 2026-04-24 | **1 of 3 — MXL 2026-04-24** |

RULE 0 stays clean, every date he has ever approved still survives, and the pointed-at flag is
unchanged. The only row that moved is the condemned-charts count, and it moved because the
numerator held at 9 while the denominator grew by 4 — **none of the four new bad-chart rulings
register as extended on this rule at all.**

### The ten new rulings — descriptive only, no cutline search

| ticker | date | his verdict | his words (short) | ANCHOR-75 | v2 label | overhead vol. above open | zones still overhead |
|---|---|---|---|---|---|---|---|
| RARE | 2026-08-20 | bad | "stuck in multi year downtrend... didn't clear any of these areas" | KEEP | IFFY_AT_FIRST_ZONE | 37% | 12 |
| BW | 2026-08-11 | bad | "gap up weak, didn't clear much of left side, still below 50d" | KEEP | INTO_SUPPLY | 37% | 9 |
| LPTH | 2026-08-14 | bad | "don't see a gap up, just chopping in range" | KEEP | INTO_SUPPLY | 17% | 6 |
| FRMI | 2026-08-11 | bad | "didn't clear anything on left side of chart" | KEEP | INTO_SUPPLY | 47% | 16 |
| WYFI | 2026-08-12 | ok | "gap up ok, but not super strong, didn't clear local highs in may nor 50d" | KEEP | IFFY_AT_FIRST_ZONE | 38% | 11 |
| NIQ | 2026-08-11 | ok | "looks decent, cleared low of basing area into previous highs area, could see resistance" | KEEP | INTO_SUPPLY | 40% | 9 |
| MRVI | 2026-08-19 | ok | "decent but bumping into recent highs so can see resistance" | KEEP | LADDER_CLIMBING | 6% | 2 |
| AVAH | 2026-08-13 | good | "cleared highs, long base, looks amazing" | KEEP | INTO_SUPPLY | 0.5% | 1 |
| TBBB | 2026-08-13 | good | "good" | KEEP | CLEAR_AIR | 0% | 0 |
| HAE | 2026-08-18 | good | "good" | KEEP | CLEAR_AIR | 0% | 0 |

"ANCHOR-75 KEEP" means the rule does NOT reject that date (`runup_low_pct_20 < 75.0` — none of
these ten ever got close; the highest was LPTH at 41%). No row was unreadable.

**What this means in plain terms:** the run-up rule keeps all six of his newly-approved charts,
correctly, and has nothing to say about any of the four new bad ones — it doesn't wrongly clear
them by accident, it simply never gets close to its 75% trigger on any of the ten. The reason the
four bad charts are bad is a different measure than run-up: all four read `INTO_SUPPLY` or
`IFFY_AT_FIRST_ZONE` on the existing supply-ladder field (9–16 zones still overhead), which is the
"didn't clear the left side of the chart" complaint in his own words, just not the one this rule
tests.

### Parity check — this reconstruction against numbers already stored in the fixture

The 09-21 session's own driver script is gone, so the strongest available check is this: 14 older
`ChartRuling` members carry `v2_label` / `v2_overhead_vol_frac` / `v2_zones_remaining` /
`extension_live_pct`, captured from an earlier run of this same probe. Re-running `read_for`
against today's prod pull and comparing:

| field | matched | where it drifted |
|---|---|---|
| `label` | **14 of 14** | none |
| `extension_live_pct` (10-calendar-day window) | **14 of 14** | none |
| `overhead_vol_frac` (full history) | 13 of 14 | CAR 2026-04-01: 0.317 now vs 0.429 stored |
| `zones_remaining` (full history) | 12 of 14 | CAR 2026-04-01 (9 vs 13), VEEE 2026-07-08 (29 vs 30) |

`label` and `extension_live_pct` never drift — both are exactly what the four-row headline and
the ten-row table's ANCHOR-75 column depend on. The two fields that DO drift, `overhead_vol_frac`
and `zones_remaining`, are the ones `supply_ladder` computes over the WHOLE bar list rather than a
fixed window — consistent with the caveat above that today's prod pull may not reach as far back
as whatever capture produced those stored numbers. The drift is small (one ticker of fourteen, one
zone-count off by one on a second) and does not touch anything in the four-row or ten-row tables,
but it is the honest reason those two v2 fields in the ten-row table above should be read as "what
the read currently sees," not as a value guaranteed stable against a longer history.

## What this does not answer

- **Whether the read has an edge.** Same as 09-21 — the 2026-08-25 backtest found the supply read
  a null winner predictor and nothing here changes that. This measures agreement with his labels,
  a different question.
- **Whether 43% is good or bad, or worse than 53%.** There is no baseline for what fraction of his
  rejects any single rule should catch, and at n=21 a difference of one chart moves it 5 points.
  The fixture forbids searching for a better cutline at this n, and no cutline other than his own
  75 was run here.
- **Why the run-up rule misses RARE/BW/LPTH/FRMI.** The per-row v2 fields above show WHAT the
  supply read already sees in all four (overhead volume, zones remaining) — that is a different
  measure than run-up and not tested against a bar here, only reported as data.
- **Whether the multi-year criteria he actually cited (an Oct-2025 double top, a 2022 base) hold
  up.** The bars this read has only go back to ~2025-08; nothing here can see further than that,
  including RARE's own "multi year downtrend."
