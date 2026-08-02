# #490 RT-2 shadow packet — measured 2026-08-02

**Purpose**: the 8-gate packet that must be signed before RT-3 (the authoritative gap flip).
Gate definitions: `docs/analysis/490_full_realtime_design_2026-07-25.md` §RT-2.

## VERDICT: **NOT SIGNABLE TODAY.** Gate 1 fails on both of its clauses.

| gate | requirement | measured | verdict |
|---|---|---|---|
| 1 residual capture | ≥95%, every miss explained | **83.9%**, 5 misses **unexplained** | **FAIL** |
| 2 fetch health | ≥99% ticks non-degraded, fallback <2% | 0 degraded ticks; fallback **0.25%** | **PASS** |
| 3 prev_close mismatch | ~0 post-fix | **0** on every trading day 7/27-7/31 | **PASS** |
| 4 tick-quality rejects | <1% + named list reviewed | **0.58%**; 14 names listed below | **PASS** (list awaits operator) |
| 5 pre-open delta ~0 | centred ~0 for STABLE names | **not validly measured** — see below | **INVALID** |
| 6 would-have-caught list | operator reviews | 97 catches; top 15 listed below | awaits operator |
| 7 volume shadow sane | rt cumulatives sane + named list | **19% of RT reads are exactly 0.00** | **CONCERN** (blocks RT-5, not RT-3) |
| 8 ~0 catches ⇒ check instrumentation | — | 97 catches — not a zero-effect case | **n/a** |

---

## Gate 1 — FAIL (83.9%, and 5 misses with no explanation)

⚠ **My first measurement said 74.2% and was WRONG.** It counted only `ep_rt_universe_catch` (the
Pass-0 full-universe path) and ignored `ep_rt_floor_flip_up` (the Pass-2 hybrid path). A residual
caught by Pass-2 does not need Pass-0. Counting **either** path: **26 of 31 = 83.9%.** Three names
(AGX, ENTG, NVTS) moved from "miss" to "caught" on that correction.

**The 5 TRUE misses — no `ep_rt_*` event of any kind on the day:**

| date | ticker | rt gap @ cross | delayed gap | cross tick | day high gap |
|---|---|---|---|---|---|
| 07-29 | QMCO | 11.00% | −0.09% | 09:35 | 12.87% |
| 07-29 | QURE | 13.97% | 4.75% | 09:31 | 14.06% |
| 07-29 | SCL | 10.31% | NULL | 09:40 | 14.45% |
| 07-30 | DY | 10.03% | 3.52% | 09:31 | 12.45% |
| 07-31 | VECO | 10.72% | 3.37% | 09:40 | 11.62% |

**What has been ruled OUT, by measurement not assumption:**
- **Not a classification gap** — all 5 are `security_type='CS'` in `mi_security_types`.
- **Not liquidity/price filters** — all are liquid, >$5 names (DY, VECO, ENTG-class).
- **Not a tick-window gap** — `ep_rt_universe_catch` fires heavily at exactly these ticks:
  09:31 ×9, 09:35 ×14, 09:40 ×13, 09:45 ×13. The overlay was running and catching other names
  at the same moments.
- **Not tick-quality rejection** — a Q1-Q4 reject logs `ep_rt_tick_quality_reject`; these logged
  nothing at all.
- **Not reachable by Pass-2** — every delayed gap is below the 5% superset floor
  (`EP_PASS1_SUPERSET_GAP_PCT`), so only the full-universe path could ever have caught them.

**What remains, untested:** they crossed between 5-minute ticks and were back under 10% when the
tick sampled. That is plausible for DY (10.03% — a hair over) but **weak for QURE, which crossed at
13.97% against a 14.06% day high** — it would have had to fall ~4 points inside 4 minutes.

**Judgement: the cause is NOT established, and the gate requires each miss explained. Do not sign
gate 1 on "probably sampling."**

### ROOT-CAUSE HUNT, 2026-08-02 — narrowed to THREE SILENT DROP PATHS

Universe filters were tested against settled data and **cleared all 5**:

| ticker | prev close | prev volume | price gate ≥$5 | volume gate ≥50k |
|---|---|---|---|---|
| QMCO | $11.28 | 1,136,742 | PASS | PASS |
| QURE | $36.66 | 3,007,067 | PASS | PASS |
| SCL | $58.01 | 127,807 | PASS | PASS |
| DY | $371.92 | 731,143 | PASS | PASS |
| VECO | $48.37 | 780,104 | PASS | PASS |

So they belonged in `_rt_universe`. Reading `_apply_rt_universe_overlay` end-to-end found **three
paths that drop a ticker with ZERO telemetry** — which is precisely the trace all 5 left:

1. **`price = sn.get("price"); if not price: continue`** — the Alpaca snapshot returned nothing
   usable for that symbol. Silent. **Leading candidate.**
