# Setup SSoT — U&R (Undercut & Rally) — #98

**Status:** SHADOW (telemetry-only, no entries). Shipped 2026-05-31. Promotion to
paper gated on `undercut_rally_signal_n10` (N≥10 settled) + advisor + this doc's
change-log discipline (`docs/setups/CHANGE_PROCESS.md`).

**Lineage:** Wyckoff "Spring" → Livermore "Shakeout-Plus-Three" → O'Neil
"Shakeout-Plus-N" → **Morales / OWL** (simplified: undercut a prior low + rally
back above = long entry; prior low = the "selling guide"; *"volume is generally
not a factor"*). Entry-technique #5 of the tight-range taxonomy
(`memory/user_tight_range_entry_techniques.md`). Operator priority 2026-05-31:
the flag/tightness/consolidation-after-run-up class is the **#2 setup to trade
after MAGNA53**; U&R is one of its entry mechanics.

## What it is
A name in a tight consolidation (flag) briefly **undercuts** a prior low — a
shallow stop-run that washes out weak holders and lures shorts — then **reclaims**
back above that low. The reclaim is the buyable signal; the undercut low is the
stop. Counter-intuitively the *lowest-risk* entry in the taxonomy: the
invalidation point is crystal-clear (rally fails → stop) and the eventual cushion
is large (entry is far below where the move runs).

## V1 criteria (deployed 2026-05-31)
Detector: `flag_detector.run_intraday_undercut_rally_scan` (every 5 min, gated
9:35–15:55 ET, Mon–Fri). Predicate: `flag_detector.is_undercut_rally`.

- **Universe:** `mi_flag_candidates` latest pre-today scan, stage ∈
  {TIGHTENING, COILED, TRIGGERED}, `base_low` populated, not already broken out
  above `base_high`. (Anchor = the precomputed `base_low` — sidesteps swing-low
  identification, which is the hard part.)
- **Anchor:** `base_low` (the prior low of the flag).
- **Undercut depth band:** `(_UR_MIN_UNDERCUT_PCT, _UR_MAX_UNDERCUT_PCT]` =
  **(2%, 8%]** below `base_low`. The lower bound is *adjacent to* the support-test
  detector's ≤2% touch band, so the two NEVER fire on the same bar — **depth is
  what distinguishes a U&R (a real stop-run that reclaims) from a support-test (a
  shallow touch that holds).** The upper cap rejects a deep undercut as a
  breakdown, not a shakeout.
- **Reclaim:** `current_price ≥ base_low × (1 + _UR_RECLAIM_FLOOR_PCT/100)` =
  back at/above `base_low`.
- **Trigger basis:** the **day's low** is the undercut probe (same-day intraday
  undercut → reclaim). One row per ticker/day (`UNIQUE (ticker, ur_date)`).
- **NO volume gate** — per Morales, volume is not a factor for U&R (the design
  departure from the #94 breakout detector). `today_volume`/`adv_20` stored as
  context only.
- **Stop / "selling guide":** the undercut low (`undercut_low`).

## Tables / surfaces
- `mi_flag_undercut_rally` — one row per detected U&R (audit: `intraday_undercut_rally`).
- **Evening-brief roundup (primary surface, operator 2026-05-31):** a quiet daily
  block in `send_evening_briefing` (via `get_undercut_rallies`) listing today's
  structurally-surviving U&Rs — chosen over intraday pings for the shadow phase.
- **Intraday Telegram FYI is OFF by default**, gated by `UNDERCUT_RALLY_INTRADAY_FYI`
  (default false — NOT the shared `SHADOW_DETECTOR_TELEGRAM_ENABLED`). Flip on when
  U&R graduates to a tradeable real-time setup (the reclaim moment then matters for
  entry). **On-demand surface: `/detectors` (today + 7d counts per detector) / `/detectors
  TICKER` (30-day hits per detector)** — `/undercutrally` (`/ur`) was RETIRED #218
  (2026-06-06 operator command review), consolidated into `/detectors` alongside
  `/flagbreaks` `/supporttests` `/mapullbacks` `/lowvolrests`.
- EOD reconciliation in `reconcile_flag_state_post_eod` flips `parent_invalidated_eod`
  if the parent ticker classified INVALIDATED at the 5:25 PM scan (audit:
  `flag_undercut_rally_reconciled`). Backward-check filters `parent_invalidated_eod = FALSE`.

## Known limitations / V2 deferrals (NOT built in v1)
- Multi-day undercut *persistence* (undercut yesterday, reclaim today) — v1 is same-day only.
- MA-anchor variant (undercut SMA10/20/50 instead of `base_low`).
- Weekly-timeframe U&R (Morales notes it works on weeklies, e.g. ROKU 2018-19).
- Short-side use (Morales uses undercut-of-prior-low as a short-cover signal).
- Market-regime confluence ("best U&Rs occur after a market turn up from a correction").
- Arbitrary swing-low universe (beyond `mi_flag_candidates`) — needs a swing-low detector.

## Change log
- **2026-07-24 — FL-5 reconcile: doc synced to code.** `/undercutrally` (`/ur`) was retired
  #218 (2026-06-06 operator command review) — folded into the consolidated `/detectors` /
  `/detectors TICKER` roll-up (`agent.py::_handle_detectors_query`) along with the other 4
  entry-technique detector commands. Also removed the dead `fishhook_detector.py` path
  reference below (no such file in the codebase; likely renamed/absorbed before this doc's
  first ship). No code change.
- **2026-05-31 (same day, post-ship)** — surfacing set to **evening-brief roundup +
  on-demand `/undercutrally`** (superseded 2026-06-06, see above); intraday Telegram FYI
  gated OFF by default (`UNDERCUT_RALLY_INTRADAY_FYI`, NOT the shared shadow env), per
  operator (quiet shadow phase; flip on at graduation). `get_undercut_rallies` getter +
  brief block.
- **2026-05-31** — V1 shipped (shadow). Table + predicate + 5-min scan + EOD
  reconcile + `/undercutrally` (superseded 2026-06-06, see above) + 12/12 predicate tests.
  Thresholds seeded (2%/8%/0%); tune on `undercut_rally_signal_n10`. Built per operator
  directive ("build U&R now as a shadow, surface via Telegram FYI, collect data to refine")
  + advisor design pass (depth-band adjacency to support-test, max-undercut cap,
  v1 scope discipline). Distinct from wick-fill (`wick_tracker.py`) — different mechanics
  (pullback-to-MA reclaim vs fill-on-wick).
