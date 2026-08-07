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
| **Stage-2 (long-term)** | `close ≥ 200d MA` AND `pivot_high ≥ 75% of the 52w high` (near highs, not a crash-recovery) | spec "Stage-2 uptrend (Minervini)" | `_SMA200_WINDOW`, `_STAGE2_NEAR_HIGH_MIN`; needs `_HISTORY_DAYS=380` |
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

## M&A suppression on the actionable stages (`flag_scan`, not `compute_flag_metrics`)

Backfilled into this SSoT 2026-07-24 (#502) — these layers had lived only in `flag_detector.py`. They
run AFTER scoring, on `COILED`/`TRIGGERED` rows only (WATCH/TIGHTENING are digest-suppressed already, so
gating them would multiply the API cost for no visible benefit). A hit rewrites the persisted row to
`stage='unqualified'` with `reason='mna_filter:<source>'` — kept, not deleted, so the filter's hit rate
stays auditable.

**Why the setup needs this at all:** once price is pinned at an announced deal value it stops moving.
Range collapses to bid–ask noise and volume bleeds out — which is *mechanically identical to a coil*.
The tightness that scores a deal-pinned name COILED **is** the pin. Geometry alone cannot tell them apart.

| Layer | Test | Catches |
|---|---|---|
| 1 — news | `ma_filter.is_likely_ma(check_polygon=True, polygon_lookback_days=21)` | deals Polygon has a headline for |
| 2 — mature pin | median (H−L)/C over last **10** sessions < **0.5%** AND ≥**5** sub-0.5% sessions | pins ≥ ~3-4 weeks old (~session 13+) |
| 3 — fresh pin (#502) | 5-session band ≤ **2.5%** AND ≥**5×** volume spike (max vol last 10 / mean vol sessions 11–40) | pins days old, through session 10 |
| 3b — sticky carry (#502 refinement, 2026-08-06) | today's band still ≤ **2.5%** AND layer 3's own conjunction fired as-of 1–**5** sessions ago (re-runs the shipped `_evaluate_fresh_pin` on the trailing window; no new persistent state) | bridges the measured session-11–12 hole below |

⚠ **Layers 2 and 3 were documented as "complementary by deal age" — that was FALSE, and is
corrected here (2026-08-06, #502).** Measured against production: layer 3's own-data conjunction
stops firing on session 11 (the announcement's volume event ages out of its 10-session window);
layer 2 doesn't reach a qualifying 10-session median until ~session 13. Sessions 11–12 are a real,
measured hole where a still-pinned deal reads as a plain coil and leaks onto the actionable board —
this is exactly what happened to ATAI on 2026-07-30/07-31 (see change log below). Layer 3b closes
that hole by carrying layer 3's own last-verified verdict forward, released the moment today's own
band stops looking pinned. All layers fail OPEN — a missing signature never suppresses.

## Change log
- **2026-08-06 — Layer 3b added: STICKY carry bridges the layer-2/layer-3 hand-off hole (#502
  refinement). OPERATOR-SIGNED.**
  **Trigger**: the 2026-07-24 layer-3 change log (below) documented layers 2 and 3 as "complementary
  by deal age." That claim was never verified against production and turned out to be false — a real
  setup (ATAI) leaked through a measured 2-3 session hole between the two layers.
  **Root cause**, session-by-session against the real ATAI cash-buyout (announced 2026-07-16,
  165.6M shares that day vs ~16.6M baseline; price welded $7.15-7.22 since):

  | session after announcement | Layer 3 (fresh) | Layer 2 (mature) median | outcome |
  |---|---|---|---|
  | 07-23 … 07-29 | FIRES (spike 18.3-18.7x) | 0.70-1.73% — no | suppressed correctly |
  | **07-30** | **STOPS** — the 07-16 spike falls out of the 10-session window on session 11 | 0.696% — no | **COILED, leaked** |
  | **07-31** | no | 0.627% — no | **COILED, leaked** |
  | 08-03 | no | 0.523% — no, misses by 0.023pp | (no candidate row) |
  | 08-04 onward | no | 0.453%, 6 sub-0.5 days — WOULD fire | masked by an unrelated ADR gate |

  Precisely: `_FRESH_PIN_VOL_EVENT_DAYS = 10` means the announcement's volume ages out of layer 3's
  own event window on session 11 — and worse, that same volume then falls INTO layer 3's baseline
  window (sessions 11-40), inflating the ADV denominator and dragging the spike ratio down further.
  Layer 2's 10-session median needs until ~session 13 to fall under 0.5%. Sessions 11-12 (calendar
  07-30/07-31) are a genuine hole, not a documentation gap — confirmed live: `mi_flag_candidates`
  shows `mna_filter:deal_pin_fresh` on ATAI 07-23→07-29, then bare **COILED** (no `mna_filter:*`
  reason, i.e. unsuppressed) on 07-30 and 07-31, then `adr_3.0pct_below_4pct` — a DIFFERENT,
  unrelated liquidity gate — from 08-04 onward. **Layer 2 is untested in the field here, not
  proven**: its 08-04 median (0.453%, 6 sub-0.5 days) would have qualified, but the row was already
  marked unqualified by the ADR gate before layer 2 ever got a chance to evaluate it — so this
  incident does not confirm layer 2 would have closed the hole on its own eventually; it confirms
  only that something else happened to mask the symptom from session 13 on.
  **The fix** (mechanism, not a threshold move — none of `_FRESH_PIN_BAND_MAX`,
  `_FRESH_PIN_VOL_SPIKE_MIN`, `_FRESH_PIN_VOL_EVENT_DAYS`, or layer 2's `_DEAL_PIN_RANGE_THRESHOLD`
  moved): `_evaluate_fresh_pin` now re-runs itself (the shipped function, not a parallel evaluator —
  the #416 lesson) on the trailing window for 1..`_FRESH_PIN_STICKY_SESSIONS` (=5) sessions back
  whenever today's own conjunction doesn't fire but today's band still reads ≤ `_FRESH_PIN_BAND_MAX`.
  A hit is carried forward and labelled `sticky_from_session=i`; recursion is guarded to exactly one
  level (a carried lookup never itself tries to carry). The release condition — today's own band
  widening past the max — is the design's whole safety property: no new persistent state exists, so
  there is nothing to leave stale when a deal breaks or price starts moving again. Audited under a
  distinct source string, `deal_pin_sticky`, kept separate from `deal_pin_fresh` so the carry's hit
  rate stays independently reviewable.
  **Evidence**: extended the 2026-07-24 replay's SAME 405-row/89-ticker corpus (2026-05-04 → 07-24,
  frozen — `scripts/probes/_502_bars.tsv`, unchanged) with a NEW extension pull covering 2026-07-25 →
  08-06 (`scripts/probes/_502_bars_ext_20260806.tsv`) — this is NOT the identical corpus the original
  evidence used; it is that corpus plus everything actionable since, confirmed via direct query that
  no COILED/TRIGGERED row for ANY ticker exists in 07-25→08-06 other than ATAI's two leak sessions
  (`mi_flag_candidates` grouped by scan_date/stage, 07-20→08-06). Run against the SHIPPED
  `_evaluate_fresh_pin` (`scripts/probes/_502_fresh_pin_replay.py`):
  - **ATAI 07-30 and 07-31 are now suppressed** — band 0.84% both days (still reads as welded),
    carried from 1 and 2 sessions back respectively. This is the regression the fix targets, closed.
  - **HUM is still preserved** — all 5 HUM rows in the base window remain `is_fresh_pin=False`; every
    HUM band (3.07-10.64%) sits above `_FRESH_PIN_BAND_MAX`, so the release condition exits before
    any carry is attempted. The designated canary is untouched.
  - **The original 11 rows are unchanged** — same 11 rows (ATAI ×2, CCRN ×2, KALV ×4, PAYO ×3), all
    still firing on their OWN data (`sticky_from_session=0`), byte-identical to pre-refinement
    behaviour; the sticky path never engages for rows whose own conjunction already fires.
  - **Net new production-behaviour change: exactly 2 rows** — ATAI 07-30 and 07-31, both hand-checked
    above. One additional row (AVNS, 2026-05-04) picked up a `sticky_from_session=5` fresh-pin flag
    it didn't have before, but AVNS was ALREADY suppressed by the mature rule (`is_pin=True`) both
    before and after this change, and the mature label always wins when both fire — so AVNS's
    production outcome and reason string (`deal_pin_signature`) are unaffected either way. Hand-
    checked, zero behavioural impact, noted for completeness rather than shipped as a "new"
    suppression.
  This is the narrow bridge it was meant to be, not a widened surface: 2 rows change outcome, both
  are the diagnosed leak, and the false-positive population (HUM, the 393 preserved rows) is intact.
  **Known approximation, measured not just asserted**: the carried lookup reuses the caller's already-
  fetched `_PIN_HISTORY_DAYS`-row window, so a carry at offset `i` sees a baseline `i` bars shorter
  than that session's own historical evaluation would have had — the as-of verdict approximates the
  historical day's own verdict rather than replaying it byte-for-byte. A shorter baseline can only
  ever RAISE the computed spike ratio, so in principle a carry could fire where the true historical
  day would not have. This replay measured that risk directly instead of leaving it theoretical: 0 of
  407 rows flipped in that direction (AVNS's fresh-flag changed under the shortened baseline but was
  independently mature-suppressed regardless, so it produced no behaviour change).
  **Anticipated effect**: closes the ATAI-class leak going forward — a fresh pin that ages past
  session 10 while still genuinely welded stays suppressed through session ~15 (5-session bridge with
  margin over the measured 2-3 session hole) instead of surfacing as an actionable COILED/TRIGGERED
  row on the digest.
  **Reversion-flag**: REFINEMENT of the 2026-07-24 layer-3 change directly below — same intent
  (suppress a still-pinned M&A target that geometry alone cannot distinguish from a coil), closing a
  hand-off gap that change's own evidence didn't test for. Not a reversal: every row layer 3 already
  caught keeps firing exactly as before (own-data, `sticky_from_session=0`); the carry only ever adds
  coverage in the specific band-still-holds-but-event-window-elapsed shape.
  **Status**: shipped, awaiting field validation — verify = ATAI (or any future fresh-pin case)
  absent as COILED/TRIGGERED from the rendered nightly HTF digest through the point its own mature-pin
  median would take over. Scope is flag-only (HTF is shadow, no order fires); unchanged from the
  2026-07-24 entry's scope carve-out.
  Tests: `tests/test_flag_fresh_deal_pin_502.py` (bridge, release, bound, fail-open, no-recursion,
  mutation-check — 7 new cases). Replay: `scripts/probes/_502_fresh_pin_replay.py --pull-ext` (base
  window `--pull` is now frozen and should NOT be re-run — see the script's own docstring for why).

- **2026-07-24 — Layer 3 added: FRESH deal-pin suppression (#502). OPERATOR-SIGNED.**
  **Trigger**: operator, 2026-07-24 — the nightly HTF digest surfaced `ATAI` as the single 🌀 COILED
  actionable setup; ATAI is a buyout. Root cause: a cash-deal pin is indistinguishable from a coil on
  geometry, and *both* existing layers structurally cannot reach a FRESH pin. Layer 1 found nothing —
  Polygon returned 2 ATAI articles in 21 days, neither carrying an M&A keyword (the #416 guards are NOT
  implicated; nothing ever matched, so nothing vetoed). Layer 2 needs a 10-session median under 0.5%,
  which a 6-session-old deal cannot reach — ATAI's median was 1.735% with 1 sub-0.5% day.
  **Evidence**: 405-row replay of every historical COILED/TRIGGERED row using the SHIPPED
  `_evaluate_fresh_pin` (not a lookalike sim — the #416 lesson), window 2026-05-04 → 07-24, 89 tickers.
  11 rows / 4 tickers suppressed (ATAI ×2, CCRN ×2, KALV ×4, PAYO ×3); **393 preserved**, including
  `HUM` — the nearest non-pin by band (3.07%) — which went on to **+25.7%** over the next 20 sessions.
  The two populations do not overlap: every fresh pin ≥ 12.6× spike, every non-pin ≤ 2.9×. Band ∈
  {2.0, 2.5, 3.0} crossed with spike ∈ {5×, 10×} all select the same 11 rows, so neither threshold is
  load-bearing. Prior measured behaviour: layer 2 had fired **5 times in its lifetime** and caught KALV
  ~29 days *after* KALV's first 4-session COILED leak; ATAI/CCRN/PAYO leaked and were never caught.
  ⚠ **Single-regime limitation** — that window is one regime. Per the #454 finding that the kill/scale
  envelope was silently bull-conditional, this calibration carries the same caveat and is due a re-cut
  at the quarterly band review.
  **Also tested and NOT shipped**: reusing the EP Claude-classifier `catalyst_quality='mna'` verdict.
  It is not in `mi_ep_alerts` (the filter suppresses before the alert row is written) and the audit-log
  store is 1-true/1-junk on N=2 — `ACLS` was graded `mna` while its own summary read "No recent news or
  catalysts found", then ran $164 → $191. The guards cannot discriminate (`matches_mna_keywords`
  returns `None` for ATAI too). Filed under #416; N=2 is below the bar to ship it *or* to close it.
  **Anticipated effect**: ~11 actionable rows suppressed per ~3 months (of 405). ATAI leaves the board.
  Layer 2's own hit rate is unchanged — layer 3 is purely additive; where both fire, the mature label
  wins (3 KALV rows). New audit source string `deal_pin_fresh` alongside `deal_pin_signature`.
  **Reversion-flag**: REFINEMENT of the 2026-05-11 deal-pin-signature change. Same intent — catch
  zero-news M&A targets by price signature; the prior statistic is correct for mature pins and simply
  has no reach on fresh ones. Not a reversal: nothing layer 2 catches is given up.
  **Status**: shipped, awaiting field validation — verify = ATAI absent as COILED from the rendered
  nightly HTF digest. Scope is flag-only (HTF is shadow, no order fires); extending the conjunction to
  EP/9M would change detection on money paths and was deliberately excluded.
  Full evidence: `docs/analysis/htf_deal_pin_fresh_2026-07-24.md`; replay:
  `scripts/probes/_502_fresh_pin_replay.py`.

- **2026-07-24 — FL-5 reconcile: doc synced to code (missing change-log entry added).** `_HISTORY_DAYS`
  is **380**, not 260 — the 6/27 entries below say "90→260" but the code moved a third time, same day,
  in a follow-up commit (`1f2f7a8`) that was never logged here: `get_recent_daily_history` filters by
  CALENDAR days, not row count, so `_HISTORY_DAYS=260` calendar only yielded ~178 TRADING rows (< 200) —
  `sma_200` silently came back `None` and the 200MA Stage-2 gate (added earlier that same day, see
  below) never actually fired; the near-high gate alone was carrying NCI's rejection. Bumped 260→380
  calendar (~261 trading rows via the ~0.685 trading/calendar-day ratio) so the 200MA check fires for
  real — reverified live: AGL 3.68× above / XMTR 1.59× / NCI 0.66× BELOW (now caught by BOTH the 200MA
  and near-high gates). Advisor-caught 6/27, same day as the Stage-2 gate ship below. No code change in
  this reconcile — doc-only correction + backfilled change-log entry.

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
  `pivot_high ≥ 75% of the 52w high` — and extended `_HISTORY_DAYS` 90→260 (a 200MA/52w-high needs ~250d;
  **superseded same-day, 260→380 — see the 2026-07-24 entry above, `_HISTORY_DAYS` is 380 in code**).
  Confirmed on the live eyeball: AGL (100% of 52w high, 4.32× 200MA) + XMTR (95%, 1.70×) KEPT; NCI (10%,
  0.81×) REJECTED. Test: `test_crash_recovery_rejected_stage2`.

> Supersedes the criteria section of `docs/setups/flag_continuation.md` (the generic-flag definition).
> See also `docs/decisions/0026-consolidation-family-unification.md` §D1 (card C4, 2026-07-19): the
> Family-A 3-way split — **HTF is the *setup*** (this file, unchanged); **Confirm is the *entry*** (the
> consolidation family's base-high breakout, `anticipation.py::confirm_signal_at`, SHADOW-only, documented
> in `flag_continuation.md`); Anticipation is the third (in-coil) entry. No criteria here changed.
