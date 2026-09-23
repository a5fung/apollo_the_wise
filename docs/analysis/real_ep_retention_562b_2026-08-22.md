# #562b — Real-EP retention: of the labelled real EPs, how many did we ever hold? (2026-08-22)

> 🗂 **DELAYED-ENTRY CONTEXT LEDGER — READ FIRST: `docs/setups/delayed_ep_reentry.md § THE CONTEXT LEDGER`.** It carries the goal, every operator ruling, every study and its result, and the open questions. Two cards ran on this subject without it on 2026-08-29 and returned nothing new. Kept complete by `tests/test_delayed_entry_ledger_complete.py`.


**MEASUREMENT ONLY. No entry technique, retry count, threshold or selection criterion is
changed or proposed as done — all of those are the operator's sole authority (THE LINE).
$0 — prod read-only via psql, no LLM calls, no paid data.**

## The question

Operator, 2026-08-22, re-opening #562 after the delayed-entry triggers study: *"Delayed entry
only works if it's a real EP… we need to look at the full pool, winners and losers and see how
many potential real EPs we keep. And then figure out how it relates to EP selection in the
first place."* The prior study (`delayed_entry_562_2026-08-22.md`) priced re-entry triggers on
44 stop-out episodes — the wrong population, because almost none of those were real EPs. This
study answers the corrected question: take every real EP in the available history, walk it
through our funnel, and count how many we actually ended up holding — then ask whether our
grading could ever have told us which ones to keep.

## The labelling rule (the load-bearing choice — stated first)

**A "real EP" = a member of the #577 must-not-miss fixture** (`tests/fixtures/must_not_miss_eps.py`),
which has exactly two label sources, neither of them my inference:

1. **Operator-named** (1): MRNA 2026-08-19 (`ep_reference_mrna_2026-08-19.md`).
2. **Evidence-named** (25 usable): the ≥10R winners from `winner_r_available_2026-08-16.txt`
   GEOMETRY 1 — tier-A gap day (real stock ever-sectored in `mi_stock_scores`, close ≥ $10,
   $vol ≥ $50M, open gap ≥ 8%, 2026-03-01..07-15), 20-day forward excursion ≥ 8× own ADR,
   and R ≥ 10 with entry = EP-day HIGH, stop = EP-day LOW, over the next 60 sessions.
   TDIC 05-12 is excluded on the source's own artifact flag (halt-prone squeeze), leaving 25.

**Total: 26 labelled real-EP events.** Reproducibility check, run fresh against prod for this
study: re-deriving the screen + geometry-1 R from `mi_daily_closes` reproduces the evidence set
**26 of 26, zero differences** (my run counts 81 tail winners vs the frozen 78 — four flips at
the 03-02/03-03 data edge where my query has a proper 20-day ADR lookback and the original had
none; the ≥10R label set is byte-identical either way).

⚠ **The label is outcome-conditioned BY CONSTRUCTION** — that is what ground truth means here
(the operator's own evidence screen labels real EPs by what they went on to do). Therefore this
study reports **retention counts and ranks only**; no return of the labelled set is ever banked
as an achievable result (that would be the select-by-peak trap).

⚠ **The label window closes at 2026-07-15.** The evidence rule needs a 60-session forward
window; 07-16..08-21 gap days cannot be confirmably labelled until ~mid-October. I scanned the
extension window anyway: **335 gap days, 5 truncated-window tail winners, ZERO at ≥10R yet** —
so no members are silently missing from the current era, and MRNA (operator-named) is its only
representative.

## Data and provenance

- **Captures** (pulled once, read many): scratchpad `562c_q1..q5.psv` + `562c_q*.sql` —
  pool/era boundaries, per-member sweep across all four surfaces, full day boards for the 11
  member sessions, the rebuilt 2026-03-01..08-21 gap-day corpus (1,100 rows) with per-row
  funnel joins, and the complete magna53 trade ledger + trading calendar.
- **Era boundaries determine what is knowable** (from `missed_winners_why_2026-08-16.txt`,
  re-verified on prod today): `mi_ep_scan_log` exists from **2026-04-13**; live `mi_ep_alerts`
  rows survive only from **2026-05-11** (old 90-day purge); `mi_live_trades` /
  `mi_paper_trades` kept forever; universe floors below the gap floor were silent (no row).
- **⚠ #583 stale rows in `mi_ep_missed_outcomes`** (369 of 442 high_unentered, 90 of 113
  moderate_alert, 2,117 of 2,766 scan_filter rows have `last_refreshed_at` > 7 days old):
  this study uses that table **only as frozen presence evidence** (proof an alert/scan existed
  in the purge era). **Every outcome column of it was dropped entirely** — stale and fresh
  alike — both because of #583 and because its return basis is the gap-day open
  (`missed_outcomes.py:480`), not our fill (trap 1). `source='historical_scan'` replay alert
  rows (150, e.g. QURE 05-29) are excluded from live-alert evidence throughout.
