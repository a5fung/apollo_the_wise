# #94 intraday flag-break detector — N≥10 graduation read (2026-09-15)

**Review:** `data_gated_reviews.yaml::intraday_flag_break_signal_n10` (ADR 0005 Phase 2 gate).
**Verdict the review's OWN gate fires: SIGNAL WEAK → bucket 2, REVISE before Phase 2.**
Runner output (verbatim, `scripts/_b94_intraday_flag_break_evidence.py`, run 2026-09-15 on prod, read-only):
N=163 settled, avg 10d **−0.95%**, 48/163 (**29.4%**) reached +5% at 10d. Gate 2 requires `WR<25% OR avg<0`; avg<0 fires it.

**⚖ THE LINE.** Nothing was flipped. Graduating this detector to an entry, or revising its criteria, is the operator's
decision (CHANGE_PROCESS applies to every item on the revise menu). EP-first priority stands
(`priority-ep-profitability-before-new-setups`): no gate here says PROMOTE, so there is no collision to route — but
sequencing even a revise sits behind #508.

## The decision this serves

Whether the intraday flag-break detector graduates from telemetry to an operator-confirm entry (`/flagbreak ENTER`).
What would change it: N≥10 with avg 10d ≥ +3% AND ≥35% of breaks up 5%+ at 10d (the gate's PROMOTE line). Neither
holds on any cut below.

## Population

- **Source rows:** `mi_flag_breaks`, all 168 rows ever (2026-05-26 → 2026-09-14, 119 tickers), joined to
  `mi_daily_closes` for the break-day open/close and the next 5/10/20 trading closes, highs and lows.
  Dumped once to `/tmp/gated3/breaks_raw.csv`; every number here is computed locally from that file.
- **Gate population (the predicate, verbatim):** `break_date ≤ today−12d`, `parent_invalidated_eod = FALSE`, 10th
  forward close present → **n=163** rows, 115 tickers. 5 survivors are not yet settled (PBF 09-01, PBF 09-02, WDAY
  09-03, XHLD 09-09, IOVA 09-14).
- **Entry proxy:** the gate and runner use the **break-day OPEN**. The realistic operator-confirm fill is
  `break_price` (the detection price); it sits a median **+2.6%** ABOVE that open (mean +3.1%), because the open
  precedes the break. Both are reported. `pct_above_base_high` at detection: median 1.4%, 33% of fires under 0.5%.
- **⚠ ERA — the parent universe was rebuilt on 2026-06-27** (#356: `flag_detector` swapped from the n=1 50%/60d
  flag to the sourced HTF 90%/40d spec + Stage-2 trend + 6/28 liquidity floors). The intraday detector's own gates
  did not change, but the names it scans did: the parent's actionable roster fell from ~1,000/month (May–Jun) to
  ~65/month (Jul–Sep). Fires dropped from 152 to 17. **Era A = fires ≤ 06-26 (retired parent); Era B = fires ≥ 06-29
  (current parent).** The pooled gate number is 93% Era A. Any promotion decision concerns Era B.
- **Same-day invalidation filter is a no-op here, by construction.** `reconcile_flag_state_post_eod` flips
  `parent_invalidated_eod` only when the parent is classified INVALIDATED at the SAME day's 17:25 scan. A name that
  broke above `base_high` intraday almost never closes below the base's lowest close (or, since 6/27, below the 50d)
  that same day — 0 of 168 breaks ever were flagged. The filter therefore cannot discriminate for this table; a
  broken reconcile job would read identically. (It does act on the sibling tables — 122/529 pullbacks, 44/68 tests.)
- **Independence:** 43 of 168 rows re-fire within 10 days of a prior fire on the same ticker; first-fire-per-campaign
  n = 124 (111 settled Era A, 9 Era B). Shown beside raw n.
- **What the system already did on those dates:** 4 breaks coincided with an EP alert, 1 with a live-trade alert date.
  **All 17 Era B breaks are also rows in `mi_htf_breakout_shadow`** (#356 Phase 3 — the HTF breakout-entry shadow
  with its own 3R settlement) because the #94 scan writes that row itself; 0 of 151 Era A breaks are (table shipped
  06-28). See §Supersession.
- **Data artifacts excluded from the break_price and R reads:** CRWD 2026-07-01 — detection price 781.50 on
  pre-split shares, stored closes 193.19 on 4:1-adjusted shares; base_low 617.74 exceeds every stored close. Kept in
  the runner's verbatim N=163 (its open→close read is internally consistent); dropped where the two bases mix.
