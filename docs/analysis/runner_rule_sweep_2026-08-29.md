# Runner-rule sweep — same 194 trades, only the post-partial rule varies

**Date:** 2026-08-29 (PT) · **Parent:** `docs/analysis/ep_backtest_run1_2026-08-29.md` (run 1)
· **Status:** read-only evidence. Nothing changed, nothing deployed, nothing proposed.
· **Standard:** `docs/methodology/analysis_standard.md` — §1 answered in §0; Gate 6 sections present.

---

## §0 · The decision this serves

Run 1 found: 106 of 194 filled trades hit the +2R partial, and **82 of those 106 gave the
runner all the way back to breakeven and finished at exactly +0.33R**. Operator, on the
outlier framing: *"that's exactly what EP strategy is, find the outliers, how can you not know
this."* The runner is where the expectancy lives, and the current breakeven stop surrenders it
on 82 of 106 winners.

1. **Decision:** holding the same trades and entries, does any runner rule beat the current
   move-stop-to-breakeven rule?
2. **What would change it:** a rule whose mean AND distribution beat the control on the
   identical cohort, with the cost of the wider stop quantified, not hand-waved.
3. **Population:** run 1's Run U scored cohort, n=194, reproduced exactly (§1).
4. **What would make it wrong:** §5 — concentration in a few correlated names, daily-bar
   granularity, marks-vs-realized exits at the window's end.

**HEADLINE:** almost every looser runner rule beats the control on mean — best is
**hold-20-sessions-then-sell (+0.36R vs +0.14R, same 194 trades)** — but every one of them
buys the mean by flipping the median trade from **+0.33R to −0.33R** (win rate 55% → 25–44%),
and **no rule separates from the control at 95% confidence on this sample** (best:
P(better) ≈ 0.97, CI includes zero). The mechanism is unambiguous: the 82 breakeven
round-trips are worth **+12R to +51R** under every alternative rule; most alternatives pay
part of that back by clipping the 24 existing runners early. The direction is consistent
across 11 of 13 rules; the magnitude is not yet statistically settled at n=194.

---

## §1 · Method / population

- **Population: run 1's Run U replayable rows, reproduced row-for-row.** The sweep loads the
  SAME captures (`/Users/alvinfung/.claude/jobs/6b173ac9/tmp/bt_*` — `mi_intraday_bars` +
  `mi_daily_closes` pulls, captured once in run 1; zero new DB reads) and GATES on a full diff:
  the control rule must match run 1's stored reason and R on **all 295 replayable rows**
  before any other rule is computed. It does (`GATE PASS`, `runner_sweep_stdout.txt`).
  Scored cohort n=194; the same 194 rows score under every rule (0 rows lost to any rule).
- **Harness: `scripts/probes/_bt_replay.py` EXTENDED IN PLACE** with a `runner_rule`
  parameter (uncommitted working-tree edit) — not a second replayer. The default rule is
  byte-identical to the original: the original self-test battery and both mutation tests are
  green, a `default_rule_reproduces_original_battery` test pins it, and the 295-row diff pins
  it against real data. Driver: `scripts/probes/_runner_sweep.py`.
- **What is FIXED across every rule (shared code, not convention):** population, admission,
  the 09:31–09:59 stop-limit fill at ORB high, the `entry − 2R` hard stop, the +2R partial
  (1/3 off at exactly +1.0R), stop-first tie-breaks, the 40-session horizon, coverage
  handling. **Only the stop governing the remaining 2/3 after the partial fires varies.**
