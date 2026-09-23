# HTF — the pole window, the pivot anchor and the ADR floor, replayed from raw bars (2026-09-04)

**One session, two PLAN lines (#592, #610), one detector.** Everything below is a replay of the
SHIPPED `compute_flag_metrics` over the stored candidate history (27,446 `mi_flag_candidates`
pairs, 2,174 tickers, 2026-06-29 → 09-04) from raw `mi_daily_closes` bars, with prod's three
state-threading queries mirrored per variant. Harness: `scripts/probes/_592_610_htf_grid_replay.py`.
The unmodified constants reproduce prod's stored stage on **99.58%** of pairs; every one of the
115 mismatches is accounted for (97 = the 07-18 mean→median ADV change mid-window, 10 = the
post-compute M&A filter, 8 = bars revised since the scan). $0 spent.

## Method and population — WHICH rows, over WHAT window, derived HOW

**Population:** every `mi_flag_candidates` (ticker, scan_date) pair stored between **2026-06-29 and
2026-09-04** — **27,446 pairs across 2,174 tickers**. Not a sample: the whole stored history for the
window, which begins where candidate storage begins.

**Derivation:** for each pair, the SHIPPED `compute_flag_metrics` is re-run from raw `mi_daily_closes`
bars, with prod's three state-threading queries mirrored per variant so stage transitions
(WATCH → TIGHTENING → COILED → TRIGGERED → INVALIDATED) reproduce rather than being recomputed
statelessly. Each grid variant re-runs the same 27,446 pairs with one constant changed.

**Baseline fidelity, stated because a replay that does not reproduce prod cannot be trusted to
predict it:** the unmodified constants reproduce prod's stored stage on **99.58%** of pairs. All 115
mismatches are individually accounted for — 97 from the 2026-07-18 mean→median ADV change landing
mid-window, 10 from the post-compute M&A filter, 8 from bars revised since the original scan. **No
mismatch is unexplained**, which is what licenses reading the deltas below as effects of the changed
constant rather than as replay noise.

**Forward returns** are next-20-session moves from the first actionable day, on the same daily bars.
**Cost: $0** — no paid call; every input was already stored.

## What this does NOT answer

- **It does not settle the pole DEFINITION.** The grid prices five variants; picking one is an
  operator decision (§ the fork below), and this document deliberately does not pick it.
- **It does not establish that HTF makes money.** Every number here is detection behaviour — days on
  the board, stage transitions, and raw forward moves. **It is not realized R through any bracket**,
  no entry or stop is simulated, and the money question is #397's, explicitly out of scope.
- **It cannot generalise from the labelled corpus, which is N=7** (grown from 2 on 2026-09-04: CDNA,
  HNGE, NCI, ATAI, OUST, SHAZ, REPL — every member a verbatim operator label). Seven names. They
  are useful as worked cases and are worthless as a rate.
- **The forward window is short.** The added names' next-20-session moves span a period where SPY was
  +3.9% and QQQ −0.7%; two months is not a regime sample, and several names are truncated by the
  window's own end rather than by an exit.
- **It does not judge whether the 3 dropped names SHOULD be dropped.** That is a filter-list
  judgment reserved to the operator by CHANGE_PROCESS rule 3, and nothing here should be read as
  certifying it.
- **It says nothing about intraday behaviour.** Everything is daily-bar; a name's path within a
  session is invisible to this method.

## 1. #592's diagnosis is wrong on both counts — there was no pole-window bug to fix

| #592 claimed | What the bars say |
|---|---|
| `_RUNUP_LOOKBACK_DAYS=40` "measures the stub" of HNGE's pole | 40 sessions IS the sourced criterion (90%+ in 4–8 weeks). HNGE's pole is 05-04 $45.01 → 07-13 $91.50 = **+103% over 49 sessions (10 weeks)**; from the 04-15 low it is 60 sessions. The spec's OWN two scanner forms reject it on the trader's date: `C/C40 = 1.14`, `High40/Low40 = 1.30` (need 1.90). |
| the pivot is chosen by VOLUME and "picked 11 Aug over 13 July" | Inverted. On 08-13→08-17 the volume rule **kept 13 July** (2.48M) over 11 Aug (2.21M, the higher price) — the anchor that gave the HIGHER runup (77%). The 77%→41% drop on 08-18 is **13 July leaving the 25-session pivot lookback**, i.e. the detector's own 5-week flag limit (`_BASE_AGE_MAX=25`). |

Runup for HNGE at each anchor: 13 Jul pivot → 40d **+77%**, 60d +120%; 11 Aug pivot → 40d **+41%**,
60d +78%, 70d +109%. Admitting HNGE on the trader's date (08-21/24) needs **both** retired n=1 knobs
(ratio 1.50 AND a 60-session window) — under 1.50/60 it TRIGGERs on 08-24, which is what the old
generic-flag detector would have said. **HNGE is a labelled positive that sits outside the
definition the operator sourced and signed on 6/27–6/28.** That is a methodology fork for him
(§4), not a measurement defect. CDNA — the control — fits the 40-session window (pole 06-09 →
08-03) and is kept by every variant.

## 2. The real anchor defect (measured, then fixed): a wick over the pole top became the pole top

The stable-anchor rule walked the pivot on any high that beat the prior top by
`max(1%, 0.25×ATR)`. When that high was a **wick** — price never CLOSED above the pole top — the
40-session pole window slid INTO the flag and a qualified pole re-read as a stub. Over the window,
9 names went from a ≥90% actionable row to a `runup_` reject inside 7 days via a pivot walk:

| ticker | walk | beat over top | bar closed above the top? | pole read | fwd20 from reject | later re-qualified? |
|---|---|---|---|---|---|---|
| QLYS | 07-16 | +2.2% | no (159.32 vs 164.17) | 94% → 88% | **+31%** (MFE +40%) | never |
| CHYM | 08-31 | +2.2% | no (33.20 vs 33.41) | 110% → 71% | truncated | never |
| INTA | 08-25 | +1.5% | yes — 08-21 closed 41.35 > 41.12 (resolved; walks correctly under the fix) | 98% → 86% | truncated | never |
| DELL | 08-05 | +3.4% | yes (467 > 461) | 103% → 34% | −5% (fwd10) | never |
| MAN | 07-30 | +2.5% | yes (55.86 > 55.70) | 112% → 88% | +12% | never |
| PGEN | 08-21 | +3.6% | yes (7.44 > 7.23) | 103% → 56% | truncated | never |
| RBRK | 07-07 | +3.3% | yes (87.36 > 86.45) | 105% → 54% | +7% (MAE −20%) | never |
| SNOW | 07-10 | +0.4% | flag hit the 25-session limit | 128% → 88% | +25% | never |
| TWLO | 07-16 | +0.8% | flag hit the 25-session limit | 96% → 28% | +21% | never |

**Fix (shipped, `_flag_resolved_by`)**: a decisive high over a FORMED flag (≥ `_BASE_AGE_MIN_WATCH`
bars) walks the pivot only if some bar since the flag formed has CLOSED above the pole top. No new
constant, no volume term. A pole still extending walks exactly as before. Of the 9 above it holds
only the two pure wicks (QLYS, CHYM); DELL/MAN/PGEN/RBRK/INTA had closed above the top and still
walk; SNOW/TWLO are the flag limit. The full diff (below) finds six more names the 7-day heuristic
missed (BFLY, MBX, NIQ, OKTA, REPL, TRAX).

**Why not the state machine's volume test.** The first cut reused the TRIGGERED gate (close above the
flag's highest close on ≥1.5× the flag's recent volume). Replayed, it held the anchor BELOW price
for weeks on real pole continuations that ran on 1.3–1.5× volume — NEO +40% and RNG +16% above a
stale pivot — and lost prod's correct WATCH rows for both (2,175 rows / 379 tickers changed, +165/−22
actionable rows). A pole top price has closed above is not a pole top; the close test is the
geometry, volume is the entry's business.

