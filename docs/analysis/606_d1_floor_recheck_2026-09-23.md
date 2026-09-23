# #606 D-1 universe floor — recheck on 14 trading days of shadow data

**Written 2026-09-23.** Read-only against prod (SELECT only), $0 spent, nothing flipped. This is
the `d1_universe_floor_dollar_volume_606` gated review firing — a replay of
`docs/analysis/606_d1_floor_2026-08-31.md`'s method on `mi_universe_floor_shadow`, the shadow
table #606 shipped specifically to give this question more than one week of data. **This is a
DETECTION CRITERION. Nothing was changed. This document is evidence only — any change is the
operator's sole authority.**

## Verdict: (b) — the floor should stand

The equal-recall SHAPE claim replicates (a dollar-volume floor still beats price+share-count at
matched recall, on 4x the sample). But the MECHANISM claim reverses — D-1 liquidity predicts
EP-day liquidity *better* now, not worse, which undercuts the reason given for preferring dollar
volume — and the admitted-side COST is now measurable for the first time, and it is material: at
the level the original card liked ($1M), a straight swap would drop 12 of the 118 real,
currently-caught candidates (10%), of MFE quality indistinguishable from the ones kept. (a)
needs both legs to hold; only one does, so this is (b), not (a). Nothing is being proposed to the
operator.

## Method and population

