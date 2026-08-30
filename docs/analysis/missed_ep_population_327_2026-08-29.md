# #327 Stage 0+1 — The missed-real-EP population, and the 620@EPC band (2026-08-29)

> 🗂 **DELAYED-ENTRY CONTEXT LEDGER — READ FIRST: `docs/setups/delayed_ep_reentry.md § THE CONTEXT LEDGER`.**
> This is Stage 0+1 of the approved plan (`crystalline-waddling-charm`): settle what is settleable
> in #562, then build the population every later stage depends on.

**⚖ THE LINE — MEASUREMENT ONLY.** Entry discipline, selection criteria, gates, safeguards and
re-entry rules are the operator's sole authority. Nothing here is flipped, proposed-as-decided,
or changed. $0 — prod read-only via psql, no LLM calls, no paid data, no bar backfill run
(the sibling backfill card owns that; this stage uses daily bars plus already-persisted minutes).

## The decision this serves

The operator's question behind the delayed-entry program (P1): *a real EP got past us on day 1 —
what do we watch for, in what order, with what buy and stop?* #562 priced eight triggers on the
WRONG population for that question — 44 episodes we entered and were stopped out of. Stage 2 will
re-price the same ladder on the population that matches the question: **real EPs we never got
into.** This document builds that population, tags every member with WHY it got past us, and
prices how it differs from the stopped-out cohort — because if the two populations did NOT
differ, #562's ranking might transfer and the later stages could be skipped. (They differ.
Materially. §5.)

## Stage 0 — the 620@EPC band, updated to 2026-08-28

#562's only positive arm (620 turn near the EP-day close, +0.21R/trade) drew its entire positive
sum from two open marks. Both were re-replayed here with an independent port of
`geometry_sweep_572.simulate` (same policy: +2R partial half → breakeven → MAX(SMA10,SMA20)
daily-close trail → 20-session time stop), verified by exact reproduction of the study's own
08-21 marks before extending the data to 08-28:

| position (n=2 open at 08-21) | verify @08-21 | status @08-28 |
|---|---|---|
| SMCI (entry 08-06 12:50 @30.15, stop 29.33) | +5.45R (matches study) | **SETTLED +4.19R** — SMA-trail exit at the 08-24 close (35.17), partial banked |
| TEAM (entry 08-10 11:41 @148.14, stop 145.00) | +4.77R (matches study) | **still open, marked +7.73R** at the 08-28 close (190.415) |

