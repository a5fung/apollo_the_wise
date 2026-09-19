# #299 — Should we pay for the tape-axis re-grade? One page to say yes or no to (2026-09-19)

**The answer: NO — do not fund it. The free features already answer the question the paid run was
built to ask. The one genuinely new thing the tape axis would tell the judge — how violently the
stock opened — does not exist yet when 7 in 10 of today's HIGH alerts are graded (61 of 85 alert-days
since Aug 1 were graded before 9:35), and where it can be measured it points the WRONG way on the EPs
you named: HTFL, MRNA and CHPT opened more violently than roughly 9 in 10 alerts. If you still want a
paid read, the smallest honest one is $34 for the whole path (option B), not the $170 carried since June.**

## What you are deciding

- **Yes / no / scoped**: spend **$86** (full) or **$34** (scoped) to re-grade past HIGH alerts twice —
  with and without the tape block in the judge prompt — so you can label whether the grade changes the
  tape causes are right.
- Your own condition (2026-09-05): *"until we can justify the spend by a concrete outcome that is useful
  for our system, we don't spend... we can also scope it smaller to spend less for an early read."*
- A finding, not a change: nothing here flips a toggle, a prompt or a rule. **The spend is yours; the
  wiring is yours; the entry rule is yours.**

## What a tape-axis read would CHANGE — the decision it moves

- **One decision: the judge's tier on a HIGH alert.** The judge is load-bearing today
  (`holistic_judge_enabled = on` since 2026-06-10; 178 of 181 alerts in the last 95 days carry
  `grade_engine_authority = judge`). A HIGH → MODERATE demote removes the Telegram HIGH alert and the ORB
  entry. Nothing else in the system reads the tape block.
- **The block's only directional instruction is a demote cue** (the pace and dollars-traded lines are neutral facts). It tells the judge: *"Opening-range ÷ ATR: X (>~0.25-0.30 = a
  violent open — bracket geometry is structurally poor; weigh entry quality, not just the catalyst)"*,
  plus a premarket-pace line and a dollars-traded line. It carries no promote instruction.
- **So on the four named EPs the judge already graded HIGH (PLTR, TEAM, HTFL, MRNA) it can only leave
  them alone or demote them.** No recall upside on the ground truth — only recall risk. On the other
  three (BFLY, ABNB, CHPT) the judge never ran; the axis structurally cannot act on them.

## What it would have read on the seven EPs you named (n=7, the whole ground-truth list)

| EP | graded at (ET) | what the judge would have seen AT GRADE TIME | 5-min OR ÷ ATR (pct of 319 alerts) | 1-min ORB bar ÷ ATR (pct of 317) | existing `tape_tier` | what would differ |
|---|---|---|---|---|---|---|
| BFLY 06-18 | never (catalyst graded `routine`, score ≤25 of 50) | — | 1.92 (84th) | 0.21 (8th) | — | nothing — the axis cannot reach a name the judge never grades |
| PLTR 08-04 | 07:00 | *"9.3x the premarket baseline by 07:00 ET"* — the prompt already shows `Pre-mkt RVOL: 9.34` | 1.11 (54th) | 0.90 (71st) | clean | nothing new: the pace line restates a number the judge already has |
| ABNB 08-07 | never (top-20 gap cut — a rule replaced 08-22) | — | 1.88 (84th) | 1.00 (78th) | — | nothing — never scored |
| TEAM 08-07 | 08:50 | *"25.5x the premarket baseline by 08:50 ET"* — prompt has `Pre-mkt RVOL: 25.54` | 1.13 (54th) | 0.50 (41st) | clean | nothing new |
| HTFL 08-14 | 07:00 | *"8.5x the premarket baseline by 07:00 ET"* — prompt has 8.53 | **2.63 (94th)** | **1.75 (97th)** | clean | nothing new at grade time; at 9:35 the block would read "violent". The live entry rule already refused it (`stop_too_wide`: ORB range $2.55 > 1.5×ATR $2.19). Stock 31 → 49. |
| MRNA 08-19 | 07:10 | *"14.0x the premarket baseline by 07:10 ET"* — prompt has 13.95 | **2.07 (88th)** | **1.37 (91st)** | **junk** — the only junk flag among 107 HIGHs since 07-21 | nothing new at grade time; at 9:35 "violent". Your *"textbook EP"*. |
| CHPT 09-03 | never (market cap $134M) | — | **3.29 (99th)** | **1.29 (90th)** | — | nothing — never scored |

- **Of 7 named EPs: 4 reached the judge, 0 would gain anything, and 3 (HTFL, MRNA, CHPT) sit at the
  88th–99th percentile of opening violence — the class the block tells the judge to mark down.**
- The analysis standard's own rule: *if a conclusion puts the labelled EPs in a losing bucket, the
  conclusion is wrong, not the EPs.* With n=7 you can read every row; that is what makes it decisive.

## The $0 check, run first — what the free features already say

Same features the paid run would put in the prompt (`tape_features.compute_or_atr`, the premarket-pace
line, liquidity), computed from stored bars for every HIGH alert. No LLM call. Probe + captures:
`scripts/probes/_299_tape_free_features.py` / `.sql`.