**Before/after of the shipped fix, same 27,446 pairs:**

| | pre-fix (prod) | fixed |
|---|---|---|
| pairs whose stage or pivot differs | — | 350 rows / 110 tickers (305 are rejected→rejected bookkeeping) |
| actionable rows (10.4/day) | 508 | 529 (10.8/day) |
| newly actionable | — | 26 rows / 8 names: **QLYS** (+24% fwd20), **TRAX** (+18%), OKTA (−5%), MBX (−14%), BFLY (−16%), REPL (0%), NIQ, CHYM (truncated) |
| no longer actionable | — | 5 rows / 3 names: OUST, SHAZ (1–2 rows on 06-29, seed-chain — an older held pivot makes the flag deeper than 25%), REPL (2 rows) |
| from 08-03 (seed chain aged out) | — | +6 rows / 3 names, −2 rows / 1 name |
| CDNA (must-not-miss) · HNGE | 18 rows · never | 18 rows · never (unchanged) |
| match vs prod's stored stages | 99.58% | 99.44% |

SNOW and TWLO are the 5-week flag limit, not the anchor — that horizon is the operator's (§4).

## 3. #610: the collapse is the signed criteria swap; the ADR floor is nearly moot under it

Verified in prod: WATCH rows May 1,885 · Jun 1,636 · **Jul 146 · Aug 131**; intraday breaks
(`mi_flag_breaks`) May 61 · Jun 91 · **Jul 7 · Aug 4** · Sep 3; candidates scanned flat (12.0k /
14.1k / 12.5k / 11.6k). Decomposed: the ADR+ADV floors cut the runup gate's INPUT by 1.87× (7,131 →
3,822 rows reaching it); the runup gate's KILL RATE went 46% → 78–85% (2.45×). Product 4.6× =
3,851 → 833 rows past the gate. The runup swap (1.50→1.90, 60→40) is the bigger factor — and it
is the operator-signed 6/27 rebuild working as designed: the detector went from a generic-flag
finder to the rare HTF.

**The grid** (window 06-29 → 09-04, 49 scan days; "act/day" = actionable rows per day; outcomes
from the scan-date close; tape over the window: SPY +3.9%, QQQ −0.7%, IWM −1.0%):

