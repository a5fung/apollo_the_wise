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

---

## CDNA follow-up, 2026-09-24 — two flags, two breakouts, and our board never reached TRIGGERED

**The trader's update** (Leif Soreide, 2026-09-24 11:37 AM, operator-shared; tweet and his MarketSurge
chart saved in `docs/methodology/operator_shared_charts/2026-09-24_htf_cdna_leif_soreide/`):
*"$CDNA High Tight Flag. Took a first scale after a few risk multiples. Still long. Name is extended
and the greater genomics theme is still hot. This is not the kind of action you typically see when
you should be on the sidelines. Leaders that keep paying while the average stock looks soft are
exactly the kind of follow-through I want on the board for the next high tight flag masterclass."*
His chart on the day: $62.61, **+15.3%** on volume **+144%** over its 50-day average, RS 99,
0.7% off its 52-week high, 50-day average dollar volume $56.6M, market cap $2.81B. His marks: the
pole 6/22 close 25.05 → 8/3 high 49.76 (+99%, 30 bars), the flag 8/3 → 8/17 (−9.5%, 11 bars), a
second shelf with a 53.67 high in late August.

**Method and population:** every `mi_flag_candidates` row for CDNA from 2026-08-25 to 2026-09-23,
read from prod 2026-09-24 (n = 20 scan days). The COILED and TRIGGERED gates were read from
`flag_detector.py` the same day.

| scan dates | our stage | what it saw |
|---|---|---|
| 08-18 → 08-25 | TIGHTENING | first flag under the 49.76 pivot; 08-25 closed **2.1% above it** |
| 08-26 → 09-01 | unqualified | the pivot moved to each new high (51.13, then 53.67 on 08-27); base age 0–2 |
| 09-02 → 09-11 | WATCH | second flag under 53.67; pole re-measured as +96% from 07-08; base low 46.69 |
| 09-14 → 09-17 | TIGHTENING | price range tight (0.60–0.68 of the base's early range), volume not (0.90–1.06) |
| 09-18 → 09-23 | unqualified | new highs 54.49, 54.46, 56.85 moved the pivot again |

**What it shows:**
- **We saw both flags — TIGHTENING twice — and neither breakout could register.** TRIGGERED needs
  COILED within the last 5 sessions (`_COILED_LOOKBACK_DAYS`), and CDNA never reached COILED.
- **What blocked COILED differed each time.** August: price range never contracted (0.95–1.29 against
  a 0.75 bar). September: range did (0.60–0.68), but volume stayed at 0.90–1.06 of the base's early
  volume against a 0.70 bar, and the two-bar fresh-tight path read 1.0 against 0.6.
- **After each breakout the pivot follows the new high**, so the board resets to a young base instead
  of carrying a "broke out" state.
- **The surfacing gap from 08-25 still stands:** even TIGHTENING reached nobody.

## What this does not answer

- **One name, not a verdict.** Whether the 0.70 volume bar is too strict needs both directions measured
  across flags (#592 era); tuning on CDNA alone would be fitting one chart (his own rule for this corpus).
- **Tradeability.** A stage board is not a setup; this says nothing about an entry, stop or result by
  our rules (#354).
- **09-24 itself:** tonight's scan row was not yet written when this was recorded.

