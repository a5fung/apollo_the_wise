# #481 — MAX_EXTENSION_PCT provenance verification (registry finding #358)

**Date**: 2026-07-18 · **Scope**: verify-only (THE LINE — no detection value or code changed).
**Question**: `ep_detector.MAX_EXTENSION_PCT=50.0` ("up 50%+ in last 5 trading days") is uncited in
`scripts/gate_provenance_registry.py`, and the SSoT `docs/setups/magna53_ep.md` documents a
DIFFERENT extension rule (`prev_close ≤ 1.50× SMA-10`). Which is true: (a) same guard described
inconsistently → SSoT contradicts code (real drift), (b) two complementary guards → SSoT
incomplete, or (c) one is dead code?

---

## VERDICT: (a) — REAL DRIFT. The SSoT contradicts the code.

There is exactly **one** live hard extension gate, and it is the code's 50%/5-day rule. The SSoT's
`prev_close ≤ 1.50× SMA-10` rule **has never existed in the codebase** — git shows the SSoT was
born with the wrong formula at its creation (2026-05-07) while the code already enforced the
50%/5-day rule, and no commit has ever contained an SMA-10 extension check in the EP path. This is
documentation-side drift from birth (a mis-transcription at SSoT creation), not silent code
divergence — but the operational risk is the same: anyone reading the SSoT as authoritative (its
stated purpose) believes a gate exists that does not.

Per the task's (a) branch: **ESCALATED to operator** (§4). No code change proposed.

---

## 1. Every extension guard in the LIVE MAGNA53 path (exhaustive)

### G1 — Hard filter: `MAX_EXTENSION_PCT = 50.0` (the only hard extension gate)

- **Constant**: `agents/market_intelligence/ep_detector.py:99` —
  `MAX_EXTENSION_PCT = 50.0   # Skip if already up 50%+ in last 5 trading days before the gap`
- **Baseline fetch**: `ep_detector.py:1629-1644` — batch `MIN(close)` from `mi_daily_closes` over
  `[today−10 calendar days, today)` (~5 trading days + buffer). Deliberately MIN, not a single
  5-days-ago point — catches a stock that surged 3 days ago and is re-extending (matches the
  CLAUDE.md "EP Detection" note verbatim).
- **Gate site**: `ep_detector.py:1858-1866` —
  `extension_pct = (prev_close − min_close_5d) / min_close_5d × 100`; if `≥ 50.0` → **hard
  reject** (`continue` before scoring; `_log_filtered(c, "already up N% in prior 5 days
  (extended)")`). Applied pre-scoring, so it gates HIGH and MODERATE alike — nothing this filter
  skips can ever reach a HIGH.
- **Telemetry alias**: this skip-reason is the `extension_gate` bucket
  (`missed_outcomes.py:418` — `skip_reason ILIKE '%extended%'`; also
  `scripts/ep_selectivity_breakdowns.py:245`, `scripts/ep_latency_audit.py:83`). ADR 0003 §3's
  funnel table (49 skips, 24.5%) measures THIS gate's volume but does not sign its formula.

### G2 — Score penalty: `prior_momentum` (extension-flavored, different lookback — a downgrade, not a gate)

- **Site**: `ep_detector.py:1158-1167` inside `_score_ep` — `prior_3m_change ≥ 50` → **−25**;
  `≥ 30` → **−15**; else 0. 3-MONTH lookback, score deduction only (can demote a would-be HIGH
  below threshold but never hard-rejects).
- **Source**: code comment cites Qullamaggie — "best if stock has not rallied past 3-6 months".
  This is the only sourced extension-adjacent element in the whole path.

### Checked and EXCLUDED (not extension guards; listed so the enumeration is exhaustive)

| Candidate | Location | Why excluded |
|---|---|---|
| `orb_range > 1.5 × ATR` | `backtester/filters.py:203` (`check_filters`, called at `ep_detector.py:1870`) | ORB stop-width gate (`SETUP_STOP_TOO_WIDE`) — the only 1.5× in `check_filters`; unrelated to price extension. No SMA/extension logic anywhere in `check_filters`. |
| `prev_close <= m.sma_10 * 1.20` | `db.py:3392, 3664` | `get_anticipation_universe` — ADR 0013 Family-A consolidation universe, not MAGNA53. |
| `orb_extension_shadow.py` | `broker/` | ORB **time-window** extension shadow telemetry — different sense of "extension". |
| SMA10/20 trail | `broker/exit_logic.py` | Exit-side trailing stop, not an entry gate. |