2. **`_rt_quality_read` → `return None, None, meta`** — no trade print AND no corroborating minute
   bar returns a `None` *reason*, and the caller logs only `if reject`. Silent.
3. **`if rt_gap < MIN_GAP_PCT: continue`** after the quality read — the name crossed, then the
   accepted price fell back under the floor. **Benign**, but silent, so indistinguishable from (1).

⚠ **And the coverage shortfall was structurally invisible**: `ep_rt_universe_degraded` fires only
when `stats["batches_failed"]` is set — a whole-BATCH failure. A tick where every batch succeeded
but individual symbols came back empty logged nothing. With `EP_RT_UNIVERSE_CONCURRENCY=1` and a
15 s budget across the full ~3,325-symbol universe, partial symbol coverage is entirely plausible
and was unmeasurable.

**Gate 1 was therefore not answerable from stored data — the distinguishing evidence was never
recorded.** That is the honest reason it could not be signed, and it is now fixed rather than
argued: all three paths emit (`ep_rt_universe_coverage` per tick unconditionally, plus
`ep_rt_no_price` and `ep_rt_retreated_below_floor` per ticker-day).

▶ **The decision is now one market session away.** Monday's scans separate "the feed never returned
the symbol" from "we saw it and correctly declined". If coverage reads ~100% and the misses show up
as retreats, gate 1 is a sampling artefact and signable. If coverage is short, the delayed-snapshot
seeding plus partial RT fetch is the real ceiling on real-time detection — a far more important
finding than the gate number.

⚠ **A structural note that may matter more than the number.** `_rt_universe` is built from the
**delayed Polygon snapshot** (`ep_detector.py:2362` — every ticker in `snapshots` clearing the
non-gap filters), then RT prices are overlaid onto it. So the "full real-time universe" is only as
complete as the *delayed* snapshot that seeds it. If a name is missing or thin in that snapshot at
that moment, no amount of real-time data reaches it. That is a plausible mechanism for all 5 and it
is the thing to test first.

## Gate 4 — PASS on rate; the NAMED list is the operator's to judge

0.58% reject rate (14 of 2,401 scan rows), under the 1% bar. Per CHANGE_PROCESS r3 the agent does
**not** classify these — the list goes to the operator.

```
PNW   outside_band     rt 10.55%  @09:10  07-27
PRE   outside_band     rt 10.41%  @09:30  07-27
KNSA  no_bar_confirm   rt 10.18%  @08:20  07-28
ANIK  stale_quote      rt 10.56%  @07:45  07-29
INVX  outside_band     rt 30.09%  @09:15  07-29
IPCX  no_bar_confirm   rt 10.35%  @09:40  07-29
MYGN  no_bar_confirm   rt 13.29%  @07:00  07-30
BDC   stale_quote      rt 10.75%  @07:15  07-30
NPKI  stale_quote      rt 11.95%  @07:50  07-30
MKTX  no_bar_confirm   rt 27.16%  @08:00  07-30
COHU  no_bar_confirm   rt 10.60%  @09:30  07-30
FLS   no_bar_confirm   rt 10.01%  @09:30  07-30
BGDE  stale_quote      rt 19.95%  @07:40  07-31
FET   stale_quote      rt 16.04%  @09:05  07-31
```

## Gate 5 — INVALID measurement, not a fail

The gate asks for the pre-open rt-vs-delayed delta to centre **~0 for STABLE names**. What I measured
(pre-open median **+1.97**, p10 −4.66, p90 +8.51) was taken over the flip/catch population — which is
**by construction the set where rt and delayed disagree**. That is a selection-biased sample and it
cannot answer the question asked. It is not evidence of a problem and must not be read as one.

**To measure it properly**, the denominator must be all scan-log rows carrying both `gap_pct_rt` and
`gap_pct_delayed` — including the overwhelming majority where they agree — not the events that fire
only on disagreement.

## Gate 6 — the would-have-caught list (operator reviews)

97 catches over 5 shadow days. Top 15 by real-time gap:

```
INVX 30.09% (delayed n/a) @09:05 07-29     MKTX 29.64% (n/a) @08:05 07-30
RACC 23.15% (delayed 1.21%) @09:50 07-30   PLPC 22.39% (n/a) @09:30 07-30
SILC 20.59% (n/a) @08:15 07-29             JLHL 20.39% (0.49%) @09:40 07-27
SPRC 19.91% (−1.43%) @09:35 07-30          BGDE 19.27% (n/a) @07:30 07-31
CBZ  17.67% (n/a) @08:20 07-29             BNAI 16.67% (1.97%) @08:50 07-27
FET  16.04% (n/a) @08:55 07-31             MPLT 14.38% (−2.11%) @09:35 07-29
HURN 14.16% (n/a) @09:31 07-29             BUUU 13.80% (4.45%) @09:45 07-27
BLZE 13.62% (3.17%) @09:35 07-31
```

