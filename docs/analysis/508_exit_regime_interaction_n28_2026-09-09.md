# Exit × regime at n=28 live: regime DOES change the right exit, and the swing is 0.78R on one rule

**2026-09-09 · read-only offline replay · $0 · the `exit_regime_interaction_review` gate (n≥25,
ready since 2026-07-29 and never run) · probes `_508_pull_snapshot.sh` → `_508c_regime_separability_2026-08-17.py`**

## Method / population — which rows, over what window

- **Rows.** `mi_sell_discipline_records` joined to `mi_live_trades`, fresh prod snapshot pulled
  2026-09-09 (read-only `COPY TO STDOUT`): **59 records total — live/magna53 n=28**, paper/magna53
  n=24, paper/9m_day2 n=7.
- **Only live/magna53 decides.** Paper cells are reported separately and never pooled: different
  sizing, different safeguards, different fills.
- **`9m_day2` is excluded** — deprecated strategy, not evidence.
- **Regime is ENTRY-STAMPED** (`mi_live_trades.regime`), not date-joined from `mi_market_regime`.
  The two disagree on 5 of 17 live trades because a day's regime can be REVISED after entry, and
  the operator adopted the entry-stamp on 2026-08-08. ⚠ **The review's own predicate still uses the
  date join**, which reads Bull=9 where the entry-stamp reads 11 — the fire was valid, the count
  it fired on was not the one this analysis uses.
- **Exit variants are a replay** of stored minute and daily bars under each candidate rule, using
  the tested `_508_exit_rule_replay.py` engine unchanged. Nothing was re-implemented.
- **At registration (2026-07-29) this cohort was n=10, every regime ≈ −0.9R, zero winners anywhere.**

## What changed since registration: regime now separates on realized R

| entry-stamped regime | n | realized R | wins | peak R reached | share ≥2R |
|---|---|---|---|---|---|
| Bull | 11 | **+0.01** | 4/11 | +2.06 | 45% |
| Choppy | 9 | −0.28 | 2/9 | +1.88 | 22% |
| Correcting | 7 | **−0.97** | 0/7 | +1.50 | **43%** |
| Crisis | 1 | — | — | — | n<4, not a result |

**The Correcting row is the finding.** Those trades reach +2R at **43%** — statistically level with
Bull's 45% — and **not one of the seven ended positive**. The excursion is there; nothing banks it.
Bull, on the same rule, converts 4 of 11. So the giveback is no longer uniform the way it was at
n=10: it is now concentrated in Correcting.

## The answer to his July question, and the rule that shows it

> *"does taking early profits in correcting vs bull regime work better"* — operator, 2026-07-29

**Yes, and it reverses.** Replayed on live/magna53 only:

| exit rule | live-Bull (n=11) | live-Correcting (n=7) |
|---|---|---|
| **actual (what we ran)** | +0.01 | **−0.97** |
| `ADR1_exit_all` | **−0.29** | **+0.49** |
| `R2_exit_all` | **+0.36** | **+0.27** |
| `R1.5_exit_all` | +0.36 | +0.06 |
| `R2_part1/3+BE` | +0.28 | −0.30 |
| `R1_part1/3+BE` | +0.25 | −0.44 |

- **In Correcting, ONLY full-exit arms turn positive.** Every partial-plus-breakeven arm stays
  negative (−0.12 to −0.75). Taking a third off and moving to breakeven does not survive a
  correcting tape; the remainder gives it all back.
- **`ADR1_exit_all` is the cleanest demonstration of regime dependence: +0.49 in Correcting,
  −0.29 in Bull.** Same rule, **0.78R swing**, opposite signs. In Bull it is the worst arm on the
  board — it cuts the runners that make Bull work.
- **`R2_exit_all` is the only arm positive in BOTH** (+0.36 / +0.27) and beats what we actually ran
  in both regimes. If a single non-regime-aware change were wanted, that is the candidate.

## Recommendation — evidence only; the ruling is the operator's

⚖ **This is sell discipline. Nothing has been changed and nothing will be on my authority.** Two
options, stated as a fork:

1. **Regime-aware exit:** full exit near +1 ADR in Correcting, keep partial-plus-breakeven in Bull.
   Largest measured gain, and it matches his July hypothesis — but it fits two rules to two small
   cells and is the easier of the two to overfit.
2. **One rule, `R2_exit_all`:** positive in both regimes, beats actual in both, nothing conditional
   to get wrong. Smaller gain in Correcting (+0.27 vs +0.49) and gives up the Bull tail.

**My recommendation is (2)** — at n=11 and n=7 the regime-conditional gain is not worth the
overfitting risk yet, and `R2_exit_all` improves both cells without a conditional. Revisit (1) when
Correcting reaches n≈15.

## What this does not answer

- **Sample.** n=11 Bull, n=7 Correcting, n=9 Choppy, n=1 Crisis. These are cells, not populations,
  and a single trade moves a mean by ~0.1R.
- **It is a replay, not a live result.** No arm here has ever run on real money; fills are modelled.
- **It does not test whether the ADR arms interact with position sizing**, which also moves by regime.
- **Choppy is under-examined** — it sits between the two on realized R but was not given its own
  head-to-head grid.
- **Paper is excluded by design**, so nothing here says whether the same ordering holds there
  (paper/magna53 Bull is −0.62 over n=19, i.e. materially worse than live Bull — a difference this
  analysis notes but does not explain).
