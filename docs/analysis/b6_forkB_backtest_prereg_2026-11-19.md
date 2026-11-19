# B6 fork B backtest — PRE-REGISTRATION (written 2026-11-19 PT, before any trade-outcome data)

**Question.** If the earnings rubric's composite score (below 22) could no longer downgrade a catalyst
from strong to routine, which of the names it cut would have become trades under today's rules, and
were those trades worth having — big winners added AND losers added?

**Status.** Measurement only. Nothing live changes (THE LINE). Review: `b6_gate_inversion_post_rescale`
(`data_gated_reviews.yaml`); owner SSoT `docs/setups/catalyst_rubric.md`; pulls and phase-2 code under
`scripts/probes/_b6_backtest_1119/`.

## What has already been seen (disclosed — it cannot be unseen)

- The 5-session price read of 2026-11-10 and 2026-11-19: PASS 2 of 65 reached +20% vs DOWNGRADE 12 of 164
  (post-rescale); pre-rescale 7% vs 7%.
- The 5/20-session returns of 14 named PASS rows, and the names of seven downgraded runners
  (NTSK, FPS, BETR, EAF, HRI, HAYW, GDYN) from the 11-10 doc.
- The general alert replay in `scripts/ep_replay_data/campaigns_era_d.tsv` (all alerts, not this
  cohort), read only to calibrate the thresholds below: 267 alerts → 99 settled trades (37%),
  6 of 99 at +3R or better (6%), 46 of 99 near-full losers, mean +0.17R.
- NOT seen: any entry, stop, R or replay result for a downgraded or PASS candidate; any
  `mi_ep_scan_log` row for this cohort; which downgraded names would have cleared the bar.

## The counterfactual — exact definition

The gate (`ep_detector.py` ~5530–5946): on an earnings name graded strong / game-changer with a
revenue-stage company, the rubric scores a composite; below 22 the raw grade AND the acting grade are
set to routine, logged once per ticker per day as `catalyst_earnings_revenue_weak_downgrade` with
`from_quality`. Routine pays 0 catalyst points instead of 15 (strong) or 25 (game-changer), fails the
"routine + gap under 12%" filter, and loses the pre-market-shares bypass that needs strong.

Fork B has two possible mechanisms. Both are computed; which one IS fork B is a ruling (see the end).

| Column | Mechanism | Effect on a composite-downgraded name |
|---|---|---|
| **B1 (primary)** | The composite is still scored and recorded but takes no action | Grade stays at `from_quality`. The revenue-growth safety net does not fire (it runs only when the rubric could not score). |
| B2 | The rubric gate is switched off (`CATALYST_RUBRIC_GATE_ENABLED`) | The safety net takes over: stored `q_revenue_yoy_pct` under 5% → still downgraded; 5% or more → grade stays; no stored number → treated as still downgraded (the recovery / carve-out chain is not replayed). |

Per name, per scan tick (`mi_ep_scan_log` is one row per ticker per tick):

1. Ticks before the downgrade event's timestamp are factual — nothing changes.
2. From the downgrade tick on, the acting grade is restored to `from_quality`, IF the stored acting
   grade on that tick is routine. A tick whose stored grade is not routine means the grade corrector
   already reversed the downgrade — the gate did not act there and the tick stays factual.
3. A tick killed at a stage that does not read the grade (volume gate, extension cap, quality filter,
   cooldown, duplicate, shortlist cap, M&A) stays killed.
4. A tick killed at `post_grade_filter` for "routine catalyst, gap under 12%" or the pre-market-shares
   floor is re-run through the live `_grade_floor_filters` with the restored grade and the stored gap,
   volume and pre-market volume ratio.
5. Re-score. Points come from `ep_rubric.SCORE_WEIGHTS` (never typed here):
   counterfactual score = stored score + 1.25 × (catalyst points of `from_quality`) × multiplier,
   because a routine row carries 0 catalyst points. Game-changer with a gap of 10%+ also gets the
   raw-60 conviction floor (presents as 90 — always over the bar). The multiplier (1.0, or 1.2 on a
   Bull day) is worked back from the stored score and breakdown where the breakdown exists, and
   cross-checked against `mi_market_regime`; where it does not exist, from the regime table.
   A step-4 tick has no stored score: it is scored by the live `_score_ep` from stored inputs, taking
   the float and theme points from any scored tick of the same ticker-day, else as a low/high band.