**The judgement this list is for**: several are small/obscure symbols (JLHL, BUUU, MPLT, BNAI, BGDE,
RACC). Admitting them is the practical consequence of the flip, and whether that cohort is wanted is
the operator's call, not a measurement.

## Gate 7 — CONCERN: 19% of real-time volume reads are exactly zero

Of 182 volume-shadow events since the fix, **35 read `rt=0.00x`** — including
`FBRX delayed=800.05x rt=0.00x`, `VEEE 413.10x → 0.00x`, `TRAX 33.37x → 0.00x`. A real-time RVOL of
exactly zero on a name showing 800× delayed RVOL is a plumbing failure, not a disagreement between
two honest measurements.

**This does NOT block RT-3** — the volume flip (`ep_rt_volume_authoritative`, RT-5) is a separate,
later decision, ≥3 market days after the gap flip. But **RT-5 cannot be signed until this is
explained**, and the 61 "would flip" events are not trustworthy evidence while a fifth of them are
zeros.

## What would make this signable

1. **Explain the 5 gate-1 misses** — replay one ticker tick-by-tick and confirm whether it was in
   `_rt_universe` at the tick. Either it was (and retreated → sampling, explainable) or it was not
   (and the delayed-snapshot seeding is the real ceiling on RT coverage).
2. **Re-measure gate 5** on the unbiased denominator.
3. **Operator reviews the two named lists** (gates 4 and 6).
4. Gate 7 is deferrable to the RT-5 decision, but should be filed now.


---

# OPERATOR RULINGS — 2026-08-02

## Gate 6 (the would-have-caught cohort) — *"not against smaller stocks per say, but some of those charts looks quite poor"* … *"looks about right in terms of vol split"*

**Ruled: size is not the objection, TRADABILITY is.** He endorsed the dollar-volume split as the
right lever. Not yet a shipped threshold — no number is signed.

⚠ **The tension to carry into any threshold work**: a liquidity floor would have cut **RACC, the
single best performer in the cohort (+31.1% open→close, $1M dollar volume)**. Whatever floor is
proposed must be scored against that, not just against the names it cleans up.

## Gate 4 (tick-quality rejects) — two named rulings

- **MYGN 07-30 `no_bar_confirm` — ruled a GOOD rejection.** Operator: *"I don't see >10% except for
  on specific 1min bar and it crashed back down immediately, so this is a good avoid, especially
  knowing next day it dropped 46%."* This is the guard working exactly as designed: a single
  uncorroborated print, no confirming minute bar, rejected.
- **FET 07-31 `stale_quote` — operator says the setup LOOKS LEGIT and asked why a stale quote is
  grounds for rejection.** Answered below; the honest reading is that the reject reason is
  MIS-NAMED, and the real cause is the mandatory bar corroboration.

### What the three reasons actually mean (`_rt_quality_read`, `ep_detector.py:1660-1697`)

For a name only real-time data can admit (`rt_only=True`), **Q3 — a corroborating minute bar — is
MANDATORY**. The reason string names the most-informative *failed* guard, which is why it misleads:

| reason | what actually happened |
|---|---|
| `no_bar_confirm` | quote FRESH, print in-band, but **no confirming minute bar** — a lone print nothing else supports (MYGN) |
| `stale_quote` | **no confirming minute bar**, AND the quote was too old (>30s RTH / >300s pre-open) to cross-check the print either |
| `outside_band` | quote fresh, but the print sits outside bid/ask ±0.5% and no bar corroborates — a late-reported / off-exchange odd print |

**So `stale_quote` does NOT mean "we rejected it because the quote was stale."** In every case the
binding constraint is the missing minute bar; the quote state only decides what the failure is
*called*. FET was rejected for want of corroboration, not for quote age.

⚠ **The structural consequence, and it is the actionable part: 10 of the 14 rejects fired
PRE-MARKET** (07:00-09:15). Pre-market is exactly where minute bars are sparsest and quotes thinnest,
so a mandatory-bar rule is at its strictest precisely where a real pre-open mover is hardest to
corroborate. That is a design trade-off, not a bug — but it is the reason a name like FET that
"looks legit" gets dropped, and it should be an explicit operator decision rather than a side effect.

## Judge demotions — operator ALIGNED with the judge

*"aligned, the stocks looks fine but not true EP moving."* Both CLF (HIGH→MODERATE, still a net loss
behind a tripled EBITDA) and WKC (tier held, profit surge attributed to transient fuel-price
volatility) were **correct calls**. The 5-day run does not make them EPs.

▶ **Consequence for #513 (the digest rebuild): the monthly sweep's
`⚠️ UNJUSTIFIED-DEMOTION sweep` heading is LOADED and was wrong here.** It labelled two correct
judgements "unjustified" purely because price rose afterwards. Rename it to something neutral —
"demotions that subsequently ran" — so the surface asks a question instead of asserting an error.