- **The rules** (post-partial only; R unit = entry − hard_stop, as run 1):

  | rule | runner governed by |
  |---|---|
  | breakeven (CONTROL) | stop to entry, touch — today's live bracket |
  | hard | no breakeven move; `entry − 2R` stop stays, touch |
  | sma10 / sma20 | daily close below the stock's real SMA10/SMA20 → exit at that close (live `exit_logic.py` semantics: close-below, prior closes end D−1 per #548); hard stop stays as touch floor |
  | live_trail_be | what the live exit ladder composes: breakeven touch floor PLUS close below max(SMA10, SMA20) → exit at that close |
  | atr1 / atr2 | chandelier: touch of (peak close − 1×/2×ATR14@entry), ratcheting, prior-session peak (no same-bar lookahead), floored at hard stop |
  | gb25 / gb50 | give back 25%/50% of peak-close gain: close below entry + 0.75/0.50 × (peak − entry) → exit at that close |
  | t3 / t5 / t10 / t20 | hold N sessions after the partial day, sell the Nth session's close; hard stop stays as touch floor |

  ATR14 uses the admission filter's own arithmetic (absolute, through D−1). Trail SMAs are
  the stock's real moving averages (27 prior closes + entry-day close + held closes). Inputs
  census: 0 trades missing ATR14, 1 with <20 prior closes (P 05-11, IPO — SMA20 falls back
  to SMA10, the live None-guard), 0 missing the day-0 close.
- **Era:** entries 2026-04-13 → 08-28 admitted under TODAY's rules (run 1's Run U,
  catalyst-generous arm). All run-1 caveats inherit (§5).
- Captures: `runner_sweep_results.json`, `runner_sweep_rows.tsv` (per-trade R under all 15
  variants), `runner_diag*_out.txt`, `runner_trace_out.txt` under the job tmp dir.

## §2 · The numbers — every rule against the control, same 194 trades

Sorted by mean. `floor-outs` = of the 106 partial-takers, how many ended at exactly −0.33R
(runner rode back to the original hard stop — a winner turned net loser: THE cost of not
moving the stop). `given-up / gained` = paired per-trade deltas vs the control.

| rule | n | mean R | median R | win% | floor-outs (of 106) | worse than ctrl | R given up | better than ctrl | R gained | runner marks still open at data end |
|---|---|---|---|---|---|---|---|---|---|---|
| **t20** | 194 | **+0.358** | −0.333 | 25% | 57 | 67 | −44.3 | 24 | +86.3 | 16 |
| t5 | 194 | +0.296 | −0.333 | 36% | 37 | 59 | −43.6 | 46 | +73.4 | 2 |
| sma20 | 194 | +0.283 | −0.333 | 31% | 45 | 61 | −44.5 | 31 | +72.0 | 17 |
| t3 | 194 | +0.273 | −0.333 | 40% | 27 | 50 | −50.4 | 55 | +75.8 | 2 |
| atr1 | 194 | +0.265 | −0.333 | 44% | 17 | 49 | −42.1 | 56 | +65.9 | 2 |
| atr2 | 194 | +0.238 | −0.333 | 36% | 31 | 62 | −48.1 | 38 | +66.8 | 8 |
| gb25 | 194 | +0.236 | −0.333 | 43% | 22 | 49 | −43.0 | 56 | +61.2 | 1 |
| t10 | 194 | +0.230 | −0.333 | 28% | 51 | 67 | −52.3 | 32 | +69.2 | 9 |
| gb50 | 194 | +0.229 | −0.333 | 42% | 25 | 49 | −39.4 | 45 | +56.3 | 12 |
| hard | 194 | +0.207 | −0.333 | 21% | 63 | 68 | −43.4 | 14 | +56.1 | 43 |
| sma10 | 194 | +0.144 | −0.333 | 33% | 39 | 63 | −51.3 | 34 | +51.6 | 9 |
| **breakeven (control)** | 194 | **+0.142** | **+0.333** | **55%** | 0 | — | — | — | — | 24 |
| live_trail_be | 194 | +0.131 | +0.333 | 55% | 0 | 11 | −22.4 | 22 | +20.2 | 7 |

Control reproduces run 1 exactly: mean +0.142 / median +0.333 / 82 trades at exactly +0.33R /
24 above (their median +1.98R) / 85 stopped at −1.0R. Same 85 stops and 3 held-to-close rows
under every rule by construction.

**Where each rule's money comes from — the 82 scratches vs the 24 existing runners
(the decomposition that answers the finding directly):**