**1. The feature is mostly absent when the grade is made — the June "79%" no longer describes today.**

| era | HIGH alert-days (n) | opening range existed at grade time |
|---|---|---|
| May–Jul | n=237 | 151 (64%) |
| Aug 1–21 | n=67 | 19 (28%) |
| Aug 22 → Sep 17 (current admission era) | n=18 | 5 (28%) |

The scan now grades most HIGHs pre-market (7:00–9:30), where the opening range is None by construction.

**2. The block's threshold is wrong for gap days — it would call almost every alert "violent".**

| range measured | n | median ÷ ATR | reads "violent" (> 0.30 per the prompt) |
|---|---|---|---|
| 5-min opening range (9:30–9:34, what the rig computes) | n=319 | 1.05 | 306 (96%) |
| 1-min ORB bar (9:30, what the entry uses) | n=317 | 0.61 | 268 (85%) |

A cue that fires on 96 of 100 alerts separates nothing: the judge either ignores it (a null result) or
marks down almost everything. Written for ordinary days, not for a stock gapping 15%.

**3. Does opening violence separate the winners? No — and the "orderly" end is the worst.**
1-month close-to-close return, no stop; only pre-08-22 alert-days have settled outcomes.

| 5-min OR ÷ ATR | n | ≥ +20% in a month | ≥ +40% | p90 | median |
|---|---|---|---|---|---|
| low third (0.13–0.85, "orderly") | n=62 | 5 (8%) | 2 | +16.3% | −8.8% |
| mid third (0.85–1.52) | n=62 | 7 (11%) | 3 | +26.0% | −3.1% |
| high third (1.52–3.55, "violent") | n=64 | 6 (9%) | 0 | +19.5% | −0.6% |
| 1-min bar, low third (0.00–0.47) | n=62 | 6 (10%) | 2 | +17.5% | −5.8% |
| 1-min bar, high third (0.90–2.16) | n=63 | 8 (13%) | 1 | +20.6% | −3.2% |

The prompt's own cut (≤ 0.30 = orderly) holds only n=5 rows — too few to judge; the tertiles are the read.

**4. Premarket pace is already in the prompt.** `Pre-mkt RVOL` sits on the judge's SETUP line for every
alert; the tape's pace line re-renders that number for the 72% graded pre-market (for post-open grades
it becomes a session-pace read — a different number, but see row 3 of the table above for how little
pace separates). Tail cut: below-median pace 11 of 83 (13%) big winners vs above-median 6 of 80 (8%) — no
separation, and it leans against a "hot = good" read. The named EPs sit at the 49th–81st percentile.

