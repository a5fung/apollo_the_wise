# Tape Quality Score (TQS) — structure-tightness / character filter for EP setups

**Status:** DESIGN — nothing gated to live. Shadow build is the only near-term action; any hard filter is
THE LINE (operator sign-off + backtest + evidence-gate). Design: Fable 2026-07-21, operator-aligned;
numbers reproduced + corrected by `scripts/probes/_tape_quality_step0.py`.

---

## 1. The problem it solves

EP (episodic-pivot) alerts get contaminated by low-quality **"gap-and-crap"** penny-like names — a stock
gaps up, spikes and collapses, and its outcome is a coin flip. This is **universal, not setup-specific**:
wide-and-loose tape is bad across ALL EP charts — gap-and-go / punch-through, gap-into-congestion / fades,
everything. It was simply most *visible* in the #331 "fades_into_congestion" cohort (weak-base gappers),
which is where it was discovered; gap-and-go names gap from strength and show fewer obvious offenders, but
the filter applies equally (operator, 2026-07-21: *"this applies to all charts — wide and loose is bad
generally"*). **TQS is a universal EP structure-quality read, not a #331 stratifier** — and the validation
in §3 reflects that (scored over the whole cohort, all alignment classes; #331 is just one application).

The operator's definition of quality is precise and **not trend direction**:

> Quality = **tight** price action — basing, trending up, down, or flat, direction doesn't matter. What we
> reject is **wide-and-loose**: large reversing bars, constant swings, whippy penny-stock character.
> **Caveat (operator):** an EP itself is a large bar — do NOT filter out what makes an EP an EP.

## 2. The metric

Measured over the **20 sessions strictly BEFORE the alert** — the gap/EP day is excluded by construction, so
a name is never penalised for its own thrust.

- **Per-bar primitive — NTR** (intraday range %) = `(high − low) / close × 100`. Deliberately **not**
  gap-aware TR: an overnight gap that then trades tight intraday is orderly; only intraday travel counts.
  Percent-of-close → $5 and $500 names compare directly.
- **Components:**
  | field | definition | role |
  |---|---|---|
  | `ntr_med` | median NTR | LEVEL / context + internal normaliser — **never gates** |
  | `spike_ct` | # bars with NTR > **2×** `ntr_med` | whipsaw frequency |
  | `spike_held` / `spike_rev` | each spike classified HELD (closed in outer 30% of its range in-direction AND kept ≥40% over the next 2 closes) vs REVERSED | **the EP-thrust discriminator** — a big bar that *holds* is fine; big bars that *reverse and repeat* = junk |
  | `bmr2` | **2nd-largest** NTR ÷ `ntr_med` | outlier magnitude, robust to exactly one legit event bar (earnings / prior EP) |
  | `adr` | mean NTR (Qullamaggie ADR%) | surfaced context only |

- **Verdict (rule "R1"):**
  ```
  tape_junk   = spike_rev >= 2  OR  spike_ct >= 4  OR  bmr2 >= 3.0
  tape_watch  = (not junk) AND (spike_rev == 1 OR spike_ct in {2,3} OR bmr2 >= 2.5)
  tape_clean  = otherwise
  unknown     = < 15 live bars   (NEVER junk — no penalty for missing data)
  ```

**Why not ADR% alone?** Measured on the 467-row cohort: `adr ↔ ntr_med` correlate +0.99 (one "level" factor),
but level ↔ the spike/reversal axis are **orthogonal** (ρ ≈ 0.05). The junk signal lives entirely in the
**reversal count**, not bar size. A level gate would delete the best winners — so ADR% stays as a surfaced
number, and the outlier/reversal terms do the filtering.

## 3. Validation (`scripts/probes/_tape_quality_step0.py`, prod cohort N=469)

**Operator-labelled 6/6 correct** — and it honours the EP-thrust caveat: **FCEL grades `clean` at ADR 15.1**
(0 spike bars) while junk HTCO is ADR 41 (4 spikes / 2 reversed). The discriminator is the reversal count,
not the volatility level.

| ticker | verdict | spikes (held/rev) | bmr2 | adr |
|---|---|---|---|---|
| FCEL / SHAZ / CRML | clean | 0 / 0 | 1.4–1.7 | 10.8–15.1 |
| GLND | junk | 3 (1/2) | 2.1 | 21.2 |
| HTCO ×2 | junk | 4 (2/2) | 8.2–8.3 | 41–42 |

**Tier × fwd-5d** (full cohort, all alignment classes — the *universal* result, not a fades-only cut):

| tier | share | settled | avg | med | loss ≤−5% | loss ≤−10% | win ≥5% |
|---|---|---|---|---|---|---|---|
| tape_clean | 67% | 197 | +10.0% | +6.8% | **0** | **0** | 57% |
| tape_watch | 24% | 70 | +9.6% | +5.1% | 3 | 0 | 53% |
| tape_junk | 8% | 18 | +13.2% | +9.2% | 2 | **2** | 78% |

**The well-powered result: `tape_clean` — 197 settled names, ZERO losses even ≤−5%.** Tight tape → doesn't
blow up. The junk tier owns the only two ≤−10% crashes in the whole cohort, but it's a **barbell** (78% win —
it has chance winners like HTCO +72%), so this is a **character / tail filter, not an outcome predictor**
(CRML: clean and flat by design).

> **Correction on the record:** the original design report stated junk held "11" crashes; reproduction shows
> **2** (an 11 is arithmetically impossible against a +9.2% median). The cohort is crash-poor. This makes the
> "don't hard-gate yet" call *stronger* — you can't gate real money on a 2-event tail. The durable signal is
> the clean side (0 losses / 197 settled), not the crash count.

**#331 reframe:** junk-filtering does **not** kill the fades edge (avg survives ~+12%); it removes the (small)
crash tail. "fades **+ tape_clean**" is the interesting #331-v2 cell — a direction-check only at current N.

## 4. Rollout — staged, with gates

| Stage | What | Money? | Gate | ETA |
|---|---|---|---|---|
| **1. Shadow annotate** | record TQS fields on each alert/shadow row + a `TAPE: clean/watch/junk` line on the alert + an NTR sparkline; add an ex-junk column to the #331 evidence probe | **No** (display + shadow columns) | **AUTHORIZED 2026-07-21** — telemetry-only (must NOT block an order, alter sizing, or demote `ep_score`) | **~2026-07-31** |
| **2. Operator labelling pass** | eyeball the flagged `junk` list — per our own rule (SSoT #4) the agent must NOT self-classify a filter list | No | **Operator** (needs Stage 1's surfaced list) | event-gated on Stage 1 |
| **3. Suppression backtest** | replay which past HIGH alerts a `junk` gate WOULD have suppressed + their outcomes | No (analysis) | **Data-gated** — needs ≥30 settled junk rows (currently 18) + more crash events | data-gated, not calendar |
| **4. Hard-gate / demote decision** | whether/how TQS gates or de-prioritises live EP entries | **YES** | **THE LINE** — operator sign-off + Stage 3 backtest + CHANGE_PROCESS | not before 2+3 |

**Recommended posture (Fable + agreed):** annotate + de-prioritise in shadow first; **never** a hard filter
without Stage 3. Keep TQS OUT of `meta_rubric_compose` (those axes are boost-only by guardrail) — this is
junk-*down* detection hygiene, a separate layer that runs after the existing price/liquidity gates.

## 4a. Adopted engineering guardrails (Gemini review, 2026-07-21)

- **A. `unknown` ≠ blanket pass for IPOs.** A name with `<15` live bars scores `unknown` (never junk), but a
  raw IPO/SPAC is *inherently* unseasoned. Stage-1 rule: `unknown` must render as **"unseasoned"**, NOT
  "clean", and the existing base-age / IPO gates remain responsible for the trade decision — TQS never
  upgrades a too-young name.
- **B. No lookahead — verified.** `spike_held`'s 2-day give-back look is taken **within the pre-alert window
  only** (`trade_date < alert_date`); a spike on the last in-window bar falls back to close-position only. The
  score never reads the alert day or beyond. (Confirmed in `_tape_quality_step0.py`.)
- **C. Do NOT trade the junk barbell.** `tape_junk`'s 78% win rate is a fwd-5d *point* outcome — a tight
  ORB/MA stop gets shaken out by the intraday violence long before that 5-day number lands. The 78% is a
  reason the filter is *soft* (annotate, don't hard-block yet), never a reason to chase junk.

## 5. Caveats (all pins provisional)

- **Underpowered tail:** 2 crash events → term-level crash discrimination is not powered; thresholds are from
  the cohort distribution (spike_rev p95=2, bmr2 p95≈2.6), NOT crash-calibrated.
- **Single Bull-heavy window** (Mar–Jul 2026) — re-check as Choppy/Correcting rows accrue.
- **Junk survivorship:** junk names settle at a lower rate (18/39) — likely halt/delist — so junk *downside is
  understated*.
- **fwd-5d is a point outcome** — it can't see intra-window path whip (a +9% settle that traversed ±40% is
  untradeable with stops).
- Thresholds finalise only after the Stage-2 labelling pass + Stage-3 accrual.

## 6. Reproduce
`docker exec apollo-market python scripts/probes/_tape_quality_step0.py` — labelled-6 check + tier×outcome +
#331 stratification. Read-only. Reuses `_331_gap_alignment_step0.classify`; the axis it stratifies is
`docs/decisions/0033-gap-structure-alignment-axis.md`.
