# Weekly-review reviews teed up — 2026-07-19 (Sunday digest follow-up)

Two data-gated reviews from the 7/19 weekly digest, pulled to **decision-ready**. Both are
detection-criterion / strategy calls → **operator sign-off + CHANGE_PROCESS + (for a ship) N≥10
backtest** before any flip (THE LINE). Evidence is entry-aware (closed `mi_live_trades`, not
close-to-close drift — per the 2026-05-18 methodology correction).

## 1. `rel_volume_large_cap_floor_evidence` — READY, matrix says SHIP (operator ruling)

Entry-aware, closed `magna53` trades, joined to `mi_ep_alerts` (HIGH) + `mi_stock_scores` (ADV):

| cohort | N closed | WR | avg P&L | total |
|---|---|---|---|---|
| **rvol<0.5 · largecap ADV≥$50M** | **20** | **15%** (3/20) | −$213 | −$4,263 |
| rvol≥0.5 · largecap (control) | 8 | 25% (2/8) | −$56 | −$447 |
| rvol<0.5 · smallcap-other | 6 | 33% (2/6) | −$293 | −$1,758 |
| rvol≥0.5 · smallcap-other | 6 | 0% (0/6) | −$1,341 | −$8,046 |

**Large-cap floor: N=20 (cleared the N≥10 bar; was 7 on 5/18), 15% WR < 30% → decision matrix = SHIP**
`rel_volume ≥ 0.5x AND ADV ≥ $50M` for HIGH alerts. rvol<0.5 (15%) underperforms the rvol≥0.5 control
(25%) — directionally confirmed. Caveat: whole book is negative in this window, so the filter shrinks a
*losing* cohort rather than turning it positive; net effect = avoid −$4,263 of realized losses on 20 trades.
Ship path: `LARGE_CAP_RELVOL_FLOOR_ENABLED` (or shadow-first), SSoT `magna53_ep.md` change-log, N≥10
backtest. **Operator decision.**

**⚠ Separate finding (not this filter's scope):** the *worst* cluster is **rvol≥0.5 smallcap-other, 0/6,
−$8,046** — the rel_volume floor would NOT catch these. A distinct problem worth its own look.

## 2. `rel_volume_small_cap_biotech_floor_evidence` — NOT READY (DEFER)

Closed biotech/pharma rvol<0.5 cohort = **N=1** (RLAY-class). Far below the N≥10 discipline bar. The
alert-count predicate may read ≥10, but the entry-aware **closed-trade** evidence is a single trade →
no decision. **Defer**, re-run when the closed cohort reaches ~10.

## 3. `gap_atr_3_5x_band_negative_ev` — PREMISE WEAKENED (lean CLOSE / fold into #306)

`_b53_atr_normalized_gap_backward_check` re-run on the current cohort:

| band | N | avg 5d | median | WR ≥+5% | ≥+10% |
|---|---|---|---|---|---|
| <1.5x | 24 | +2.24% | +0.8% | 43% | 35% |
| 2-3x | 34 | +2.32% | +2.1% | 41% | 28% |
| **3-5x** | **28** | **+0.59%** | **−1.3%** | 29% | 18% |
| 5x+ | 9 | −0.46% | −0.2% | 22% | 22% |

The 5/25 premise ("3-5x is the ONLY band with **negative** avg return, −0.75%") **no longer holds** — 3-5x
is now **+0.59%** (positive). It's still the softest band (lowest mean among the positive bands, and the only
one with a **negative median −1.3%** → left-skew: losers bigger than winners, worst WR 29%/18%). So the
original "negative-EV outlier" was largely a 60d-window artifact (decision branch **b**). The residual signal
= the left-skew/give-back pattern, which is **already the subject of #306** (winner-harvest / giveback exit
tune). **Rec:** close this review as window-artifact + note the 3-5x left-skew as a data point for #306's
partial-take axis — don't open a separate ATR-band gate. **Operator ruling.**

---
Origin: 7/19 weekly digest "Reviews ready" list. Reviews live in `data_gated_reviews.yaml`
(`rel_volume_large_cap_floor_evidence`, `rel_volume_small_cap_biotech_floor_evidence`,
`gap_atr_3_5x_band_negative_ev`). Nothing applied — all await operator ruling.