| rule | net R on the 82 round-trippers | net R on the 24 existing runners | total Δ vs control |
|---|---|---|---|
| t3 | +50.9 | −25.5 | +25.4 |
| atr1 | +41.7 | −17.8 | +23.9 |
| gb25 | +39.9 | −21.7 | +18.2 |
| sma20 | +39.3 | −11.8 | +27.4 |
| t5 | +37.5 | −7.7 | +29.8 |
| t20 | +34.8 | **+7.2** | +42.0 |
| hard | +12.6 | 0.0 | +12.6 |
| live_trail_be | +19.3 | −21.5 | −2.2 |

- **Every rule's improvement is the 82.** Under the control they contribute exactly zero
  beyond the partial; under every alternative they are worth +12R to +51R in aggregate.
- **Most rules pay a runner-clipping tax on the 24:** a trail or time exit sells AOSL/BABA/
  QCOM-class runners earlier than the control's 40-session mark. t20 is the exception (it
  even beats the mark on the 24 — momentum in this window faded after ~a month, so selling
  session 20 beat holding to session 40).
- **live_trail_be — the full live exit ladder — is a wash vs the control** (+0.131 vs
  +0.142): it harvests +19.3R from the scratches (it can only improve them — its floor is
  the same breakeven touch) and gives back −21.5R clipping the big runners early. The live
  system's actual behavior on this cohort ≈ the harness's control.
- Ex-AOSL+BABA (run 1's two carriers): control mean **−0.007**; t3 +0.199, t20 +0.162,
  t5 +0.151, sma20/atr1 +0.142 (all n=192). The alternatives' edge does NOT reduce to the
  two monsters — the control's does. The looser rules turn ~10–20 mid-sized runners
  (QCOM, STM, NVTS, MRVL, RKLB, FTK, DOCN, COHR, SGML) into paid outcomes; the control
  scratches every one of them.
- Month split (n: Apr 48 / May 65 / Jun 14 / Jul 25 / Aug 42): the alternatives win by
  amplifying April and July (trend months) — e.g. t20 Apr +1.07 & Jul +1.30 vs control
  +0.66/+0.51 — while May/June stay negative under every rule (atr1 is the only rule that
  turns May positive, +0.03 vs −0.34). No rule's edge lives in a single month, but all of it
  lives in trend months.

## §3 · Does anything beat the control? The statistical answer

Paired bootstrap on per-trade deltas vs control (10k resamples; second row clustered by
calendar week, 19 clusters, because April/July semis moved together):

| rule | mean Δ/trade | 95% CI (per-trade) | P(Δ>0) | P(Δ>0), week-clustered |
|---|---|---|---|---|
| t20 | +0.216 | [−0.00, +0.47] | 0.973 | 0.970 |
| t5 | +0.154 | [−0.01, +0.33] | 0.968 | 0.963 |
| sma20 | +0.141 | [−0.07, +0.39] | 0.896 | 0.869 |
| t3 | +0.131 | [−0.07, +0.33] | 0.902 | 0.914 |
| atr1 | +0.123 | [−0.04, +0.29] | 0.927 | 0.926 |
| gb25 | +0.094 | [−0.06, +0.25] | 0.884 | 0.898 |
| hard | +0.065 | [−0.12, +0.29] | 0.722 | 0.670 |
| live_trail_be | −0.011 | [−0.13, +0.10] | 0.424 | 0.423 |

**No CI excludes zero.** The honest verdict: the direction (looser runner > breakeven) is
consistent and mechanistically explained, the best candidates are t20 / t5 / atr1, and the
control is NOT confirmed beaten at conventional confidence on 194 trades whose winners
cluster in two theme runs. What settles it is more sample (the system keeps trading) — not a
different analysis of the same window.

## §4 · The cost of each rule, stated plainly

- **The median trade gets worse under every improving rule.** +0.33R → −0.33R: the modal
  partial-winner stops being a scratch and becomes a small net loser. Win rate 55% → 25–44%.
  Psychologically this is a different book: t20 means ~57 of every 106 partial-winners ride
  all the way back down to the original stop and finish red.
- **Floor-outs are the whole cost.** No rule loses more than −1R on any trade (the hard stop
  never widens); the cost is winners surrendered back to −0.33R, in the counts tabled above.
- **Overnight gap pricing (touch exits priced at the level are optimistic):** re-pricing all
  touch exits at the open when a bar opens through the level costs −0.016 to −0.025R of mean,
  uniformly — it does not reorder the table (`runner_sweep_stdout.txt`, gap-fill block).
- **Marks vs realized:** the control's entire right tail (all 24 survivors) is an UNREALIZED
  40-session/data-end mark; atr1/gb25/t3/t5 realize all but 1–2 of their exits. `hard` is
  the worst offender in the other direction: 43 of its 106 runners are still-open marks.
  t20: 16 (late-August entries lack 20 post-partial sessions).

## §5 · Adversarial — what would make this wrong

- **Are all rules the same bet on a handful of names? Substantially yes — quantified:** the
  top-5 positive deltas carry 86–305% of each rule's total improvement (over 100% means the
  rest of the book is a net drag). The same names recur across every rule (STM/QCOM/NVTS
  04-2x, MRVL/COHR 07-30, RKLB 05-08, FTK 08-03, BABA 07-08). That is also the strategy's
  stated thesis — find the outliers, hold them — but it means the between-rule ranking
  (t20 vs t5 vs atr1) is noise; only the shared direction (don't surrender the runner at
  breakeven) has weight, and even it doesn't clear 95% (§3).