| variant | act/day | tickers | episodes | TRIG | first-WATCH fwd20 | new TRIG vs base (fwd10) | CDNA | HNGE |
|---|---|---|---|---|---|---|---|---|
| **1.90 / 40 / ADR 4.0 (shipped)** | 10.4 | 95 | 176 | 3 | n=105 med **−6.1%**, 62% <0 | — | kept | never |
| 1.90 / 40 / 3.5 | 10.4 | 97 | 178 | 3 | med −5.5% | +0 | kept | never |
| 1.90 / 40 / 3.0 | 10.6 | 98 | 179 | 3 | med −5.5% | +0 | kept | never |
| 1.90 / 60 / 4.0 | 19.2 | 171 | 355 | 5 | n=214 med −3.9% | +2 (LQDA −23%) | kept | WATCH→COILED 07-10→08-17, then 78% → rejected |
| 1.90 / 60 / 3.0 | 20.3 | 182 | 375 | 6 | med −3.6% | +3 | kept | same |
| 1.50 / 40 / 4.0 | 34.0 | 290 | 583 | 14 | n=348 med −0.9% | +11 (med −3.1%; fwd20 n=4 all <0) | kept | 07-10→08-17 only; 41% on 08-21 |
| 1.50 / 60 / 4.0 | 42.0 | 355 | 760 | 16 | n=445 med −1.8% | +13 (med −3.9%) | kept | **TRIGGERED 08-24** (the trader's date) |
| 1.50 / 60 / 3.0 | 51.0 | 428 | 907 | 21 | n=503 med −1.6% | +18 (med −3.1%) | kept | same |

**ADR, read straight:** under the sourced 1.90 runup, 4.0% → 3.0% admits **+3 tickers and 0
breakouts** in 2 months. The names the floor kills almost all fail the 90% pole anyway (a name with
<4% daily range rarely doubles in 8 weeks). The 7,560 ADR rejects in #610 were real, but they were
not HTFs in waiting. The ADR floor only matters if the runup definition loosens (at 1.50/60 it is
worth +9 act/day). The data-gated `htf_adr_threshold_tune` review (N≥10 settled shadow winners)
stays as the eventual data-fit; there is nothing to decide today.

**Outcomes, read straight:** every variant's first-WATCH fwd20 median is negative against a flat
tape; the loosest variants are "less negative" only because they admit more, not because they find
winners. TRIGGERED events are 3 in two months under the sourced spec (CHYM, WDAY, XMTR) — the
shadow table IS being fed (15 rows / 10 tickers, last written 09-03; the #592 line's "last written
08-19" worry is stale). None of this is a money question (#397 is out of scope here) but it is the
context for it: **the sourced HTF board's admits go down over the next month on median.**

## 4. What is the operator's to rule (not decided here)

1. **The pole definition.** Sourced = 90%+ within 40 sessions, measured at the pole top (signed
   6/27–6/28, "use the primary definition"). The trader's HNGE label implies a pole of 10–13 weeks.
   Admitting HNGE-class poles means the 60-session window (2× the board, +2 breakouts of which one
   is −23%) or the full retired 1.50/60 pair (4× the board, HNGE TRIGGERs on his date, breakouts'
   fwd20 all negative on n=4). CDNA needs neither.
2. **The flag horizon.** `_BASE_AGE_MAX=25` / `_PIVOT_LOOKBACK_DAYS=25` = the spec's 3–5 weeks.
   SNOW (+25%) and TWLO (+21%) were dropped at week 5; HNGE's flag on the trader's date was in week 6.
3. **ADR 4%**: measured immaterial under 1.90; leave at 4% unless (1) changes.

## 5. Also found, not fixed

- `close_below_base_low_close` INVALIDATED re-arms as the base's lowest close creeps down, so a name
  flips INVALIDATED → TIGHTENING (CDNA 07-22→07-29 then 07-30). State-machine quirk, cosmetic on
  the board, worth knowing before trusting INVALIDATED as terminal.
- 227 of 27,446 pairs were scored by prod on a bar older than the scan date (no bar for that
  ticker that day at 17:25 ET). Harmless in this replay; it is why "scan_date" ≠ "last bar" can
  happen in `mi_flag_candidates`.
- The WATCH reason string starts with `runup_…` exactly like the reject string, so a
  `reason LIKE 'runup_%'` census over-counts unless it filters on `stage`. #610's 6,878 figure was
  stage-filtered and is right.

## 6. Reproduce

```
# pull SQL is in the harness docstring; bars/pairs go to the session scratchpad (28 MB)
python scripts/probes/_592_610_htf_grid_replay.py --data-dir <dir> --only-base   # reconcile
python scripts/probes/_592_610_htf_grid_replay.py --data-dir <dir>               # full grid
```
Labelled corpus: `tests/fixtures/htf_labelled.py` + `tests/test_htf_labelled_corpus.py` (HNGE, CDNA;
N=7 as of 2026-09-04 — every member operator-labelled. No corpus was built from the detector's own criteria;
that would be circular).