**No `prev_close ≤ 1.50× SMA-10` check exists in `ep_detector.py`, `backtester/filters.py`, or
anywhere in the live EP entry path.** (`grep sma_10|sma10|SMA-10` across
`agents/market_intelligence/` — every hit is anticipation, 9M, wick, pivot, parabolic (SMA-50), or
exit-side.)

## 2. What the SSoT claims (`docs/setups/magna53_ep.md`)

- **Line 19** (Universe/eligibility): "**Extension**: prev_close ≤ 1.50× SMA-10 (stocks already
  extended pre-gap don't qualify — chase risk)"
- **Line 30** (Filters): "**Extension cap**: prev_close > 1.50× SMA-10 → skip"
- **Line 53** (Score computation): "Multi-factor: gap_pct + pm_rvol + catalyst_quality multiplier
  + regime + RS + extension" — secondary inaccuracy: `_score_ep` has **no "extension"
  component** (breakdown keys: gap, rel_volume, catalyst, float, analyst, neglect,
  vol_conviction, prior_momentum, theme_bonus, conviction_floor). The nearest is G2's
  `prior_momentum` (3-month), which line 53 does not name.
- The SSoT change log contains **no entry** about the extension rule — the SMA-10 wording is
  untouched since doc creation.

Note the two formulas are cousins but NOT equivalent: both cap "≤ ~50% above a recent baseline,"
but the baselines differ (10-day **average** vs 5-day **minimum** close). A stock up 40% steadily
over 10 sessions can pass one and fail the other. A reader implementing from the SSoT would build
a materially different gate.

## 3. Git provenance (the decisive evidence)

