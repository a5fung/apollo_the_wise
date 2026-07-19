# HTF — High Tight Flag (Family-A Setup 2)

**Phase**: Shadow (telemetry-only — NO order fires from the detector; `/flags`→`/htf` board + #94
intraday break + EOD digest are observational). Promotion path: the breakout-entry shadow → paper → live.
**Origin (SOURCED)**: O'Neil (*How to Make Money in Stocks*), Minervini (*Trade Like a Stock Market
Wizard*), Qullamaggie — operator-sourced + shared, `docs/methodology/operator_shared_notes.md` (HTF block,
2026-06-22). **Provenance rule (ADR 0013 §2 / #358): every gate below cites that source; no unsourced number.**
**Code**: `agents/market_intelligence/flag_detector.py` — `compute_flag_metrics`. Daily 17:25 ET scan +
the #94 intraday break scan.

> **Why this exists (the n=1 story):** the prior criteria (`runup ≥ 50% / 60d`, `proximity ≤ 20%` off the
> pivot close, + the #80 runup-scaling) were built on **n=1** — a single-case pick (first commit
> 2026-05-01), never validated. That is the exact reason Family-A was split into the *sourced* setups: the
> generic runup→coil detection moved to **Anticipation** (the coil-finder), freeing this detector to become
> the *specific* HTF — the `90%` flagpole is the "high tight" trait that distinguishes a monster-runup flag
> from a generic coil. The swap REPLACES an unsourced n=1 number with the literature (operator-confirmed
> 2026-06-27: no N≥10 P&L backtest — the old 50/60 was the n=1; the gate is spec-correctness + a `/flags`
> eyeball + the sourced sign-off, on an alert-only/no-money detector).

## Detection criteria (sourced — `compute_flag_metrics`)

The 5-stage state machine (`unqualified → WATCH → TIGHTENING → COILED → TRIGGERED`/`INVALIDATED`), the
hysteresis, and the volatility-relative tightness gates (range/vol contraction, fresh-tightening, RMV) are
UNCHANGED (operator: "I like how it shows which stage a stock is at"). Only the runup + flag-depth + trend
criteria were swapped/added.

| Gate | Sourced value | Source | Code |
|---|---|---|---|
| **Flagpole magnitude** | `pivot_high / 40d_low ≥ 1.9×` (≥90% in ~8wk) | spec `C≥1.9×C₄₀` / `High₄₀≥1.9×Low₄₀` | `_RUNUP_MIN_RATIO=1.90`, `_RUNUP_LOOKBACK_DAYS=40` |
| **Flag depth** | `base_low ≥ 0.75×pivot_high` (≤25% pullback, on the ABSOLUTE low) | spec `Close≥0.75×High₄₀`, tightened to the low | `_FLAG_DEPTH_MIN=0.75` |
| **Trend** | `close ≥ sma_50` AND MAs stacked `10≥20≥50` (Stage-2 uptrend) | spec "above the 10/20/50 MAs" | `_SMA50_WINDOW` + the trend block |
| **Stage-2 (long-term)** | `close ≥ 200d MA` AND `pivot_high ≥ 75% of the 52w high` (near highs, not a crash-recovery) | spec "Stage-2 uptrend (Minervini)" | `_SMA200_WINDOW`, `_STAGE2_NEAR_HIGH_MIN`; needs `_HISTORY_DAYS=260` |
| **Flagpole data-artifact** | reject a >50% single-day close jump with `vol < 2× window avg` | Gemini 6/27 (split / bad-tick backstop) | runup-window guard |
| **Flagpole volume** | ≥1 day in the 40d window at `vol ≥ 2× window avg` | spec "undeniable institutional demand"; Gemini 6/27 | `spike_days ≥ 1` |
| **Liquidity** | ADV > 500k shares, ADR > 4% | spec | ✅ ENCODED 6/28 in `compute_flag_metrics` (per-ticker — so EVERY universe path is gated, not just the organic SQL one; VERIFY found the $5M dollar-vol floor didn't cover it). Tunable named constants: `_HTF_MIN_ADV_SHARES=500_000` (firm liquidity floor) + `_HTF_MIN_ADR_PCT=0.04` (STARTING value — 4% is NOT canonical, sources 3-6%; DATA-GATED tune `htf_adr_threshold_tune` once the breakout-shadow accrues N≥10 settled winners). Impact: dropped 1 of 2 current candidates (under-liquid). |
| **Tightness / vol dry-up** | volatility-relative range/vol contraction + RMV | ADR 0013 (signed) | UNCHANGED |
| **Breakout entry** | close > flag-high on ≥150% ADV (buy-stop-limit) | spec | `_BREAKOUT_VOL_RATIO=1.50` (Phase-3 shadow) |
| **Catalyst-backed** | — | spec | OUT OF SCOPE — separate catalyst axis (#189/#201), not flag geometry |

### Reasoned deviations from the literal spec (documented per the provenance rule)
- **Flagpole anchor (✅ VERIFIED 6/28 — the detector form IS the primary definition, not a deviation):**
  the detector measures the runup at the **pivot** (the pole top) — `pivot_high / min(low, 40d ending at
  pivot) ≥ 1.9`. This IS the primary O'Neil/Minervini definition: the pole is the run-up measured AT its
  peak. Verify 6/28 (20 prod names) confirmed a today-anchored trailing-40d form (`high(40d)/low(40d)` from
  scan_date) DIVERGES — it qualifies ~3/10 fewer post-pole bases, because today's window has walked off the
  early-runup low and measures from INSIDE the flag, not the pole. Operator-confirmed 6/28: HTF is a
  well-defined setup — use the PRIMARY definition, do NOT invent our own; the today-anchored form was a
  non-primary interpretation, REJECTED. (memory `feedback_established_setup_use_primary_definition`)
- **Flag depth on the absolute low (not the close):** the spec writes `Close≥0.75×High₄₀`; we tighten to
  `min(low)≥0.75×High₄₀`. O'Neil/Minervini reject a deep intraday shakeout that rallies to a tight close
  (the spring uncoiled). Operator-endorsed (Gemini 6/27); confirm via the eyeball.
- **`#80` runup-scaling removed (CHANGE_PROCESS #3 — why it was WRONG, not just superseded):** #80 relaxed
  the proximity band to ~35% for high-runup names. That is correct for a GENERIC flag (deeper bases are
  still valid setups) but WRONG for HTF, where ≤25% tightness is DEFINITIONAL — the "tight" in
  high-tight-flag. The generic-flag recall #80 served is now Anticipation's job; HTF is the tight subset.
- **The 10-day is not a close-above floor:** a flag routinely tests the 10/20 MA on a support pullback
  (it's the stop/trail reference, not a veto). The trend gate vetoes on the 50-day + the MA stack instead.

## Management (Phase 4, shadow)
Scale 33–50% into strength 3–5 days post-breakout → move the remainder to breakeven → trail the runner on
the 10/20-day **EMA** (exit only on a daily close below). Stop = the tightest-day low / 10–20 EMA, hard
max-loss 5–8%. Sizing risk 0.5–1% of equity. Target = the flagpole height added to the breakout.

## Change log
- **2026-07-19 — Doc cross-ref only: ADR 0026 D1 / card C4 (flag_continuation retirement).**
  **Trigger**: `#354`/ADR 0026 card C4 rewrote `flag_continuation.md` to document its retirement as a
  standalone strategy and absorption as the Confirm(b) entry; added a pointer here for discoverability.
  **Evidence**: N/A — no detection-criterion, gate, or code change in this file; pure cross-reference.
  **Anticipated effect**: none in production. **Reversion-flag**: NEW (doc-only addition, nothing
  reversed). **Status**: shipped 2026-07-19.

- **2026-07-18 — ADV liquidity floor: MEAN → MEDIAN (bugfix, #402(2)).**
  **Trigger**: #402 /simplify code review found `compute_flag_metrics`'s liquidity gate computed ADV as
  `sum(volume)/len` (mean) while every other ADV computation in this codebase — `db.get_adv_from_daily_closes`
  (the cited SSoT, `PERCENTILE_CONT(0.5)`), `rs_engine`, `ep_detector`, and this SAME file's own #94
  intraday-break-scan query (which already comments "matching db.get_adv_from_daily_closes SSoT — median
  is spike-immune") — uses median. **Evidence**: internal consistency, not a new threshold — the
  `_HTF_MIN_ADV_SHARES=500_000` floor value is unchanged; only the aggregation method computing the
  statistic compared against it was wrong. **Anticipated effect**: stricter for spike-influenced tickers —
  a ticker whose trailing-20d volume includes one large block-trade/climax day could previously clear the
  floor on an inflated mean; the median now reflects steady-state liquidity, so those borderline names may
  newly reject (`adv_Xk_below_500k_shares`). No effect on tickers without a volume spike in the window.
  **Reversion-flag**: NEW (bugfix — first correction of this specific bug, not a reversal of a signed
  threshold call). **Status**: shipped, awaiting field validation. No N≥10 P&L backtest — this detector is
  shadow/telemetry-only (no money); see the 6/27 entry below for the same carve-out. Test:
  `test_adv_floor_uses_median_not_mean_spike_robust` (`tests/test_htf_criteria.py`).

- **2026-06-27 — Sourced HTF rebuild (replaces the n=1 50/60).** Flagpole 50%/60d → 90%/40d; flag depth
  off-pivot-close-20%-(scaled-to-35%) → absolute-low ≤25% flat; ADDED the 10/20/50 Stage-2 trend filter,
  the flagpole data-artifact guard + pole-volume confirmation. #80 runup-scaling removed (reason above).
  Reversion-flag: REFINEMENT (an unsourced n=1 → the sourced literature; not a reversal of a signed call).
  Gate: spec-correctness (tests/`test_htf_criteria.py`) + `/flags` eyeball + operator sign-off (sourcing).
  NO N≥10 P&L backtest (the alert-only detector touches no money; the money breakout-entry validates
  separately shadow→paper→live). Refs #356, `docs/roadmap/family_a_setups_split_2026-06-22.md`.

- **2026-06-27 (eyeball catch) — Stage-2 long-term gate added (operator: "NCI is not valid").** The
  10/20/50 alone PASSES a sharp crash-recovery (the short MAs catch up fast): NCI spiked $110 → crashed
  $4 → bounced to $11 (−90% from its high, BELOW the 200d) and read as a "221% flagpole" that was a
  dead-cat bounce. Added the spec's "Stage-2 uptrend" long-term gate — `close ≥ 200d MA` AND
  `pivot_high ≥ 75% of the 52w high` — and extended `_HISTORY_DAYS` 90→260 (a 200MA/52w-high needs ~250d).
  Confirmed on the live eyeball: AGL (100% of 52w high, 4.32× 200MA) + XMTR (95%, 1.70×) KEPT; NCI (10%,
  0.81×) REJECTED. Test: `test_crash_recovery_rejected_stage2`.

> Supersedes the criteria section of `docs/setups/flag_continuation.md` (the generic-flag definition).
> See also `docs/decisions/0026-consolidation-family-unification.md` §D1 (card C4, 2026-07-19): the
> Family-A 3-way split — **HTF is the *setup*** (this file, unchanged); **Confirm is the *entry*** (the
> consolidation family's base-high breakout, `anticipation.py::confirm_signal_at`, SHADOW-only, documented
> in `flag_continuation.md`); Anticipation is the third (in-coil) entry. No criteria here changed.