- **Footnotes:** 39 rows (05-26/27) predate the #145 idempotency guard (already-broken names could re-fire);
  1 row (08-04) read a stale 07-31 parent scan (08-03 dark day, #522). `base_low` is populated on all 168.
- Era of the exit side: forward returns are raw closes with no stop and no management — not a trade replay.
  Stop-aware rows use stop = `base_low` (the gate's own stop), −1R when any daily low ≤ stop within the window.

## The numbers

Runner's verbatim gate inputs (entry = break-day open), pooled:

| cut | n | avg 10d | ≥+5% at 10d | ≥+10% at 10d |
|---|---|---|---|---|
| ALL (gate) | n=163 | −0.95% | 48 (29.4%) | 36 (22.1%) |
| TRIGGERED | n=10 | −3.00% | 3 (30%) | 3 (30%) |
| COILED | n=22 | −1.13% | 8 (36%) | 7 (31%) |
| TIGHTENING | n=131 | −0.76% | 37 (28%) | 26 (19%) |
| in Sugar-Baby cohort | n=10 | +0.40% | 4 (40%) | — |
| not in cohort | n=153 | −1.04% | 44 (28%) | — |

### Tail first (entry = break-day open, gate population)

| window | n | mean | median | p90 | ≥+5% | ≥+20% | ≥+40% | ≤−10% |
|---|---|---|---|---|---|---|---|---|
| 5d | n=163 | +3.4% | +2.5% | +21.1% | 67 (41%) | 19 (12%) | 4 (2%) | 30 (18%) |
| 10d | n=163 | −0.9% | −2.6% | +22.0% | 48 (29%) | 19 (12%) | 6 (4%) | 53 (33%) |
| 20d | n=159 | −2.6% | −7.0% | +27.1% | 53 (33%) | 23 (14%) | 8 (5%) | 70 (44%) |
| MFE 10d (max high — NOT a return) | n=163 | +16.7% | +12.1% | +36.3% | 130 (80%) | 45 (28%) | 13 (8%) | — |
| MFE 20d (max high — NOT a return) | n=159 | +20.9% | +15.2% | +47.9% | 135 (85%) | 60 (38%) | 22 (14%) | — |

Big movers: QURE 06-03 +78%, BFLY 06-10 +60%, BLZE 06-23 +59%, PRCH 06-16 +51%, QMCO 06-01 +46% (10d). Without the
top name: mean −1.4%, median −2.6%, 18/162 ≥+20% — no single name carries it. **Every ≥+20% mover is Era A.**

### Realistic fill (entry = `break_price`, CRWD excluded)

| window | n | mean | median | p90 | ≥+5% | ≥+20% | ≥+40% | ≤−10% |
|---|---|---|---|---|---|---|---|---|
| 10d | n=162 | −4.0% | −6.0% | +16.0% | 37 (23%) | 10 (6%) | 4 (2%) | 66 (41%) |
| 20d | n=158 | −5.5% | −9.5% | +22.8% | 47 (30%) | 18 (11%) | 6 (4%) | 78 (49%) |

The open-price proxy flatters the read by ~3 points of average and halves the ≥+20% count. It is a look-ahead entry:
you cannot buy the open of a day on the knowledge that it will break.

### Stop-aware (stop = base_low, −1R on any daily low ≤ stop; median risk ≈ 20% of price)

| entry | window | n | stopped | mean R | median R | total R | ≥3R | ≥4R |
|---|---|---|---|---|---|---|---|---|
| open | 10d | n=162 | 18% | +0.10R | −0.14R | +16.0R | 3 (2%) | 1 (1%) |
| open | 20d | n=158 | 33% | +0.07R | −0.41R | +11.1R | 6 (4%) | 5 (3%) |
| break_price | 10d | n=162 | 18% | −0.13R | −0.26R | −20.3R | 0 (0%) | 0 (0%) |
| break_price | 20d | n=158 | 33% | −0.13R | −0.49R | −21.3R | 3 (2%) | 3 (2%) |

A 20%-wide stop turns a +40% mover into 2R. The gate's stop and the gate's hold window are mismatched for a 4R+ book.

### By era — the read that matters for a promotion

| era | entry | n (tickers) | avg 10d | median 10d | ≥+5% 10d | ≥+20% 10d | ≥+20% 20d | p90 10d | stop-aware 10d |
|---|---|---|---|---|---|---|---|---|---|
| A ≤06-26 (retired 50/60 parent) | open | n=151 (108) | −1.3% | −5.0% | 45 (30%) | 19 (13%) | 23/150 (15%) | +23.3% | +0.09R, 19% stopped |
| A first-fire only | open | n=111 (108) | +0.5% | −2.6% | 34 (31%) | 16 (14%) | 19/110 (17%) | +24.4% | +0.19R |
| **B ≥06-29 (current HTF parent)** | open | **n=12 (8)** | **+3.0%** | +2.8% | 3 (25%) | **0 (0%)** | 0/9 | +6.5% | +0.19R, 0% stopped |
| B first-fire only | open | n=9 (8) | +3.2% | +3.9% | 3 (33%) | 0 | 0/7 | +6.7% | +0.22R |
| B | break_price | n=11 (7) | +1.7% | +2.2% | 2 (18%) | 0 | 0/8 | +6.4% | +0.12R |

Era B roster (open entry): XMTR 06-29 +2.7%, CRWD 07-01 +5.2%, OKTA 07-01 +6.9%, OKTA 07-06 +2.9%, RBRK 07-06 −5.6%,
SNOW 07-07 +2.0%, CDNA 07-31 +6.7%, MBX 07-31 +2.3%, MBX 08-04 +2.7%, CHYM 08-19 +4.4%, CDNA 08-25 +3.9%,
CHYM 08-28 +1.6% (10d). Tight, positive, and tail-less: p90 +6.5%; 20d MFE p90 +21.8%, 2 of 9 ever traded 20% above entry.

**Era B on the runner's own rule would read MARGINAL (avg 0–3%, WR 25–35%) — but at 12 rows / 8 tickers it is under
the review's own N≥10-of-independent-events bar (9 first fires), and it shows zero tail.**

## Supersession — the system already settles these events

The HTF breakout shadow (`mi_htf_breakout_shadow`, #356 Phase 3, shipped 06-28) has exactly 17 rows, and they are
the 17 Era B breaks — **by construction, not by coincidence: the shadow row is written by the #94 scan itself**
(`run_intraday_flag_break_scan` step 7, "Persist + audit + HTF shadow", `flag_detector.py` ~2174). Every #94 break
since 06-28 is a shadow row; Era A has none because the table did not exist. The shadow carries its own entry
(buy-stop-limit), its own stop (SMA10-anchored), an 8% max-stop-distance reject, and 3R settlement. Its read on the
same names, 10 settled: 1 capture (CDNA 07-31, +3R), 3 stops (−1R), 6 open (−0.38R to +0.72R); 7 of 17 carry
`would_reject_reason = stop_distance_gt_8pct`. #94's Phase 2 (`/flagbreak ENTER`, stop at base_low) would be a
second entry surface on #94's own output, with a wider stop, beside a settlement path that already exists.

**Fork for the operator (not decided here):** close this review as superseded by #356's HTF breakout path, or keep
both accruing. One-line rec: supersede — in the current era every #94 break IS an HTF shadow row, and #356 already
owns the go-live evidence for it.

## The revise menu, as the gate lists it (each item is a criterion change → CHANGE_PROCESS)

- Minimum `pct_above_base_high` (33% of fires are under 0.5% above the high — the zero-margin trigger the 5/27
  first-fire note already flagged).
- Volume-pace threshold (median detection volume 19% of ADV, projected ≥100%).
- Opening-30-min guard (17% of fires before 10:00 ET).
- Stage filter — pooled stage slices do not separate (TRIGGERED n=10 −3.0%, COILED n=22 −1.1%, TIGHTENING n=131
  −0.8%); Era B is too small to slice.
- Cohort overlay — n=10 in cohort, not decidable.

None of these is recommended here; the Era B evidence (n=12, 0 tail) cannot rank them.

## What this does not answer

- **Universe vs regime.** Era A (May–Jun) and Era B (Jul–Sep) differ in BOTH the parent universe and the market. The
  disappearance of the ≥+20% tail after 06-27 cannot be attributed to the HTF spec from this data.
- **Whether the HTF-era detector has an edge at all** — 12 settled rows from 8 tickers is not an N≥10 of independent
  events; it accrues at ~4 a month.
- **Actual fills.** No minute-bar simulation (ADR 0005 requires one before any Phase 2). `break_price` is the
  snapshot at a 5-minute scan tick, not a fill; the open proxy is look-ahead.
- **Any exit rule.** Raw close-to-close returns; the stop-aware rows use daily lows (an intraday touch of `base_low`
  counts as a full stop) and no partials, trail or time stop.
- **The Era A tail under today's rules** — those names were admitted by a parent detector that no longer exists;
  replaying them under the HTF spec was out of scope (`replay-raw-bars-not-old-trade-rows`).
- **Whether `parent_invalidated_eod` ever fires for breaks** — 0 of 168 is consistent with both a working and a
  broken reconcile; the sibling tables prove the job runs, not that this branch does.
- Sugar-Baby cohort interaction (n=10).

Working files: `/tmp/gated3/` (breaks_raw.csv, results_breaks.txt, results_breaks_clean.txt, b94_runner_output.txt,
htf_overlap.txt, htf_shadow_outcomes.txt, compute.py). Prod was read only.