**The band (the arm's 31 fires):**

- **Settled trades only: +0.45R sum over n=30 closed** (was −3.74R over 29; SMCI's +4.19R settle
  is the whole move). Per-trade **+0.02R**, median **−1.00R**, 17 full stops — still far inside
  the engine's own measured optimism (+0.41R/trade, #572), so the settled read remains
  **indistinguishable from zero**.
- **With the one open mark: +8.18R sum** (n=30 settled + TEAM's open mark).
- **No conclusion is drawn from the open mark.** TEAM's 20-session window settles **2026-09-08**
  (or earlier via the trail); the full pre-registered #562 re-cut remains ~mid-September, and the
  other arms (EPC-REC n=3, EPH-BRK n=5, 620-ANY n=2, 620@PDH n=1 open at 08-21) stay unsettled
  until then.
- Caveat: SMCI's settle is a settle **inside the simulator**, not a live fill; the +0.41R/trade
  calibration applies to it like every other number from this engine.

## Method — population, label rule, eras

- **"Real EP" label — the load-bearing choice, stated first.** Three tiers, none my invention:
  - **Tier 1 (n=24 missed events):** the #577 must-not-miss fixture
    (`tests/fixtures/must_not_miss_eps.py`) — the operator-blessed ground truth: ≥10R winners
    (entry = EP-day high, stop = EP-day low, 60 fwd sessions) from
    `winner_r_available_2026-08-16.txt` geometry 1, over the tier-A gap-day screen (real stock,
    close ≥$10, $vol ≥$50M, open gap ≥8%, 2026-03-01..07-15, 20d excursion ≥8×own ADR). Of its
    26 members: TDIC excluded on the source's own artifact flag; INTC 04-24 and MRNA 08-19 were
    ENTERED (they are not "missed"; INTC is in the stopped-out cohort, MRNA is live and censored).
  - **Tier 2 (n=25 missed events):** the SAME evidence file, same geometry, next band down —
    the 5–10R winners. Justification from the operator's own arithmetic, not convenience:
    THE GOAL states the average winner must exceed **4R** to break even at a ~20% win rate, and
    every 5–10R member clears that bar. The file's own band edges are used (the 4R line falls
    inside its unsplit 2–5R band, which is therefore left OUT — see §6). None of the 25 was
    ever entered.
  - **Tier 3 (n=6 events, PROVISIONAL):** the same tail screen re-run forward over
    2026-07-16..08-10 from `mi_daily_closes` (265 qualifying gap days). Six reached ≥8×ADR
    within their forward window; their ≥10R/60-session labels cannot be confirmed until
    ~mid-October, so they carry a provisional tag and are reported separately, never pooled.
- **⚠ The label is outcome-conditioned BY CONSTRUCTION** — the operator's evidence screen labels
  real EPs by what they went on to do. This document therefore reports population composition
  and ex-ante features; no return of the labelled set is banked as achievable (the
  select-by-peak trap). The deeper weakness is in §6.
- **Populations derived fresh from prod** (read-only, captured once to
  `~/.claude/jobs/6b173ac9/tmp/327s1_*`): `mi_daily_closes` (14,536 rows, union tickers),
  `mi_ep_alerts` (420 rows, live rows survive from 05-11 only — purge era), `mi_ep_scan_log`
  (from 04-13 only), `mi_live_trades` (kept forever), `mi_intraday_bars` (SMCI/TEAM replay),
  `mi_strategies` (magna53 = the only live signal cited; 9m_day2 / fishhook_v3 /
  flag_continuation confirmed deprecated and not used).
- **Stopped-out comparison cohort: the frozen #562 44** — re-derived byte-identical from
  `mi_live_trades` (magna53, closed/stopped, last exit stop_hit), after excluding the two
  episodes that postdate the study's 08-21 edge (ABCL 08-10 closed 08-24; CRWD 08-27).
- **⚠ Floor-censoring handled:** `mi_ep_scan_log` is floor-censored (MIN_GAP_PCT 8.0 → 10.0 on
  05-17 → 9.0 on 08-19; June–July logged zero rows in the 9–10% band). Every population and
  metric here derives from `mi_daily_closes`, which has no floor; the scan log is used only to
  attribute WHY a name was killed, never to define who existed. Tier-3's IQV and GFI are exactly
  the class the scan log cannot see.
- **Metrics, one method for every group:** gap% = EP-day open vs prior close; $vol = EP-day
  close×volume; ADR20 = mean daily range over the 20 pre-EP sessions; MFE20/tailx = max high of
  the next 20 sessions vs the EP-day close, in % and in ADR units. Kill attributions for
  tiers 1–2 are from `missed_winners_why_2026-08-16.txt` and
  `real_ep_retention_562b_2026-08-22.md` (this stage re-verified their scan/alert/trade joins on
  prod rather than re-deriving them — recalling context, not restarting it); tier-3 attributions
  are fresh from this pull.

## The population — 55 missed real-EP events (49 tickers), every one tagged

| class (why it got past us on day 1) | n | members | gate today |
|---|---|---|---|
| **top-20-by-GAP admission cap** | **22** | t1: MU, STRL, ASX, SNDK, ALGM, NBIS, AMKR, BE, USAR, QBTS, HUT, IREN, APLD (all 04-08, reconstructed ranks 97–342) + SNOW 05-07, UMC 05-06, ARM 05-06 (logged) · t2: AUGO 03-25, OKLO/MSTR/GLXY 04-08, NSIT 05-07, BRKR 05-06 | **CHANGED 08-22** — cap remains but ranks by pre-score, not gap |
| catalyst/score gate (score<50, old grading) | 5 | t1: QCOM 04-24, AMD 04-24 · t2: NOK 04-23, UMC 05-26, HPE 05-29 | **CHANGED** — lattice flip + ONE-GRADE fork fix (08-22), rubric v4 (08-27) |
| routine-catalyst discard (the P15 buried rule) | 2 | t2: OUST 05-04, VSH 05-13 | **CHANGED** — grading stack replaced (as above) |
| M&A catalyst filter | 1 | t1: QURE 05-29 | still live |
| session/pm RVOL gate | 3 | t1: UMC 04-17 · t2: FCEL 04-29, SDOT 06-17 | **CHANGED** — real-time volume authority + no-reject-on-missing-data (#489/#490, 08-27/28) |
| extension gate | 2 | t2: MXL 04-24, SDOT 06-08 | net unchanged (75% loosening REVERTED to 50%, 08-29) |
| mcap floor | 2 | t2: ALMU 04-13, MRAM 04-30 | still live |
| silent universe floors (prev close <$5 / prev-day vol <50k) | 2 | t2: ELPW 04-22, ELPW 04-24 | still live, still unlogged |
| blocked at entry — cap / breaker / stop width | 3 | t2: FTNT 05-07 (max_positions 5/5), STX 04-29 (circuit breaker), BAND 04-30 (stop_too_wide) | all three safeguards still live |
| alerted, no entry pipeline existed (March) | 2 | t1: FLY 03-12 · t2: FLY 03-20 | pipeline exists now |
| alerted 11:25 ET — infra skip, out of ORB window | 1 | t2: VPG 05-12 | window rule still live |
| pre-instrumentation, cause unknowable | 4 | t1: SMTC 03-30, MRVL 03-31, AEHR 03-31 · t2: LGN 03-27 | — |
| **tier 3 (provisional, current era)** | **6** | IQV 07-23 (silent: gap 9.1% under then-10% floor — **would pass today's 9.0%**), DFNS 07-27 (silent: prev close $4.35 <$5 floor; tailx 23.3, the era's fattest tail), DFNS 07-28 (extension gate), AXTI 07-30 (top-20-by-gap cap), GFI 08-05 (silent: gap 8.2%, under 10% then AND 9% now), AU 08-07 (top-20-by-gap cap) | floor since lowered (IQV's killer); cap ranking since changed (AXTI/AU's) |

- **One rule dominates: the top-20-by-gap cap took 22 of 55** — and it was still killing current-era
  provisional real EPs in July–August (AXTI, AU) right up until its ranking basis changed on 08-22.
  Whether pre-score ranking would have admitted them is untested (the pre-score did not exist then).
- **Classes the brief expected that are EMPTY in this population:** cooldown (its two hits, FLY
  05-05 and HIMX 05-07, sit in the excluded 2–5R band) — worth knowing before Stage 2 slices by class.
- **Concentration caveat, restated:** 13 of tier 1's 24 sit on ONE session (04-08); 45 of 55
  events predate 05-11 (purge era). These are not 55 independent trials of the current system.
- **Today's-stack replay (from the #577 fixture, not re-derived):** 7 of tier 1 would STILL die
  at today's 9.0% floor (STRL, ASX, NBIS, QCOM, HUT, SMTC, IREN — gaps 8.1–8.7%; the recorded
  BASELINE_DEBT).

## How the missed population compares to the stopped-out 44 — it differs, three ways

Same metric code, same tables, both cohorts (per-event rows in `327s1_metrics.psv`):

| group | n | med gap% | p25–p75 gap% | med $vol M | med ADR% | med MFE20% | med tailx | tailx ≥8 | tailx ≥4 |
|---|---|---|---|---|---|---|---|---|---|
| stopped-out #562 cohort | 44 | 15.3 | 12.1–20.9 | 866 | 5.8 | 11.5 | 1.9 | 3 (7%) | 11 (25%) |
| missed tier 1 (≥10R) | 24 | **9.8** | **8.7–11.1** | 561 | 6.3 | 66.8 | 10.8 | 24 (by label) | 24 |
| missed tier 2 (5–10R) | 25 | 14.6 | 9.3–26.9 | **235** | 6.2 | 72.9 | 11.5 | 25 (by label) | 25 |
| tier 3 (provisional) | 6 | 10.7 | 9.1–56.3 | 519 | 8.2 | 70.0 | 9.0 | 6 (by label) | 6 |

1. **Ex-ante, the gap distributions point OPPOSITE ways.** The ≥10R missed EPs cluster at
   8.7–11.1% gaps (21 of 24 under 12%); the episodes we entered and stopped out of cluster at
   12.1–20.9% (only 11 of 44 under 12%). We have been entering the big-gap crowd while the
   ≥10R class gaps small — the AUC-0.34 "gap runs backwards" finding, now visible as a
   population split. Tier 2's liquidity is also one-quarter of the stopped cohort's ($235M vs
   $866M median).
2. **By outcome composition (partly by construction): only 3 of 44 stopped-out episodes went on
   to a ≥8×ADR tail** (INTC 04-24, SMCI 05-06, NRIX 06-08 — the three known lived winners),
   and only 11 of 44 to ≥4×ADR. The missed population is all-tail BY LABEL, so this row is not
   evidence about "missed vs stopped" behaviour — but it IS evidence about #562's instrument:
   **every #562 arm was priced on a population that was ~93% tail-free.** An arm can only
   recover a tail that exists.
3. **Overlap between the populations is one name** (INTC, entered-and-stopped, fixture member).
   They are genuinely different sets, not two views of one set.

**Consequence for the plan (the question this section exists to answer):** the populations
differ materially — ex-ante on gap and liquidity, and in tail composition. **#562's arm ranking
cannot be assumed to transfer; Stage 2's re-run on THIS population is necessary, not optional.**
Had the rows matched, Stages 2–3 could have reused #562's numbers; they cannot.

## What this population does NOT include, and why

- **Real EPs that failed.** The definition is outcome-conditioned — the operator's warning that
  "went up a lot" must not be equated with "was a real EP" cuts BOTH ways, and this is the
  population's single biggest weakness: a genuine repricing event whose move died (or whose tail
  ran past the 20-session screen window) leaves no label, so under-admission of the label itself
  is invisible (P14 applied to the labelling rule). Only operator labelling could fix this;
  MRNA-class operator-named events are the mechanism (n=1 so far, and it was entered).