- `docs/setups/magna53_ep.md` created in `59e4601` (2026-05-07, "Setup SSoT: write-it-down
  discipline") **already containing** the SMA-10 wording. `git log -S "SMA-10" --
  docs/setups/magna53_ep.md` → only `59e4601` (never edited since).
- At that same commit, `git show 59e4601:agents/market_intelligence/ep_detector.py` **already
  contains** `MAX_EXTENSION_PCT = 50.0` + the 5-day-MIN-close formula (lines 78, 615-630,
  799-803 of that revision) — identical semantics to today.
- `MAX_EXTENSION_PCT` traces to the market-agent POC commit `cb28911` (through `930c766`,
  `28e89d2`). `git log --all -S "sma_10 * 1.5" -- agents/market_intelligence/` → **no commit,
  ever**.
- **Conclusion**: the code rule predates the SSoT and never changed; the SSoT mis-transcribed the
  guard at creation. The registry note's hypothesis ("may have silently diverged from the
  documented SSoT rule") is REFUTED — the code never diverged; the SSoT was never right.
- `docs/methodology/operator_shared_notes.md`: **no** EP-extension citation in any form (the
  50%-adjacent notes there are the flag_detector 50%/60d runup and HTF spec — different
  constants). Neither the 50%/5-day form NOR the 1.50×SMA-10 form ties to any methodology thread,
  ADR, or operator note.

## 4. ESCALATION — operator decision required (THE LINE: not pre-decided here)

**What the code enforces (live, since inception):** hard-skip any candidate whose `prev_close` is
≥ 50% above the MIN close of its last ~5 trading days (G1), plus a −25/−15 score penalty at
3-month +50%/+30% (G2, Qullamaggie-sourced).

**What the SSoT claims:** hard-skip when `prev_close > 1.50× SMA-10` — a rule that has never
existed in code.

**The question for the operator:** *Which extension rule is intended?*
- **If the live 50%/5-day rule is the intent** (it is the rule every backtest, the ADR 0003
  funnel, and all live history have been running): the fix is documentation + provenance only —
  correct `magna53_ep.md` lines 19/30 to the 50%/5-day-MIN formula (and line 53's score-factor
  list to name `prior_momentum` instead of "extension"), log it in the SSoT change log as a
  transcription correction (not a criterion change — the live criterion is unchanged), and then
  cite the corrected SSoT text in `gate_provenance_registry.py` (its convention accepts
  `docs/setups/*.md`; the sign-off on the correction is what makes the citation non-circular).
- **If the 1.50×SMA-10 rule is the intent**: that is a detection-criterion CHANGE (the live gate
  would be replaced) → full CHANGE_PROCESS: SSoT read, N≥10 backtest of both forms, operator
  sign-off. Not this card.

Until ruled, `ep_detector.MAX_EXTENSION_PCT` **stays uncited** in
`gate_provenance_baseline.json` — correct per the registry's own discipline (never invent a
citation to shrink the count).

---

## 5. Dispositions — the other two registry findings

### 5a. `db.get_anticipation_universe:dvol_min = $20M` — SOURCED (as an explicit probe); sign-off ask stands

ADR 0013 §2.3 (`docs/decisions/0013-consolidation-plays-post-runup.md:127-128`) names the value
itself: "**Liquidity floor** ≈ ≥$20M/day dollar-volume (probe value). Source: sanity floor, not a
selection edge — sign off the exact number." The 6/16 funnel (line 124: 1478 → 751 at ≥$20M/day)
ran on this number. So the constant is NOT unsourced — it traces to the signed ADR, which itself
records it as a probe pending exact-number sign-off. **Citation edit to apply**
(`scripts/gate_provenance_registry.py`, the `dvol_min` entry):

```python
"citation": {
    "file": "docs/decisions/0013-consolidation-plays-post-runup.md",
    "text": "≥$20M/day dollar-volume (probe value)",
},
"note": "ADR 0013 §2.3 liquidity floor — sourced as an EXPLICIT PROBE (the ADR's own text: "
        "'sanity floor, not a selection edge — sign off the exact number'). The exact-number "
        "sign-off is still outstanding (operator one-liner: sign $20M as-is or name a "
        "replacement); the 6/16 funnel (1478→751) ran on this value.",
```

(The cited substring appears verbatim at ADR line 127; passes `check_gate_provenance._normalize`.)
Plus route the one-line ask to the operator digest: "**dvol_min: sign $20M as-is, or name a
different number** (ADR 0013 §2.3's own deferred ask)."

### 5b. `flag_detector._HTF_MIN_ADR_PCT = 0.04` — SOURCED verbatim; cite and CLOSE

`docs/methodology/operator_shared_notes.md:97` — the 2026-06-22 operator-shared HTF blueprint
(the registry's own named source of truth, shared verbatim to GROUND setup #356): "**LIQUIDITY /
VOL:** ADV > 500,000 shares; ADR > 4%." The sibling constant `_HTF_MIN_ADV_SHARES=500_000`
**already cites this exact sentence** (registry lines 222-232, text "ADV > 500,000 shares") — the
ADR-floor half of the same sentence being left uncited was an oversight. The code comment's "4% is
NOT canonical (sources run 3-6%)" is a broader-literature caveat, not an absence of source; the
operator-shared spec pins 4%, and `docs/setups/htf.md` (line 35) + `data_gated_reviews.yaml`
(`htf_adr_threshold_tune`) already carry the data-gated re-tune. **Citation edit to apply**
(`_HTF_MIN_ADR_PCT` entry):

```python
"citation": {
    "file": "docs/methodology/operator_shared_notes.md",
    "text": "ADR > 4%",
},
"note": "HTF ADR floor — sourced verbatim from the 2026-06-22 operator-shared HTF blueprint "
        "(same sentence as _HTF_MIN_ADV_SHARES's citation). The code comment's 'sources run "
        "3-6%' stands as literature context; the data-gated tune (htf_adr_threshold_tune, "
        "data_gated_reviews.yaml) remains the calibration path.",
```

This CLOSES the finding — no escalation needed.

### Mechanics after applying 5a + 5b

Re-run `python scripts/check_gate_provenance.py --update-baseline` so
`scripts/gate_provenance_baseline.json` shrinks `3 → 1` (only `ep_detector.MAX_EXTENSION_PCT`
remains, pending the §4 ruling). The baseline shrinking via real citations is the checker's own
sanctioned path.

---

## Summary table

| Registry finding | Disposition | Action |
|---|---|---|
| `ep_detector.MAX_EXTENSION_PCT=50.0` | **(a) real drift — SSoT contradicts code** (SMA-10 rule never existed in code; SSoT born wrong 2026-05-07) | **ESCALATE**: operator rules which extension rule is intended (§4). Stays uncited until ruled. |
| `db...:dvol_min=$20M` | Sourced — ADR 0013 §2.3 names it as an explicit probe | Cite (§5a) + one-line operator sign-off ask. |
| `flag_detector._HTF_MIN_ADR_PCT=0.04` | Sourced — operator notes line 97, verbatim "ADR > 4%" (same sentence as the already-cited ADV sibling) | Cite (§5b). CLOSED. |
