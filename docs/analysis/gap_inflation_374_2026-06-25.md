# #374 STEP-1 — EP pre-market gap inflation: frequency + impact (2026-06-25)

**Trigger:** SNX 6/25 stored a 11.22% gap (helping it reach HIGH) off an implied ~$315 pre-market
price that was outside its 280–296 range both days; the real open gap was ~0%. Operator asked: how
often does a thin/unrepresentative pre-market print inflate the gap, and does it tip names into HIGH?

## How the gap is measured (why this happens)

`gap = (current − prevDay.c) / prevDay.c` (`collector.py`), where `current` = the latest pre-market
minute-bar close / last trade, snapped at **detection time** (EP scan runs 7–10 AM, mostly pre-open).
The gap then feeds MAGNA53 directly — **gap magnitude is worth up to 25 of ~100 points**
(`ep_detector.py:902-911`). So one bogus or unrepresentative pre-market print sets the gap AND the
score. Pre-market detection is *by design* (catch the gap before the 9:31 ORB), so the fix can't just
be "use the open" — it must protect legit early gappers.

## Frequency (HIGH alerts since 2026-05-01, stored gap vs actual open gap)

| metric | count | % of HIGH |
|---|---|---|
| HIGH alerts (with open + prev-close data) | 342 | — |
| stored gap inflated **> 3%** vs open gap | 49 | **14%** |
| stored gap inflated **> 10%** vs open gap | 18 | **5%** |

It is **not rare** — ~1 in 7 HIGH alerts carries a pre-market gap meaningfully above what actually
opened, and 1 in 20 by >10%.

## Two regimes (the guard must distinguish them)

Worst inflations:

| ticker | date | stored | open | inflation | read |
|---|---|---|---|---|---|
| WEST | 05-08 | 41.2 | 16.4 | +24.7 | faded, still a big gap |
| IMVT | 05-20 | 35.3 | 15.8 | +19.5 | faded, still big |
| AXTI | 05-01 | 16.8 | **−0.5** | +17.3 | **VANISHED** — opened flat/down |
| DYN | 05-20 | 17.9 | 1.6 | +16.2 | **VANISHED** |
| QURE | 06-17 | 75.2 | 61.4 | +13.8 | real — 61% is still a monster |
| MLTX | 06-22 | 19.1 | 4.2 | +14.9 | mostly vanished |

- **Real-but-faded** (QURE 75→61, WEST 41→16): the pre-market gap was real; it cooled but the name
  still gapped hard. A HIGH here is arguably correct.
- **Gap-VANISHED** (AXTI 16.8→−0.5, DYN 17.9→1.6): the stored gap is essentially fiction at the open —
  these are the false HIGHs. This is the operator's SNX class (a real but unrepresentative thin print).

## Guard implications (STEP-2 — operator + CHANGE_PROCESS)

Target the **vanished** class, keep the **faded** class. Candidate signals (need backtest + sign-off):
1. **Sanity-bound** the pre-market `current` against the recent range (e.g. reject/clamp a price far
   outside the trailing N-day high/low) — directly catches the SNX/$315 + AXTI cases.
2. **Liquidity gate** — require min pre-market volume / ≥N prints at the gap level before trusting it
   (distinguishes thin-but-real from a lone print).
3. **Re-confirm/re-score at the open** — keep the early alert, but re-grade the gap on the opening
   print before the score is load-bearing.
- ⚠ DETECTION criterion → CHANGE_PROCESS + N≥10 backtest + operator sign-off before any change.
- Open methodology question for the operator: is scoring on the pre-market gap (vs a confirmed open
  gap) the right design at all, given a measurable ~14% inflation rate?

**STEP-1 status: DONE** (frequency + impact quantified). STEP-2 (guard design + backtest) is the
operator-gated next step.
