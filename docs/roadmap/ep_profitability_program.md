# The Real EP Plan

**Canonical location: `docs/roadmap/ep_profitability_program.md` (filename kept as-is so existing
task cross-links hold) — named 2026-08-12 so all EP work has one place to ground from.**

**Created 2026-08-11 (operator: top priority — "not that we need to find an answer but we need a
path to it"). This is a FRAMING document: goals, what is measured, open questions, task coverage,
and blind spots — across all four surfaces at once, so the operator can direct the work from one
place. It proposes NO change to any strategy, threshold, rubric, or toggle. Every selection, entry,
exit, and sizing decision named here is the operator's (THE LINE). Where a fork exists it is stated
as his decision with its cost. Each surface carries at most ONE labelled recommendation.**

**Consolidated 2026-08-12 (operator: "we should be systematic... not fragmented work").** His two
2026-08-12 findings — the "what is a real EP" reframe and his pushback on the structure readout —
and the #562/#545 corrections that had only ever landed in PLAN.md or chat are folded in below.
This doc, not chat or `operator_shared_notes.md`, is where an EP question's current answer lives;
§1a is the single register of what's open, §1b is the sequence for what's next.

---

## GOAL — and the rule that governs every finding below

**GOAL — make EPs PROFITABLE: filter the universe on all the factors that matter, not just a gap,
so that a small win rate is carried by winners large enough to give positive expectancy.**

At a 20% win rate with 1R losers, the average winner must exceed **4R just to break even**
(0.2 × W = 0.8 × 1R → W = 4R). **Win rate and reward are ONE target, never two** — ~20% is the
operator's rough marker (2026-08-12), not the objective standing alone (his correction, same day,
to an earlier one-line-goal draft of this same section).

**How each surface serves it, and the test for whether new work belongs in this doc:** Selection
filters the universe down to real EPs. Entry captures what survives the filter without losing it to
mechanism. Delayed entry catches the ones the first attempt missed. Exit keeps what the winners
give instead of round-tripping it. Anything below that does not tie to one of those four is flagged
as such, not quietly kept.

**Why this couples Selection and Exit, not two separate goals:** being more selective raises the win
rate; letting winners run raises R. Neither alone reaches positive expectancy, and a change that
helps one while damaging the other is a net loss — every future proposal must be judged on BOTH.
This is the arithmetic behind the operator's 2026-08-11 ruling to let winners run (no peak-lock
giveback floor): at a 20% win rate, capping winners near +2.6R — what a half-of-peak floor would
have done to PLTR — is mathematically fatal, since 4R is break-even (`docs/setups/exit_discipline.md`
2026-08-11). It also reframes §0's headline number: 0-of-19 is not only a bad win rate — the cohort
on average REACHES +1.54R and KEEPS −0.91R (§5) — both terms of the equation are failing at once.