- **Sub-8% gappers and the tail screen's own floors** (close <$10, $vol <$50M at D0): a real EP
  below any of them cannot enter the evidence screen at all. The label inherits its own gap floor.
- **The 2–5R band** (19 events incl. SMCI 05-06, NRIX 06-08, FLY 05-05, HIMX 05-07): straddles
  the 4R break-even line unsplit, so it was excluded whole rather than split by a cut the source
  file does not make. Cost: the population's only cooldown-kill examples sit there.
- **07-16..08-10 events are provisional** (≥10R labels confirmable ~mid-October); 08-11+ events
  are not yet screenable at all (forward window too short).
- **Four members are unknowable forever** (SMTC, MRVL, AEHR, LGN — pre-instrumentation).
- **MODERATE-tier and never-screened alerted names** that lack a winner label — this is a
  missed-REAL-EP population, not a missed-alert population.

## What this does not answer

- Whether any delayed-entry trigger RECOVERS these names at 4R+ — that is Stage 2, on this
  population, with the #562 harness unchanged.
- Whether the 08-22 pre-score ranking would have admitted the cap-killed 22 — the pre-score did
  not exist on their days; a replay of it over those boards is a separate, cheap question.
- TEAM's settled outcome (09-08) and the full #562 re-cut (~mid-September) — pre-registered,
  unchanged.
- Whether tier 3's six survive to ≥10R labels (~mid-October).

## Files

- Captures + probes (pulled once): `~/.claude/jobs/6b173ac9/tmp/327s1_*.sql/.psv`,
  `327s1_analyze.py`, `327s1_metrics.psv` (per-event rows, all four groups)
- Label sources: `tests/fixtures/must_not_miss_eps.py` (#577) ·
  `docs/analysis/winner_r_available_2026-08-16.txt` · `docs/analysis/missed_winners_why_2026-08-16.txt`
- Companions: `real_ep_retention_562b_2026-08-22.md` (the funnel this builds on) ·
  `delayed_entry_562_2026-08-22.md` (the stopped-cohort study Stage 0 updates)