**5. The existing tape function does not separate either.** `tape_tier` (#498): clean 3 of 70 (4%) big
winners vs watch/junk 1 of 11 (9%); its single junk flag among 107 HIGHs is MRNA.

**6. The system already has this rule where the range is actually known.** The live entry refuses a
name whose 1-min ORB range exceeds 1.5×ATR (`setup:stop_too_wide`). In practice it refused 9 of the 192
MAGNA53 alert-days that reached the entry stage since 05-11 (4.7%, `mi_live_trades`); the same arithmetic
on all 317 HIGH alert-days reads "too wide" on 21 (7%) — the gap is alert-days that never reach entry.
Its known action on the ground truth was to refuse HTFL. Putting the same idea in the judge as a demote
cue duplicates a gate that already acts at 9:31.

## The options, priced — whole path, one number each

`pricing_for(effective_model("JUDGE_MODEL"))` = claude-opus-5 at $5 / $25 per million tokens; a judge
call is 5,149 tokens in + 477 out (measured p50 of live `ep_grade_judge` calls, last 45 days) = $0.0377,
$0.0381 with the tape block. Path = the eval, the post-wire re-run the June plan requires, and 12 months
of running cost.

| option | rows | judge calls | eval | + post-wire re-run | + 12 months live | **WHOLE PATH** |
|---|---|---|---|---|---|---|
| **A — FULL**: every HIGH alert-day, both arms ×3 replicates | n=322 | 1,932 | $73 | $12 | $0.39 | **$86** |
| **B — SCOPED**: only alert-days graded after 9:35 (the opening range existed), both arms ×2 | n=175 | 700 | $27 | $7 | $0.39 | **$34** |
| **C — nothing**: close #299 on the $0 check above | n=0 | 0 | $0 | — | — | **$0** |

- **Why not the $170 from June:** June priced 570 rows at an assumed $0.05 per call. The table today holds
  322 unique HIGH alert-days and the measured cost is $0.038 per call.
- **Caveat on B:** 151 of its 175 rows are May–July alerts, admitted by rules replaced 08-19 → 08-22 (gap
  floor, separation scoring, pre-score shortlist). It answers *"did the block change the judge's mind"* on
  the old population, for a feature available on 28% of today's alerts.
- **A different design, not the rig — named, not recommended:** a second judge call at 9:35 for
  pre-market-graded HIGHs, able only to cancel a still-unfilled stop-buy. 30 of 42 MAGNA53 fills since
  June (7 in 10) were done before 9:35, so it could act on ~3 in 10. It touches entry — **your call**,
  not mine. Running cost $33 a year plus the build.

## What we do at each outcome

| outcome | what we do |
|---|---|
| **You choose C (recommended)** | Close #299 as answered by the free features. The judge keeps grading without the block — no regression, it never had it. One optional $0 follow-up: rewrite the threshold text in `tape_features` / the prompt on gap-day percentiles (median 1.05, top-10% 2.2) so nobody re-proposes the 0.30 cue; prompt text on an unwired feature, not THE LINE. |
| **You fund A or B and the result is NULL** (no stable verdict changes) | $34–86 spent to learn the judge ignores the block. Close #299; nothing wired. |
| **Tape changes verdicts and you label them RIGHT** | CHANGE_PROCESS entry + your sign-off → wire the tape into `_judge_shadow` → re-run → monthly backward check. Expect the demotes to sit at high OR ÷ ATR — where HTFL, MRNA and CHPT live — so this branch means you are comfortable marking that class down. |
| **Tape changes verdicts and you label them WRONG** (HTFL/MRNA-class demotes) | Close #299 with the answer *"harmful as designed"*; nothing wired. |
| **Tape PROMOTES something** | Outside the design (the block has no promote cue). Judge noise unless it survives the replicate check. |

## Method / population

- **Population:** every `score_tier = 'HIGH'` row in `mi_ep_alerts` (355 rows, 2026-05-11 → 09-17),
  reduced to the FIRST HIGH row per ticker-day = **n=322 alert-days** (the row that fired the alert and
  the ORB order). Eras split at 08-01 and at 08-22 (`rule_eras.SEP_SCORE_DATE`, the current admission
  era). The table only reaches back to 05-11, so June's "569 HIGHs since 03-16" is not reproducible.
- **Features:** 5-min opening range from `mi_intraday_bars` (9:30–9:34, the rig's `opening_range`) and
  the 9:30 one-minute bar; ATR-14 from `mi_daily_closes` strictly before the alert date, through the
  live `compute_or_atr`; premarket pace = the stored `pm_rvol` (the number `compute_pm_vol_curve`
  renders); liquidity = ADV shares × prior close (the scan tick's dollar-volume fields are only populated
  from September). Hand-checked on HTFL 08-14: OR 36.04–39.88 = $3.84, ATR-14 $1.46 → 2.63; its 1-min
  bar $2.55 and 1.5×ATR $2.19 reproduce the live `stop_too_wide` skip text exactly.
- **Outcome:** `mi_signal_outcomes` `ep_alert` 1-month close-to-close (191 of 322 settled; 0 of 18 in
  the current era). No stop in it — a −30% row was −1R in reality. Tail first (≥20% / ≥40% / p90), median
  after, per the analysis standard.
- **Ground truth:** `docs/methodology/operator_labelled_eps.md`, all 7 names; the three that never became
  alerts get their opening range straight from the bars.
- **Availability at grade time:** `detected_at` ≥ 09:35 ET (the grade moment; not mutated post-grade).
- **Pricing:** `shared.llm_models.pricing_for` on today's resolved judge model; token counts from
  `api_usage`, caller `ep_grade_judge`, last 45 days (n=91 calls, p50).

## What this does not answer

- Whether a **re-calibrated** opening-range cue (threshold set on gap-day percentiles, e.g. top 10% =
  > 2.2) would help. The tertiles show no tail difference, but each third is n≈62 and every settled
  outcome predates the 08-22 admission rules.
- Whether **liquidity / spread** would help: no spread data exists for the population, and every named EP
  is a large cap where dollars-traded is trivially fine.
- Anything about the **current admission era's outcomes**: 18 alert-days since 08-22, none settled.
- The value of the **9:35 re-grade design** — priced above, never measured.
- What the judge would actually DO with the block: that is exactly what the paid run measures, and this
  page argues it is not worth measuring as designed. A null here is "the free features cannot justify
  it", not "tape can never matter".

## ⚖ THE LINE

Nothing was flipped. The judge toggle, the judge prompt, the tape wiring (still not passed by the scan),
the `stop_too_wide` entry rule and every entry/exit rule are untouched. Funding, wiring, and any change
to how the opening range gates entry are the operator's decisions and are put to him here, not made.

## Sources

- June rig + the finding this page re-tests: `docs/analysis/tape_judge_eval_299_2026-06-17.md`,
  `scripts/eval_tape_judge.py`, `agents/market_intelligence/tape_features.py`.
- The judge prompt's SETUP and TAPE blocks: `agents/market_intelligence/ep_grade_judge.py` (the
  `Pre-mkt RVOL` line and the `--- TAPE / INTRADAY CHARACTER ---` block).
- The live entry rule this duplicates: `agents/market_intelligence/broker/order_manager.py`
  (`SETUP_STOP_TOO_WIDE`, ORB range > 1.5×ATR).
- Reproduction: `scripts/probes/_299_tape_free_features.sql` (three read-only captures) →
  `PYTHONPATH=. python3 scripts/probes/_299_tape_free_features.py`.
