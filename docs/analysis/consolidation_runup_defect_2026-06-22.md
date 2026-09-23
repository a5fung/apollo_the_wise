# Consolidation §2 Runup-Detection Defect — the runup is measured INSIDE the base

**Date:** 2026-06-22  ·  **Severity:** CRITICAL (structural)  ·  **Setup:** Family-A "consolidation play" (#270 / #354), SHADOW (no real money)  ·  **Found via:** operator spotted STM (clean COILED flag) absent from the consolidation board.

## Summary

The §2 consolidation **runup canary measures the "runup" over a window that sits INSIDE the base.** For any *developed* setup — a real runup followed by a multi-day base, sitting at/near new highs — it reads the **base's internal range** as the "runup," finds it too small, and rejects the name. The runup phase and the base phase are **collapsed into one window.** The textbook setup (runup FIRST, THEN a separate base) is structurally invisible to it.

## The setup it is supposed to detect

Three **sequential, separate** phases: **(1) RUNUP** — a large move up over weeks → **(2) BASE / consolidation** — tightening (range + volume contraction) over days–weeks → **(3) breakout / entry.** The runup must be measured **before** the base, over a window that does **not** overlap it.

## The defect (code)

- **`db.py::get_anticipation_universe`** (universe proposer): `anchor` = earliest date of the **MAX close in the last 15 sessions**; `runup_ratio` = best **10-session** rolling `MAX/MIN close` over the last 12 sessions; must be ≥ `RUNUP_MIN` (1.15). Plus a `|close %change| ≤ 1.0%` **same-day** compression gate.
- **`anticipation.py::evaluate_consolidation`**: `runup_ratio = closes[anchor_idx] / min(closes over the 10 sessions ENDING AT anchor_idx)`; `< 1.15` → returns `None` (rejected before any coil eval). `coil_days = today − anchor`.
- **THE FLAW:** the anchor is the **recent max close**, and the runup is measured over the **10 sessions ending at the anchor.** For a name at/near new highs after a developed base, the anchor lands on a **recent** bar (the base high, or today's new high), so the 10-session runup window is **entirely inside the base.** It measures the base's range, not the runup.

## STM proof (live data, 2026-06-22)

STM structure from `mi_daily_closes`:

```
RUNUP:  44.46 (Apr 20) ──climbs──▶ 79.71 (Jun 3 peak)    real runup (~+80% in-window; ~+162% off the true 60d low; flag reports +162%)
BASE:   Jun 4 ─────────────────▶ Jun 22  ranges 70.72–79.91, ~12 sessions, NEW HIGH today (79.91)
```

What the code computes:
- `anchor` = max close in last 15 sessions = **79.91 (TODAY, Jun 22)** — a new high, so the anchor is the most-recent bar.
- `runup_ratio` = `79.91 / min(last 10 sessions = 70.74)` = **1.13** → `< 1.15` → **REJECTED.**
- The 10-session runup window (`Jun 8–22`) **is the base.** The real runup (`Apr 20 → Jun 3`) is never looked at — it's older than the window.

So STM — a stock that ran up then based for 12 days (the setup the flag detector's COILED state is built to catch) — is structurally excluded because the runup detector measured the base and found +13%.

## Contamination assessment (operator concern: "flag may be contaminated")

- **`flag_detector.py` is CLEAN / unchanged this session** — last commit `#168` (pre-session). The live flag scanner (`_RUNUP_LOOKBACK_DAYS=60`, `_RUNUP_MIN_RATIO=1.50` = pivot_high / 60d-low, base measured separately) is **correct and untouched.**
- The #354 merge (`befb41e`) only touched `anticipation.py`. Its **Confirm mode runs on the broken §2 universe**, so it **inherits the runup flaw.** ⇒ the merge does **not** replicate flag — it replicates §2's flawed universe with a flag-break entry. The merge premise (consolidation subsumes flag) is invalid until §2 is fixed.

## Fix direction (the correct structure — what flag already does)

Separate the two phases:
1. **RUNUP** over a **long lookback** (e.g. 60 days) from the low that **precedes** the base up to the runup peak (which may be older than the recent window).
2. **BASE** = the recent tight period **after** the peak (range + vol contraction).

The runup window must **not** overlap the base. This is exactly `flag_detector`'s structure — so the fix should **reuse flag's proven runup/pivot logic** (search-before-build), not invent new short-window math.

## Status

- ✅ Defect confirmed + written up 2026-06-22.
- ⏳ Full e2e structural review of the setup (runup / base / entry phases) — in progress.
- ⏳ Advisor review + the fix — pending.

The §2 runup detection is **operator-SIGNED methodology** → the redesign goes through CHANGE_PROCESS + operator sign-off. Operator directed the fix on 2026-06-22 ("do not wait … issue a fix").

---

## Second failure mode — FALSE POSITIVES (garbage entries fire). Live data 2026-06-22.

The "fired today" list is full of downtrends/uptrends with no contraction. Every fired name has `fresh_tightening=FALSE` and `tight_close_streak=0` — **none are "coiled" by the detector's own state machine** — yet they fired:

```
BTU   31.21 → 24.12   -23% DOWNTREND over the base   fired ANTICIPATE (range 3.8%, vol 0.64)
UFO   59.34 → 48.72   -18% DOWNTREND                 fired ANTICIPATE (range 3.3%, vol 0.78)
DRUG  74.50 → 59 → 63 -15% then bounce               fired ANTICIPATE (range 5.8%)
PTGX  102.8 → 115.0   UPTREND, not a coil            fired CONFIRM
KEEL  fired CONFIRM with 11.9% daily range, rmv=100  not remotely tight
```

**Mechanism:** the entry gate (`is_entry_tight`: daily range ≤7% + vol ≤ADV) is **satisfied by a quiet decline** — a stock bleeding −2 to −3%/day has small ranges + light volume, so it reads as "tight." There is **no holding-near-high check, no range-contraction-vs-base test, and no requirement that the name be in the coiled state.** A controlled bleed-down is indistinguishable from a consolidation.

## E2E structural review (fork, 2026-06-22) — verdict: NOT sound; phase-1 redesign required

1. **CRITICAL** `db.py ~6450-6453` (`pk` CTE): anchor = "earliest date of MAX close in last 15 sessions" → for a new-high name the anchor is today/recent (inside the base), re-pinning to every new high. **Root defect.**
2. **CRITICAL** `anticipation.py:677-678`: runup measured inside the base (inherits #1). [the STM bug]
3. **CRITICAL** `anticipation.py:756` (`entry_signal_at`) + `:796-797` (`confirm_signal_at`): both require a base strictly AFTER the anchor (`run_lo ≤ anchor_idx → None`; `idx < anchor_idx+2 → None`). With a recent anchor → real breakouts **cannot fire**; flat/declining non-new-high names **do** → the inversion (surfaces weak, drops strong).
4. **CRITICAL** `db.py:6471-6472`: absolute flat-today gate `|c0/c1−1| ≤ 1%` + `ORDER BY today_pct ASC` standing in for multi-day tightness; drops any high-ATR leader on a 2%+ day.
5. **MAJOR** runup lookback too short: `RUNUP_WINDOW=10` (~21-session max reach); the 60-day CTE feeds only liquidity, not runup. Flag uses 60d.
6. **MAJOR** runup floor too low: `RUNUP_MIN=1.15` (+15%) vs flag's 1.50 (+50%) → 325 weak names (noise).
7. **MAJOR** three inconsistent runup formulas for one concept (no SSoT).
8. **MINOR** carry-forward only preserves anchors for already-captured names; a name first seen at new highs never gets a valid anchor (STM: 0 rows).

The base-tightness primitives (`is_entry_tight`, `fresh_tightening`) and the entry/confirm signal *shapes* are reasonable — they all just hang off a broken anchor.

## Redesign plan (phase 1 — the anchor)

1. **Fix the anchor as the true runup PEAK** over a long lookback (≥60d), located from a pre-base low — NOT "max close in last 15 sessions." Once found, the peak is **fixed**, not re-pinned to new highs.
2. **Measure the runup over the long window** (peak / pre-peak low ≥ the signed floor, e.g. 50% like flag), separate from the base.
3. **Base = strictly after the fixed peak**; require **holding near the high (not declining) + actual range/vol contraction** — the missing false-positive guard.
4. **Entry fires after the fixed peak** (the existing entry shapes work once the anchor is right).
5. **Single source of truth** for the runup; eliminate the 3 inconsistent formulas.
6. **Reuse `flag_detector`'s proven runup/pivot logic** (search-before-build — flag already does runup→base→breakout correctly). **Architectural option to weigh with advisor/operator:** rather than rebuild §2's runup math, feed flag's already-correct coiled candidates into the consolidation entry logic (the *real* merge).

Floor (15%→50%?) + the flat-today gate are signed methodology → **operator sign-off required** before the redesign ships.