- The only returns cited anywhere are actual recorded trade P&L from `mi_live_trades`.
- **Window**: retention is measured at 5/10/20 trading sessions after the EP day, all inside
  the prior study's 1..25 following-session window — unchanged.

## Result 1 — the funnel: 26 real EPs in, 0 confirmed held at day 5

| stage | count | who |
|---|---|---|
| labelled real EPs | **26** | 25 evidence + MRNA |
| left ANY trace in our funnel | 10 | the other 16 died before the first logged surface |
| alerted (live HIGH) | **3** | FLY 03-12 · INTC 04-24 · MRNA 08-19 |
| entered (a fill) | **2** | INTC (paper) · MRNA (live) |
| still held at day 5 | **0** | INTC stopped day 0 (11:47 ET, −$477); MRNA censored at day 2 |
| still held at day 10 / 20 | 0 / 0 | — |

MRNA is the one live case still open: +2R partial banked day 0, 3 shares at breakeven, day 2
at the 08-21 data edge. It can still become 1 of 26. Nothing else can.

## Result 2 — where each real EP died, by name and stage

| stage of loss | n | members |
|---|---|---|
| **top-20-by-gap admission cap** | **16** | MU, STRL, ASX, SNDK, ALGM, NBIS, AMKR, BE, USAR, QBTS, HUT, IREN, APLD (all 04-08, reconstructed rank 97–342 market-wide, pre-scan-log) + SNOW 05-07, UMC 05-06, ARM 05-06 (logged `outside top-20 gap cap`) |
| session RVOL gate | 1 | UMC 04-17 (`rel_vol 0.1x < 2.0x post-open`) |
| score < 50 | 2 | QCOM 04-24 (32.4), AMD 04-24 (32.4) |
| M&A catalyst filter (+ score 14–32) | 1 | QURE 05-29 |
| pre-instrumentation, cause unknowable | 3 | SMTC 03-30, MRVL 03-31, AEHR 03-31 (passed floors, inside cap; no logging existed) |
| alerted, never entered | 1 | FLY 03-12 — HIGH alert (frozen `high_unentered` row; the entry pipeline did not exist in March) |
| entered, stopped out day 0 | 1 | INTC 04-24 — alert row purged, trade row survives: in 09:31 @ 84.04, stop hit 11:47 ET |
| entered, still open (censored) | 1 | MRNA 08-19 |

**One gate — the top-20-by-gap admission cap — killed 16 of 26 real EPs**, more than every
other cause combined. It ranks by GAP SIZE, and on a market-wide mass-gap day a real EP
gapping 8–13% sits behind hundreds of bigger gappers.

## Result 3 — the concentration caveat, stated before the numbers get quoted

**13 of the 26 sit on ONE session (2026-04-08, the mass-gap day), and 24 of 26 predate
2026-05-11**, i.e. the purge-era/pre-instrumentation half of our history. These are not 26
independent trials of the current system; they are largely one regime, one week of chaos, and
one admission rule meeting it. That does not soften the retention count — it locates it: the
funnel loses real EPs in bulk precisely on the days that produce them in bulk (P4: slots and
caps bind hardest exactly when the market hands out the most).

## Result 4 — selection: our grading does not separate real EPs. On this set it runs backwards.

- **Only 7 of 26 real EPs were ever graded at all** (6 with surviving scores + INTC's 100
  recovered from its trade row). The other 19 died before scoring existed or before scoring
  was reached.
- **Scores of the graded seven**: ARM **−12**, UMC 05-06 **21.6**, QURE **31.7**, QCOM
  **32.4**, AMD **32.4** — versus INTC **100** and MRNA **115.2**. Five of seven scored below
  the 50 admission bar.
- **Era-controlled base rate**: in the same core window, **59% of all other scored gap days
  cleared 50** (135 of 227). Real EPs went **0 for 5**. A random gap day was more likely to
  clear our bar than a labelled real EP. (Tail winners generally: 47% of scored winners
  cleared 50 vs 59% of non-winners — same direction, from `562c_check`.)
- **Within-day rank (the 5-slot question)**: AMD 6th of 9, QCOM 7th of 9, QURE 8th of 13,
  UMC **15th of 16**, ARM **dead last, 16th of 16** on their own days. The two real EPs the
  grader DID like — INTC and MRNA (rank 1 of 11) — were both entered. **When a real EP clears
  the grader it does reach the book; the failure is that 5 of 7 graded real EPs ranked in the
  bottom half of their day's board** while the day's slots went to AMD −$831, SMCI −$639,
  DELL −$272, ARM(d2) −$391.
- **The current stack still fails recall upstream of grading**: the #577 fixture replay
  records 7 of 25 evidence members dead at today's 9.0% gap floor (STRL, ASX, NBIS, QCOM,
  HUT, SMTC, IREN — gaps 8.1–8.7%), the recorded BASELINE_DEBT.