- **Daily-bar granularity:** intra-hold minute bars are not in the capture, so trail checks
  are daily. Both semantics were run for the SMA trails: close-below (live's own semantics,
  used in the table) and intraday-touch (`sma10_touch`/`sma20_touch`: means +0.19/+0.30 vs
  +0.14/+0.28) — the choice moves means by ±0.05 without reordering the conclusion. Same-bar
  peak-then-stop ambiguity resolves conservatively (prior-session peak, stop-first). A
  minute-level trail on the runner days remains unmodeled either way.
- **Survivorship toward the window's end:** the cohort is FIXED at the control's 194 scored
  rows and every rule scores the same 194 — no rule silently drops rows (0 across the board).
  The residual channel is marks-at-data-end (§4) plus run 1's 16 no-bars exclusions, which
  flatter all rules equally and the control alike.
- **Verification:** control reproduced against run 1 row-for-row (295/295) before any rule
  was computed; harness self-tests + both mutation tests + 8 new runner-rule synthetic tests
  green; two trades hand-traced end-to-end from the raw captures (QCOM 04-24: partial on
  session 1, t20 exit at session-21 close 248.82 = the reported +12.2R delta; sma20 exit
  session 29 at 215.94 < SMA20 224.49 = the reported +8.2R delta) — `runner_trace_out.txt`.
- **Inherited from run 1, unchanged:** Run U over-admits (catalyst-generous arm; the judge,
  sustain/RVOL gates and premarket inputs are not reconstructible for $0), fills are
  mechanical at exact prices with no slippage, and the sign of the WHOLE system's expectancy
  is still the L/U band question. This sweep compares runner rules WITHIN that cohort; it
  does not tighten the band.

## What this does not answer

- **Whether any rule beats the control out of sample.** n=194, winners concentrated in two
  correlated theme runs; no CI excludes zero. This is evidence of direction, not a settled
  ranking among t20/t5/atr1/sma20.
- Position-sizing or portfolio effects of a 25–44% win-rate book (drawdown strings of
  −0.33R floor-outs interacting with the daily loss limit and breakers — not modeled, per
  run 1 D6).
- Hybrids not in the candidate list (e.g. breakeven-after-N-sessions, partial-at-trail
  ladders, regime-switched rules) — the sweep covers the brief's list plus the live ladder.
- Anything about entries, admission, the partial itself, or the initial stop — all
  deliberately frozen.
- The live judge/catalyst reconstruction (run 1 Stage 1b, ~$40, not spent).

## ⚖ THE LINE

Evidence only. Exit discipline is the operator's sole authority. Nothing here was changed,
deployed, or proposed as a change — the harness edit is an uncommitted working-tree probe
extension, the live system is untouched, and any action on these numbers (including "collect
more sample and re-run") is the operator's decision alone.