**⚠ NO SINGLE TRADE IS EVIDENCE (operator, 2026-08-12) — this governs how every finding below may be
read.** Verbatim: *"some that look exactly like a EP may end up being a loser, that happens and
expected, we cant expect perfection and guarantees... The opposite is also true, we may miss trades
that aren't EP per our criteria and they go on to be big winners, that is also ok, provided our EPs
gives us positive return that is worth the risk."* A textbook EP can lose — expected, not a defect
in the criteria. A name correctly excluded can run — also expected, not a miss. The only thing that
can be engineered is positive expectancy ACROSS MANY TRADES. **Every claim below is a distribution
with its N and its distinct sessions; a single case illustrates a mechanism and never carries a
conclusion by itself.** Applied to what is already in this doc:
- **SE (2026-08-11)** illustrates the gap floor's mechanism (one point-in-time sample, no re-look)
  — not a finding that the floor is wrong. Whether it's right needs the full block distribution
  (#559), which does not exist yet.
- **BW / FRMI (2026-08-11)** illustrate what loose admission can let through; two losers in one
  session do not establish that admission is loose.
- **The 19 closed live losers** are a run long enough to be worth explaining, but still one
  strategy over roughly nine weeks — it licenses "look hard for a mechanism," not "the approach is
  broken."
- Read "shows"/"proves" on any single-session case below as "illustrates" instead.
- **Corollary for the sequence (§1b): a question that can only produce anecdotes is not scheduled
  next.** If a question needs a distribution and doesn't have one, the next step is collecting
  observations, not re-analyzing the few that exist.

Every figure below is from prod (query named) or an in-repo doc (path named), verified 2026-08-11.
Nothing is estimated; unmeasured things say "unmeasured".

---

## 0a. WORKED EXAMPLES — the operator's own cases, kept HERE so they are not buried

⚠ **This table is deliberately at the TOP and deliberately SHORT.** Operator, 2026-08-12: *"make
sure all these are durably captured, we'll keep collecting evidence but don't want these important
context and examples being lost in bigger doc as we move forward."* Every row is a real named case
he raised; the one-line entry is the index, the verbatim capture lives in
`docs/methodology/operator_shared_notes.md` under the dated heading. **Add rows; do not let this
grow into prose.**

| Case | Date | What it illustrates | Verbatim |
|---|---|---|---|
| **NBIS** | 08-12 | **The first FALSIFIABLE structure definition** — clears a level that previously rejected price (50-day; prior highs ~$227), then HOLDS it after the first pullback. Failure case stated too: gaps and falls back below, or never breaches. Also: graded "moderate" on a marginal beat while revenue grew >400% — surprise vs magnitude | notes 08-12 |
| **HTFL · ETON · VERA** | 08-14 | **A LABELLED PREDICTION, stated PRE-OPEN** — HTFL/ETON clearing key levels near or above all-time highs (strong); VERA chopping above a few days' range but still deep in a downtrend (**weakest, he would not trade it**). Score the outcome and compare to our grades — the label was fixed before the result | notes 08-14 |
| **EROC** | 08-12 | A CORRECT skip (stop too wide, 1.5×ATR) on a name he judged a good EP — the skip taxonomy, and the join into delayed entry: "no today" is not "no forever" | notes 08-12 |
| **SE** | 08-11 | His four delayed-EP conditions, stated on a live name. Skipped by the gap floor at 9.2% vs 10%, reclaimed +10.5% in four minutes. RS 88.5, above all MAs, **in no theme at all** — the coverage gap in one stock | notes 08-11 |
| **BW / FRMI** | 08-11 | Gap size ranks backwards: BW gapped 34.9% at RS 1.5 (rank 2397), FRMI 17.0% at rank 1661 — both below every MA, both dead inside 60 seconds. "A gap is a signal, not the setup" measured | plan §2 |
| **ABCL** | 08-11 | The +2R rule's first correct live firing — limit filled AT the $10.08 target, stop to the $8.96 entry the same second | plan §5 |
| **FIGS** | 08-07 | The two defects that opened the exit work — market sell filled +1.13R against a +2R target; "stop moves to breakeven" was a DB flag the daily pass read, hours too late | plan §5 |
| **PLTR** | 08-05→ | Breakeven did NOT cap the runner — partial taken, stop to entry, still open at ~+4.6R six days later. The evidence behind "we let winners run" | `docs/setups/exit_discipline.md` |
| **The 5 missed stories** | 06-15→07-31 | AUGO+HYMC · MU+SNX · HUT+IREN · EME+PWR · COHU+MPWR — 5 of the 9 clear same-day co-gap stories in 60 days; 4 were grouped the same night and discarded at the 3-member floor | plan §563 |


## 0. The situation, in five verified facts

1. **19 closed live trades in 60 days: 0 winners, 19 losers, −$416.19 total. Best trade −$2.40.**
   (`mi_live_trades WHERE account_mode='live' AND status='closed' AND alert_date >= CURRENT_DATE-60`,
   prod 2026-08-11.) The honest statement is "nothing has been TAKEN as a win", not "nothing works":
   the only positive results are the two OPEN positions — PLTR (entered 08-04 @ $149.05, 4 of 6
   shares remaining after a partial that banked +$33.27; ~$175 on 08-11) and ABCL (85 sh @ $8.96,
   entered 08-10; ~$9.69 on 08-11). **His numbers, stated once (2026-08-12): target win rate ~20%
   (see GOAL above for why that number alone isn't the goal); his stated fear is 10% or below;
   measured reality is worse than the fear.**
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
   +10.5% within four minutes. The two names we entered died inside 60 seconds. **One session — it
   illustrates the mechanism this program investigates, not a proven pattern (GOAL section above).**
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

## 1a. OPEN QUESTIONS REGISTER — every question and concern he has raised

**Single source** — the per-surface sections below (§2–§5) point here instead of repeating their
own lists. Per the GOAL section: **Status reflects whether we have a DISTRIBUTION, not whether one
case looked persuasive.** "Answered by" names the thing that would actually move the status.

1. **What makes a REAL EP, not just a gap?** [Selection] Belief: a gap is a necessary signal, not
   sufficient — today a big-enough gap plus catalyst grade effectively passes as the EP itself, and
   the grade carries no separating information (game_changer = 59% of alerts, 0 winners on either
   top grade, §0.2). Answered by: a real-EP winner reference set (row 2), not a re-run of the same
   null. **Status: OPEN — reframed 2026-08-12.**
2. **Is chart structure a usable filter, and how do you encode "part science, part art"?**
   [Selection] Belief: one crude binary (above all 3 SMAs, fixed-lookback high-clears) was tested
   and ruled OUT as the encoding — his objection is that lookback and MA-relevance are contextual,
   not fixed (§2). Includes the Stage-2/trend-context classifier gap (his SE condition 3) — does
   not exist. Answered by: a reference set of real EP winners from OUTSIDE our fills (unowned,
   §7 gap 8) — not another feature swept against our own zero-winner cohort. **Status: OPEN — one
   bad proxy ruled out, the concept itself untested.**
3. **What is "delayed entry," and what are its shapes?** [Delayed entry] Belief: it is a FAMILY,
   open horizon (same day / next day / next week) — NOT the flag-stage watch machine and NOT only
   the 620 timing tool; both were explicitly ruled out by him as THE definition, same day (§4).
   Buy point + stop remain unnamed; candidates in evidence (FIRST5-break, base-then-turn/TEAM,
   reclaimed-floor/SE) await his ruling once shapes are enumerated. Answered by: HIM naming the
   shapes he actually trades — step 1, not ours to infer (#562). **Status: OPEN — blocked on his
   enumeration.**
4. **Are we too loose, and therefore overtrading?** [Selection] Belief: his concern, evidenced by
   alert cadence tracking the earnings calendar (1–2/day quiet weeks, 7–10/day earnings weeks) and
   grade inflating on the same days (§0.2–3). Answered by: an earnings-season-conditioned selection
   measurement — no task owns it (§7 gap 7). **Status: OPEN — unowned.**
5. **Does theme membership belong in selection?** [Selection] Belief: cannot be used until absence
   is unambiguous — SE (coverage miss, his SE condition 4) and FRMI/BW (true negatives) carry the
   same "no theme" value with opposite meanings (§2). Answered by: #563's judged read of the
   unlinked same-day pairs (run 2026-08-12, dated section below): **5 clear one-story miss pairs
   of 351 (1.4%, 5 of 27 sessions; 8 of 351 / 2.3% with probables)** — pair-level absence is a
   true negative ~98% of the time, but 4 of the 5 clear misses were same-night cogap groups killed
   at the 3-member floor, so "no theme" still cannot be read as "no story" without checking the
   discarded-cohort surface. **Status: ANSWERED 2026-08-12 — coverage measured; the fork returns
   to the operator (see the dated section); the ranking prerequisite is satisfied.**
6. **What is a realistic win rate?** [Selection, program-wide] Belief: his target ~20%, coupled to
   reward per the GOAL section (4R average winner needed at 20%); his stated fear is 10% or below.
   Measured: 0 of 19 closed live trades won. Answered by: a larger, cleaner outcome sample (the
   alert-level variable, §1) — 0/19 is a floor stat on an all-losing run, not a rate estimate.
   **Status: OPEN / UNMEASURED beyond the raw count.**
7. **Why does the alert run while the bracket dies, and which geometry fixes it?** [Exit/Entry]
   Belief: mechanism identified — the 1-minute ORB stop (~3% range) shakes out real winners; 20 of
   21 HIGH-cohort bracket losers rose over the next 5 days (#468b, n=21), reconfirmed 08-12 (6 of
   14 settled losers' alerts ran ≥+5% within 5 days, n=14) (§6.4). Answered by: which alternative
   geometry has edge — #482's shadow accrual (5-min lane currently WORSE, 0/14) + the #545 grid.
   **Status: PARTIALLY ANSWERED — mechanism known on a real N; fix unproven.**
8. **Has re-entry after a stop-out actually been tested?** [Entry/Delayed entry] Belief: same-day
   1-min re-entry (R3) tested, killed on 0-for-7. Same-day 5-min-range re-entry tested 08-09 on the
   full 17-trade stop-out set — fired 9 of 17; net looked positive only because of ONE outlier
   (THC, +12.43R on a razor-thin stop); the other 8 net −4.67R, the same failure shape R3 was
   killed for. Next-day / N-day re-entry: never tested. Answered by: #545's grid — sweep next-day/
   N-day + a mechanical proxy for his TEAM-style "base-then-turn" re-entry. **Status: PARTIALLY
   ANSWERED — same-day tested twice and looks weak; next-day/N-day open.**
9. **Should a blocked gap-floor entry get a second look inside the ORB window?** [Entry] Belief:
   SE's 08-11 skip illustrates the mechanism (single point-in-time sample, no re-look) — it is not
   evidence the floor is wrong (GOAL section). Answered by: #559's 08-31 false-block split — the
   full distribution of everything the gate has ever blocked. **Status: OPEN — evidence-gated,
   named fork §9.3.**
10. **Should entry slots be ranked rather than first-come/alphabetical?** [Selection/Entry] Belief:
    today's entry path has no ranking at all (alphabetical by ticker). The 08-11 board illustrates
    that it can matter (SE ranked last, was the only strong name) — one session. Answered by:
    #533's per-session rank-correlation readout across every multi-alert day. **Status: PARTIALLY
    ANSWERED — in progress, due 08-12; named fork §9.1.**
11. **Does the repaired carryforward change the delayed-entry funnel at all?** [Delayed entry]
    Belief: unknown — the feed was dark ~7 weeks (fixed 08-11), so funnel history before that date
    is measured on a broken input; clean accrual starts 08-11. Answered by: ~2–3 weeks of clean
    accrual, then re-cut. **Status: OPEN — evidence-accrual (calendar).**
12. **Does the new exit stack (resting-limit + broker-breakeven) actually bank the excursion?**
    [Exit] Belief: unknown — zero `profit_trigger_*`/`partial_exit_*` events since ship 08-10; a
    rule is not live until it fires once. (Separately, the "+2R" unit itself may not be consistent:
    entry-to-stop spans 0.15–1.17 ADR, a 7.7× range — unresolved on current data.) Answered by: its
    first live firings, plus the pre-committed watch triggers (partial fires → remainder scratched
    → runs ≥+4R same session: once = review, twice = revert). **Status: OPEN — evidence-accrual
    (occurrence).**
13. **What hold/re-entry rules suit the fat right tail** (next-day/N-day time exits, character-
    conditioned trail, a second partial higher up)? [Exit] Belief: unswept beyond the items in row
    8; owned by the #545 grid + #306 STEP-2. Answered by: the cohort accrual clocks
    (`exit_tune_cohort_review` at n=20/40/60; n=20 fires on the next close). **Status: OPEN —
    evidence-accrual.**
14. **Is exit even the binding constraint, or is it upstream in selection/entry?** [Exit,
    program-wide] Belief: the shadow ORB control (same alerts, no broker) shows zero winners across
    bull AND correcting months — "exit changes make losses smaller; they are not expected to make
    the strategy profitable" (`exit_discipline.md`). This is why the GOAL section couples Selection
    and Exit rather than treating either as sufficient alone. **Status: PARTIALLY ANSWERED — exit
    confirmed NOT sufficient alone; selection/entry share the burden, extent unmeasured.**
15. **Are we STORING what next quarter's test needs, before the earnings flow stops?** [Program-wide,
    capture] Measured 2026-08-15 (the dated CAPTURE AUDIT section below): the earnings-window
    `mi_ep_alerts` rows — the richest per-alert record — delete on **2026-11-08** (90d weekly purge),
    the week next quarter's test would start; minute bars exist for only 44% of alert ticker-days
    (traded names only), so the intraday HOLD test / 620 timing / #559 reclaim split currently
    depend on a vendor refetch. Answered by: the operator ordering the audit's ranked gap list
    (1: stop purging `mi_ep_alerts`; 2: intraday-bar retention; 3: minute bars for every alert
    ticker-day). **Status: OPEN — audit done, fixes unordered; retention clock running.**

---

## 1b. SEQUENCE — the systematic path (dependency order, not an importance ranking)

Per the corollary above: a step that can only produce anecdotes is not scheduled — it becomes "get
more observations" instead. Each step tags which part of the GOAL it moves and what it is blocked
on: **operator** (needs his ruling/enumeration) · **evidence-accrual** (needs time/more rows) ·
**capacity** (needs agent time, available now).

0. ✅ DONE — outcome variable chosen: score every alert, not just fills (§1). Everything below
   builds on this. *(serves: measurement foundation for all four surfaces)*
1. **#563 — theme coverage read**, due 08-15. Gates the theme-strength feature before it can enter
   any ranking work (§6.3, register row 5). *(serves: Selection)* Blocked on: **evidence-accrual**
   (his judged sample of the 357 pairs).
2. **#533 — within-day ranking + grade-conviction readout**, due 08-12, in progress. Independent of
   #563 for non-theme features. *(serves: Selection)* Blocked on: **evidence-accrual** (multi-alert
   days).
3. **The structure / "real EP" question specifically** — separate from #533's general readout;
   needs a reference set of real EP winners from OUTSIDE our fills before any conclusion is
   possible (his 08-12 correction, register row 2). No task owns building this set; scoping it
   (source, sample size, method) is his call, not ours to invent. *(serves: Selection)* Blocked on:
   **operator** (unowned gap, needs his scoping) + **capacity** once scoped.
4. **#562 — delayed-entry enumeration.** Step 1 is HIM naming the candidate follow-up shapes; no
   further code-reading on the flag-stage machine is useful until he does (his own correction,
   twice, same day — register row 3). *(serves: Delayed entry)* Blocked on: **operator.**
5. **#482 — bracket-geometry shadow accrual.** Keep 1-min ORB live; accrue alternatives to N≥30
   (5-min lane currently WORSE, 0/14 — geometry is not an obvious fix, register row 7).
   *(serves: Exit, via entry geometry)* Blocked on: **evidence-accrual** (time).
6. **#559 — admission re-cut**, 08-31. Pinned to 14 trading days after the 08-10 exit-stack change
   — re-measuring sooner would just re-measure the old exits. *(serves: Entry)* Blocked on: **the
   calendar** (a form of evidence-accrual).
7. **The 08-10 exit stack's first live firing** (resting-limit + broker-breakeven, register row
   12). Zero fires since ship; unmeasurable until it acts once. *(serves: Exit — the "keep the
   winners" half of the GOAL arithmetic)* Blocked on: **evidence-accrual** (occurrence).
8. **The recalibration forks** — grade reservation, ranked slots, gap-floor re-look, naming the
   delayed-EP setup (§9) — each waits on its evidence step above landing, then is an **operator**
   ruling, not an agent decision.

Capacity note: this is a sequence, not a sprint plan — "we don't have to do everything today or
tomorrow" (his words). Steps 1, 2, and 5 are the only ones needing agent time now; step 3 needs his
scoping before agent time is useful; step 4 needs his time, not ours.

---

## 2. Surface 1 — SELECTION / RANKING

**GOAL (operator's words):** *"does it capture the main goal of selecting best EPs in a given day
when there's many?"* (2026-08-05) · reserve HIGH/game_changer for the absolute best (2026-08-11) ·
themes are part of the ranking (2026-08-11: *"don't forget that themes are important and part of it
as well to the ranking"*), per the north-star chain: subtle RS → early theme → matures → buy before
mainstream. Good = given N alerts and 5 slots, the slots go to the names a strong-group,
leader-context read would pick, and the conviction label separates outcomes.

⚠ **REFRAMED 2026-08-12 (operator, supersedes "which alert should we have taken" above — read this
first).** Verbatim: *"it's not so much just ranking itself, but more what is a real EP... just any
sufficient gap up is a EP which makes us overtrade, gaps are the signal that EP might be there, but
we need to do more to filter for real EPs... we haven't fully implemented the spirit of 'neglected
stock gapping through key levels' that qullamaggie looks at, some of the trades we make it just gaps
into congestion, resistance areas and had no strength to break through it, this is where chart
structure is important."* (full quote: `operator_shared_notes.md` 2026-08-12.) Three claims: (1) a
gap is a SIGNAL, not the setup — today it effectively IS the setup, hence overtrading (register
row 4); (2) "neglected stock gapping through key levels" is only half-implemented — we have the gap,
not the neglect or the key-levels test; (3) chart structure — does the gap clear something or land
in congestion — is the missing criterion (register row 2). The 08-11 board below illustrates it on
one live session — gap size ranked the four names exactly backwards — one session, not a
distribution (GOAL section above).

**WHAT IS MEASURED**
- The worked case, 2026-08-11 (prod-verified, one session — an example, not evidence):

  | name | ep_score | gap | RS comp | RS rank | above 10/20/50MA | theme? | outcome |
  |---|---|---|---|---|---|---|---|
  | RIOT | 115.2 | 17.9% | 32.6 | 1641 | no | 1 | cancelled — ORB unfilled |
  | FRMI | 96 | 17.0% | 31.7 | 1661 | no | 0 | stopped 09:31:40, −$31.49 |
  | BW | 96 | 34.9% | 1.5 | 2397 | no | 0 | stopped 09:31:56, −$49.60 |
  | SE | 54.7 | 10.6% | 88.5 | 281 | **yes** | 0 | **skipped** (gap floor, §3); +10.5% by 09:35 |

  The separation runs the wrong way: our score put the only strong name LAST. **One session — this
  illustrates a possible mechanism, it does not prove one (GOAL section).** Hypothesis (not a
  finding): the score rewards gap size + catalyst grade and has no term for trend context, so a
  dead stock gapping huge outranks a leader gapping modestly (commit `237f516`).
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
  08-11 board illustrates both readings on one session: FRMI and BW were in NO theme and died in 60
  seconds (reads true negative); **SE was ALSO in no theme** (0 `mi_themes` rows in 10 days,
  prod-verified) while the
  operator says the retail group it belongs to is strong (reads coverage failure). Same feature
  value, opposite truths. Board-wide: the latest 7-day theme snapshot dedups to 120 themes
  averaging 2.5 members, 95 of 120 holding ≤3 (prod; the session's earlier `get_active_themes`
  read: 91 / 3.2 / 71-of-91) — and the 08-07 software cohort gapped together while belonging to
  nothing (#471).
- **Consequence: theme membership cannot be a ranking input until absence is unambiguous — which
  makes coverage (#563) a PREREQUISITE of the ranking work, not a parallel track.** (Also listed
  in §6 interactions.) #560's steady-state cost check feeds directly into this: if theme
  assignment gets pulled on cost, #563's coverage input changes under it (§6 interaction 14).

**THE 2026-08-12 STRUCTURE READOUT, and his correction the same day**

Probe `scripts/probes/_533_structure_admission_probe.py` (244 settled HIGH alerts, 2026-05-11..08-11,
5-day forward outcomes; captured once from prod, $0 to re-run) tested whether chart structure at the
gap — one crude binary: prior close above all of SMA10/20/50, plus fixed-lookback high-clears —
separates alerts that ran from alerts that died. **It does not, on this data**, and where a feature
survives tape control its direction is the OPPOSITE of the thesis (gapping through a "blue sky" prior
high did slightly WORSE, not better). The cohort's base rate is high regardless of structure — about
64% of alerts make a high ≥+5% within 5 days whether or not they sit above their moving averages —
and within-session (21 sessions with a genuine choice), the above-all-3 bucket won the day 11 times
and lost 10: a coin flip. The 19 closed live losers were structure-poorer than the board overall (5
of 19 above all 3 SMAs vs a 41% cohort base rate) — directionally for the thesis — but 6 of those 14
settled losers' ALERTS went on to a high ≥+5% within 5 days regardless (HUT, NVCR, SMCI, QBTS, THC,
MANE): the same #468b pattern (§6.4) on fresh names (n=14). The 08-11 board (table above) survives
verbatim in the probe output. **What could not be measured:** no alert after 08-04 has a settled
5-day outcome yet — the exact sessions that motivated the thesis (SE/BW/FRMI, TEAM/FIGS/NET, ABCL)
are still open; re-run is $0 from ~08-18.

⚠ **His pushback (2026-08-12, later) — and he is right.** Reporting this as "structure does not
separate" overclaims what one crude proxy ruled out. His objection, verbatim: *"our sample size is
small, and EPs are rare... chart structure is part science part art, how you determine if it's
gapping up above certain levels depends on what the chart looks like, sometimes you go further back
because we see multiple tests of certain levels that failed previously, sometimes you don't...
The better way to see this is probably to have a few winners to compare it with."* Two separate
errors, both his catch: (1) a fixed binary cannot represent a judgment that is contextual — the
lookback depends on whether the chart shows failed prior tests, and "above the MAs" is only wanted
when the MA is close enough to be realistic; (2) the deeper design error — **you cannot learn what a
winner looks like from a cohort that has zero winners.** All 19 closed live trades lost; hunting for
separation inside an all-losing population was never going to find one. His fix: the next
measurement needs a **reference set of real EP winners from OUTSIDE our own fills** — the question
becomes "what do real winners look like, and how many of our alerts look like that," not "did our
structured alerts beat our unstructured ones." **No task owns building that reference set yet
(register row 2, §7 gap 8, sequence §1b step 3) — this is the unresolved piece, not the null above.**

**Action: none.** No admission change is supported by either the readout or the correction — nothing
tightened, nothing proposed as decided (THE LINE).

**OPEN QUESTIONS for this surface → the consolidated register, §1a (rows 1, 2, 4, 5, 6, 10).**

**Labelled recommendation (one, selection):** run #533's readout with theme-STRENGTH features
joined offline (all inputs are dated and retained — `mi_themes` back to 2026-03-19, so any past
day's board is reconstructible at $0) before any grade or score work is even discussed. This is
separate from — and does not substitute for — the structure/real-EP reference-set question above.

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
- **The gap floor's record through 08-10: 4 blocks, 4 correct** (all faded names, −$46.06 saved on
  the two preventable fills — WKC, QBTS). On 08-11 it blocked SE at 09:31:10 on a 9.2% single-sample
  read (`setup:gap_below_floor: rt 9.2% < 10% floor (alert said 10.6%, last $125.36 vs prev close
  $114.80)`, prod row), which reclaimed to +10.5% by 09:35. **Per the no-single-trade-is-evidence
  rule (GOAL section): this illustrates the mechanism — a single point-in-time sample with no
  re-look — not a finding that the gate is wrong.** Whether it's right can only be answered by the
  DISTRIBUTION of everything the gate has ever blocked (register row 9); the gate's block rate has
  been counted, its FALSE-block rate never has (#559 DoD now adds the split: blocked-and-stayed-
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

**OPEN QUESTIONS for this surface → the consolidated register, §1a (rows 7, 9, 10).** The
trigger-offset question is fork 6 in §9 (#541, blocked on him); the cooldown/ADV-floor cost
questions are #557/#556 in the task inventory §7 — both already scoped tasks with measurement-first
DoDs, not open definitional questions.

**Labelled recommendation (one, entry):** change nothing before 08-31; the #559 re-cut plus the
false-block split is already the right next measurement, and any threshold moved now would
invalidate its comparability window.

---

## 4. Surface 3 — DELAYED ENTRY

⚠ **"Delayed EP" is NOT a setup today — and saying so is a definition, not a hedge (CLAUDE.md,
SETUP vs FAMILY).** It has no named buy point and no named stop. Naming it requires exactly two
things: **a defined buy point and a defined stop.**

⚠ **CORRECTED, same day, TWICE (2026-08-11) — read before "WHAT EXISTS" below.** First: *"On the
delayed entries, it has nothing to do with HTF, remember the 620 discussion we had and how i
entered TEAM? that is the delay entry we discussed"* — ruling OUT the flag-stage watch machine
(WATCH/TIGHTENING/COILED/TRIGGERED) and the HTF 90%/40d hypothesis as his concept. Then, hours
later: *"620 is just one tool i use, delay entry is just saying we wait for a followup setup after
EP, it can be same day, next day or next week... delay entry requires broad exploration"* —
correcting his own prior correction: 620 is ONE instance, not the definition either. **The
definition that stands: delayed entry = a FAMILY, open horizon — we wait for a follow-up setup
after the EP, same day / next day / next week — not a single named mechanism.** (Both quotes:
PLAN.md #562.) Whether carryforward — the plumbing that populates the watch list — still matters
to this broader family, or only mattered to the specific flag-stage machine just ruled out, is
UNRESOLVED; stated as two quotes here, not reconciled by us.

**GOAL (operator's words, both stand, tension unresolved above):** carryforward *"is critical to
delayed entries for EP"* (08-11, early). The target population is real and large: 64.4% of
failed-Day-1 HIGH names (56 of 87) made a high ≥+5% above gap-day open within 21 days
(`_p74_post_ship_audit.md`, 08-11 run). Good = named setup(s) that catch a usable fraction of that
population — the p74 review's stated target is 60–70% capture vs 51% measured and a 34.2% baseline
(ADR 0003).

**WHAT EXISTS, disentangled (things that share one label, not all confirmed as his concept):**
1. **The carryforward + flag-stage watch lane** (`flag_detector.py`, 17:25 ET): failed MAGNA53
   names and 9M EPs are carried into the staging machine. ⚠ **Confirmed NOT his delayed entry**
   (correction above) — its funnel numbers below are real facts about THIS mechanism, not evidence
   about his concept. Kept because it's the only built, measured lane.
2. **The #270 "Delayed-EP Re-entry" spec** (`docs/setups/delayed_ep_reentry.md`): tiny-cap
   fast-runner undercut-and-reclaim lane, analysis complete, deployable wiring gated — a
   DIFFERENT population (sub-$500M, +40% gaps) from the SE-class large-name delayed EP. Not
   confirmed as his concept either.
3. **The operator's own delayed entries**, done by hand: TEAM 08-07 (re-entered the stock Apollo
   was stopped out of, $144.39 at ~11:50, stop at low-of-day — *"no hard rule so hard to copy"*,
   #545) and the SE read (below). **These two — plus whatever else he names — ARE the family; step
   1 is enumerating the rest (below), not further measurement of the lane in (1).**

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
- **A hypothesis for WHY TRIGGERED never fires (the staging machine borrows HTF's 90%/40d runup
  gate, `docs/setups/flag_continuation.md`/`htf.md`) — MOOT, not verified.** It would explain why
  the flag-stage machine rarely fires, but that machine was confirmed NOT his delayed entry
  (correction above), so the explanation answers a question he isn't asking. Left here as a fact
  about the flag detector only, not as a live hypothesis for this surface.
- **The closest thing to a labelled positive example** — the operator's SE read, verbatim in
  `docs/methodology/operator_shared_notes.md` (2026-08-11). His four conditions, none of which is
  in the current TRIGGERED logic: (1) gapped through while above ALL moving averages — computable
  today (`mi_stock_scores.sma_10/20/50`); (2) a decent-looking base — partially computable (RMV
  work); (3) possibly moving into a Stage 2 uptrend after bottoming/basing — NO classifier
  exists, the biggest gap; (4) the GROUP is strong and the name belongs to it — failed on OUR
  side the same minute (SE in zero themes; #563).

**OPEN QUESTIONS for this surface → the consolidated register, §1a (row 3, row 11).** The
flag-stage funnel mechanics (what TRIGGERED requires, where the 104 names died) are now a fact
about a mechanism confirmed to be the WRONG lane — kept as background, not pursued as the path to
naming his setup. The buy-point/stop candidates already in evidence (FIRST5-break from #270,
base-then-turn from TEAM, a reclaimed-floor re-look for the SE class) await his ruling once he has
enumerated the shapes.

**Labelled recommendation (one, delayed):** #562's step 1 is HIM naming the candidate follow-up
shapes he actually trades — not more code-reading on the flag-stage machine, which is now confirmed
to be the wrong lane. This is blocked on the operator, not on evidence or capacity (§1b step 4).

---

## 5. Surface 4 — EXIT

**GOAL (operator's framing):** harvest a low-win-rate, fat-right-tail population — bank the
excursion instead of round-tripping it. This is the REWARD half of the GOAL-section arithmetic: at
a 20% win rate the average winner must exceed 4R to break even, so exit's job is not "protect small
gains," it is "let the rare winner reach 4R+" — a ceiling on winners is a net loss at this win rate,
not a safety margin. The measured leak: live cohort (n=17 read, 08-08) REACHED +1.54R on average
and KEPT −0.91R; 8 of 17 touched +1R, 5 touched +2R, all closed losers (`docs/setups/exit_discipline.md`).
The only large gains today sit in OPEN positions (§0.1) — the winners are the trades we have not
closed.

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

**OPEN QUESTIONS for this surface → the consolidated register, §1a (rows 8, 12, 13, 14).**

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
6. **Re-entry disabled → delayed entry is the only second chance.** Same-day 1-min re-entry (R3)
   was killed on 0-for-7; both 08-11 stop-outs show `block:r3_reentry_disabled`. A same-day 5-min-
   range re-entry WAS swept 08-09 over the full 17-trade stop-out set: fired 9 of 17, net +7.76R —
   but that is ONE outlier trade (THC, +12.43R on a razor-thin stop); the other 8 net −4.67R, the
   same failure shape R3 was killed for (register row 8). **Next-day and N-day re-entry variants
   have still never been swept (#545)** — the operator's own TEAM fill is the existence proof of
   that tactic specifically.
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
- #562 (delayed-entry FAMILY — step 1 is HIS enumeration of candidate follow-up shapes, not further
  diagnosis; corrected 08-11 off two earlier framings [HTF/flag-stage machine, then "620 alone"] —
  pending, due 08-11, overdue, blocked on the operator)
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
8. **A reference set of real EP winners from outside our fills** — named by the operator 2026-08-12
   as the fix for testing structure, and by extension any "what does a real EP look like" question:
   *"the better way to see this is probably to have a few winners to compare it with."* No task
   owns building it; scoping (source, sample size, selection method) is his call (§1b step 3).

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
| 5 | Name the delayed-EP setup(s) (buy point + stop) | his enumeration of candidate follow-up shapes (#562 step 1, corrected 08-11) + evidence on each | until named, delayed EP stays a family, not a tradeable |
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

---

---

# CADENCE — weekly targets, daily increments, and an honest review

Operator, 2026-08-12: *"let's make sure we can systematically get closer to the answer and
implementation, it make take some time and we need to have more samples, but what i don't want to
to deviate from the goal and not making progress. We should see what can be done each day and key
progress/targets each week and review if we're meeting them."*

## The rule that keeps this honest

**A week has TWO kinds of target and both count.** Most of this plan is evidence-gated — the
answer needs samples we do not have yet — so a week spent waiting is not automatically a failed
week, and a week full of activity is not automatically a good one.

| | What it means | How a week is judged |
|---|---|---|
| **SHIPPED** | work delivered — a measurement run, a mechanism built, a fork answered | did it land, verified |
| **ACCRUED** | evidence that arrived — settled trades, alerts, decision rows | did the counter move as expected |

⚠ **A week where nothing shipped AND nothing accrued is the failure mode this cadence exists to
catch.** Say so plainly at review rather than re-dating quietly. ⚠ And per the standing rule
above: a week's accrual is measured in DISTINCT SESSIONS, not rows.

## Review

- **Daily** — the OPEN ritual (`check_plan.py --today`) already surfaces what is due. The
  sequence above says what the day should MOVE; if a day's work does not map to a sequence step
  or a goal term, that is the deviation the operator is guarding against.
- **Weekly (Friday)** — against the table below: what shipped, what accrued, what slipped and
  WHY. A miss gets a reason on the line, never a silent re-date.

## Week of 2026-08-11 → 08-14 (short week; started Tuesday)

⚠ **Token budget is the binding constraint this week** (operator 2026-08-11: ~20% until Friday's
reset), so the target is deliberately ONE thing, not four.

| Target | Type | Status |
|---|---|---|
| The Real EP Plan exists, named, with a goal and a sequence | SHIPPED | ✅ 08-12 |
| The +2R exit rule fires correctly on live money | SHIPPED | ✅ 08-11 (ABCL, limit filled at the target, stop to entry same second) |
| Theme assignment produces non-zero output | SHIPPED | ✅ 08-11 (91 new ticker slots, 0 truncation) |
| **#563 — measure the 357 same-day pairs that never became a theme** | SHIPPED | ⏳ due 08-15 — **this week's one remaining target**, and it GATES the ranking work |
| Settled sessions for the 08-05→08-12 window | ACCRUED | ⏳ settles ~08-18, on track |

## Week of 2026-08-17 → 08-21 — provisional

| Target | Type | Why then |
|---|---|---|
| Re-run the structure probe on the settled 08-05→08-12 window | SHIPPED | $0 re-run; the sessions that motivated the thesis finally testable |
| Scope + build the WINNER REFERENCE SET (sequence step 3) | SHIPPED | the operator's own fix — you cannot learn what a winner looks like from 19 losers. Scoping is HIS call |
| #543 extractor re-check on ~40 calls · #471 decision-record fork | SHIPPED | both dated, both cheap |
| More settled live trades toward a distribution worth reading | ACCRUED | 19 closed today; the 20-distinct-DAY bar on the Confirm cohort is the model for what "enough" looks like |

## What this cadence must never become

The data-gated review registry (#517) is the cautionary case in this repo: 124 entries, 50 ripe,
oldest 72 days, surfacing every Sunday and ignored — **capture without a forcing function.** If
this table stops being reviewed on Fridays it has become the same thing, and the honest move is to
say so and replace it, not to keep appending rows.

---

## STANDING SCOPE RULE — the review population is every EP we DETECTED, not every EP we traded

Operator, 2026-08-12: *"don't just look at what we traded, also look at all the EPs we detected but
didn't trade for whatever reason, that's the whole group to review."*

**This applies to every measurement in this plan, retroactively and going forward.**

### Why it changes the answers, not just the counts

- **Traded is a tiny, biased slice.** ~20 live trades against **276 HIGH alerts over 53 sessions**.
  Restricting to fills studies the names that survived *our own filters* — which is precisely what
  is under question. It cannot see a filter that is wrong.
- **The skips ARE data.** Every `skip_reason` is a decision we made: `window:out_of_orb`,
  `setup:gap_below_floor`, `setup:zero_range`, `block:*`, the position cap. The distribution of
  those reasons says WHERE the funnel loses names, and pairing each with what the name did
  afterwards says whether the loss was RIGHT.
- **The canonical case is SE (2026-08-11)** — detected, skipped on the gap floor at 9.2% vs a 10%
  floor, reclaimed to +10.5% four minutes later, and the one the operator says he would have
  traded. It exists in the alert population and nowhere in the fill population.

### What this means concretely

1. **Default cohort = all detected EPs.** Fills are a SUBSET to be reported alongside, never the
   frame. State both N's whenever they differ.
2. **Outcome is measured on the ALERT** (forward return / MFE / MAE from the alert), so a skipped
   name still has an outcome. This is already the plan's measurement basis — the scope rule is what
   makes it necessary rather than convenient.
3. **Skip-reason attribution is its own analysis and is currently unowned**: for each reason, how
   many names, and what did they go on to do. A reason that consistently drops names that ran is a
   candidate defect; a reason that consistently drops names that died is working.
4. ⚠ Combine with the standing evidence rule: a single skipped name that ran is the EXPECTED cost
   of any filter and proves nothing. Only the distribution per reason, with its N and distinct
   sessions, licenses a conclusion.

⚠ This does not license changing any skip rule. Skips are entry discipline = THE LINE; this rule
governs what we MEASURE.

---

## 2026-08-12 — #563 answered: the 357 unlinked same-day pairs, judged (register row 5)

**Question**: of the same-day EP alert pairs that never shared a theme, how many were genuinely ONE
STORY — are we under-using EP gaps to find themes early? **Answer: YES, materially — but at the
STORY level, not the pair level, and the loss point is known and singular.** All numbers re-derived
from prod 2026-08-12; queries and raw captures in the session scratchpad (`563_*.tsv`).

### The split, rebuilt (window pinned 2026-06-12 → 2026-08-10)

| Measure | Value |
|---|---|
| Days with any EP alert (ep_score ≥ 50) | 35 |
| Sessions with ≥2 same-day alerts | **27** |
| Same-day alert pairs | **366** |
| Later shared a theme (theme_date D..D+5) | **15** (3 sessions: 07-30, 07-31, 08-04) |
| Never shared a theme in D..D+5 | **351** (27 sessions) |
| Pair with a pre-existing shared board theme (D-7..D-1, non-Retired) | **1** — correction, see below |

- **Reconciliation to the prior 372/15/357** (§5 of the 08-11 seam doc): the prior probe's window
  was open-ended and ran mid-morning 08-11, catching 4 of that day's eventual 5 alerts
  (BW/FRMI/RIOT/SE by 07:25 ET; RPD only at 09:50 ET) = +6 pairs, +1 session, 0 linked. Same
  population otherwise; nothing was deleted.
- **Correction to §5's "0 shared_before"**: HUT+IREN on 07-20 DID share a non-Retired board theme
  in D-7..D-1 ("Bitcoin & Crypto Mining Infrastructure", last snapshot 07-17, written 07-17 21:06
  UTC — not a backfill; verified with §5's own expression). 1 of 366, not 0 of 372. The structural
  conclusion (co-gap links are born after the entries they describe) stands on 365 of 366.

### Method (stated per the standing rule — no sampling was needed)

- The 351 pairs are generated by only **126 ticker-day alerts across 27 sessions**, so instead of
  sampling pairs I judged **exhaustively at the session level**: every session's alerts grouped
  into stories from stored fields only — sector/industry + company name (`mi_ticker_overrides`),
  alert-day catalyst text, `catalyst_type`/`catalyst_quality`, tier. A pair is ONE STORY iff both
  members sit in the same story-group of that day (shared driver — sympathy chain or same named
  narrative), NOT merely same sector/industry: two names beating on separate earnings in the same
  sector were dismissed as unrelated. N = 351 pairs judged, 27 sessions, single grader.
- A mechanical screen (same-industry / theme-lexicon overlap / cross-mention) was built first as a
  cross-check; it would have MISSED 4 of the 8 judged miss pairs (they shared neither industry
  string nor lexicon token). Negative result worth keeping: **stored structure fields alone cannot
  find these pairs; catalyst-text judgment is what works** — which is also evidence for what a
  lane would have to read.

### The miss rate

- **CLEAR one-story misses: 5 pairs, 5 distinct sessions, 5 distinct stories** — miss rate
  **5/351 = 1.4%** of pairs (5 of 27 sessions). Four of the five are corroborated by the system's
  own same-night cogap judge; the fifth by Lane-1's own later discovery:
  06-15 AUGO+HYMC (gold/silver miners — Lane-1 finally birthed precious-metals themes holding both
  on **08-05, 51 days later**) · 06-25 MU+SNX ("AI memory & infrastructure demand surge") ·
  07-20 HUT+IREN (miners→AI-DC, the #491 story) · 07-30 EME+PWR ("AI-driven power & grid
  infrastructure") · 07-31 COHU+MPWR ("semiconductor test recovery, AI demand" — MPWR was linked
  into that night's AI-DC theme while co-gapper COHU was left out).
- **PROBABLE misses (my judgment only, no system corroboration): +3 pairs, 3 further sessions** —
  06-17 AEHR+JBL (AI-infrastructure momentum), 08-05 KTOS+TATT (defense-spend earnings wave — the
  defense theme was born the PREVIOUS evening and never picked either up), 08-07 ACMR+ONTO
  (semicap AI-capex beats). Ceiling: **8/351 = 2.3%** (8 of 27 sessions).
- **Story-level framing (the one that answers the operator's question)**: in-window the engine
  linked **4** same-day story-cohorts (AI-DC semis 07-30, AI-DC buildout 07-31, defense 08-04,
  AI-DC 08-04). Clear stories it missed: **5**. So **5 of 9 clear same-day co-gap stories in 60
  days were lost (8 of 12 counting probables)** — roughly one lost story every two weeks. The
  351-pair denominator is noise-dominated (two unrelated earnings gappers same day); the story
  denominator is the honest one.

### Where the misses were lost

| Loss point | Pairs | Detail |
|---|---|---|
| **3-member promote floor** (`_PROMOTE_MIN_MEMBERS=3`) | **4 of 5 clear** | MU+SNX, EME+PWR, COHU+MPWR, HUT+IREN: each was grouped by `narrative_cogap` the SAME NIGHT as a 2-member cohort and discarded. Not re-measured — attributed per the 08-11 §11 measurement. |
| Grouped, then **aged out** (7-day recency board) | HUT+IREN (dual) | Shared theme born 07-08, last snapshot 07-17, gone from the D..D+5 window by the 07-20 co-gap; the same-night cogap revival then died at the floor. |
| **Never grouped by any story-granularity lane** | AUGO+HYMC + the 3 probables | Only sector-binned `judge_inferred` rows touched some (mixing unrelated names — consistent with §6). AUGO+HYMC: Lane-1 eventually found the story on its own, 51 days late. |
| Recurring shape (not a lane) | 6 of 8 miss pairs | ONE member sat in some theme within D..D+5 while its co-gapper did not — coverage loses the partner, not the story. |

- **This inverts §11.2's "narrative_cogap: ZERO confirmed cases."** That read used
  later-theme-formation as ground truth; under human judgment **4 of the 5 pairs the floor
  discarded from the EP-gap lane were genuinely one story** — the forward-join could not see them
  precisely because the floor killed the only lane that had them (the
  shadow-zero-effect/instrumentation lesson, again). The floor's cost in the EP-gap lane is not
  zero; it is most of the clear miss count.

### Verdict and the fork (operator's decision — not picked)

- **Yes, we are under-using EP gaps to find themes early.** Pair-level the rate is near zero
  (1.4–2.3%, N=351, 27 sessions); story-level it is material (5 of 9 clear stories lost in 60
  days) — and 4 of the 5 losses happened at ONE known point after detection succeeded. The system
  already finds these stories same-night; it then throws them away.
- The §8 forks (F-A..F-E) return to the operator with this evidence attached. Any change to the
  floor, cogap retention, or lane behavior is a detection-criterion change: CHANGE_PROCESS +
  sign-off. The ranking work (#533) is unblocked on its coverage prerequisite: theme-absence is a
  true negative for ~98% of pairs, but only after checking the discarded-cohort surface.

### What could NOT be measured

- **Outcomes.** Whether the missed stories would have produced profitable entries — out of scope
  (coverage only; no outcome join was run).
- **3 pairs unjudgeable from stored fields**: AUGO+IDR, HYMC+IDR (06-15 — IDR has blank
  sector/industry and a catalyst text that names no driver; outside knowledge says gold miner,
  likely real, which would raise the ceiling to 11/351 = 3.1%) and KC+PENG (07-08 — KC's stored
  catalyst is a wheat-futures misidentification). Stored-data quality, not judgment, is the
  binding constraint on these.
- **Right-censoring**: "never grouped/linked" verdicts for 08-05..08-10 pairs carry ≤7-day forward
  windows (prod read 2026-08-12).
- **Judgment sensitivity**: same-industry names on independent catalysts (e.g. 06-22's four
  biotechs on four separate clinical events) were judged NOT one story. If the operator's bar
  counts a sector wave as one story, the miss count rises; the raw session groupings are in the
  scratchpad captures for re-judgment. Single grader, no second pass.

---

## 2026-08-12 — the delayed feed is doing a filter's job, and that reframes the real-time question

Operator, on being told the review population is every DETECTED EP:

> "on the point to look beyond filled trades, this is also the case for all the real-time misses
> because we've not flipped to real-time data for EPs... we get dozens of these right now in
> earnings season (e.g today there's 11). We decided not to flip because it'll admit too much,
> which is the right call but only for pragmatic reasons, we are putting up an artificial filter,
> not related to any real EP criteria, but just using delayed data because it prevents us from
> being overwhelmed. This shows the filter issue is more stark, we have it too lose to the point
> where we can't even fix what i consider a real bug, not using real-time data which is the
> correct thing to use, just so we can avoid having too many stocks/EPs. With that said, this
> cohort should also be included in our universe to review and look into given they technically
> meet our current lose criteria."

### The point, stated once

**We are using a data-latency artefact as an admission filter.** Detection reads delayed Polygon
data while the feed we pay for and trade on is real-time SIP. On 2026-08-10 the recommendation was
HOLD — do not flip the two admission switches — and the evidence behind it was real (in-window
real-time crossers ran −0.60R over n=320/14d, 80% stopping day-0, #559). **But that is a volume
argument, not a criteria argument.** Nothing about "the data arrived late" is an EP criterion.

So the hold is pragmatically right and structurally wrong at the same time, and the operator has
named why: **our admission is so loose that we cannot afford to fix a real bug.** The delayed feed
is load-bearing — it is silently doing the selectivity work the criteria should be doing.

### What follows — and it changes an ORDER, not just a list

1. **The real-time-detected-but-never-admitted names JOIN the review population.** They meet our
   current criteria; they are absent only because of when the data arrived. Combined with the
   standing scope rule above, the full universe is: filled ⊂ detected-and-skipped ⊂
   **detected-only-in-real-time**. Report all three N's.
2. **#559's flip question is SUBORDINATE to admission, not parallel to it.** Asking "should we
   flip to real-time" while criteria are loose can only ever answer "no, too much volume". The
   flip becomes genuinely answerable once admission is tight enough that volume is no longer the
   binding objection — so **tightening criteria is the prerequisite, and #559's 08-31 re-cut
   should say so rather than re-deriving the same volume answer.**
3. **Earnings season is the stress case, measured**: ~11 EPs today; the alert rate ran 1-2/day in
   late July and 7-10/day in the 08-04→08-07 window. The calendar drives the count, so any filter
   that is really a volume limiter will look best exactly when randomness is highest.

⚠ This does NOT argue for flipping the real-time switches. It argues that the reason we cannot is
a defect in admission, and that the fix is upstream of the flip. Both remain THE LINE — entry
discipline, operator's sole call.

---

## 2026-08-12 — the skip reasons are a TAXONOMY, and each one asks three questions

Operator: *"a good portion that didn't fill are also not directly related to our selection filter
(well they are, but we have broad category), e.g. stop too wide i saw on EROC this morning which is
correct on 1.5x ATR but looks like a good EP to me, so even if we filter it correctly there may be
alternate delay entry here, so it's much more complex. Also, after 9:45AM we have late arriving
EPs, so time filter may or may not be right, etc. Many parameters to work with here, i want to
leave no stones unturned."*

### Why "why didn't it fill" is not one question

A skip today is recorded as a single reason, but the reasons are of **different kinds**, and
lumping them hides which lever is which:

| Kind | Examples | What it really says |
|---|---|---|
| **Selection** | grade too low, gap below floor | we judged it not an EP |
| **Risk geometry** | `stop too wide` (1.5×ATR) | it IS an EP; the trade we would construct is too expensive |
| **Timing / mechanism** | `window:out_of_orb` (post-09:45), unfilled at the ORB high, `zero_range` | it IS an EP; our entry mechanism could not take it |
| **Portfolio** | position cap, cooldown, breaker | nothing about this name at all |

**EROC this morning is the worked case**: skipped on stop-too-wide, correct by the 1.5×ATR rule,
and the operator's read is that it was a good EP. The rule did its job and we still did not own a
good name.

### The THREE questions every skip reason must answer

1. **Was the skip right AS A SELECTION CALL?** (measure: what did the name do afterwards, per
   reason, distribution not anecdote)
2. **If the skip was right, does it imply a DELAYED ENTRY rather than nothing?** A stop too wide at
   09:31 can be a perfectly good entry at 10:30 off a tighter base. This is where the skip taxonomy
   feeds directly into the delayed-entry family (#562) — **a "no" to today is not a "no" forever.**
3. **Is the RULE itself right?** The 09:45 ORB cutoff exists for mechanism reasons, not because an
   EP arriving at 09:50 is a worse EP. Late-arriving EPs in earnings season are a real population.
   Same question for the 1.5×ATR multiple.

⚠ **Question 3 is the dangerous one** — it is the operator's, it is entry discipline, and it needs
CHANGE_PROCESS + N≥10 + sign-off. Questions 1 and 2 are measurement and can proceed.

### What this adds to the plan

- The **skip-reason attribution** analysis (named as unowned earlier today) now has a shape: split
  by KIND first, then run the three questions per reason, reporting distributions with N and
  distinct sessions.
- It is the join between the selection surface and the delayed-entry surface — the same name can
  fail admission today and be a legitimate delayed entry tomorrow, and today we simply drop it.
- ⚠ Combined with the standing rules: no single skip proves a rule wrong (EROC illustrates,
  it does not conclude), and the population is every DETECTED EP including the ones real-time
  would have caught.

---

## 2026-08-12 — DESIGN: retain the 2-member co-gap cohort, promote on the third member (#563 follow-on)

**The ruling being designed for** (operator, in the accepted framing): *don't lower the bar, stop
throwing the cohort away.* A 2-member co-gap cohort becomes a retained CANDIDATE; it reaches the
board only when it earns a third member. Design only — nothing below is decided, no code was
changed, the `_PROMOTE_MIN_MEMBERS = 3` floor is untouched. Evidence base = the §563 measurement
above plus fresh prod reads 2026-08-12 (captures: session scratchpad `564_*.tsv/txt`,
`lane2_review.md`).

### 1. Where retention lives — it already exists; build NOTHING new

- **The rows were never physically deleted.** Every 2-member `narrative_cogap` cohort persists in
  `mi_theme_candidates_shadow` (PK `(run_date, name)`); all 5 of the window's 2-member cohorts are
  still there (prod read, `564_cogap_rows.tsv`). The functional discard was v1's *amnesia*: each
  night stood alone, so nothing could ever add member 3 to a prior night's pair.
- **The retention+completion structure is the #167 Lane-2 v2 REGISTRY — operator-signed and flipped
  ON in prod 2026-08-09** (commit `9b4c5d7`, all three gates; flag `lane2_grouping_v2 = on`,
  `564_flags_raw.txt`). Mechanics, all shipped: a 2-member birth stays an ACTIVE roster narrative
  for 10 trading days (`get_lane2_active_narratives`, refreshed on touch); a later same-day
  co-gapper JOINs it (the join writes a fresh `(today, name)` row with unioned members); the
  nightly `promote_shadow_themes` (3-day window, latest row per name) promotes the night the row
  reaches 3 members — the promote door was verified open during the 08-09 gate walk (commit
  `027cc75`). Name+thesis are frozen at birth; members FIFO-capped at 12.
- **Verified live 08-10** (audit log, `564_lane2_runs3.txt`): the roster carried **7 active
  narratives including the EME+PWR, COHU+MPWR and AEIS+ZBRA 2-member cohorts** — i.e. the exact
  objects the floor used to orphan were sitting as awaiting-third-member candidates.
- Rejected alternatives: a new table (duplicates registry state); a status column (the
  `(run_date,name)` append + latest-row-per-name read already encodes candidate state); the
  `mi_theme_birth_candidates` ledger (different semantics — gate evaluations with 14-day memory,
  not lane state).

### 2. Retention window: **10 trading days** — derived, and it is the already-shipped constant

Third-member arrival, measured in the qualifying EP-alert stream (ep_score ≥ 50) for each §563
floor-killed story (N = 5 stories, 5 sessions — arrivals, not a load-bearing distribution):

| 2-member cohort (born) | Third member in the EP stream | Arrival (trading days) |
|---|---|---|
| EME+PWR 07-30 (power/grid) | FLNC 07-31 (AI-DC battery storage); AMRC 08-04 | **+1** (then +3) |
| COHU+MPWR 07-31 (semi test) | AEIS 08-04 (semicap cycle); ONTO+ACMR 08-07 | **+2** (then +5) |
| HUT+IREN 07-20 (miners→AI-DC) | completion is BACKWARD: WULF 07-06 / CLSK 07-14 must still be remembered | **10** (WULF→HUT/IREN span) |
| MU+SNX 06-25 (AI memory) | forward: **none in the remaining window**; backward: AEHR+JBL 06-17 (probable-grade) at 5-6 td | unrecoverable forward |
| AUGO+HYMC 06-15 (precious metals) | **zero further gold/silver EP alerts in the entire 60 days**; only same-day IDR (blank stored fields) | unrecoverable at any window |

- **Derivation**: every recoverable case fits inside 10 trading days; the binding case is
  WULF→HUT/IREN at exactly 10 — the SAME measured case that set `LANE2_WINDOW_TRADING_DAYS = 10`
  (and 7 *calendar* days was measured one day short on the WULF→CLSK link, per the #167 audit). The
  two unrecoverable misses had NO third member in the EP stream at ANY horizon — AUGO+HYMC's only
  candidate was same-day IDR (stored-data quality is the binding constraint), and Lane-1's 51-day
  precious-metals discovery came from RS, not from EP gaps. **A longer window therefore buys
  nothing and only accumulates stale candidates; a shorter one re-creates a measured miss.** No new
  number is picked: the window inherits the #167-signed measurement.

### 3. Board impact — quantified; the flood argument fails

- Candidate inventory: **5** two-member co-gap cohorts in 60 days (<1/week); roster prompt cap 20.
- Ceiling (all 5 eventually complete): **+5 first-time themes per 60 days**, vs **220** actual
  first-births in the same window (+2.3%) and **89** promote-path births (+5.6%) (prod,
  `564_board.tsv`).
- Measured expectation from the arrival table: **+2 new board themes** (power/grid via FLNC,
  semi-test via AEIS) **+1 refresh** of the existing crypto→AI-DC theme (the HUT+IREN join lands as
  maintenance of a prior name, not a new seat) = **+2–3 over 60 days**.
- Standing-board effect: ≤ +2–3 seats at any instant on the **82-theme / 4.76-mean** board
  (+2–4%); an untouched one-off ages out via the existing 7-day recency cap. Promoted-on-third
  cohorts enter at 3–4 members, slightly below the 4.76 mean.
- The $0.96 registry replay over this exact window (06-08→08-07, `lane2_review.md`) birthed **3**
  narratives total in its one realization. Every measurement says: not a flood.

### 4. What it can break — stated plainly

- **The bottleneck is now the model's nightly judgment, not the structure** (replay evidence,
  N=1 realization): with retention available, the replay cleanly recovered COHU+MPWR (same-night
  join into an active narrative), joined MU but never SNX, and never birthed EME+PWR or a
  precious-metals narrative, never joined HUT/IREN — ~1 of 5 clear misses recovered in that run.
  Retention *permits* recovery; the recovery rate is a forward measurement, not a guarantee.
- **Absorption / granularity loss**: the replay's single AI-DC narrative accreted **12 members
  spanning 4 stories §563 judged distinct** (memory, semi-test, miners-pivot, buildout). A
  promoted catch-all is a BROAD theme feeding judge context and R4 with mixed membership. The FIFO
  cap (12) sits exactly at the observed size. This is the granularity program's problem surfacing
  here; it argues for measuring forward behavior before any tuning.
- **The different-object question (the money surface), answered**: a cohort promoted on member-3
  night enters the live board days after its founding gaps. (a) Judge context: **no change** —
  `get_narrative_theme_candidates(days=5)` already feeds 2-member candidates into the judge's
  `active_narratives` from night 1 (grade-affecting today, unchanged by this design). (b) **R4
  bonus (money): begins only on the promote night** — the founding members' own alert-day grades
  never carried it; the third member's day does. Strictly additive vs today (today none of them
  get it), forward-only, no retroactive mutation. An asymmetry to know about, not a blocker.
- **Birth-gate interaction**: `theme_birth_gate = observe` today. If flipped `on`, a
  late-assembled cohort is a FIRST crossing and faces the RS-floor/two-sighting gate the night it
  finally completes — the gate could re-kill exactly these cohorts. Sequencing fork for the
  operator whenever the gate mode changes; in `observe` nothing is held.
- ⚠ **BLOCKING verify-live finding: the registry is currently failing in prod.** Since the 08-09
  flip: one clean run (08-10 21:17 UTC — 5 alerts, roster 7, 0 join + 0 birth + 5 seeds), then
  `narrative_theme_discovery_failed` 08-10 21:20 UTC (*"Unterminated string … char 535"*) and
  08-11 (*"'str' object has no attribute 'get'"*) (`564_lane2_runs3.txt`). **The retention lane
  has never completed a forward birth or join** — a rule is not live until it has fired once. The
  bug diagnosis/fix is a separate task, not part of this design.

### 5. CHANGE_PROCESS verdict — partial disagreement, with the reason

- **The mechanism the ruling asks for is ALREADY an operator-signed, shipped change**: the #167 v2
  flip (2026-08-09, three gates, commit `9b4c5d7`) is precisely "retain the 2-member cohort,
  complete it later, promote at 3." Recommending **Option A — rely on the shipped registry:
  verify-live its first birth/join/promote, then measure forward recovery against the §563 story
  list — changes no criterion, no floor, no lane behavior, and needs no NEW CHANGE_PROCESS cycle**;
  the signature already exists. (Disagreeing with the "yes, sign-off required" prior only in this
  narrow sense: a second signature would re-sign existing signed behavior.)
- **Everything beyond A IS a detection-criterion change — CHANGE_PROCESS + evidence + sign-off**:
  any horizon change, any floor change, a prompt nudge steering the model toward narrow
  births/joins over absorption (Option C), or a mechanical third-member matcher (Option B —
  already killed by §563's own negative result: stored structure fields cannot find these pairs;
  catalyst-text judgment is what works).
- **The operator's fork** (nothing pre-decided): **F-i** accept Option A — fix the registry
  failure (separate task), verify-live, measure recovery over forward sessions. **F-ii** if forward
  recovery under-delivers vs §563's story list, authorize a replay-measured Option C prompt change
  through CHANGE_PROCESS. Rec: F-i.

### What could NOT be measured

- **Forward recovery rate** of the live registry — zero completed births/joins since the flip, and
  the lane is currently failing nightly.
- **Whether the replay's absorption behavior recurs forward** — one realization, one model call
  per night; birth-vs-join choices are stochastic.
- **MU+SNX and AUGO+HYMC recoverability** — bounded by stored-data quality (IDR blank fields) and
  by the EP stream containing no later third member, not by any retention design.
- **Outcomes** — whether recovered themes would have produced profitable entries; out of scope
  here, consistent with §563.

---

## 2026-08-15 — CAPTURE AUDIT: what next quarter's test needs vs what we are storing (collection window closing)

**Why now (operator, 2026-08-15):** *"we are near end of earnings season but we should have a lot
of data collected this time."* Measured: 7–10 HIGH alerts/day in the 08-04→08-07 window vs 1–2/day
in late July. Anything not RECORDED now is unrecoverable for this quarter. This section audits
CAPTURE only — fields, grain, retention — against the register's questions. **Nothing here changes
detection, entry, exit, or any threshold (THE LINE); nothing was built; ranked gaps are the
operator's to order.** All facts verified on prod 2026-08-15 (queries + raw captures: session
scratchpad `capture_audit*.sql/tsv`) and in `db.py::purge_old_data` / `scheduler._weekly_cleanup`
(Sunday 02:00 ET, confirmed running: `mi_ep_alerts` MIN alert_date = 2026-05-11 = the 08-09
Sunday's 90-day cutoff, exactly).

### THE HEADLINE — the alert rows themselves are the thing that ages out first

**`mi_ep_alerts` retention is 90 days, purged weekly.** The earnings-window alert rows — the
richest per-alert record we hold (catalyst text, `catalyst_quality` grade, `judge_tier` +
rationale, `grounded_text` corpus, theme flags, tape tier, `setup_class`, `detected_at`) — DELETE
on these Sundays:

| Rows | Deleted on |
|---|---|
| 07-21..07-26 (quiet-week baseline) | **2026-10-25** |
| 07-27..08-03 | **2026-11-01** |
| **08-04..08-09 (the earnings window)** | **2026-11-08** |
| 08-10..08-16 | 2026-11-15 |

Next quarter's earnings season IS November — the comparison test loses its August reference set the
week it starts. What survives the purge: `mi_ep_missed_outcomes` (durable, 3,224 rows from
2026-02-11 — but NON-TRADED names only, and only ticker/date/score/gap/`catalyst_quality`/skip +
daily-grain outcomes) and `mi_ep_scan_log` (durable, 27,806 rows from 2026-04-13 — thin per-tick
funnel record, incl. the #489 `gap_pct_rt`/`gap_pct_delayed` pairs). The grade partially survives;
the judge's reasoning, catalyst text, corpus, theme flags, and board context do not. The table is
403 rows total — retention here is a leanness choice costing nothing to relax.
(Mitigation NOT to lean on: nightly pg_dump backups exist; old-dump retention unverified, and
restoring a November analysis from an October dump is a recovery operation, not a data store.)

### The audit table — question → fields needed → captured? → what breaks

Status: ✅ captured · ⚠ captured-but-lossy (wrong grain / subset / ages out before use) · ❌ not captured.

| Register row / need | Fields needed | Status | What breaks if lost — and when |
|---|---|---|---|
| 1–2 real-EP / structure vs winner reference set | our alerts' full feature rows to compare against outside winners | ⚠ | rich rows die 10-25→11-15 (`mi_ep_alerts` 90d); only the thin missed-outcomes summary survives |
| 2 "what did the gap CLEAR" (prior highs, bases) | daily OHLC deep lookback, full universe | ⚠ | `mi_daily_closes`: full 12,280-ticker universe but a **400-day rolling window** — ~13 months of prior-high context; multi-year bases/ATH tests need a Polygon refetch (recoverable — we pay for the API) |
| 2 SMA position at the gap | SMA10/20/50 on alert day | ✅ | `mi_stock_scores` stores only ~2,444 of 12,280 names/day, BUT SMAs recompute at $0 from `mi_daily_closes` for any name in-window; scores kept 365d |
| 2 intraday HOLD test (cleared level, held first pullback) | minute bars on alert day, ALL alerts | ⚠ | `mi_intraday_bars` covers **43 of 98 alert ticker-days since 07-28 (44%)** — traded/position names only (`track_open_position_extremes`); skips/cancels/moderates have NO stored minute path. Vendor-recoverable from Alpaca SIP later; ticker-day identity survives in durable tables |
| 3 delayed entry: what a failed Day-1 did after (620 timing, next-day) | D0..D+N minute bars + daily follow-through per failed alert | ⚠ | daily grain durable (`mi_ep_missed_outcomes` ret_1/5/20d + max_high_5/20d; `mi_ep_scan_outcomes` fwd_5/10d, healthy, settling lag only); minute grain not stored for non-traded names (same hole as above) |
| 4 too-loose / season conditioning | full per-day funnel incl. every scan tick + reasons | ✅ | `mi_ep_scan_log` durable, per-tick; season labels derivable from calendar |
| 5 theme absence / strength at alert time | dated theme state joinable to alert day | ✅ | `mi_themes` 365d, dated — any past board reconstructible offline (as §2 already states) |
| 6 win rate on the alert unit | alert-forward outcomes incl. skips | ✅ | `mi_ep_missed_outcomes` durable + never-purged trades tables |
| 7 alert runs while bracket dies | per-trade minute path + peak/kept record | ✅/⚠ | derived record durable (`mi_sell_discipline_records`, 51 rows); RAW minute paths for this quarter's trades purge **2026-12-06** (`mi_intraday_bars` 120d) — vendor-recoverable |
| 8/13 re-entry after stop-out (same/next/N-day) | post-stop same-day bars (recorder writes through 16:00 ✅, 120d); next-day minute bars (❌ unless re-traded, vendor-recoverable); daily ✅ | ⚠ | next-day/N-day sweeps (#545) lean on refetch or daily grain |
| 9 gap-floor false-block split (#559) | every block + did it reclaim within ORB | ⚠ | block DECISIONS durable (`mi_live_trades` skipped rows, 7 blocks since 08-06, rt reading embedded in `skip_reason` prose); the reclaim EVIDENCE needs alert-day minute bars — not stored for blocked names (refetchable) |
| 10 within-day ranking re-analysis | the full board's features per session | ⚠ | same as row 1–2: board reconstructions after 11-08 lose grades/judge/catalyst; probe snapshots (`scripts/probes/_533_*`, `_468_*.tsv`) hold point-in-time copies — note several are untracked/machine-local |
| 11 delayed funnel accrual | flag lane + in-play history | ✅/⚠ | `mi_flag_candidates` durable (44k rows from 05-04); `mi_stocks_in_play` 180d — May-era rows start deleting **2026-11-22** |
| 12 exit-stack first firing | order/trade/audit events | ✅ | all durable |
| RT-only cohort (08-12 ruling: joins the review universe) | detected-in-rt-never-admitted names + outcomes | ⚠ | captured as `ep_rt_universe_catch` audit rows (245 since 07-27, one per ticker-day, durable) — but THIN (ticker/gap/price/tick only; no volume/ADV/score) and in NO outcome join; daily outcomes joinable at $0 |
| Skip taxonomy (was the skip right) | reason + context per skip, durable | ✅ | three durable surfaces: `mi_live_trades.skip_reason` (machine prefix + numbers), `mi_ep_missed_outcomes.skip_category`, `mi_ep_scan_log.filter_reason` |
| Blind spot 1 correction | intraday peaks | — | "peaks are floors" is now true only pre-07-25 and for the ALERT population; since #306 (07-25) traded-name peaks are minute-accurate from `mi_intraday_bars` |
| Blind spot 11 (re-derive 08-06/07 grades) | raw catalyst corpus | ✅ | `mi_ep_catalyst_metrics` 180d — safe through a November test, deletes **2027-02-07** |

### RANKED GAPS — cheapest first (nothing built; operator orders these)

1. **Stop deleting `mi_ep_alerts` at 90d** (exempt from `purge_old_data`, or ≥365d). One line in
   the cutoffs dict; the table is 403 rows. The ONLY surface where this quarter's data is destroyed
   BEFORE next quarter's test can read it. Without it, every August-board question (rows 1, 2, 10)
   is answered from thin summaries in November.
2. **Bump `mi_intraday_bars` 120d → ≥270d** (same dict, one line) so this quarter's traded-name
   minute paths survive past 12-06 into any Q4 comparison.
3. **Persist day-of minute bars for EVERY live alert ticker-day** (skips, cancels, moderates, rt
   catches included): a small EOD loop reusing the existing `get_minute_bars_range` +
   `persist_intraday_bars` — ~10–20 names/day × 390 bars, trivial volume. Closes the 56% hole;
   makes the HOLD test, 620 timing, and #559's reclaim split answerable from OUR tables instead of
   betting on a vendor refetch. The one "start writing rows" build in this list.
4. **Join the rt-catch cohort into `mi_ep_missed_outcomes` as a 4th source** (from the durable
   audit rows) so the 08-12 "include this cohort" ruling accrues outcomes automatically. Optional
   now — the raw events are durable, so this can be done at analysis time instead.
5. **Notes, no build:** `mi_daily_closes` 400d caps structure lookback at ~13 months (Polygon
   refetch covers deeper); `mi_stocks_in_play` 180d starts binding 11-22; probe `.tsv` captures
   cited by this doc are partly untracked (machine-local) — they are point-in-time copies of data
   that will age out.

Items 1–2 are retention-of-telemetry changes; item 3 writes shadow rows; none touches any
detection/entry/exit path. All still require the operator's go — nothing was changed in this pass.

### 2026-08-15 (same day, operator-approved) — items 1-3 BUILT + backfilled

- **Item 1 shipped**: `mi_ep_alerts` exempt from `purge_old_data` — kept forever (~20-40 MB/yr).
- **Item 2 shipped**: `mi_intraday_bars` 120d → **1825d (5 years)** — the operator's frame is
  YEARS across market conditions; ~1-1.3 GB/yr at the measured 571 B/row all-in, 5y ceiling
  ≈ 6-7 GB vs 58 GB free. Bounded, not forever, so growth cannot run away.
- **Item 3 shipped**: `order_manager.persist_alert_day_paths` + execution job
  `alert_day_path_persist` (16:22 ET) — day-of minute bars for every `mi_ep_alerts` ticker-day
  UNION the day's `ep_rt_universe_catch` tickers; covered names skip; thin days log
  `path_coverage_gap`.
- **Backfill DONE (additive, ON CONFLICT DO NOTHING)**: all 276 sub-300-bar alert+rt-catch
  ticker-days since 07-28 refetched from Alpaca SIP — **0 unrecoverable**; the 98 alert
  ticker-days now hold 98/98 intraday paths (92 full; 6 sparse-tape names whose complete day
  is <300 prints). "Vendor-recoverable" is now empirically TRUE for this window.
- **Guard**: `health_checks.run_db_growth_check` in the nightly audit — records DB size + top
  tables as its own baseline (audit log IS the store); Telegrams only when pro-rated weekly
  growth >300 MB (~10x plan) or DB >30 GB, deduped to at most weekly.
- Items 4-5 remain unbuilt (item 4 stays analysis-time-doable; item 5 notes stand).

### What could NOT be measured

- **Old-backup retention** (whether pre-purge pg_dumps survive to November) — unverified; treated
  as not-a-store.
- **Alpaca historical minute-bar availability for delisted/renamed symbols** — the refetch
  assumption behind every "vendor-recoverable" above; ~~untested~~ now tested for live symbols
  07-28→08-14 (276/276 served); delisted/renamed still unexercised.
- **`mi_ep_scan_outcomes` MAX(scan_date)=08-07 on 08-15** — consistent with its designed
  [today−15, today−5] settling window (verified in `outcome_tracker._compute_ep_scan_outcomes`),
  not dark; flagged so nobody re-diagnoses it.