- Corroboration from the unlabelable current era: of the 5 truncated-window tail winners
  since 07-16, none was alerted — IQV 07-23 and GFI 08-05 gapped 8–9% (below the then-10%
  floor, silent), AXTI 07-30 hit the top-20 cap, DFNS 07-28 the extension gate. Same killers,
  this month.

## Result 5 — retention has a SECOND leak: even entered names are not held

From the complete magna53 fill ledger (51 fills ever: 26 paper-era, 25 live-era):

- **33 of 48 closed fills exited the same session.** 6 survived ≥5 sessions, 3 survived ≥10,
  **0 reached 20**. Longest ever: 11 sessions.
- So even if selection had put all 26 real EPs into the book, the current exit/entry geometry
  has never yet held ANY name 20 sessions — and §0g showed real-EP runs start 7–21 sessions
  out. The two leaks compound: selection admits ~nothing real, and conversion holds nothing
  long enough.

## How this relates back to selection (the operator's second question)

Delayed entry / confidence-scaled retries can only act on a name that produced a FIRST entry
and a stop-out. Over six months, the real-EP population inside that mechanism's reach was
**exactly one name: INTC 04-24** (MRNA has not stopped out). Meanwhile 23 of 26 real EPs never
reached a fill at all — 16 of them killed by one admission rule before grading, and the grader
ranked most of the rest at the bottom of its board. **A retry policy keyed to "how confident
are we it's a real EP" has, today, no upstream signal to key on: the ep_score is
anti-correlated with real-EP-ness on every graded member before MRNA.** Fixing retention in
this order — admission cap → grading that can rank a real EP above an ordinary gapper → then
delayed entry to survive the day-0 violence — is what the funnel arithmetic says; the choices
inside it are the operator's (P9: selectivity is what buys admission; P1: recall first).

## ⚠ What this study does NOT answer

- **Whether any delayed-entry technique keeps a real EP** — with 1 historical stop-out among
  labelled real EPs (INTC) and MRNA still open, there is no population to measure a technique
  on. That was the point of the operator's correction, and it is a data-supply fact, not a
  deferral: the population only grows if admission changes or new real EPs occur and are entered.
- **MRNA's outcome** — censored at day 2 of the 5/10/20 windows; re-readable free in
  September.
- **The 07-16..08-21 era's real-EP count** — evidence labels need 60 forward sessions
  (~mid-October). Five provisional tail winners exist; none confirmable yet.
- **Three members are unknowable forever** (SMTC, MRVL, AEHR — pre-instrumentation; no log
  surface existed). A purged MODERATE row for another March member cannot be fully excluded,
  though the 08-16 sweep of all 78 winners found none.
- **Whether the grading result generalizes** — 7 graded members, one regime, 13 events on one
  session (P8: every read is conditional on the selector and the era). The FLY 03-12 score of
  80 comes from a frozen row whose uniform value across four names that day suggests a
  backfill default; treated as "HIGH alert existed", not as a trustworthy score.

## Verdict, plain words

**We kept zero.** Of 26 labelled real EPs, three were ever alerted, two were ever entered, and
none was held to day 5 — the single live candidate (MRNA) is two days old and still open. The
losses are not spread across the funnel: **one admission rule (the top-20-by-gap cap) took 16
of 26**, mostly in one mass-gap week; the grader took or buried most of the rest — real EPs
scored BELOW the ordinary-gap-day base rate on every member it graded before MRNA, twice
ranking dead last on their own day. **Our grading does not separate real EPs from the rest; on
this set it runs backwards.** And the trade ledger shows a second, independent leak: no fill of
any kind has ever been held 20 sessions, which is where the real-EP runs live. Delayed entry
as a retention tool is downstream of both leaks — its addressable real-EP population to date
is one trade. What to change, and in what order, is the operator's call; the measurement says
the retention problem starts at admission, not at re-entry.

## Files

- This doc: `docs/analysis/real_ep_retention_562b_2026-08-22.md`
- Captures + probes (scratchpad, pulled once): `562c_q1..q5.sql/.psv`, `562c_analyze.py`,
  `562c_hold.py`, `562c_rank.py`, `562c_check.py`
- Label sources: `tests/fixtures/must_not_miss_eps.py` (#577) ·
  `docs/analysis/winner_r_available_2026-08-16.txt` (geometry 1) ·
  `docs/methodology/ep_reference_mrna_2026-08-19.md`
- Prior rounds: `delayed_entry_562_2026-08-22.md` (wrong population, superseded for this
  question) · `missed_winners_why_2026-08-16.txt` (the 78-winner attribution this study's
  member table re-verifies and extends) · `conversion_rehearsal_2026-08-18.md` (§0g)
