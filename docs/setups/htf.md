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
| **Flagpole data-artifact** | reject a >50% single-day close jump with `vol < 2× window avg` | Gemini 6/27 (split / bad-tick backstop) | runup-window guard |
| **Flagpole volume** | ≥1 day in the 40d window at `vol ≥ 2× window avg` | spec "undeniable institutional demand"; Gemini 6/27 | `spike_days ≥ 1` |
| **Liquidity** | ADV > 500k, ADR > 4% | spec | universe pre-filter (`rs_engine`) — VERIFY covers it |
| **Tightness / vol dry-up** | volatility-relative range/vol contraction + RMV | ADR 0013 (signed) | UNCHANGED |
| **Breakout entry** | close > flag-high on ≥150% ADV (buy-stop-limit) | spec | `_BREAKOUT_VOL_RATIO=1.50` (Phase-3 shadow) |
| **Catalyst-backed** | — | spec | OUT OF SCOPE — separate catalyst axis (#189/#201), not flag geometry |

### Reasoned deviations from the literal spec (documented per the provenance rule)
- **Flagpole anchor:** the spec's `C≥1.9×C₄₀` is anchor-free (trailing 40d). The detector measures the
  runup at the **pivot** (the pole top) — `pivot_high / min(low, 40d ending at pivot)` — because the
  detector catches the FLAG (post-pole), so the pole magnitude is measured where the pole actually tops.
  This is the detector-correct adaptation, NOT claimed "equivalent" — to be VERIFIED against the literal
  formula on a handful of real names (the `/flags` eyeball); document as a confirmed deviation or correct it.
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
- **2026-06-27 — Sourced HTF rebuild (replaces the n=1 50/60).** Flagpole 50%/60d → 90%/40d; flag depth
  off-pivot-close-20%-(scaled-to-35%) → absolute-low ≤25% flat; ADDED the 10/20/50 Stage-2 trend filter,
  the flagpole data-artifact guard + pole-volume confirmation. #80 runup-scaling removed (reason above).
  Reversion-flag: REFINEMENT (an unsourced n=1 → the sourced literature; not a reversal of a signed call).
  Gate: spec-correctness (tests/`test_htf_criteria.py`) + `/flags` eyeball + operator sign-off (sourcing).
  NO N≥10 P&L backtest (the alert-only detector touches no money; the money breakout-entry validates
  separately shadow→paper→live). Refs #356, `docs/roadmap/family_a_setups_split_2026-06-22.md`.

> Supersedes the criteria section of `docs/setups/flag_continuation.md` (the generic-flag definition).
