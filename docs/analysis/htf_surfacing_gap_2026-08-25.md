# HTF — we had the names and never told him (2026-08-25)

**Both high-tight-flag setups the operator brought in this week came from Twitter, not from us.
In one case we had the right read a day before the trader bought it, sitting in a table nobody
looks at.**

Recorded at his instruction ("keep this record"). Evidence-only; no rule, threshold or toggle
was touched.

---

## CDNA — we were RIGHT, and a day EARLY, and silent

Trader's post (2026-08-25): *"$CDNA long with one of the more textbook High Tight Flags I've seen
in the genomics/diagnostics/medicine theme."* **He bought it on 2026-08-19.**

Our own `mi_flag_candidates` rows for CDNA:

| scan_date | stage | base_age | note |
|---|---|---|---|
| 2026-08-12 | WATCH | 6 | runup 130%, close vs pivot −4.9% |
| 2026-08-13 | WATCH | 7 | −4.8% |
| 2026-08-14 | WATCH | 8 | −8.9% |
| 2026-08-17 | WATCH | 9 | −6.8% |
| **2026-08-18** | **TIGHTENING** | 10 | range 0.95, vol 0.65 |
| **2026-08-19** | **TIGHTENING** | 11 | range 1.00, vol 0.69 — **the day he bought** |
| 2026-08-20 | TIGHTENING | 12 | close vs pivot −5.6% |
| 2026-08-21 | TIGHTENING | 13 | −2.3% |
| 2026-08-24 | TIGHTENING | 14 | −4.5% |
| 2026-08-25 | TIGHTENING | 15 | **+2.1% above pivot** |

Run-up **130%** anchored 2026-06-09, pivot 2026-08-03 at **49.76**, base low **44.57**.
Chart facts from his screenshot agree: 6/22 close 25.05 → 8/3 high 49.76 = **+99% in 30 bars**,
then a **−9.5% over 11 bars** flag. RS 99, 50-day avg dollar volume **$42M**, market cap $2.46B —
liquid enough to be a real name, not a thin flyer.

**It never alerted.** 11 audit rows over 20 days, none of them an alert. The stage board lives in
`mi_flag_candidates` and no operator-facing surface renders it.

## HNGE — the same week, a different failure

The other HTF he brought in. We scan it every day and **reject** it: `runup_41%_below_90%`.
Its real move is 4 May $45.69 → $93.13 = **+104%**. Two defects, both filed as **#592**:
1. `_RUNUP_LOOKBACK_DAYS = 40` — HNGE's pole took ~50 sessions, so a 40-session window ending at
   the pivot starts 18 June at $85.01, two-thirds up the pole, and measures the stub.
2. The pivot is chosen by highest **volume**, not highest price (`flag_detector.py:659`) — it
   picked 11 Aug over 13 July, sliding the window further forward.

The anchor visibly drifts on our own rows: **77%** on 08-17 (anchored 14 May) and **41%** on 08-21
(anchored 18 June). Same stock, same move.

## What the pair proves

**CDNA is the control for HNGE.** Same detector, same code, and it anchors *correctly* on CDNA —
because CDNA's pole (30 bars) fits inside the 40-session window and HNGE's (~50) does not. So
**#592 is a WINDOW problem, not a detector problem.** That is worth more than either case alone.

And CDNA isolates a second, separate gap: **detection is not the binding constraint — surfacing
is.** We had the correct read, in the correct state, a day before an experienced trader acted on
it, and it reached nobody.

## Open, not resolved here

- **#592** — the pole-anchor window and the volume-chosen pivot. Measurement first: how many true
  flags are recovered and how many extra names admitted per day (both directions, P14). Detection
  criteria are THE LINE.
- **Surfacing** — `/flags` exists as a command; whether TIGHTENING/COILED should push rather than
  wait to be asked is the operator's call. Last 30 days: 1,540 names unqualified, 36 reached WATCH,
  11 TIGHTENING, 6 COILED, 1 TRIGGERED — so a push surface would be quiet, not noisy.
- **Not answered**: whether either name would have been *tradeable* by our rules, or what the
  entry and stop would have been. `#354` folds the flag detector into Family A for exactly the
  reason that a stage board is not a setup — a setup needs a defined buy point and stop, and
  WATCH/TIGHTENING/COILED/TRIGGERED are states.