6. Counterfactual HIGH = counterfactual score at or over the row's stored bar (65 post-rescale). A
   band that straddles the bar is an abstain, counted.
7. Submit time = the first counterfactual-HIGH tick, floored at 09:31 ET. First HIGH at 09:45 or later
   = outside the entry window, no trade (counted). The name must still be on the board (a scan row
   with gap 9%+, and no acted real-time flip-down) at the last tick at or before submit. ⚠ This
   board rule is an APPROXIMATION of the 09:31 entry job's own selection, which was not traced end to
   end for this doc — the funnel is reported with and without it, and check 5 below tests it.
8. A later population row for the same ticker within the 60-day alert cooldown of a counterfactual
   alert is flagged `cooldown_ambiguous` and left out of the primary set (shown separately).

Gates that would STILL drop a counterfactual HIGH, and how each is handled:

| Gate | Replayable at $0? | Handling |
|---|---|---|
| Entry window 09:31–09:44, 10:00 unfilled cancel | Yes | Harness (`walk_campaign`, `entry_cancel`) |
| Opening range valid; range not over 1.5× ATR | Yes | Live `validate_orb_entry`; ATR14 computed from daily bars (the harness's own `atr14_abs`), flagged approximate |
| Stop-limit buy never triggers / opens above the limit | Yes | Harness `entry_walk` on minute bars |
| Fade guard | n/a | MAGNA53 HIGH skips it by rule |
| Extension cap, cooldown, liquidity, shortlist cap | Yes | Factual — stored per tick (step 3) |
| Opened below the gap floor after a real-time flip-up (ON since 11-03) | Yes | Applied to every date as a current rule: flip-up audit row + 09:30 open under prev close × 1.09 → no entry |
| The judge (can demote a HIGH to no alert) | **No** — a paid model call | NOT applied per name. The counterfactual set is a pre-judge upper bound; the judge's measured keep rate on real PASS HIGHs is reported beside it |
| Grade corrector on later ticks; intraday re-grade | No | Assumed unchanged from the downgrade tick; stated |
| 5-position cap, loss limit, both breakers | No (needs the book) | Separate column only (below) |

## Is re-scoring feasible for names that never alerted? — Yes, with stated bands

- **From 2026-08-29:** `mi_ep_scan_log` stores, for every candidate at every tick, the score, the bar,
  the acting and raw grade, the full component breakdown and the score inputs (#605). Exact.
- **2026-08-22 to 08-28:** the tick's score and grade are stored, the breakdown is not. Still exact for
  strong (the add is points × multiplier); the retired agreement boost (live to 08-27) makes it a
  low/high band.
- **Pre-rescale (before 08-22):** the old score table. Re-scored as a band on the old rules (old floors,
  per-regime bar, the earnings-day promotion that the downgrade used to block). A different admission
  system — a separate column, never pooled, never part of the decision rule.
- **Where no tick carries a score at all:** not re-scored. Those names appear only in the upper bound.
- **Upper bound for every era:** every downgraded name with a 09:30 bar walked as if admitted at 09:31.
  It answers "what is the most the gate could have cost", nothing more.
- `pull_2` returns a coverage table so the split between exact / band / none is a count, not a guess.

## Checks that must pass before any counterfactual number is quoted

The 98% / 90% / 95% lines below are set without having seen what a correct build reads on them; each
result lists its misses by cause, and a miss that is a data gap (not a logic error) is said so.

1. **Re-scorer:** on factual scored ticks, stored breakdown + worked-back multiplier reproduces the
   stored score within 0.1 on at least 98% of rows; a multiplier that is not 1.0 or 1.2 (post 08-27)
   flags the row.
2. **Alert reconstruction, on the PASS arm:** "first in-window tick at or over the bar" must predict a
   real `mi_ep_alerts` row with floor tier HIGH for at least 90% of PASS names (and predict none for
   those without). If it cannot rebuild alerts that really happened, the DOWNGRADE arm is unreadable
   and the result is reported as such.
3. **Harness:** `python scripts/ep_replay.py validate` still clears its own floors; replay abstain rate
   at or under 30% in each arm (the harness ceiling); stops narrower than 0.5% of entry excluded.
4. **Entered / not entered, on real alerts:** for real post-rescale HIGH alerts with a trade row, the
   replay's verdict (entered or not) must match the real row on at least 95% (the harness's own floor);
   every miss is listed by cause. This is what tests the step-7 board rule and the entry walk together.
5. **Population first:** counts by era, by reason, by "alerted anyway" printed before any return.

## Population

Sample sizes at freeze: n = 176 downgraded and n = 74 PASS post-rescale candidates (counts from the 11-19 coverage read).

- Every `mi_ep_catalyst_metrics` row with a stored revenue growth number, alert date 2026-05-19 on,
  up to the last complete session before the pull day, plus any composite-downgrade event with no such row. DOWNGRADE = an event with reason
  `rubric_composite_*`; PASS = no downgrade event of any reason (the review's own definition).
- **Primary: post-rescale (alert date 2026-08-22 on).** Pre-rescale is its own column.
- Safeguard-blocked names stay in (what an EP is does not depend on the breaker).
- Downgraded names that alerted anyway are in both worlds — reported, not counted as "added".

## The replay

- `scripts/ep_replay.py::walk_campaign`, rule-set `ruleset_as_of(2026-11-19)` — today's entry, bracket
  (stop at entry − 2R, R = entry − opening-range low), +8R partial, breakeven arm, trail — applied to
  every campaign in both eras. Live code paths only; the phase-2 driver lives in the probe folder,
  imports the harness, edits nothing, and sets the settle horizon to the last daily bar strictly
  before the pull day.
- Day 0 on minute bars; later sessions on daily bars (the harness contract). A stop and a target in the
  same daily bar is an abstain. No forward-minute pull.
- Unit = R per campaign, one risk unit each. Still-open campaigns are listed with their mark and never
  folded into the settled numbers.
- **Abstain rate is reported first, per arm, with reasons.**

## The comparison (same replay, both arms)

| Arm | What it is |
|---|---|
| **A — added (B1)** | Downgraded names that become a counterfactual HIGH in the window and enter |
| A-B2 | The same under mechanism B2 |
| **P-floor** | PASS names put through the identical reconstruction (floor HIGH in window) — the like-for-like control, pre-judge on both sides |
| P-actual | PASS names that really alerted HIGH after the judge — shown beside P-floor so the judge's effect is visible |
| ALL-HIGH | Every real post-rescale HIGH alert of any catalyst type, same replay — the fallback comparator when P-floor is too small (below) |
| Upper bound | Every downgraded name walked as if admitted |

Reported for each arm, in this order:

1. Funnel: names → counterfactual HIGH → in window → entered → settled / open / abstain / no entry.
2. **Tail:** count at +3R or better, count at +5R, best campaign, share of entered (settled; then again
   including open marks).
3. **Both directions:** winners added AND losers added — count of near-full losses (−0.9R or worse),
   count negative, total R, mean R, median last.
4. **Per alert week:** entered, +3R count and total R by ISO week, plus total R with the best week removed.
5. **Slot cap / breakers — separate column:** for each added entry, whether that morning already had five
   open positions on the acting account, a breaker or loss-limit block on a real alert, or five or more
   real HIGH alerts ranked ahead on prior-day RS. Reported as "of N added, K would likely have been
   blocked". Never used to drop a row from the main read.
6. Judge bound: keep rate of real post-rescale PASS floor-HIGH alerts through the judge; A × that rate
   as the expected post-judge count. Context, not a per-name filter.
7. The names. A is listed in full — CHANGE_PROCESS rule 3: the operator reviews the list; the agent
   does not label any of them a good or bad cut.

## Decision rule — stated now

Read on **post-rescale, mechanism B1, arm A vs the comparator C**. "Entered" = settled or still open.

**Expected arm sizes, from counts already known (not outcomes):** about 176 downgraded and 74 PASS
candidates post-rescale; about 28 PASS names alerted; the general replay enters about 38% of alerts.
So P-floor is expected to be about 10 entered — UNDER the floor of 15 — and A somewhere between a
handful and about 35, depending on how many restored grades clear the bar.

**The comparator C, fixed now so a short PASS arm cannot stall the rule:** C = P-floor when P-floor
has 15 or more entered; otherwise C = ALL-HIGH. P-floor is shown either way, with its n, and a
result that leans on ALL-HIGH says so in its first line (it answers "are the added names as good as
what we already trade", not "as good as the earnings names the gate kept").

**Not readable at this n** (gate stays 22, nothing closes):
- any check above fails, or fewer than 15 entered in A, or fewer than 15 entered in C.
- What it looks like, so it is not mistaken for a result: at the general alert rate (6% of entries reach
  +3R), 15 entries show zero big winners about 40% of the time and two or more about 23% of the time.
  A handful of entries cannot separate "the gate cuts winners" from luck in either direction.
- Reported instead: how many entries fork B adds per quarter at the observed rate, and the date the
  SHORT arm (A or C, whichever missed) would reach 15. One re-read at that point, same rule.
- **Inert:** five or fewer counterfactual HIGHs in the whole post-rescale window means other rules drop
  these names anyway — fork B would change almost nothing. Recommend closing the review as moot.

**Brings fork B to him for sign-off** — all five:
1. Readable.
2. Tail: A has at least two campaigns at +3R or better, and A's +3R share is at least C's.
3. Net of the losers it adds: A's total R is above zero, and A's mean R is at least C's.
4. Not one earnings fortnight: A's +3R campaigns sit in at least two different alert weeks, and A's
   total R stays above zero with its best week removed.
5. The upper bound and the pre-rescale column are shown beside it and do not contradict it in sign
   (a contradiction does not veto; it is stated in the first line of the package).

The package then carries: the name list for his review, B1 vs B2 side by side, the judge bound, the
slot/breaker column, and the CHANGE_PROCESS reversal note (why the 2026-05-19 gate reasoning was
wrong, not just incomplete — or that it cannot be shown).

**Closes fork B (gate stays 22):** readable, and A's total R is zero or below, and A's +3R share is no
better than C's. The names the gate cut would have lost money as trades and carried no better
tail than the names it kept.

**Anything in between:** gate stays 22; one re-read when A reaches 30 entered, same rule, no third read.

Thresholds are fixed here. A change to any of them after the pulls are read is a new pre-registration,
dated, with the reason.

## What this does not answer

- What the judge would have said about each added name.
- Portfolio interaction beyond the separate slot/breaker column.
- Whether the composite's axes measure the right thing (operator ruling 2026-09-05: the edge is
  surprise against expectation) — this measures only the trade consequence of its downgrade.
- Non-composite downgrades (missing prior-year number, sparse news): out of scope.

## Pulls (read-only; first line of each sets the transaction read-only)

Run `pull_1` first and read its SCHEMA section before the rest — the SQL was written against
`db.py` and the earlier pulls that ran, but was not parsed locally (no psql on the build machine).

| File | Returns |
|---|---|
| `pull_1_population.sql` | Column check for every table used; last daily / minute bar; the population with era and "alerted" flag; every downgrade event as scalar fields (time, from-grade, reason, composite, caps, axes, gap, revenue growth); rubric-passed events; regime by day |
| `pull_2_scanlog.sql` | Every scan tick for each population ticker-day (stage, reason, score, bar, grades, breakdown, score inputs); coverage counts by era and stage; the score-shadow and grade-corrector rows |
| `pull_3_alerts_trades.sql` | Every live alert since 05-19 (floor / judge / final tier, detection time); every trade row of every strategy since 05-01 incl. skips and reasons (the position cap counts all open positions); prior-day RS and ADV for the population and every post-rescale alert; flip-up, flip-down, earnings-promotion and prose-downgrade events |
| `pull_4_daily.sql` | Daily bars since 2026-01-01 for population tickers and every post-rescale alerted ticker |
| `pull_5_minutes_day0_post.sql` | Alert-day 09:30–15:59 minute bars + per-name coverage, post-rescale population plus every real post-rescale alert (primary + ALL-HIGH) |
| `pull_5_minutes_day0_pre.sql` | The same, pre-rescale (separate column only) |

## Needs the operator's ruling

1. **Which mechanism is fork B** — B1 (composite keeps scoring, stops downgrading) or B2 (rubric gate
   off, the 5% revenue-growth net takes over). Rec: B1 is what the review text says; both are measured.
2. Any live change that follows a "bring" outcome — his sign-off on the name list, per CHANGE_PROCESS.
   Nothing in this backtest touches a live rule.

## Deviations recorded after the pulls ran (2026-11-19 PT) — the decision rule is unchanged

1. **Pre-rescale re-score on the old rules was not built.** The pre-rescale column is the upper bound
   only (every downgraded name walked as if admitted). It was never part of the decision rule.
2. **A reject stage the doc did not name, `gap_floor`** (the real-time gap fell under 9%), exists in the
   scan log. It does not read the grade, so it is treated like the other grade-blind stages (step 3).
3. **Slot / breaker column:** a per-ticker re-entry refusal (`block:r3_reentry_disabled`) is not counted
   as an account-level block; only account-level blocks, five open positions, or five real HIGH alerts
   ranked ahead on RS mark an added entry "likely blocked".
4. **Check 4 is also shown era-aware** (the open-below-floor rule was not live before 2026-11-03, and
   the replay applies it to every date as a current rule). The pass/fail line still uses the frozen
   95% on the plain count.
5. The "harness validate" check is numbered 3 in the doc and was run as `python scripts/ep_replay.py
   validate` (output: `scripts/probes/_b6_backtest_1119/harness_validate.out`).
6. **Check 4's "really entered" test was wrong in the first run and was corrected the same day:** it
   read a planned entry price as a fill, so five cancelled orders counted as entries. Now a filled /
   closed status or a fill time. This is a fix to the check's own arithmetic, not to its bar; the
   check fails before and after (42 of 55, then 45 of 53).
7. **Pull gap found by check 4:** scan ticks (`pull_2`) and flip events (`pull_3`) were joined to the
   earnings population, not to the wider set that includes every real post-rescale alert. The 35
   ALL-HIGH comparator names outside the population ran with the board and open-below-floor gates off.
   `pull_6_wide_ticks_events.sql` returns the missing rows; it has not been run.
8. **Outcome under the frozen rule:** NOT READABLE (check 4 failed). No threshold was changed.

### Second run, same day (2026-11-19 PT) — after `pull_6`; the decision rule and every bar are unchanged

9. **`pull_6` wired in:** the scan ticks and flip events of the 35 real post-rescale alerts outside the
   earnings population. Every comparator name now runs through the same gates as the added arm.
10. **The approximate "still on the board" rule (step 7) is REPLACED by the live submission order**, read
    from `broker/entry_pipeline.py::submit_trade_entry` and `broker/order_manager.py::_pick_entry`:
    window → open-below-floor (`check_flip_up_open_floor`) → real-time gap re-check at submission
    (`check_rt_gap_floor`: last price vs prior close under 9% → refused) → opening-range validation →
    order pick (last price over the opening-range high → limit buy at price × 1.002 under the 1.5×
    chase cap; otherwise the stop-limit bracket walked by the harness). "Last price at submission" is
    the open of the first stored minute bar at or after the submit minute — the one remaining
    approximation (no stored ticks or quotes; the ask-aware trigger is not modelled).
11. **Check 4 is scored with era-correct gates** (open-below-floor from 2026-11-03, the submission gap
    re-check from 2026-08-02), because it compares against what really happened on each date. The arms
    still apply today's rules to every date, as frozen. Chase-cap refusals are now replayed, so they
    are no longer excluded from check 4.
12. **The upper bound runs with the submission gates off** (it is "every downgraded name admitted",
    so the gates that would refuse it are part of what it bounds).
13. **Outcome under the frozen rule, second run:** all five checks pass; branch CLOSE. Supersedes item 8.
14. **Sensitivity added after the second run, NOT part of the rule:** a pre-judge comparator (every real
    post-rescale alert with floor tier HIGH). The pre-registered ALL-HIGH comparator is post-judge while
    the added arm is pre-judge; against the pre-judge one the frozen tests read IN BETWEEN instead of
    CLOSE. The frozen branch is reported as fired (CLOSE) with this stated in the first lines.
15. **Check 4 is an in-sample fit:** the fixes in items 9–11 were aimed at its own first-run misses on
    the same 56 rows. It has not been tested on rows it was not tuned against.
16. **Price-aware fills are scored on actual risk** (entry − stop), where live sizes on planned risk
    (opening-range high − stop). Affects two added entries and one comparator entry.
17. **An upper-bound split** (by why fork B does not add each name) was added to the results; context only.

Results: `docs/analysis/b6_forkB_backtest_2026-11-19.md`.