- **Table:** `mi_universe_floor_shadow`, filtered to `minutes_since_open_at_open IS NOT NULL` —
  the row's first POST-OPEN read, comparable to the original card's `setup_at_open`.
  `gap_pct_first` (often a faded pre-market print, the #595 class) was not used anywhere.
- **Rows / window:** **2,889 rows, 14 distinct trading days, 2026-09-02 → 2026-09-22.** (The
  gate's own predicate counts 15 distinct days with a rejected-side row across the *whole* table,
  not just post-open reads — one of those 15 is a pre-market-only or still-partial day with no
  post-open tick yet; 14 is what's usable here.)
- **Admitted / rejected (post-open population):** 930 rows currently pass the live floor (prior
  close ≥ $5 AND prior-day volume ≥ 50,000 shares); 1,959 currently fail it.
- **"Real candidate" definition** (the analog to the original card's `setup_at_open`): the writer
  (`universe_floor_shadow.py`) logs a row only for names that cleared the *wider* Pass-1 gap
  screen (5% at some tick, possibly pre-market), so a row can still be a faded pre-market print at
  the open. A row counts as a real candidate here only if **`gap_pct_at_open ≥ 9%`** — the
  authoritative live gap floor (`MIN_GAP_PCT` in `ep_detector.py`), checked at the actual open
  reading, not the first tick.
  - **Real candidates currently ADMITTED** (pass the two-part floor today): **118 rows** across
    all 14 days (~8.4/day).
  - **Real candidates currently REJECTED** (blocked by the two-part floor today): **397 rows**
    (~28.4/day).
  - **"Noise"** = rows that cleared the 5% Pass-1 screen but were under 9% at the actual open
    (faded prints) — 812 admitted-side, 1,562 rejected-side. ⚠ This is **not** the original
    card's 851/89 noise ratio: that table (`mi_ep_missed_outcomes`) logged every scanned ticker
    including ones that never gapped at all; this shadow table only ever logs Pass-1 gap
    clearers, so "noise" here is narrower by construction (faded gappers, not the full
    non-gapping universe). The two counts are not the same denominator.
- **Joins:** D-1 numbers (`prev_close`, `prev_day_volume`, `prev_day_dollar_volume =
  prev_close × prev_day_volume`) come straight off the shadow row — no join needed. EP-day
  dollar volume for the mechanism check and MFE for the tradeability check both come from
  `mi_daily_closes` (full-day close × volume), joined on ticker + scan_date, the same way the
  original card did it — **not** `today_dollar_volume_at_open` (that shadow column is a
  same-day read from the first few minutes of trading and would badly understate a full trading
  day; using it would silently shrink the correlation's scale versus the original method).
  `mi_daily_closes` data run through 2026-09-22, so late-week scan dates (09-18 through 09-22)
  have a truncated forward window for MFE — flagged below, not hidden.

## The five-level sweep

Recall and cost are both measured against the **currently-accruing rows on both sides** —
this is the comparison the original 5-day card structurally could not make, because its
population (`mi_ep_missed_outcomes`, floor-skip category) held only rejected-side rows; it had
no admitted-side rows to compute a cost against, so its cost column was never actually
measured, not zero.

| D-1 $-volume floor | recall — real candidates recovered from today's rejects | cost — real candidates today's floor keeps that this would drop | noise (faded prints) also swept in from the rejects |
|---|---|---|---|
| $250k | 207 / 397 (52%) | 0 / 118 (0%) | 760 / 1,562 (49%) |
| $500k | 168 / 397 (42%) | 1 / 118 (1%) | 559 / 1,562 (36%) |
| **$1M** | **147 / 397 (37%)** | **12 / 118 (10%)** | **397 / 1,562 (25%)** |
| $2M | 122 / 397 (31%) | 23 / 118 (19%) | 272 / 1,562 (17%) |
| $5M | 87 / 397 (22%) | 47 / 118 (40%) | 160 / 1,562 (10%) |

Plain words: recall is how many currently-excluded real gap names a level would let in; cost is
how many real names we catch **today** that level would newly throw out; noise is how many
faded, non-real prints ride along with the recall gain (more grading-slot load, not money).

⚠ **$250k and $500k aren't really swaps.** The live floor already implies D-1 dollar volume ≥
$250k mechanically ($5 price × 50,000 shares), so those two rows cost almost nothing by
construction — read them as "loosen the floor a little," not "replace it with dollar volume."
The real swap-vs-current-floor comparison starts at $1M, where cost turns material.

**Cost-side quality check** (are the 118→12 dropped-at-$1M names junk, or real?): their MFE
(peak move after the open — see caveat below) averages **+16%, median +7%** (n=12, thin), against
the full currently-admitted pool's **+17% mean, +10% median** (n=118). Indistinguishable. We
would not be cutting weak names — we'd be cutting ordinary members of the pool we already keep.

## Shape claim — replicates

The original's other headline ("at equal recall, dollar volume beats price+share-count") was
re-tested directly: sweep price-only floors (P ≥ $4/$3/$2/$1, volume ≥ 50k unchanged) on the same
397 rejected-side real candidates, find the dollar-volume level that recovers the *same* number
of real names, and compare how much faded-print noise rides along.

| price floor (matched recall) | noise swept in | dollar-volume floor at same recall | noise swept in |
|---|---|---|---|
| P≥$4 (11 real) | 96 | ≈$54.6M | 21 (78% less) |
| P≥$3 (42 real) | 226 | ≈$17.3M | 60 (73% less) |
| P≥$2 (71 real) | 396 | ≈$8.4M | 114 (71% less) |
| P≥$1 (145 real) | 716 | ≈$1.04M | 385 (46% less) |

This holds up well on the larger sample — noise reduction at equal recall is even larger at the
tighter price cuts than the original's headline "43% fewer" (found near $1 recall). **The shape
claim replicates.**

## Mechanism claim — does not replicate

Original: log-log correlation of D-1 dollar volume vs. EP-day dollar volume, **r = 0.44, n = 89**
(interpreted as "D-1 liquidity barely predicts EP-day liquidity" — the argument for not gating on
D-1 data being useless at any threshold).

Recheck, same method (log-log Pearson, D-1 dollar volume vs. full-day EP-day dollar volume from
`mi_daily_closes`), on the rejected-side real candidates (the same population type the original
89 came from): **r = 0.71, n = 395**. On all 515 real candidates on both sides: r = 0.77.

r² went from about 0.19 (original) to about 0.50 (recheck) — D-1 liquidity now explains roughly
half the spread in EP-day liquidity, not a sixth. **The correlation nearly doubled on 4x the
sample — the opposite direction from the original finding, and it does not replicate.** This
doesn't kill the shape claim (dollar volume can still be the better filter *shape* even if D-1
data predicts today reasonably well) — but it removes the "D-1 data barely predicts today, so a
same-day check matters more than which D-1 floor we use" framing the original leaned on.

## Tradeability / MFE re-check

Joined the 397 rejected-side real candidates to `mi_daily_closes`: 395 matched (2 tickers had no
close row). **MFE is not a return** — it's the highest price reached from the day's open through
up to 5 forward trading sessions, no exit rule, no fees or slippage, nothing banked.

- All 395: mean MFE **+31%**, median **+11%**, 82 (21%) reached ≥30% MFE.
- Restricted to the 204 names with a *full* 5-forward-day window (191 of the 395 are truncated —
  mostly scans from 09-18 through 09-22, where `mi_daily_closes` hasn't caught up yet): mean
  **+28%**, median **+10%**, 17% reached ≥30%. Consistent with the full set — truncation isn't
  inflating the headline.
- 303 of 395 (77%) traded ≥$100k EP-day dollar volume, the original card's $1k-size
  tradeability proxy.

This matches the original's shape (real movement, broadly tradeable at small size) — the excluded
population is genuinely not garbage. That finding stands; it just isn't sufficient on its own,
given the cost and mechanism results above.

## Caveats

- **Window length:** 14 trading days, ~3 weeks — longer than the original's 5, still one
  continuous stretch, not multiple regimes. The regime label itself is still not captured (same
  gap the original flagged).
- **MFE is not R, not a return, not a fill.** No bracket replay, no exit discipline, no
  slippage/spread. It only says these names moved; it says nothing about what a trade would have
  banked (the #577 lesson).
- **"Noise" denominator changed from the original.** See Method section — not the same 851/89
  ratio; narrower by construction because the shadow table only logs Pass-1 gap clearers.
- **Cost-quality n=12 at the $1M level is thin.** Directionally similar to baseline, not a
  statistically separable claim.
- **Same-day liquidity** (whether a D-1-excluded name that wakes up same-day should be admitted)
  is a separate question, tracked by its own gated review (#584) — not re-litigated here.

## What this does not answer

- **Whether any specific level should replace the live floor.** THE LINE — that decision, and
  whether to bring it to the operator at all, is his alone; this recheck's own result is (b), so
  nothing is being proposed.
- **Spread / fill quality.** No quote history for these names; untested here, same gap as the
  original card.
- **Catalyst character.** MFE says price moved; it says nothing about whether these are EP-grade
  setups the judge would actually grade well, or pumps/dilution plays it would refuse.
- **Downstream grading/alert volume.** How many of the recovered real names would clear the score
  bar needs a grading pass, not a $0 SQL replay.
- **Any regime other than this one continuous 3-week stretch.**

## ⚖ THE LINE

The D-1 universe floor is a detection criterion. Nothing was changed, flipped, or proposed for
change. Verdict (b) means: report this against the original headline, and say the floor should
stand as-is — not because the shape claim was wrong (it wasn't), but because the mechanism claim
reversed and the cost the original couldn't see turns out real. If the operator wants to revisit
this later, the open thread is #584 (same-day liquidity), not a lower D-1 floor.
