# EP Profitability Program — the framing document

**Created 2026-08-11 (operator: top priority — "not that we need to find an answer but we need a
path to it"). This is a FRAMING document: goals, what is measured, open questions, task coverage,
and blind spots — across all four surfaces at once, so the operator can direct the work from one
place. It proposes NO change to any strategy, threshold, rubric, or toggle. Every selection, entry,
exit, and sizing decision named here is the operator's (THE LINE). Where a fork exists it is stated
as his decision with its cost. Each surface carries at most ONE labelled recommendation.**

Every figure below is from prod (query named) or an in-repo doc (path named), verified 2026-08-11.
Nothing is estimated; unmeasured things say "unmeasured".

---

## 0. The situation, in five verified facts

1. **19 closed live trades in 60 days: 0 winners, 19 losers, −$416.19 total. Best trade −$2.40.**
   (`mi_live_trades WHERE account_mode='live' AND status='closed' AND alert_date >= CURRENT_DATE-60`,
   prod 2026-08-11.) The honest statement is "nothing has been TAKEN as a win", not "nothing works":
   the only positive results are the two OPEN positions — PLTR (entered 08-04 @ $149.05, 4 of 6
   shares remaining after a partial that banked +$33.27; ~$175 on 08-11) and ABCL (85 sh @ $8.96,
   entered 08-10; ~$9.69 on 08-11).
2. **The top grade is the modal grade.** `game_changer` = 48 of 81 alerts (59%) over 60 days
   (commit `92f3873`, 08-11; re-verified same day on the rolling window: 58 of 96 HIGH ticker-days
   = 60%). Outcomes do not separate by grade: game_changer 14 closed avg −$22.54, 0 winners; strong
   5 closed avg −$20.14, 0 winners. Operator: *"we should reserve HIGH/gamechanger to absolute
   best, not just anything that gaps up though that remains a key criteria."*
3. **The alert rate follows the calendar.** HIGH alerts/day: 1–2 in late July (07-21..07-29),
   then 10 / 7 / 8 / 9 across 08-04..08-07 (prod, `mi_ep_alerts` per-day count). Operator:
   *"during earnings season, we basically buy every day because there are gap up and downs
   everyday, lots of randomness."*
4. **2026-08-11's within-day ranking was inverted** (full board in §2; prod-verified). We scored
   SE last of four and skipped it; it was the only name with underlying strength and reclaimed
   +10.5% within four minutes. The two names we entered died inside 60 seconds.
5. **Delayed entry barely exists.** The p74 review: alpha capture 51% (53 of 104) vs a 34.2%
   baseline (ADR 0003), target 60–70% — but only ONE of the 104 reached TRIGGERED inside 21 days
   (#562, PLAN.md). And the carryforward feeding the watch list had been dark ~7 weeks (query
   pointed at the paper account; fixed 08-11, commit `93dcd21`).

---

## 1. THE MEASUREMENT PROBLEM — read this before any surface

**You cannot rank, grade, or tune on realized P&L when 19 of 19 lost.** A ranking signal needs
outcome variance; this cohort has none — every label maps to the same result, so fitting anything
against it is fitting noise. This one fact shapes the whole program (commit `16b627e`).

**The alternative outcome variable — already built, reuse it, do not rebuild:**
- **Unit = the ALERT, not the fill.** Forward return / MFE / MAE at 1/3/5/10/21 days for every
  alert **including skips, cancels, and stop-outs**. That is where the variance lives: SE was
  skipped and made +10% the same morning; 56 of 87 failed-Day-1 names (64.4%) made a high ≥+5%
  above gap-day open within 21 days (`scripts/probes/_p74_post_ship_audit.md`, regenerated
  08-11). N goes from 19 traded → 81 alerted in 60 days → ~3,100 alert-outcome rows since
  February.
- **The machinery exists:** `mi_ep_missed_outcomes` (3,114 rows, 2026-02-11 → 2026-08-10, with
  ret_1d/5d/20d, max_high_5d/20d, skip_reason — prod schema) · `mi_ep_scan_outcomes` (fwd_5d/10d)
  · `scripts/ep_delayed_capture_audit.py` (21-day forward walk per failed alert) ·
  `scripts/probes/_468_moderate_realized_r.py` (reconstructs realized-R as-if-ORB-entered under
  the exact live geometry, for names never entered). Extend these; do not mint a fifth harness.
- **Why alert-level is also the CORRECT unit, not just the bigger one:** the #468b diagnosis
  found 20 of 21 HIGH-cohort bracket losers were on stocks that then ROSE over 5 days (#482,
  PLAN.md) — a day-1 stop-out is evidence about the BRACKET, not about the pick. Trade outcomes
  conflate selection with entry geometry and exit rules; alert-forward returns isolate selection.
- ⚠ **N over rows, everywhere:** 81 alerts across ~20 sessions is ~20 observations of any
  per-session question, and multi-alert days (the only days where a choice exists) are fewer
  still. The 08-04..08-07 earnings window is most of the usable within-day sample.

---

## 2. Surface 1 — SELECTION / RANKING

**GOAL (operator's words):** *"does it capture the main goal of selecting best EPs in a given day
when there's many?"* (2026-08-05) · reserve HIGH/game_changer for the absolute best (2026-08-11) ·
themes are part of the ranking (2026-08-11: *"don't forget that themes are important and part of it
as well to the ranking"*), per the north-star chain: subtle RS → early theme → matures → buy before
mainstream. Good = given N alerts and 5 slots, the slots go to the names a strong-group,
leader-context read would pick, and the conviction label separates outcomes.

**WHAT IS MEASURED**
- The worked case, 2026-08-11 (prod-verified, one session — an example, not evidence):

  | name | ep_score | gap | RS comp | RS rank | above 10/20/50MA | theme? | outcome |
  |---|---|---|---|---|---|---|---|
  | RIOT | 115.2 | 17.9% | 32.6 | 1641 | no | 1 | cancelled — ORB unfilled |
  | FRMI | 96 | 17.0% | 31.7 | 1661 | no | 0 | stopped 09:31:40, −$31.49 |
  | BW | 96 | 34.9% | 1.5 | 2397 | no | 0 | stopped 09:31:56, −$49.60 |
  | SE | 54.7 | 10.6% | 88.5 | 281 | **yes** | 0 | **skipped** (gap floor, §3); +10.5% by 09:35 |

  The separation is total and runs the wrong way: our score put the only strong name LAST.
  Hypothesis (not a finding): the score rewards gap size + catalyst grade and has no term for
  trend context, so a dead stock gapping huge outranks a leader gapping modestly (commit `237f516`).
- **The entry path has NO ranking at all.** `live_tracker.process_new_alerts_live` orders by
  `DISTINCT ON (ticker) … ORDER BY ticker, ep_score DESC` → the surviving order is ALPHABETICAL;
  which alerts get the 5 slots is decided by ticker name and ORB timing. Measured 08-04 (10 HIGH):
  the cap-blocked names were AEIS (first alphabetically) and ZBRA (last). The only composite that
  exists (`briefing._ep_composite_key`) orders the morning briefing for reading and never touches
  entry (#533, PLAN.md).
- Grade inflation + calendar cadence: §0 facts 2 and 3. The grade inflates exactly when
  randomness is highest.
- The theme term in the score is decorative: R4 in-theme bonus = +10, shipped 2026-05-17
  telemetry-only — 0 tier crossings in its pre-ship 60d check (`docs/setups/magna53_ep.md`).

**THEMES AS A RANKING INPUT — and the trap that decides whether it is usable**
- What we STORE today, per theme (`mi_themes`, prod schema): `stage`, `score`, `rs_avg`,
  `days_active`, `consecutive_accelerating`, `pct_above_20sma`, `parent_theme`, `tickers`. Per
  alert (`mi_ep_alerts`): `in_active_theme` (bare membership), `theme_gated_tier/score`,
  `in_narrative_cohort`. What we do NOT store: any theme-STRENGTH feature joined to the alert row
  at alert time (strength = rs_avg / stage / member count / acceleration streak — the thing the
  operator actually judges by eye). Membership is stamped; strength is not.
- ⚠ **A missing theme is AMBIGUOUS today, and that decides usability.** Absence can mean (a) the
  name genuinely has no group behind it — a real negative — or (b) our coverage missed it. The
  08-11 board is the proof: FRMI and BW were in NO theme and died in 60 seconds (reads true
  negative); **SE was ALSO in no theme** (0 `mi_themes` rows in 10 days, prod-verified) while the
  operator says the retail group it belongs to is strong (reads coverage failure). Same feature
  value, opposite truths. Board-wide: the latest 7-day theme snapshot dedups to 120 themes
  averaging 2.5 members, 95 of 120 holding ≤3 (prod; the session's earlier `get_active_themes`
  read: 91 / 3.2 / 71-of-91) — and the 08-07 software cohort gapped together while belonging to
  nothing (#471).
- **Consequence: theme membership cannot be a ranking input until absence is unambiguous — which
  makes coverage (#563) a PREREQUISITE of the ranking work, not a parallel track.** (Also listed
  in §6 interactions.) #560's steady-state cost check feeds directly into this: if theme
  assignment gets pulled on cost, #563's coverage input changes under it (§6 interaction 14).

**OPEN QUESTIONS** (each with what would answer it)
1. Within one session, does ANY stored feature (ep_score, grade, gap, RS/rank, above-MAs, dollar
   volume, theme membership/strength, regime, alert time) order the morning's alerts the way
   their forward returns landed? → #533's per-session rank correlation over every multi-alert
   day, alert-level outcomes, never pooled. In progress, due 08-12.
2. Does the conviction label carry information at all, and should game_changer be rare? → same
   cohort measurement; then a recalibration fork (CHANGE_PROCESS + sign-off) that currently has
   NO owning task (§7 gaps).
3. Should selection be earnings-season-aware (cadence-conditioned bar or per-day cap)? →
   unmeasured; no task owns it (§7 gaps).
4. Is trend context (above-MAs / RS rank / Stage-2) the missing score term? → falls out of #533's
   feature read; but a Stage-2 classifier does not exist (§7 gaps).
5. Does the rubric downgrade losers more than winners (pooled)? → #448's B6 backtest (a different,
   pooled question — do not confuse it with the within-day one).

**Labelled recommendation (one, selection):** run #533's readout with theme-STRENGTH features
joined offline (all inputs are dated and retained — `mi_themes` back to 2026-03-19, so any past
day's board is reconstructible at $0) before any grade or score work is even discussed.

---

## 3. Surface 2 — ENTRY

**GOAL:** capture the qualified name without losing it to mechanism, and don't enter names that no
longer qualify on truthful data. The operator's sharpest framing (#545): *"EP stocks is a winning
cohort overall (not high win rate, but major winners can be found here) however, entry/exit tactics
is the big challenge."* Entry discipline itself (trigger level, stop basis, floors) is his alone.

**WHAT IS LIVE TODAY** (all verified in `mi_safeguard_state` / code, 08-11)
- ORB mechanics: stop-limit buy @ ORB high, stop @ ORB low, window 9:31–9:44 ET, 10:00 unfilled
  cancel. Ask-aware trigger fallback (`entry_ask_aware`, on 08-07 — INSM/QNST venue kills) and
  price-aware chase with 1.5× risk cap (#500). Fade guard: MAGNA53 passes `None` (skipped).
- Real-time gap floor at submission (`ep_rt_entry_gap_recheck`, on since 08-02): one point-in-time
  sample at ~09:31; blocks if rt gap < 10%. Flip-down authority at the scan tick
  (`ep_rt_gap_down_authoritative`, on). 3-bar sustain rule on shadow catches (`ep_rt_sustain_enabled`).
  Full real-time admission (`ep_rt_universe_authoritative` + `ep_rt_gap_authoritative`) — OFF,
  operator-ruled HOLD 08-10 (#559).
- Same-day re-entry after a stop: DISABLED (R3, killed on 0-for-7). Both 08-11 stop-outs carry
  `block:r3_reentry_disabled` on their closed rows.

**WHAT IS MEASURED**
- **The gap floor's record just split.** Through 08-10: 4 blocks, 4 correct (all faded names,
  −$46.06 saved on the two preventable fills — WKC, QBTS). On 08-11 it produced its first likely
  FALSE block: SE skipped at 09:31:10 on a 9.2% single-sample read
  (`setup:gap_below_floor: rt 9.2% < 10% floor (alert said 10.6%, last $125.36 vs prev close
  $114.80)`, prod row) — and SE traded back above the floor by 09:35. ⚠ The gate's block rate has
  been counted; its FALSE-block rate never has (#559 DoD now adds the split: blocked-and-stayed-
  below vs blocked-and-reclaimed-within-ORB).
- **The bracket geometry is close to zero-edge on the HIGH cohort.** #468b: entry = ORB high,
  stop = 1-min ORB low (~3% range), median 12-minute hold, and 20 of 21 losers were on stocks
  that then ROSE over 5 days — a 1-minute-range stop shakes out winners. Operator ruled 7/18:
  KEEP the 1-min ORB live; accrue shadow evidence on alternatives (5-min bar, re-entry after
  stop, established-intraday-low entry, ATR/structure stop) → #482.
- **Real-time crossers as a cohort are bad under the OLD exits:** −0.60R over n=320 alerts /
  14 days, 80% stopping day-0; the gate-passing subset was WORSE (−0.69R). Only positive pocket:
  pre-open HIGH, n=5 (TSAT +10.93R never stopped) — too thin to size on. HOLD stands; re-cut
  08-31 after 14 trading days of the new exit stack (#559 — the window is pinned to the original
  measurement's own window, so the two cuts are comparable).

**OPEN QUESTIONS**
1. What is the gap floor's false-block rate, and is a one-tick sample at the noisiest second of
   the session the right mechanism? → #559's 08-31 split. Any re-look/re-check behaviour is a NEW
   entry mechanism = operator fork (cost each way: keep = SE-class misses on reclaimed names;
   add = re-admits genuine faders like FTNT/WKC/QBTS, the exact class the guard exists to stop).
2. Which entry/stop geometry has edge on this cohort? → #482's shadow accrual + the #545 grid
   (entry timing × stop basis). Unmeasured until shadow rows settle.
3. Should slots be RANKED rather than first-come-alphabetical? → measure first (#533), then an
   operator fork; no build task exists (§7 gaps).
4. Trigger exactly AT the ORB high made INSM invalid on arrival — offset or not? → #541, blocked,
   explicitly the operator's decision.
5. Do the cooldowns and the $1M ADV floor cost more than they protect at $760/trade? → #557, #556
   (both filed with measurement-first DoDs).

**Labelled recommendation (one, entry):** change nothing before 08-31; the #559 re-cut plus the
false-block split is already the right next measurement, and any threshold moved now would
invalidate its comparability window.

---

## 4. Surface 3 — DELAYED ENTRY

⚠ **"Delayed EP" is NOT a setup today — and saying so is a definition, not a hedge (CLAUDE.md,
SETUP vs FAMILY).** It has no named buy point and no named stop. What exists is a WATCH machine
(carryforward → flag stages WATCH/TIGHTENING/COILED/TRIGGERED) that almost never reaches its
actionable stage, plus a separate pre-deploy spec for a different population. Naming a delayed-EP
setup requires exactly two things: **a defined buy point and a defined stop** — and that naming is
what #562's diagnosis feeds.

**GOAL (operator's words):** carryforward *"is critical to delayed entries for EP"* (08-11). The
target population is real and large: 64.4% of failed-Day-1 HIGH names (56 of 87) made a high ≥+5%
above gap-day open within 21 days (`_p74_post_ship_audit.md`, 08-11 run). Good = a named setup
that catches a usable fraction of that population — the p74 review's stated target is 60–70%
capture vs 51% measured and a 34.2% baseline (ADR 0003).

**WHAT EXISTS, disentangled (three different things that share one label):**
1. **The carryforward + flag-stage watch lane** (`flag_detector.py`, 17:25 ET): failed MAGNA53
   names and 9M EPs are carried into the staging machine. This is the lane #562 interrogates.
2. **The #270 "Delayed-EP Re-entry" spec** (`docs/setups/delayed_ep_reentry.md`): tiny-cap
   fast-runner undercut-and-reclaim lane, analysis complete, deployable wiring gated — a
   DIFFERENT population (sub-$500M, +40% gaps) from the SE-class large-name delayed EP.
3. **The operator's own delayed entries**, done by hand: TEAM 08-07 (re-entered the stock Apollo
   was stopped out of, $144.39 at ~11:50, stop at low-of-day — *"no hard rule so hard to copy"*,
   #545) and the SE read (below).

**WHAT IS MEASURED**
- **The funnel almost never fires.** Of 104 alpha names in the p74 review, ONE reached TRIGGERED
  inside 21 days (#562). Prod today: current flag board = 6 WATCH · 1 TIGHTENING · 0 COILED ·
  4 INVALIDATED · 595 unqualified; distinct TRIGGERED tickers in 60 days = **3**. Nearly all
  "capture" credit is the loose WATCH stage — a name goes on a list and nothing fires.
- **The input was broken for ~7 weeks.** The MAGNA53 carryforward query read the paper account
  and fed nothing (fixed 08-11, commit `93dcd21`). So the funnel's historical death-points are
  measured on a partially dark input; clean funnel data starts 08-11.
- **The freshest 60d re-run is starker than the review:** ANY downstream pickup on alpha names =
  10 of 56 (17.9%); the flag lane contributed 3 (5.4%) (`_p74_post_ship_audit.md`).
- **A hypothesis for WHY TRIGGERED never fires, to be verified by #562 from code, not assumed:**
  the staging machine's live parameters serve the HTF setup — a 90%/40d runup gate
  (`docs/setups/flag_continuation.md`, `htf.md`). A carried-forward EP that gapped 10–30%
  will rarely satisfy a near-double runup criterion. If confirmed, the binding constraint is a
  borrowed parameter set, not a threshold to tune. (`flag_continuation.md` itself warns the
  parameters legitimately differ by consumer.)
- **The closest thing to a labelled positive example** — the operator's SE read, verbatim in
  `docs/methodology/operator_shared_notes.md` (2026-08-11). His four conditions, none of which is
  in the current TRIGGERED logic: (1) gapped through while above ALL moving averages — computable
  today (`mi_stock_scores.sma_10/20/50`); (2) a decent-looking base — partially computable (RMV
  work); (3) possibly moving into a Stage 2 uptrend after bottoming/basing — NO classifier
  exists, the biggest gap; (4) the GROUP is strong and the name belongs to it — failed on OUR
  side the same minute (SE in zero themes; #563).

**OPEN QUESTIONS**
1. What exactly does TRIGGERED require today, gate by gate, and where did the 104 names die in
   the funnel? → #562's DoD (describe before proposing), due now.
2. What is the delayed-EP BUY POINT and STOP? (Candidates already in evidence, for the operator
   to rule on once #562 lands: FIRST5-break with first-5-min-low stop from #270; base-then-turn
   as demonstrated on TEAM; a reclaimed-floor re-look for the SE class.) → no task owns the setup
   NAMING after #562's diagnosis (§7 gaps).
3. Does the repaired carryforward change the funnel at all? → forward data from 08-11; ~2–3
   weeks of accrual before the funnel is re-cut honestly.
4. Which of the operator's four SE conditions are worth encoding, and can condition 3 (Stage 2)
   exist without a stage classifier? → unowned (§7 gaps).

**Labelled recommendation (one, delayed):** #562 is the gating item of the whole program — a lane
whose actionable stage fires 1-in-104 is the largest un-opened surface, and its diagnosis costs $0
(code reading + funnel counting on retained data).

---

## 5. Surface 4 — EXIT

**GOAL (operator's framing):** harvest a low-win-rate, fat-right-tail population — bank the
excursion instead of round-tripping it. The measured leak: live cohort (n=17 read, 08-08) REACHED
+1.54R on average and KEPT −0.91R; 8 of 17 touched +1R, 5 touched +2R, all closed losers
(`docs/setups/exit_discipline.md`). The only large gains today sit in OPEN positions (§0.1) — the
winners are the trades we have not closed.

**WHAT IS LIVE TODAY** (toggles verified in prod 08-11)
- Hard stop @ ORB low; **raise-only floor enforced against the broker** (08-10 bug fix — a stale
  DB value could previously let a trail pass LOWER a live stop).
- **+2R partial (1/3) via RESTING LIMIT at the target** (`profit_take_resting_limit`, on 08-10;
  replaces the 5-min-poll → market sell that filled FIGS at +1.13R instead of +2R).
- **Breakeven at the broker on partial** (`breakeven_at_broker`, on 08-10; previously breakeven
  was TRUE in the DB and absent at the broker — FIGS stopped at the ORIGINAL stop 6h before any
  daily pass could act). `partial_exit_leg_safe` on (bracket-leg cancel-then-new, the only
  mechanism Alpaca permits).
- **Seeded MA trail** (08-08 fix): the 10/20-SMA trail now uses the STOCK's history, not the mean
  of our holding period — it can act from day 1 instead of being structurally dead on ≤2-day holds.
- Day-3/5 time partial superseded by `PROFIT_TRIGGER_R = 2.0` (08-01, operator-signed). Giveback
  peak-lock: built dark, no live caller (#306).
- ⚠ **The 08-10 stack is UNFIRED: zero `profit_trigger_*` / `partial_exit_*` audit events since
  08-10** (prod). Per the standing lesson, a rule is not live until it has fired once — deployed
  + green is not evidence it can act.

**WHAT IS MEASURED**
- Replay evidence behind the +2R rule: 36 closed trades, 34 candidate rules, +0.43R vs actual
  under the REAL poll fill; not expected to change win rate — it makes losses smaller
  (`exit_discipline.md` 08-01 entry). The one live firing under the OLD mechanism (FIGS) lost
  −0.37R to two defects, both now fixed and both fixes unfired.
- Seeded-trail replay over every recorded trade: paper n=33 mean +0.64R → +1.27R (8 better /
  2 worse); live has only 3 measurable trades — 15 of 17 closed same-day before any daily pass
  could run.
- Harvest capture KPI: partial-taken winners captured 18% of aggregate MFE ($5.9k of $32.8k
  peak), 3 round-trippers (#306 STEP-0).
- ⚠ Regime cell: ALL closed live trades were taken in Correcting/Choppy/Crisis, ZERO in Bull
  (measured 08-06) — every exit conclusion we hold is a non-bull conclusion
  (`exit_tune_bull_regime_read` fires at 8 bull closes; today 0).

**OPEN QUESTIONS**
1. Does the resting-limit + broker-breakeven stack actually bank the excursion? → its first live
   firings, plus the pre-committed watch triggers (partial fires → remainder scratched → runs
   ≥+4R same session: once = review, twice = revert).
2. Is the trigger unit right — R vs daily ranges? Entry-to-stop spans 0.15–1.17 ADR (7.7×), so
   "+2R" is not one distance (`exit_discipline.md` limitation 3). Unresolvable on current data;
   accrues with the cohort reviews.
3. Hold rules for the fat tail — next-day / N-day, character-conditioned time exits (the biotech
   note), trail-by-character? → the #545 program grid + #306 STEP-2 sweep; the sample clocks are
   `exit_tune_cohort_review` (n=20/40/60 — at 19 closed, the n=20 review fires on the next close)
   and the bull-regime read.
4. Is the exit even the binding surface? `exit_discipline.md` limitation 5, verbatim: the shadow
   ORB control — same alerts, no broker — shows zero winners across bull AND correcting months;
   *"exit changes make losses smaller; they are not expected to make the strategy profitable."*
   The binding constraint may be upstream (selection/entry geometry) — which is why this program
   holds the four surfaces together.

**Labelled recommendation (one, exit):** let the just-shipped stack run its 14 trading days
untouched — it is the clock #559 is pinned to, and every further exit change resets the
comparability window for BOTH surfaces.

---

## 6. INTERACTIONS — how a change on one surface invalidates evidence on another

This is the part that makes the program holistic. Each edge is a standing constraint on sequencing.

1. **Exit → everything.** Every realized-R and P&L statistic to date was measured under an exit
   stack that materially changed on 08-01 and again on 08-10. #559 already encodes the
   consequence: admission cannot be re-measured until 14 trading days of the NEW exits accrue
   (08-31). The same logic applies to any surface that would consume realized outcomes — which is
   why the program's outcome variable moves to the alert (§1), which is exit-independent.
2. **Ranking → zero variance.** Selection evidence on realized outcomes is unusable while 19 of
   19 lost (§1). Any conclusion of the form "grade X performs better" is currently undefined.
3. **Theme coverage → ranking (PREREQUISITE, not parallel).** Theme membership cannot be a
   ranking feature while absence is ambiguous (§2): SE (coverage miss) and FRMI/BW (true
   negatives) carry the same value with opposite meanings. #563's number — do the 357 unlinked
   same-day pairs contain groups we should have had? — decides whether the feature is usable.
   Sequencing: #563 before (or inside) #533's theme-feature readout.
4. **Entry geometry → selection evidence.** 20 of 21 bracket losers rose over 5 days (#468b): a
   day-1 stop-out does not mean the pick was wrong. Judging selection by trade outcomes punishes
   the picker for the bracket. Alert-level outcomes break this entanglement.
5. **Entry gap floor ↔ delayed entry.** A false entry block (SE) is only a full loss if no
   delayed lane exists to catch the name later. The blocking policy (#559 fork) and the delayed
   capability (#562) should be decided TOGETHER: a working delayed-EP lane lowers the cost of a
   conservative gap floor, and conversely, tightening entry without a delayed lane forfeits the
   64% of failed names that run within 21 days.
6. **Re-entry disabled → delayed entry is the only second chance.** Same-day re-entry was killed
   on 0-for-7 (R3); both 08-11 stop-outs show `block:r3_reentry_disabled`. Next-day and N-day
   re-entry variants have never been swept (#545) — the operator's own TEAM fill is the existence
   proof of the tactic.
7. **Carryforward repair → funnel history.** The watch-list input was dark ~7 weeks; funnel
   death-point attribution before 08-11 is measured on a broken input. Clean accrual starts now;
   re-cut the funnel in ~2–3 weeks, not tomorrow.
8. **Calendar → grade and cadence.** Alert volume and grade inflation both peak in earnings
   season — the selection question is hardest exactly when the per-day sample is biggest and the
   evidence noisiest. Within-day analysis must not pool earnings-window days with quiet ones.
9. **Regime → external validity.** All closed live trades are non-bull; nothing measured yet
   transfers to a bull tape. The bull cell fills only by trading through one
   (`exit_tune_bull_regime_read`).
10. **Sizing (out of scope, named because it interacts).** At ~$760/trade (#556), dollar totals
    are small and floors calibrated for institutional risk may be mis-scaled; all program
    readouts should be in R, not dollars. Sizing itself is untouched and operator-owned.
11. **Judge/rubric changes → #533 (selection axis analogue of edge 1).** #533's within-day
    readout scores alerts on TODAY's stored features, including the grade. If #335 flips the
    theme-axis weight or #368's weighting decision lands mid-measurement, #533's readout stops
    describing a fixed system — same comparability problem edge 1 states for exits, on selection.
12. **Grade recalibration (§9 fork 2) → #197.** #197's cap+1 game_changer shadow is
    promotion-gated on N≥30 fires of TODAY's game_changer population. If the operator's
    recalibration fork lands (reserving the grade, making it rare), the population #197 is
    accruing against changes mid-count — its N≥30 would mix pre- and post-recalibration fires.
13. **Theme-engine structural work → #563's coverage count.** #563 counts 357 same-day
    ticker/theme pairs against the CURRENT `mi_themes` snapshot. #553 (false-merge fix), #529
    (crypto↔AI-infra merge, blocked_by #471), and #505/#506 (parent-child repair) all change
    that snapshot's shape. Landing any of them mid-#563-measurement moves the denominator #563 is
    counting against — sequence #563's read around them or re-cut after they ship.
14. **#560's cost verdict → #563's input.** #560 measures theme-assignment's steady-state dollar
    cost and states it will "pull it if the backlog does not clear." A pull changes what gets
    assigned at all — the exact coverage #563 is counting. The two should be read together, not
    independently.
15. **The 08-06/08-07 catalyst-extractor outage (#543) sits inside the doc's own cited
    earnings-window sample.** #543: `catalyst_metrics_extractor` threw on every call from
    2026-08-06 for ~2 sessions, wrongly grading 14 earnings names/day as weak on an exception —
    including the 08-07 software cohort (§2, #471). §1 calls 08-04..08-07 "most of the usable
    within-day sample" for the ranking question. Any grade-inflation or within-day-ranking
    conclusion drawn from 08-06/08-07 specifically is partly an artifact of a since-fixed
    extraction bug, not pure selection signal. (Also §8 blind spot 11.)
16. **HTF/Family-A tuning → #562's funnel diagnosis.** #562 is auditing WHERE the 104 alpha
    names die in the TRIGGERED funnel, on the hypothesis that it borrows HTF's 90%/40d runup
    gate (#356). If #394 (coil-finder tune) or #397 (HTF money gate) change those thresholds
    while #562 is mid-diagnosis, the funnel's death-points move under the audit — sequence #562
    before further HTF threshold changes, or re-read it after they land.

---

## 7. TASK INVENTORY — what is filed, where it lives, and the gaps

Format per task: **#ID (substance — status, ETA).** All PLAN.md lines below now carry a matching
reverse pointer back to this doc + their surface (`[ep_profitability_program.md — <surface>]`) —
navigable both directions. Board count unaffected (link-only edits).

**Selection / ranking:**
- #533 (within-day ranking + does the grade mean anything — in_progress, due 08-12, top priority)
- #448 (B6 rubric backtest, pooled — pending, due 09-15)
- #368 (theme-axis weighting + operator labeling — in_progress, due 08-12; the live block is
  the operator's labeling pass, not the task status)
- #335 (theme-axis load-bearing flip — pending, due 08-25)
- #486 (judge↔theme cross-validation — pending, due 08-15)
- #519 (chart-vision offline proof — in_progress, due 09-01)
- #547 (grade-surface regression gate gap — pending, due 08-12)
- #331 (gap-vs-structure axis — blocked, due 08-25)
- #333 (catalyst durability axis — pending, due 08-14)
- #452 (correlated-book shadow; operator ruled 08-11 don't promote the cap — deployed, due 09-01)
- #561 (readable weekly movers surface — pending, due 08-29)
- **#504 (NEW — not previously linked here). META-RUBRIC ROADMAP: sequences #368 → weight
  calibration → #335's load-bearing flip, and names "arbitrate between competing EPs for limited
  slots" as a first-class rubric portfolio use — the closest thing gap 4 below has to an owner
  today (pending, due 08-13).**
- **#560 (NEW). Measures the steady-state DOLLAR cost of theme assignment and states it will
  "pull it if the backlog does not clear" — the backlog it is measuring IS the coverage gap
  #563 counts, so a pull decision here changes #563's input (pending, due 08-18).**
- **#197 (NEW). cap+1 game_changer slot SHADOW, promotion-gated N≥30 — a live slot-allocation
  experiment conditioned on the top grade, directly touching §9 forks 1 and 2 (in_progress,
  due 08-18).**

**Entry:**
- #559 (admission re-cut 08-31 + NEW false-block split — pending, due 08-31)
- #541 (trigger-at-ORB-high — blocked, operator fork, due 08-13)
- #482 (bracket-geometry lab — pending, due 08-16)
- #556 (ADV floor vs actual size — pending, due 08-13)
- #557 (cooldown cost — pending, due 08-14)
- #359 (mcap floor review — pending, due 09-22)
- #540 (deployed mechanism fix, Alpaca rejection reasons — deployed, due 08-21)
- #414 (deployed mechanism fix, stop-limit gap/no-trigger — deployed, due 08-13)
- #545 (program frame — pending, due 08-14; spans Entry/Delayed-entry/Exit, see below)
- **#488 (NEW — reclassified off the doc's own text, which was headed toward delayed entry on
  the RMV/consolidation-guard mention; the task itself says the halt-data capture "helps the LIVE
  ORB path (not the nightly consolidation guard)" — that is Entry). Authoritative halt data via
  Alpaca-WS `statuses`, gated on operator entitlement confirmation (pending, due 08-15).**

**Delayed entry:**
- #562 (what IS the trigger — the gating diagnosis — pending, due 08-11, due now)
- #545 (delayed/re-entry variants + the TEAM worked case — see Entry above for status)
- #270 spec (`delayed_ep_reentry.md`, wiring gated — no open PLAN.md line; PLAN.md line 31 marks
  it close-pending/done, doc-only reference now)
- #297 (Family B EP rework — pending, due 08-13)
- #354 (Family-A merge — in_progress, due 09-15)
- #327 (consolidation shadow→paper ladder, step 3 — in_progress, due 08-30)
- #353 (consolidation entry→paper graduation — blocked, due 08-12)
- #394 (coil-finder tune — pending, due 08-16)
- #397 (HTF money gate — pending, due 08-21)
- #283 (wick_fill promotion — pending, due 09-01)
- **#356 (NEW — background, not an active open question). HTF Setup 2 detection — deployed,
  verify-live confirmed 6/29, ETA 08-12 is a re-check date not a verify date. This is where the
  90%/40d runup gate #562 is auditing as the TRIGGERED logic's likely borrowed parameter set
  actually comes from (`docs/setups/htf.md`) — listed for traceability, not as unfinished work.**

**Exit:**
- #548 (resting-limit + breakeven — deployed, verify-live due 08-14)
- #306 (winner harvest STEP-2 sweep — deployed, due 08-21)
- #545 (program grid — see Entry above for status)
- #523 (stop-coverage leg repair — pending, due 08-11, due now)
- #525 (breaker account-mode split — deployed, due 08-11)
- #528 (CRMD recorder skip) — **CLOSED 2026-08-09 (commit `1f2374f`), verified in production.**
  Kept here as historical context only; it is not open work and carries no PLAN.md line.
- `exit_tune_cohort_review` (fires at n=20 — next close)
- `exit_tune_bull_regime_read` (fires at 8 bull closes; 0 today)

**Cross-surface / measurement:** #563 (theme coverage of EP gaps — PREREQUISITE for ranking's
theme feature — pending, due 08-15) · `mi_ep_missed_outcomes` + #468 probes +
`ep_delayed_capture_audit.py` (the alert-level outcome machinery, already built).

⚠ **Deliberately NOT added above** — the ADR-0032 theme-hierarchy program (#538, #529, #530,
#505, #506, #491, #553, #555, #554, #551) is a separate initiative (theme parent-child, merges,
thesis-identity) the operator has not named as ranking work; only #563 (coverage) and #560
(assignment backlog/cost) are that direct. Four of those IDs still matter to this program as
**evidence sources**, not owners — see §6 interaction 13.

**⚠ THE GAPS — questions with NO owning task** (the "no stones unturned" list):
1. **Stage-2 / trend-context classifier** — SE condition 3, named by the operator as part of his
   own trigger; no task exists anywhere. Biggest single capability gap on the board.
2. **Acting on grade inflation** — #533 MEASURES whether the label means anything; no task owns
   the recalibration fork if it confirms (reserving game_changer is a judge/rubric change:
   CHANGE_PROCESS + sign-off). #448's decision matrix covers `composite_min` only. #197's cap+1
   shadow is adjacent (a slot-COUNT experiment) but does not own recalibration either.
3. **Naming the delayed-EP SETUP** — #562 stops at diagnosis + options; no task owns defining the
   buy point + stop and standing up its shadow lane after the operator rules.
4. **Ranked slot allocation at entry** — the alphabetical selection is measured (#533) but no
   task owns building a ranked alternative; deliberate (entry discipline = his call), but once
   #533 reports, the fork needs a home. #504's roadmap NAMES this use ("arbitrate between
   competing EPs for limited slots") without yet building it — closest thing to a future owner.
5. **Gap-floor re-look mechanism** — #559 counts false blocks; nothing owns the design question
   "should a blocked name get a second sample inside the ORB window", which is the SE-class fix
   if he wants one.
6. **Theme-STRENGTH features at alert time** — stored per-theme, never joined to the alert;
   #563 owns coverage and #368 owns judge weighting, but nobody owns making rs_avg / stage /
   member count / acceleration available as alert-row ranking features (smallest gap — could fold
   into #533's feature assembly).
7. **Earnings-season conditioning** — the operator's "we buy every day into randomness" has no
   task asking whether the bar, the cap, or the cadence should be season-aware.

---

## 8. WHAT WE CANNOT MEASURE TODAY — known blind spots, stated as findings

1. **Recorded intraday peaks are floors.** `highest_price_seen` polls ~10-minutely; four live
   trades lived 0.8–11.7 minutes, so their recorded MFEs understate truth (CRCL's real peak was
   +1.62R against a recorded 0.00). Minute-bar reconstruction is possible per-name but is not
   what the tables hold (`exit_discipline.md` limitation 2).
2. **The new exit stack has never fired.** Zero trigger/partial events since 08-10 — its effect
   is unmeasurable until first fire, and the #559 clock runs on trading days, not firings (a
   zero-firing window is itself a defined answer: HOLD stands).
3. **Open-position censoring.** The only positive outcomes (PLTR, ABCL) are open and excluded
   from every realized statistic by construction. Any "0 winners" headline must carry this.
4. **The gap floor's historical false-block rate** — blocks were logged, reclaims were not
   counted; the split exists only from #559's added DoD forward.
5. **The delayed funnel's history is contaminated** by the 7-week dark carryforward; only
   post-08-11 funnel data is clean.
6. **Theme absence is uninterpretable** until #563 (coverage vs true negative — §6.3).
7. **The bull cell is empty.** 0 closed live trades in a Bull regime; nothing measured transfers.
8. **Per-session N is tiny.** ~20 sessions in 60 days, fewer with real multi-alert choice; the
   within-day question accrues at ~1 observation per trading day.
9. **Retention floors:** `mi_ep_alerts` from 2026-05-11, `mi_flag_candidates` from 2026-05-04,
   `mi_daily_closes` from 2025-07-07, `mi_themes` from 2026-03-19 (prod MIN() checks 08-11) —
   lookbacks beyond ~3 months lean on `mi_ep_missed_outcomes` (from 2026-02-11) only.
10. **The human baseline is not fully specifiable.** The operator's own delayed entries — the
    thing the machine is meant to approximate — are, in his words, *"no hard rule so hard to
    copy"*; the SE four-condition read is the closest labelled example we hold.
11. **Two of the four earnings-window days are contaminated by a since-fixed extraction bug.**
    #543: `catalyst_metrics_extractor` threw on every call 2026-08-06 through ~08-07, wrongly
    grading 14 earnings names/day as weak and caching the failure. §1 names 08-04..08-07 as
    "most of the usable within-day sample." Grade-inflation and within-day-ranking reads that
    include 08-06/08-07 are measuring the bug's blind spot along with real selection behavior
    (§6 interaction 15) — not separable after the fact without re-deriving those two days' true
    grades from raw catalyst text.

---

## 9. The operator's open forks, collected (nothing pre-decided)

| # | fork | evidence it waits on | cost of each branch |
|---|---|---|---|
| 1 | Ranked vs first-come slot allocation | #533 readout (08-12) | keep: slots stay alphabetical; change: entry-path selection change (CHANGE_PROCESS) |
| 2 | Reserve game_changer / recalibrate the grade | same cohort readout | keep: modal top grade carries no signal; change: judge-surface recalibration, needs a task (§7.2) |
| 3 | Gap floor: keep single-sample vs add a re-look | #559's false-block split (08-31) | keep: SE-class misses; add: re-admits genuine faders (WKC/QBTS class) |
| 4 | RT admission flip (universe + gap authority) | #559 re-cut post-exit-stack | flip early: re-measures old exits; hold: the NVVE/TRAX-class residual stays uncaught |
| 5 | Name the delayed-EP setup (buy point + stop) | #562 diagnosis + his ruling on the candidate entries | until named, delayed EP stays a family, not a tradeable |
| 6 | Trigger at vs above the ORB high | #541 (blocked on him) | at: venue kills on fast gappers (mitigated by ask-aware); above: pays up on every entry |
| 7 | Bracket geometry (1-min ORB vs alternatives) | #482 shadow accrual | keep: the shaken-out-winner pattern persists; change: money-path geometry change, N≥10 + sign-off |

---

*Sources are inline throughout: prod queries run 2026-08-11 over `mi_live_trades`, `mi_ep_alerts`,
`mi_stock_scores`, `mi_themes`, `mi_flag_candidates`, `mi_safeguard_state`, `mi_audit_log`,
`mi_ep_missed_outcomes`; docs `magna53_ep.md`, `exit_discipline.md`, `flag_continuation.md`,
`htf.md`, `delayed_ep_reentry.md`, `operator_shared_notes.md`, ADR 0003; PLAN.md task lines;
commits `16b627e`, `92f3873`, `237f516`, `96c6823`, `93dcd21`, `0627692`; probe outputs
`_p74_post_ship_audit.md` and the `_468*` series. Numbers not re-derivable from these are marked
unmeasured.*
