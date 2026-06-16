# Methodology primitives catalog — SEARCH HERE BEFORE BUILDING ONE

**Why this exists:** on 2026-06-16 the #270 build nearly reinvented "tightness" from scratch even
though **RMV** (a built, validated contraction metric) already existed — it was only recovered from
operator memory. Same class as the RMV miss: a built capability goes unfound and gets re-derived.
**Before you implement a methodology primitive** (a tightness / volatility / volume / momentum /
contraction / catalyst / liquidity measure, or a setup detector), **grep this file + the codebase
for an existing one and reuse it.** This is the design-time analog of `/simplify`'s reuse check.
Reuse > reinvention; if you extend a primitive, update its row here in the same commit.

**Status legend:** `telemetry` = computed + persisted, NOT gating yet (shadow) · `load-bearing` =
gates real decisions · `evaluated` = a data-gated review is open on it (`data_gated_reviews.yaml`).

> This is a LIVING registry, seeded 2026-06-16 — not exhaustive. Add a row whenever you build or
> discover a primitive. If a row's file:function is stale, fix it (memories/docs drift; code is truth).

## Tightness / contraction (the cluster that caused the RMV miss — check ALL of these first)
| Primitive | What it measures | Where | Persisted | Status |
|---|---|---|---|---|
| **RMV** (Relative Measured Volatility) | DeepVue/TraderLion 0–100 contraction index (smoothed ATR-range min-max); ~0 tight coil, ~100 expansion | `flag_detector.py:179 _compute_rmv` | `rmv_5d`,`rmv_15d` on `mi_flag_candidates` (+ `mi_delayed_ep_lifecycle` telemetry) | telemetry · **evaluated #54** `rmv_phase2_evaluation`; #270 STEP 0 (`docs/analysis/delayed_ep_rmv_step0_270.md`) |
| **fresh_tightening** | 2-bar range/vol contraction vs the early base (the COILED-stage gate) | `flag_detector.py:238 _compute_fresh_tightening` | `range_contraction_ratio`,`vol_contraction_ratio`,`fresh_2bar_tr_pct` on `mi_flag_candidates`; `fresh_tightening`/`fresh_2bar_tr_pct`/`atr14_pct` on `mi_anticipation_lifecycle` (#270 recorder, reused 6/16 via `anticipation.compute_fresh_tightening`) | load-bearing (flag) · telemetry (#270) |
| **ATR-14 %** | mean true range over 14d, the tightness reference point | `flag_detector.py:166 _atr_14` (+ `_wilder_tr:149`) | `atr14_pct` on `mi_flag_candidates` | load-bearing |
| **base_run** | consecutive contained "base days" (maturity proxy for a developed coil) | `anticipation.py base_run` (ported from `_270_anticipation_replay.py:99`) | `base_run` on `mi_anticipation_lifecycle` | telemetry (#270) |
| **pullback_shape** | which pivot a tightening pullback pulled into (gap-low / MA / low-vol-rest); daily-bar EOD analog of the entry-technique annotator | `anticipation.py detect_pullback_shape` (#270, 6/16) | `pullback_shape`/`pullback_shapes`/`armed_shape` on `mi_anticipation_lifecycle` | telemetry (the Stage-B generalized-gate calibration set) |
| **tight cluster** | residual-correlation clustering of co-moving tight names (Lane-1 theme) | `correlation_engine.py:169 _compute_tight_clusters_sync`, `:31 _compute_residual_correlations` | `mi_correlation_clusters`/`mi_themes` | load-bearing |
| **entry-technique annotations** | flags which of the 5 tight-range entry mechanics are valid (breakout/support/MA-pullback/low-vol/U&R) | `flag_detector.py:2546 compute_entry_technique_annotations` (snapshot + flag-candidate bound — daily-bar analog = `anticipation.detect_pullback_shape`) | on flag candidate | telemetry |

> Pradeep `|close %change| ≤ 0.4%` tight-close is a methodology *input* (operator 6/16), recorded as
> `tight_close_pct` (#270); calibrated ~1.4% for tiny-caps, not 0.4% (see #270 STEP 0 doc).

## Volatility / volume / liquidity
| Primitive | What it measures | Where | Status |
|---|---|---|---|
| **volatility_ratio** | short/long realized-vol ratio (10/50) | `rs_engine.py:112 _volatility_ratio` | load-bearing (RS) |
| **adv_20 / dollar-vol floor** | median 20d volume (spike-robust); $-vol liquidity floor | `db.py:6090 get_adv_from_daily_closes`; `rs_engine.py MIN_DOLLAR_VOL` (#286) | load-bearing |
| **RVOL / open-intensity projection** | relative volume vs ADV, projected after 9:45 | `ep_detector.py` (MAGNA53), `ninem_detector.py` | load-bearing |
| **9M anomaly** | effective vol ≥ 3× ADV, $50M turnover, directional-conviction gates | `ninem_detector.py` | load-bearing (`mi_9m_ep_alerts`) |

## Momentum / RS / regime
| Primitive | What it measures | Where | Status |
|---|---|---|---|
| **RS composite** | 40%×1M + 30%×3M + 30%×6M percentile rank over ~9700 names | `rs_engine.py:109 compute_rs_scores` (+ `_compute_sma:103`) | load-bearing (`mi_stock_scores`) |
| **crypto RS** | BTC-ratio relative strength | `crypto/rs_engine.py:109 compute_rs_scores` | load-bearing |
| **regime / state changes** | market regime + state-transition alerts | `state_alerts.py:49 detect_state_changes`, regime engine | load-bearing |
| **parabolic metrics** | days-up streak, velocity delta, base low (parabolic-short setup) | `parabolic_detector.py:198 compute_parabolic_metrics` (+ `_sma:127`,`_compute_base_low:135`,`_compute_velocity_delta:166`) | load-bearing |

## Setups / detectors (named tactics)
| Detector | Setup | Where | Status |
|---|---|---|---|
| **MAGNA53 EP** | episodic pivot score + Claude/Perplexity validation | `ep_detector.py:620 _score_ep` | load-bearing |
| **9M EP (Pradeep)** | virgin 9M-volume universe; sugar-baby Day-2 ORB | `ninem_detector.py` | load-bearing |
| **Continuation flag** | post-runup VCP/Qullamaggie tightening (5 stages) | `flag_detector.py:377 compute_flag_metrics` | load-bearing + intraday flag-break (#94) |
| **Fishhook** | reclaim-after-undercut fill mechanic | `fishhook_detector.py` | built (shadow) |
| **Wick-fill** | gap-wick fill tracker | `wick_tracker.py` | shadow · **#283** promotion eval |
| **U&R (undercut & rally)** | undercut prior low → reclaim (Morales/OWL) | future detector **#98** (greenlit, may be unbuilt — verify before citing) | planned |
| **#270 anticipation** | gap → tightening pullback (arm; undercut = 1 shape) → reclaim(ready) → coil/entry → harvest | `anticipation.py` (Step 3; generalized recorder 6/16) | shadow |

## Catalyst / grading
| Primitive | What it measures | Where | Status |
|---|---|---|---|
| **catalyst rubric / scaling** | multi-axis catalyst composite (theme/policy/shortage/sales/product/mgmt/M&A) | `catalyst_rubric.py:293 composite_with_scaling` | load-bearing (rubric v3) |
| **EP holistic judge** | bidirectional promote/demote grade vs the floor | `grade_holistic` (ADR 0011) | shadow→load-bearing toggle |
| **materiality** | company-relative catalyst significance (deal $ vs revenue/mcap) | #189 (materiality stage) | building |
| **news-source quality drift** | source-mix drift detector | `news_source_quality.py:156 detect_drift` | load-bearing (#71/#72) |

## Audit / observability primitives
| Primitive | What it measures | Where | Status |
|---|---|---|---|
| **band classification + drift guard** | L1/L2/L3 anomaly bands; slow-drift L2→L3 downgrade | `system_audit.py:1050 _band_for`, `:1066 _is_slow_drift`, `_classify_band`, `:1081 _directional_ratio` | load-bearing |
