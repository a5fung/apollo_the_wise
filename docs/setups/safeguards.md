# Portfolio Safeguards SSoT

**Phase**: live in production. The drawdown breaker (#6 below) is **ACTIVE as of 2026-06-03** (flipped pre-cutover on paper, operator decision — validate the full system before live) — the daily 16:12 ET cron emits transition audit events but `_check_safeguards()` now ENFORCES it (size-down by tier: WATCH 1.0× / REDUCE 0.5× / BLOCK 0×). Flipped to active 2026-06-03 (pre-cutover, on paper validation — see change-log).
**Code**: `agents/market_intelligence/broker/live_tracker.py::_check_safeguards` (lines 101-212+).

## Definition

Portfolio-level pre-trade gate. Every entry submission (MAGNA53 EP today; any future strategy) calls `_check_safeguards()` before placing an order. The function returns `(True, None)` to allow or `(False, skip_reason)` to block. Each safeguard is checked in order; first block short-circuits.

This is **not** a per-setup quality gate (those live in setup-specific SSoTs like `magna53_ep.md`, `ninem.md`, etc.). These are the guards that protect the *portfolio* from compounding damage regardless of which setup generated the candidate.

## Active safeguards (in order)

1. **`live_trading_enabled`** — env-gate kill switch (`LIVE_TRADING_ENABLED`). Returns False if disabled. No skip reason — the entire pipeline early-exits. ⚠️ BOOT-READ (restart-gated) — for an INSTANT runtime halt use #2.
2. **`manual_trading_halt`** (`BLOCK_TRADING_PAUSED`) — operator's one-command runtime kill switch (#345, 2026-06-19). `/pause` sets `mi_safeguard_state(safeguard='manual_trading_halt', account_mode='live')='on'`; read **per-entry** in `_check_safeguards` (LIVE path only) so it takes effect on the NEXT entry with **NO redeploy**; `/resume` lifts. FAIL-SAFE: an unreadable flag blocks the live path under a DISTINCT `INFRA_HALT_STATE_UNREADABLE` reason (never mislabels as operator-paused). On pause it also **cancels resting unfilled real-money entry brackets** (`cancel_unfilled_entries(account_mode='live')` via the execution facade — the proven 10:00/EOD cancel path; the 10:00 ET cleanup backstops a failed cancel) so a mid-morning `/pause` stops fills-in-flight, not just new orders. Open POSITIONS are untouched — they keep their resting broker stops (not a flatten). Paper/shadow unaffected. HARD gate: required live + verified before `live_real_enabled=TRUE`.
3. **`max_concurrent_positions`** (`BLOCK_MAX_POSITIONS`) — count of open `mi_live_trades` rows in `db.OPEN_POSITION_STATUSES` = `('filled','order_placed','confirmed')` ≥ `MAX_CONCURRENT_LIVE_POSITIONS` (5). Bounds total simultaneous exposure. **`pending_confirmation` is EXCLUDED (#436 fork B, 2026-07-11):** a staged-paper proposal is inert (no broker order, no confirm path since #364) so it is not a position and must not consume a slot; a real auto-entry flips `pending_confirmation → confirmed` in-process so it is counted the instant it is real. The vocabulary is the single constant `db.OPEN_POSITION_STATUSES`, reused by `get_open_position_count`, `live_tracker.count_open_positions` (the shared cap-count SQL: `_check_safeguards` per-mode + per-strategy AND the #461 insert-time recheck), and `coverage_drift` so "open" can never drift between the cap and the drift detector. **Enforced transactionally (#461, 2026-07-18):** the `_check_safeguards` read is the cheap early gate; the AUTHORITATIVE check is an atomic recount + INSERT (+ auto-enter confirm flip) in one transaction under a per-`account_mode` `pg_advisory_xact_lock` at the entry pipeline's insert step, so concurrent candidates can never both pass on a stale count (see change log 2026-07-18 — cap VALUE unchanged).
4. **PDT guards** — ⚠️ **RETIRED 2026-06-04 (#181).** FINRA Rule 4210 + Alpaca's new intraday-margin framework eliminated the PDT designation and the $25K floor; the `BLOCK_PDT_LOCKOUT_ACTIVE` / `BLOCK_PDT_LOCKOUT_IMMINENT` guards were removed from `_check_safeguards`. Overextension is now Alpaca's broker-side intraday-margin pre-trade check (margin-deficit orders rejected) — no Apollo-side day-trade gate replaces it. See change log 2026-06-04. *(Was: at equity < $25K, block if `pattern_day_trader=True` or `daytrade_count ≥ 3`.)*
5. **`daily_loss_limit`** (`BLOCK_DAILY_LOSS`) — sum of `total_pnl` of trades **CLOSED today** (ET, by `closed_at` — **NOT** `alert_date`; FL-2 coverage fix 2026-07-24) that realized a loss, ≤ `-equity * DAILY_LOSS_LIMIT_PCT` (-2%). Catastrophic intraday backstop on today's **realized** losses, including **multi-day positions that stop out today** (Day 2-5 SMA-trail / partial / time-stop closes). Magnitude-based, not count-based.
6. **`circuit_breaker`** (`BLOCK_CIRCUIT_BREAKER`) — last `CIRCUIT_BREAKER_CONSEC_LOSSES` (=10) closed trades all losses, cooldown until `latest_loss_at + CIRCUIT_BREAKER_COOLDOWN_DAYS` (=1d). **KEPT — operator-ruled 2026-07-31 ("we should keep the circuit breaker"). NO LONGER DEPRECATED; the removal pre-committed below is CANCELLED.** Threshold bumped 5→10 on 2026-05-08. ⚠ Two structural properties are ACCEPTED, not fixed (constants.py:319): it is **self-perpetuating** — a loss closing DURING cooldown advances `latest_loss_at` and re-arms for another 24h — and **methodology-blind**, since a closed-trade streak over-weights losers when the methodology holds winners to a trailing stop. Both were observed live on 2026-07-31: FTNT closed −$6.63 at 09:37:50 on 07-30, which alone re-armed the cooldown to 09:37:50 on 07-31 and blocked FLNC/COHU/NWL/FET (all alerted 09:31:00) plus MPWR (09:35:42) — six live alerts, zero entries. See change log 2026-07-31.
7. **`drawdown_breaker`** (`BLOCK_DRAWDOWN_BREAKER`) — ACTIVE as of 2026-06-03. **EFFECTIVENESS REVIEWED 2026-07-30 — VERDICT: UNPROVEN ON LIVE MONEY (review stays OPEN).** ⚠ My first pass concluded 'net-helped' off the PAPER account and the operator corrected it: *"why looking at paper? we've switched to real money a month ago."* The review's own predicate names paper because it was written PRE-CUTOVER. **On LIVE the breaker has NEVER acted**: state WATCH, peak $5,000 (07-03), drawdown −4.36%, 28 snapshots, evaluated 07-29 — and WATCH is multiplier 1.0×, a warning that sizes nothing down. REDUCE needs −7%, BLOCK −12%; neither has fired live, and zero entries carry `block:drawdown_breaker` lifetime. **So: tracking correctly, protecting nothing yet.** The first real test is a live drawdown reaching −7%. One REDUCE trip in the whole active phase (2026-06-05 → 07-06, 31 days); BLOCK has never fired and zero entries carry `block:drawdown_breaker` lifetime. PRE-CUTOVER PAPER CONTEXT ONLY (not the verdict): one REDUCE trip 06-05→07-06 (31d) where enforcement was real — REDUCE-window n=6 avg risk $297 / notional $7,311 vs $917 / $18,504 outside, ~1/3 of normal (the 0.5× compounding with regime sizing). ⚠ But that paper 'saving' rests on ONE trade: SYRE is −$1,483 of the −$2,493 total (60%), the other five average ~−$200, and the comparison group outside the window is a SINGLE trade. Directional at best. Persisted state machine; when `mi_safeguard_state.state='TRIPPED'`, blocks. See "Drawdown breaker — Mechanics" below.

⚖ **OPERATOR RULING 2026-08-23 — the 20% position cap STAYS. Do not re-open it.**
*"let's leave it for now, this will be solved with a large account eventually."*

**What was asked:** #571 found the cap silently truncated 11 of 22 closed live trades, cutting
intended risk from ~$48 to as little as $15 — we traded the name, just smaller. Only 4 names were
missed outright (share count rounded to zero). He asked whether to raise the cap.

**Why it stays, in plain words:** the cap is not a second risk rule, it is arithmetic —
`MAX_CONCURRENT_LIVE_POSITIONS = 5` × 20% = 100% of the account, so 20% is exactly what lets a
full book be held without margin. Raising it does not add risk-per-trade (the risk budget is
unchanged either way); it trades **breadth for concentration** — at 33% you hold 3 names, not 5.
On a bigger account the cap stops binding on its own, because the share count needed for a
$50-risk trade is a smaller fraction of equity.

**The gap-down worry, measured:** 17 of 22 closed trades never saw an overnight; of the 5 that
did, the worst lost $24.13 against a $22.55 budget (1.07×). Nothing has gapped badly through a
stop. A larger position would scale that overage proportionally, not disproportionately.

**Still shipping:** the cap's truncations are being made VISIBLE (audit row + the intended-vs-placed
figure). The value is unchanged; only the silence is. Evidence:
`docs/analysis/position_sizing_571_2026-08-23.md`.

## Position sizing — regime-keyed risk multiplier (#456, operator-ruled 2026-07-26)

**Phase**: ✅ **LIVE.** `REGIME_SIZING_ENABLED=true` verified in BOTH `apollo-market` and `apollo-execution` on 2026-08-23; the regime multipliers below have been the acting sizing rule since 2026-07-26, and the VIX-scaled + `qqq_ema_bullish`-halve behaviour they replaced applies only to trades placed BEFORE that date. ⚠ This paragraph read "flag OFF by default, production behaviour unchanged" for four weeks after the flip — found 2026-08-23 by #571's sizing measurement, which had to establish from prod data what this file should have stated. A safeguard doc that describes the wrong rule is worse than none: it gets cited authoritatively (CHANGE_PROCESS), and it is the hidden-rule failure P15 names. The default in code remains `false`; what is stated here is what is ACTING. This section documents the risk_pct COMPUTATION at the spec-builder step (upstream of the safeguards list above); the drawdown-tier + per-strategy composition below (`final_shares = ...`) is unchanged and multiplies on top of whatever risk_pct this section produces.

**Flag**: `REGIME_SIZING_ENABLED` (env var, default `false`). Flip: set `REGIME_SIZING_ENABLED=true` and redeploy — **broker/order_manager.py and flag_detector.py run on `apollo-execution`, so the flip needs `bash scripts/deploy.sh execution` (or `both`), NOT the market-agent default** (per the 2026-07-23 #500 mis-scope lesson — a broker change deployed to the wrong service is silently dark). No DB migration; no code change to flip back (`REGIME_SIZING_ENABLED=false` + redeploy reverts instantly).

**Mapping** (`constants.REGIME_RISK_MULTIPLIER` + `regime_risk_multiplier()`), applied as `risk_pct = RISK_PCT × regime_risk_multiplier(regime_label)`:

| Regime | Multiplier | Evidence status |
|---|---:|---|
| Bull | 1.00× | Evidenced (N=29, −0.35R avg, the only bucket with a real win rate) |
| Choppy | 0.75× | Evidenced (N=9, −1.19R avg); level set mild because Bull↔Choppy is the flappiest classifier boundary |
| Correcting | 0.50× | **STRUCTURAL PRIOR, not a measurement** — N=5 (below the N≥10 CHANGE_PROCESS bar). Direction evidenced (0/5 wins, −1.02R); level borrows the drawdown-breaker REDUCE grammar (0.5× = "keep fishing, half exposure") |
| Crisis | 0.25× | **STRUCTURAL PRIOR, not a measurement** — N=0 (zero pipeline trades have ever seen a Crisis label). Pure prior: matches the old VIX formula's own floor, severity-monotone |
| missing / stale / unrecognized label | 0.25× | Fail-SAFE floor, not evidence-based — see "Fail-loud fallback" below |

Full evidence + the 43-trade cohort + the counterfactual-weighting table: `docs/analysis/456_regime_sizing_proposal_2026-07-26.md`.

**What's folded**: the separate `qqq_ema_bullish` binary ×0.5 halve (order_manager.py ×2 call sites + the flag_detector.py HTF shadow) is REMOVED when the flag is on — operator ruling: *"VIX is not the only gate"* — the regime classifier already scores the bearish tape (VIX is one weighted input into it), so the halve double-counted it. VIX no longer scales sizing directly; it only feeds the regime classifier (`regime.py`).

**The 3 sizing sites, all routed through ONE resolver** (`broker/order_manager.py::_resolve_regime_risk_pct` — no scattered copies):
1. `order_manager.prepare_orb_order` (MAGNA53 ORB entry, real money).
2. `order_manager.prepare_prior_day_low_orb_order` (prior-day-low stop; renamed from
   `prepare_9m_day2_orb_order` on 2026-08-02 when the 9M Day-2 ENTRY was deleted — the builder was
   never 9M-specific. Its live consumer today is the 5-min ORB SHADOW lane (#482), so this site is
   currently shadow-only, not real money.)
3. `flag_detector.prepare_htf_breakout_order` (HTF breakout SHADOW — **never submitted**, no real money). This function is deliberately PURE/sync (must not cross the execution boundary per its own docstring, #154/#296), so it calls the pure `constants.regime_risk_multiplier()` lookup directly under the same flag, WITHOUT the fail-loud alerting (that needs async DB/Telegram I/O — see below). Its only caller hardcodes `regime_record=None` today, so under the flag this permanently pins the shadow's fixed-notional multiplier at the 0.25× floor — a uniform scale on a fixed notional (the function's own comment: "R is equity-independent"), so the #356 edge dataset isn't corrupted, but it IS a real behavior change under the flag. Not rewired as part of #456 (out of this card's scope — the caller's `None` hardcoding predates this change).

**Excluded on purpose — offline backtester copies**: `backtester/engine.py::_position_size` and `backtester/tracker.py::_position_size` carry their OWN duplicate `qqq_ema_bullish`-halve formula, used only by offline scan+simulate replay (no money, no live path). Left untouched by #456 — grep found them during the "handle all 3 sites" sweep but they are not part of the proposal's 3 identified sites and changing them would silently move the calibration methodology the Q4 ship-and-accrue evidence path depends on (re-running #454 §5(a)'s regime-stratified replay would now diverge from live sizing unless these are updated in a follow-up change of their own). **Watch item**: if/when that replay is run to evidence the Correcting/Crisis priors, either fold these two copies first (its own CHANGE_PROCESS entry) or explicitly note the live/backtest sizing-formula divergence in that analysis.

**Fail-loud fallback** (operator ruling 5: *"it should fail loud so we can fix"*): a missing, stale, or unrecognized-label regime read floors to 0.25× AND fires a Telegram alert + `sizing_regime_fallback` audit event, **deduped once per ET day per `account_mode`** (audit-log-as-state pattern, mirrors `intraday_drawdown`'s crossing dedup — the first occurrence each day writes the alert; later same-day/same-mode occurrences are silent no-ops, but still floor correctly).

- **Staleness gate**: `regime_date` must be `>= last_trading_day(today − 1 day)` — i.e. the last COMPLETED trading day strictly before today, NOT `last_trading_day(today)` itself. **This distinction matters**: on any ordinary trading day `last_trading_day(today) == today`, so the naive predicate from the original proposal draft would floor + alert EVERY morning (the regime nightly runs at 17:00 ET and stamps `regime_date = ` the day it ran, so a 9:31 ET entry always reads YESTERDAY's row by design — that is the expected normal case, not staleness). Caught before ship via advisor review. Pinned both directions in `tests/test_regime_sizing.py`: Tuesday-reads-Monday = fresh (normal case), Tuesday-reads-Friday = stale (a broken Monday nightly), Monday-reads-Friday = fresh (weekend gap, no nightly Sat/Sun).
- **Known limitation (accepted, not fixed)**: the staleness gate is weekend-only (`last_trading_day`'s own scope — no market-holiday calendar). The trading day immediately after a market holiday reads one day tighter than necessary and floors+alerts as a false positive (~9×/yr). Safe-direction (floors size, never oversizes) — not worth a holiday calendar for this.
- **Known race (accepted, documented)**: the ORB monitor processes up to 5 candidates concurrently (`Semaphore(5)` + `gather`), so on the FIRST fallback morning multiple candidates can all read "not yet alerted" before any commits — bounded to a handful of duplicate Telegrams that morning (matches the #461-class precedent), never a sizing-correctness issue (the floor multiplier itself is unaffected by the race).
- **`today` is THREADED, not independently re-read** (advisor-caught during review): `prepare_orb_order` / `prepare_prior_day_low_orb_order` take an explicit `today` param — the caller's ALREADY-resolved value (`process_new_alerts_live`'s `today`), the same value used for the regime fetch + alerts query + `submit_trade_entry(today=...)` — passed through the `_magna_spec_builder` closure in `live_tracker.py`. (The `_ninem_spec_builder` closure and `submit_9m_day2_trade` were deleted 2026-08-02 with the Day-2 entry, #515; the threading discipline is unchanged for the sites that remain.) A second, independent `et_today()` call inside `order_manager.py` would have been an unpinned second clock source in the money path (a real risk under `EXECUTION_MODE=http`'s cross-container split, or a bar-fetch retry spanning a midnight-ET boundary). Both functions default `today=None → et_today()` only for callers without one on hand. Pinned in `tests/test_regime_sizing.py`.
- **Test coverage caveat (flagged, not resolved — operator's call)**: the fail-loud dedup's SQL predicate (`(created_at AT TIME ZONE 'America/New_York')::date = $2`) is exercised in `tests/test_regime_sizing.py` against a MOCKED `conn.fetch`, never a real Postgres — the same shape as `intraday_drawdown`'s shipped (and live-validated) predicate, so it inherits that precedent's correctness rather than being independently proven. A DSN-gated real-PG sibling test (pattern: `test_461_cap_lock_real_pg.py`) would close this gap but wasn't added here — flagged for the operator to decide whether it's needed before the live flip, given the flag ships OFF and the flip itself requires its own shadow-verify.

**Operator-facing display** (`briefing._format_regime_section`'s "size ≈X×" line, morning briefing) is kept in sync with the flag so it never shows a stale multiplier — under the flag it no longer depends on VIX being present.

## Drawdown breaker — Mechanics

**TIERED REDESIGN 2026-05-18**: The original binary OK/TRIPPED design hard-blocked entries on any -5% drawdown. For a 20-30% win-rate strategy, P(7 consecutive losses) = 13.3% — meaning -7% drawdowns are statistically NORMAL variance, not strategy failure. Hard-blocking during normal variance structurally prevents the methodology from finding the winners that pay for losses. The tiered design adjusts SIZING with drawdown depth instead of fully stopping.

**Equity source**: `alpaca_client.get_account()` returns current `equity` (cash + open-position MTM). Already includes unrealized — open winners' gains lift equity, which is the entire point of the methodology-aware shape.

**Peak source**: `MAX(equity)` over last `DRAWDOWN_PEAK_WINDOW_DAYS` (=30) snapshots in `mi_account_equity_snapshots`, scoped to `account_mode`. Snapshots written daily at 16:12 ET cron (`account_equity_snapshot` job).

**Tiered state machine** (`mi_safeguard_state` table, PK `(safeguard, account_mode)`):

| State | Trip threshold | Release threshold | Sizing multiplier | Audit event (entry) |
|---|---:|---:|---:|---|
| OK | — | — | 1.0× | (no event) |
| WATCH | drawdown ≤ -4% | drawdown ≥ -2.5% | 1.0× | `drawdown_watch_entered` |
| REDUCE | drawdown ≤ -7% | drawdown ≥ -4% | 0.5× | `drawdown_reduce_entered` |
| BLOCK | drawdown ≤ -12% | drawdown ≥ -7% | 0.0× | `drawdown_block_entered` |

**Transition logic** (`_next_state` in `broker/drawdown_breaker.py`):

- **Trip-side**: jump to deepest applicable tier in ONE snapshot. A -15% one-day drop from OK lands directly in BLOCK, not WATCH-REDUCE-BLOCK over three days.
- **Release-side**: step up at most ONE tier per evaluation, gated on per-tier release threshold (asymmetric hysteresis at each boundary). Prevents flap.

**Sizing composition** (applied in `entry_pipeline.py` post-spec_builder):

```
final_shares = floor(spec.shares × strategy.position_size_multiplier × drawdown_tier_multiplier)
```

Per-strategy (#65) and drawdown tier multipliers compound multiplicatively — a strategy at 0.5× during REDUCE state = 0.5 × 0.5 = 0.25× sizing. This is methodology-correct: bleed weeks should compound conservative sizing across both axes. (The worked example used to be 9M Day 2 at 0.5×; that strategy was deleted 2026-08-02, #515. **No strategy currently carries a multiplier other than 1.0** — the mechanism is live and untested by a second strategy until one is promoted.)

**Account-mode scoping**: paper history doesn't carry over to live. Live cutover starts a fresh peak. `mi_safeguard_state` row is per `(safeguard, account_mode)`.

## Drawdown breaker — Why tiered instead of binary

For a 20-30% WR momentum strategy with R-expectancy positive:

| Event | Probability | Drawdown |
|---|---|---|
| 7 consecutive losses (at 1% each) | 13.3% | -7% |
| 10 consecutive losses | 5.6% | -10% |
| 13 consecutive losses | 2.4% | -13% |

The binary -5% trip caught NORMAL variance. After a normal drawdown, the strategy needs to keep trading to find the winners (3-10R) that pay for the losses. Pausing for ~30 days after a normal drawdown structurally breaks the strategy.

The tiered design preserves the safeguard's purpose (catastrophic loss prevention) WITHOUT preventing the methodology from operating during expected variance. WATCH = informational, REDUCE = halve risk (still fishing), BLOCK = true catastrophic floor (rare).

**Daily loss limit (2% of account)** remains in place as the same-day blow-up guard, independent of this tiered cumulative-drawdown logic.

- **Min-history gate** (active phase only): `snapshots_count ≥ MIN_SNAPSHOT_HISTORY_DAYS` (=7). Don't trip on sparse history (new account / mode flip). Shadow always evaluates and emits regardless (calibration data from day 1).
- **Stale-data fail-open** (advisor-flagged): if most recent snapshot is older than 48 hours, `sufficient_history=False` and the breaker is effectively disabled until data freshens. Protects against silent cron-failure lockouts on a week-old peak. Active-phase reads see `state='OK'` because `recompute_drawdown_state` won't transition without fresh data.
- **Legacy `TRIPPED` state migration**: pre-2026-05-18 `mi_safeguard_state` rows with `state='TRIPPED'` auto-migrate via `_next_state` on next recompute. Maps to REDUCE state (0.5× multiplier) until the recompute cron repopulates with a proper tier.

## Drawdown breaker — Design choices

These are deliberate, not oversights. Future readers should understand the reasoning before changing them:

- **Daily resolution, not intraday**. Peak is captured at 16:12 ET close, NOT intraday max. Drawdown is *understated* relative to true peak-to-current — conservative for trip purposes (less false-positive). Catches day-to-day equity erosion. Intraday volatility is the daily-loss-limit's job (#4 above). Together they cover the magnitude side at two timescales: the 2% intraday daily-loss limit + the tiered multi-day drawdown breaker (WATCH −4% / REDUCE −7% / BLOCK −12% from the 30-day peak). *(FL-5 reconcile 2026-07-24: was "5% multi-day" — a leftover from the pre-tiered −5%/−2.5% binary breaker retired 2026-05-18.)*
- **State machine, not per-call evaluation**. `_check_safeguards()` is called per-candidate (20+ times per scan tick on busy days). Per-call drawdown computation would flood the audit log with duplicate events. Instead: evaluate ONCE daily at the cron, persist state, hot-path reads via cheap PK lookup.
- **Dedicated `mi_safeguard_state` table**, not derived from `mi_audit_log`. PK lookup is materially faster than scanning audit log; table is extensible to other future safeguards; explicit state beats derived state for an active-phase hot path.
- **Env-var phase gate**, not strategy-registry phase. Registry is for strategies; this is a portfolio safeguard. Single env var (`DRAWDOWN_BREAKER_PHASE=shadow|active`) is the entire promotion mechanism.
- **No backfill from `mi_live_trades`**. Realized P&L alone can't reconstruct equity-at-time including unrealized. Day-1 baseline insert is the only "backfill". 7-day cold-start gate handles new-account scenarios.

## Other notes

- **`mi_account_equity_snapshots` is generically reusable** beyond this safeguard — analytics, `/status` enrichment, cross-strategy ranking allocator track-record dimension (#31 Phase 2). Future readers: do NOT assume the table belongs exclusively to drawdown-breaker semantics. Add columns and consumers freely; the table stays mode-scoped and idempotent per (date, mode).
- **Manual deposits/withdrawals** (live mode only): a $5K deposit looks like +5% equity (raises peak); a $5K withdrawal looks like -5% drawdown (false trip). Currently undetected. Defer to first quarter of live data; revisit via Alpaca `account_activities` API if it becomes a real problem.

## Known limitations / open questions

1. **Manual deposits/withdrawals**: not detected; deferred. See above.
2. **Quarterly hard peak reset**: not implemented. Using rolling 30-day window instead. Natural recency. Revisit if a stretched-out drawdown leaves a stale peak that prevents legitimate recovery.
   - ⚖️ **OPERATOR-RULED 2026-08-03 — KEEP THE ROLLING WINDOW. Do not switch to a high-water mark.** His reason, verbatim: *"leave it otherwise it'll take too long to recover."* A fixed high-water mark would hold the reference at an old peak and keep sizing suppressed long after the account started recovering.
   - ⚠ **The trade-off he accepted, stated plainly so it is never re-derived as a surprise:** the reference peak follows a decline DOWNWARD, so under a slow enough bleed the −7% REDUCE tier can be structurally unreachable however large the cumulative loss. Observed live on 2026-08-03: the $5,000 cutover peak rolled out of the 30-day window on 8/02, the reference became $4,967.16, and the measured drawdown IMPROVED −4.49% → −3.86% while the account gained nothing (equity $4,775.56). **This is the accepted cost of faster recovery, not an open defect.** The intraday 2% daily-loss limit remains the fast-timescale backstop.
3. **Cross-mode peak transfer**: paper peak does NOT inform live peak (mode-scoped table). Intentional — live cutover starts a fresh peak per CLAUDE.md cutover plan. If this proves wrong (e.g., user wants paper history as live's seed peak), it's a small change.

## Promotion plan (shadow → active)

> ⚠ **PROMOTION TIMING DISPUTED — flagged 2026-06-03; operator to confirm; DO NOT flip until resolved.** This section (≥14d POST-cutover, paper-not-evidence) conflicts with `data_gated_reviews.yaml::drawdown_breaker_promotion`, which records an *advisor 2026-05-10 reversal* (paper-evidence-sufficient + arm BEFORE cutover), AND with the composite `live_cutover_decision` review's Step D (arm AT cutover). This SSoT was edited 2026-05-18 — after the claimed 5/10 reversal — without updating this section, so the docs can't be ranked among themselves; the operator (a participant in the 5/10 review) is the tie-breaker. Safe-if-wrong default regardless: **armed BEFORE real money goes live** (arm-on-paper is observable/recoverable; going live disarmed is not). Do NOT rewrite this section to a side until confirmed.
>
> ✅ **RESOLVED 2026-06-03 (operator — tie-breaker, participant in the 5/10 review):** arm the breaker **BEFORE** live cutover; **paper shadow telemetry IS sufficient validation evidence.** Rationale: paper exists to validate the FULL system — including the breaker in *active* mode — before real money; going live with the safeguard disarmed in the highest-risk window defeats its purpose. The "≥14d post-cutover / paper-not-evidence" text below is the **pre-5/10 plan and is SUPERSEDED** (see change-log 2026-06-03). The actual env flip is pending operator go and slotted pre-cutover (#174).

**Trigger**: ≥14 calendar days of post-live-cutover shadow telemetry. Paper telemetry serves as threshold sanity-check only — NOT promotion evidence.

**Validation queries** before flip:

```sql
-- Trip/release transition history (post-cutover)
SELECT created_at, summary, detail FROM mi_audit_log
WHERE event_type IN ('drawdown_breaker_tripped','drawdown_breaker_released','drawdown_check_unavailable')
  AND created_at AT TIME ZONE 'America/New_York' >= '<live_cutover_date>'
ORDER BY created_at;

-- Daily state evolution
SELECT s.snapshot_date, s.equity, st.state, st.last_drawdown_pct
FROM mi_account_equity_snapshots s
LEFT JOIN mi_safeguard_state st
  ON st.account_mode = s.account_mode AND st.safeguard='drawdown_breaker'
WHERE s.account_mode = 'live'
ORDER BY s.snapshot_date DESC;
```

**Acceptance gates**:
- Trip rate ≤ ~1× per quarter equivalent
- Zero `drawdown_check_unavailable` clusters (Alpaca API reliability concern)
- ≥1 `drawdown_breaker_released` observed (proves recovery path works)

**Flip steps**:
1. Set `DRAWDOWN_BREAKER_PHASE=active` (env var, restart container).
2. ~~Mark `CIRCUIT_BREAKER_CONSEC_LOSSES` / `CIRCUIT_BREAKER_COOLDOWN_DAYS` deprecated.~~ **CANCELLED — operator-ruled 2026-07-31: the count-based breaker is KEPT.**
3. ~~Remove the count-based block from `_check_safeguards` after 30 days of clean drawdown-active operation.~~ **CANCELLED, same ruling.** The two breakers now run TOGETHER: count-based (hard block on a 10-loss streak) + tiered drawdown (sizes down, then blocks on equity drawdown). Removing either needs a fresh operator sign-off.
4. Update this file's change log: shadow → active, evidence link to validation queries.

## Kill / scale criteria — live-money evaluation bands (✅ SIGNED by operator 2026-06-12 — #268b)

**Purpose**: pre-committed, evidence-derived bands that decide when live trading is
killed, reduced, or scaled — agreed BEFORE real money, so a drawdown never sets
policy emotionally. These are **operator decision triggers** (evaluated in the
Sunday weekly digest + on demand), NOT new mechanical blocks — the mechanical
guards remain the daily-loss limit (2%) and the tiered drawdown breaker.

**Calibration source**: #268 Phase B 12-month selection replay, judge-HIGH cohort
(n=399 simulated trades, 2025-06-09→2026-05-04; `docs/analysis/selection_replay_268_phaseB.md`).
The healthy-year fingerprint these bands are set OUTSIDE of:

- expectancy **+0.95R/trade**, win rate 30%
- max R-drawdown **−24.1R**, worst losing streak **15**
- trailing-20-trade expectancy: p5 = **−0.63R**, minimum = **−1.03R**,
  **25% of all trailing-20 windows negative**
- monthly expectancy range −0.64R to +2.71R (4 of 12 months negative)
- R distribution: 62% full −1R stops; the edge lives in the 13% of trades ≥ +3R

**Design principle**: a kill rule must not fire on the normal variance of a
healthy year. A profitable year of this strategy CONTAINS a 15-loss streak, a
−24R drawdown, and whole quarters of negative trailing-20 windows. Each
threshold below sits beyond the worst value the +0.95R year produced.

| Band | Trigger (live closed trades) | Pre-committed action |
|---|---|---|
| **SCALE UP** | ≥ 40 live trades AND trailing-40 expectancy ≥ +0.5R AND equity above starting equity | Raise risk/trade one notch (0.25% → 0.5% → 0.75%), operator confirm at each notch |
| **HOLD** | anything between the bands | No change |
| **REDUCE** | trailing-20 expectancy ≤ −0.70R (below healthy p5 −0.63) OR losing streak ≥ 16 (exceeds worst observed 15) | Halve risk/trade until trailing-20 expectancy ≥ 0 |
| **KILL → paper** | trailing-20 expectancy ≤ −1.05R (worse than the worst healthy window −1.03) OR cumulative live R ≤ −30R (beyond the −24R healthy maxDD) OR drawdown breaker BLOCK tier (−12% equity) | Stop live entries; revert to paper; full postmortem + operator re-arm decision required |

**Floor**: no expectancy-based REDUCE/KILL before **20 live closed trades**
(sample-size floor) — until it clears, only the equity-based guards
(daily-loss, drawdown breaker) bind, and they bind from day 1. A distinct-
entry-day independence floor was proposed and measured alongside this floor
2026-08-09, then REMOVED before shipping — see change-log entry below for
why (it was never calibrated, and the correlation problem it targeted does
not hold on this system's own data).

**Open-book reporting (2026-08-09, informational — see change-log below)**: every
band message also states current open-position count and days held, alongside
the closed-trade stats — so a REDUCE/KILL landing while a runner is still open
reads as a visibly partial picture. This is REPORT ONLY: open positions never
enter the score, trigger, or threshold above (ruled out on evidence: 4 of 6
live Bull trades touched ≥+1R and every one closed red; FIGS peaked past +2R
and closed −$7 — a band that reads unrealized gains would relax exactly when
the give-back problem is worst). Precisely: the closed-cohort triggers
(trailing-20/-40 expectancy, losing streak, cumulative R) cannot see the open
book at all. The pre-existing SCALE UP equity condition ("equity above
starting equity", `mi_account_equity_snapshots`) is unchanged by this — it was
already, by design, marked to market and therefore already reflects open
positions; that is a signed 2026-06-12 input, not something this change added
or touched.

**Coherence note**: at 0.5% risk/trade, the healthy-year −24R maxDD ≈ −12%
equity — the R-based kill band and the existing BLOCK tier converge at that
risk level. At the likely 0.25% cutover sizing, the R-bands bind first: R-bands
measure **strategy health**, equity bands measure **account health**. Both on
purpose.

**Caveats carried from the calibration**: the replay cohort is the historical
scan's view of the year (~47% recall of live alerts, IEX 1-min-ORB entry
geometry, Lane-2 narratives dark before 2026-06). These bands are an initial
calibration — re-derived quarterly via the P6 replay-regression job as live
data accrues, through this change process.

**Standing review (operator condition #1 at sign-off)** — three explicit layers:

1. **Weekly EVALUATION (mechanical)**: the Sunday weekly digest computes the
   live cohort's trailing-20/-40 expectancy, current losing streak, and
   cumulative R, compares them against the band thresholds, and prints the
   verdict line (SCALE/HOLD/REDUCE/KILL + the numbers). **Band TRANSITIONS
   additionally Telegram immediately** at trade-close evaluation (operator
   requirement 2026-06-12: every band hit surfaces as an alert, not just in
   the Sunday summary; transition-only, deduped — same pattern as the
   drawdown-tier alerts). ✅ **IMPLEMENTED #275 (2026-06-19)**: weekly-digest
   verdict section (`system_review`) + a daily **16:13 ET** EOD evaluation
   (`kill_scale_band_eval` job → `kill_scale_bands.run_band_evaluation`) that
   Telegrams on a band TRANSITION (deduped via `mi_safeguard_state`;
   daily-resolution mirrors the drawdown-tier alert — the band inputs only
   refresh at the 16:12 equity snapshot, so per-trade granularity would read
   stale equity). On-demand: `scripts/evaluate_kill_scale_bands.py`. Evaluator =
   `kill_scale_bands.evaluate_kill_scale_bands` (12 boundary tests pin the bands
   OUTSIDE the healthy envelope). Meaningful once live trades accrue post-6/22
   (pre-launch: HOLD below the 20-trade floor; ∅→HOLD baseline is not alerted).
2. **Quarterly REVIEW of the bands themselves**: registered as
   `data_gated_reviews.yaml::kill_scale_bands_quarterly_review` — auto-surfaces
   in the Sunday review when due, **first due 2026-08-01**, recurring quarterly
   (rides the same session as the model-selection quarterly review; sweep
   cadence Feb/May/Aug/Nov 1). Inputs: live R-distribution vs the calibration
   envelope, P6 divergence, the override log, the demote-side watch-metric.
3. **Event-driven**: a P6 replay-regression report showing the accruing
   distribution diverging from the calibration envelope pulls the review
   forward — don't wait for the quarter boundary. ✅ **IMPLEMENTED #302 v0
   (2026-06-19)**: `replay_regression.py` surfaces the accruing LIVE R-dist
   beside the `CALIBRATION_ENVELOPE` (#268b, now a single code constant in
   `kill_scale_bands.py`) as a SECTION of the Sunday weekly review + persists a
   `replay_regression_snapshot` audit row each week (the quarterly review's
   input (b) history); on-demand `scripts/replay_regression.py`. SURFACES only
   — **no automated divergence verdict** (comparing a small live cohort to the
   full-year n=399 envelope dimension-by-dimension is statistically invalid;
   path stats maxDD/streak can't be reached for months, per-trade expectancy is
   noise at low N — the operator judges divergence at the quarterly review).
   LIVE-only (paper's R-dist is the IEX selection artifact).

A band change from any layer requires its own change-log entry here; the bands
are never silently re-tuned.

**Operator override (operator condition #2 at sign-off)**: the operator retains
explicit authority to override any band outcome in either direction — trade
through a REDUCE/KILL trigger, or kill/de-size before a trigger fires.

*Mechanism (today, procedural)*: the operator states the override in any
operator channel (Telegram to Apollo, or a dev session) — e.g. "override
kill/scale: continue at full size, reason: ...". Apollo then (a) writes a
`kill_scale_override` row to `mi_audit_log` with direction + rationale, and
(b) adds a change-log entry here. Nothing mechanical needs bypassing — the
bands are decision triggers, not code blocks.

*Mechanism (#275 SHIPPED 2026-06-19)*: the digest + transition-alert band
evaluation reads active `kill_scale_override` rows (cleared-aware via a later
`kill_scale_override_cleared`) and annotates its verdict line ("… — operator
OVERRIDE ACTIVE since <date>: <reason>") instead of re-prompting every week.
Write surface: `scripts/set_kill_scale_override.py set "<direction>" "<reason>"`
(or `clear`); or tell Apollo "override kill/scale: …" and it calls
`record_override`. STILL add a change-log entry here when you set one.

*Scope limit*: this override covers the BANDS only. The mechanical guards —
2% daily-loss limit and the tiered drawdown breaker (including its −12% BLOCK
tier) — are NOT overridable through this clause; changing those is its own
CHANGE_PROCESS with its own evidence bar. (If a KILL is triggered solely by
the BLOCK tier, the breaker still blocks entries mechanically regardless of a
band override.)

Every override is reviewable at the quarterly review — repeated overrides in
one direction mean the bands are mis-set and should be recalibrated, not
overridden again. Pre-commitment is preserved by making overrides visible,
not impossible.

## Change log (newest first)

### 2026-08-08 — Partial-exit circuit breaker is now PER ACCOUNT MODE (#525, operator-signed)

**A PAPER success was closing the LIVE breaker.** `_consecutive_partial_exit_failures` counted
failures since the last `partial_exit_committed` with **no `account_mode` filter anywhere in the
query**, so a simulated success switched off a real safety stop.

**Measured on prod before the fix — the reason this was urgent rather than theoretical:**

| | successes that reset the breaker | recorded genuine failures |
|---|---|---|
| paper | **12** | **5** |
| live | 2 | 0 |

Twelve of the fourteen resets this breaker had ever seen came from the paper book.

**Classification: BUG FIX, not a criteria change.** Invariant 3 of the dual-account safety
backbone is *"`account_mode` filter on every trade query"* (`docs/architecture/dual_account.md`).
This query simply violated a rule already signed; the threshold (3), the window, and the
success-aware semantics are all unchanged.

**Attribution was the hard part.** `mi_audit_log` has no `account_mode` column and these rows
never wrote one. Mode is now resolved from an `account_mode` key written into `detail` from this
commit onward, falling back to a `trade_id` → `mi_live_trades.account_mode` join for every
historical row — so the fix works retroactively, not only for new rows. Both use regex extraction
rather than `detail::json`, because prod already contains rows with malformed/truncated detail and
a JSON cast would raise — a safety device that errors is a safety device that is off.

**Deliberate asymmetries, each chosen in the fail-safe direction:**
- A **success** closes the breaker only for **its own mode**.
- An operator **`partial_exit_breaker_reset` still clears BOTH** — it is a deliberate, audited
  action naming the fault it clears, and it should clear it everywhere.
- An **unattributable failure COUNTS** for the mode being asked about; an **unattributable success
  closes NOTHING**. Over-counting delays trading; under-counting removes a stop.

**Verified against prod before deploy:** under the new logic both books read **0** failures
(threshold 3), so nothing trips on deployment. The breaker check runs before the trade row is
loaded, so the mode is resolved by its own one-field lookup rather than moving the breaker later.

Tests: `tests/test_partial_breaker_per_mode_525.py` (8), mutation-checked against a mode-blind
success anchor, unfiltered failures, and dropping the mode from the success row.


### 2026-08-05 — `circuit_breaker`: a REALIZED PARTIAL now counts as an outcome (operator-signed)

**Change**: the streak query reads closed trades **UNION realized partial exits on still-open
trades**. `CIRCUIT_BREAKER_CONSEC_LOSSES` (10) and `CIRCUIT_BREAKER_COOLDOWN_DAYS` (1) are
UNCHANGED, and the rule is still "are the last N outcomes ALL losses". This changes WHAT COUNTS as
an outcome, not the threshold or the pause.

**Trigger**: 2026-08-05 — five HIGH alerts (APPS, KTOS, KODK, TATT, KMT) all `block:circuit_breaker`,
cooldown to 15:50 ET, armed by BLZE closing −$36.79 at 15:50 the previous day. Second occurrence in
six days (2026-07-31 blocked six).

**Operator's reasoning** (2026-08-05): *"winners tend to be held longer, so in case of PLTR we're
holding, if it continues to do well, we'll continue to hold, though we took partial profit today, so
this circuit breaker will remain basically for a long time"* and *"what we need to prevent is
perpetual blockers otherwise we'll never trade."*

**The bias, measured.** The streak read CLOSED trades only. Losers close fast — all 14 live losses
closed within ~a day — while winners are HELD by design. So the only event that could break the
streak was a winner CLOSING, the very thing the methodology delays. **14 closed live trades, ZERO
winners**: that escape has never once been able to fire. This is the *methodology-blind* property the
2026-07-31 ruling ACCEPTED; it is now answered rather than accepted.

**⚠ This invalidates the 2026-07-31 ruling's stated premise** (CHANGE_PROCESS r3). That entry kept
the breaker partly because the drawdown breaker "has never acted" on live money. The count-based
breaker had not acted either at that time — it has now blocked **11 entries across two days**
(6 on 07-31, 5 on 08-05). The keep-ruling stands; its "never acted" framing does not.

**Evidence (r1, N=14 ≥ 10)** — `scripts/probes/_535_breaker_replay.py`, read-only, $0:

| loss-expiry window | unblocks 2026-08-05? | still trips on the real 14-loss streak? |
|---|---|---|
| none (shipped behaviour) | no | yes |
| 21 days | no | yes — peaks at 11 |
| **14 days** | yes | **NO — peaks at 8, never trips** |
| 10 days | yes | **NO — peaks at 6** |
| 7 days | yes | **NO — peaks at 6** |

**So loss-expiry was REJECTED**: every window that would have unblocked today also leaves the breaker
unable to fire on the exact bleed it exists for, because those losses arrived ~1 per 2 days and would
expire faster than they accumulate. That is disarming the safeguard, not modernising it. The operator
proposed expiry and the replay ruled it out — recorded here so it is not re-proposed without new data.

**Partials-count, by contrast, is surgical**: threshold untouched, nothing disarmed, and today's
$33.27 (PLTR 307, 2 sh @ $165.69, 09:45 ET — the FIRST realized profit on live money) breaks the
streak from 09:45 onward. Verified against prod: that row now sorts above BLZE's loss, so the last 10
outcomes are no longer all losses.

**Not counted: UNREALIZED gains.** 5 of 12 live trades reached +1R or better and ALL FIVE finished
losers (#503); "currently up" is near-uninformative here and counting it would disarm the breaker
during exactly the round-tripping it should catch. The +2R trigger converts held winners into
realized profit anyway, so partials capture most of the intent without the round-trip risk.

**Honest limitation**: one partial closes the breaker. That is a low bar and deliberately matches the
existing semantics (any win breaks the streak). If it later proves too easy, the fix is a size or
count qualifier on the partial — an operator threshold, not a mechanism change. And if the trade
later closes red, that close enters as its own loss: nothing is erased in either direction.

**Reversion-flag**: REFINEMENT of the 2026-07-31 keep-ruling. Reversion = drop the UNION arm; the
threshold and cooldown never moved. Tests: `tests/test_circuit_breaker_partials_535.py` (7),
including one that fails if loss-expiry is ever added without re-running the replay.

**Per-mode isolation preserved**: both arms filter `account_mode`, so a paper partial can never clear
a live breaker.

### 2026-08-04 — A stop is now resting during EVERY minute of market hours (post-close refresh, 16:20 ET)

**Trigger**: operator, 2026-08-04 — *"do we have a stop always during market hours ... if not,
then it's all garbage."* The answer was **no, for the first five minutes of every session.**

**The hole, measured both ways in prod**: the entry bracket is submitted `TimeInForce.DAY`, so its
stop LEG expires at the 16:00 close. `morning_stop_refresh` re-placed it as a standalone GTC — but
at **09:35**. PLTR 307 on 2026-08-04: leg expired at 16:00, and the live account then reported zero
open orders with all 6 shares free. QBTS on 2026-07-28: refreshed 09:35, stopped out 09:36:24. So
every Day-2+ position traded 09:30-09:35 with no resting stop — the most volatile five minutes of
the day, and the ones an overnight gap resolves into.

**Change**: new job `post_close_stop_refresh` at **16:20 ET** (execution-owned) places the next
session's GTC stop the evening before, covering **same-day fills too**. `morning_stop_refresh` is
unchanged and stays as the backstop for a stop that dies overnight.

**Why 16:20 is safe where 09:35-same-day was not**: ADR 0029 D1 removed same-day fills from the
morning pass because at 09:35 their OTO child is LIVE and holding the shares, so re-placing raced
it (the WULF `insufficient qty available` self-conflict). After the close that child has already
expired — there is nothing to race. The asymmetry is deliberate and pinned by a test.

**Direction of change**: strictly MORE protection — it adds coverage, changes no stop PRICE, no
threshold, no sizing. Idempotent: a position whose stop is already resting is skipped (the #444
account-mode fix keeps that skip branch reachable). A position it cannot protect now Telegrams and
writes a `stop_refresh_failed` audit row instead of only logging.

**Residual gap**: 16:00-16:20 ET, and after-hours if a stop is placed but the venue will not act on
it outside regular hours. Accepted — the operator's condition is market hours.

**Tests**: `tests/test_stop_always_during_market_hours.py` (11).

### 2026-07-31 — Count-based `circuit_breaker` KEPT; its pre-committed removal CANCELLED (operator-ruled)

**Change**: none to behavior. The breaker's `DEPRECATED` marking and the removal steps it was queued
for are cancelled. `CIRCUIT_BREAKER_CONSEC_LOSSES` (10) and `CIRCUIT_BREAKER_COOLDOWN_DAYS` (1) are
UNCHANGED and `_check_safeguards` is untouched. Documentation-only.

**Operator ruling (2026-07-31)**: *"we should keep the circuit breaker."*

**What the prior decision actually was** — worth stating exactly, because "deprecated" reads as "off"
and it was neither off nor a plan to run without a breaker. The 2026-05-18 decision was to run ONE
breaker instead of two: retire the COUNT-based block and let the TIERED DRAWDOWN breaker carry the
job (WATCH → REDUCE 0.5× at −7% → BLOCK at −12%). Rationale: a strategy that cuts losers fast and
holds winners to a trailing stop produces loss streaks by construction, so counting closed trades
over-weights losses (*methodology-blind*), and the count-based cooldown re-arms itself when a loss
closes during it (*self-perpetuating*). Both criticisms remain TRUE — under this ruling they are
ACCEPTED, not answered.

**Why the prior reasoning no longer holds** (CHANGE_PROCESS r3). The removal was conditioned on
"after #7 promotes to active". #7 DID promote (2026-06-03) — but the 2026-07-30 effectiveness review
found it **UNPROVEN ON LIVE MONEY: it has never acted.** State is WATCH at −4.36% drawdown, and WATCH
is multiplier 1.0× — it sizes nothing down. REDUCE needs −7%, BLOCK −12%; neither has fired live, and
zero entries carry `block:drawdown_breaker` lifetime. The condition was met in NAME (a phase flag
flipped) and not in SUBSTANCE (nothing became protected). Executing the removal would have retired
the only BREAKER that has actually fired on real money in favour of one that has not, while the live
cohort is 0-for-9 (#503). ⚠ Precision: removal was never "no protection" — `daily_loss_limit` (−2%),
`max_concurrent_positions` (5) and the `/pause` manual halt are untouched by any of this. What was at
stake was the loss-STREAK block specifically.

**Accepted consequence, stated plainly so it is not a surprise later.** A loss streak can cancel whole
trading days, and the cancellation is arbitrary in timing: the cooldown expires at
`latest_loss_at + 24h` — the WALL-CLOCK time the last loss closed — so an expiry landing inside the
09:31–09:45 ORB submission window kills most of that day's entries, and an expiry after 09:45 kills
all of them.

**Evidence — the live day that prompted the ruling (2026-07-31, verified vs prod)**: six live-mode EP
alerts, ZERO entries, empty book. FLNC · COHU · NWL · FET all alerted at 09:31:00 ET and MPWR at
09:35:42, each blocked `block:circuit_breaker: cooldown until 2026-07-31T13:37:50Z`; BLZE (09:56:31)
missed the window entirely (`window:out_of_orb`). The cooldown traced to a SINGLE loss — FTNT closed
−$6.63 at 09:37:50 ET on 07-30 — which is the self-perpetuating property, observed live. Second
occurrence in a week (CORZ, 07-28). The trip itself was CORRECT, not spurious: ten consecutive losses
is a true reading of a real problem, and that problem is #503's subject.

**Not ruled here**: the cooldown's anchoring. The operator ruled on WHETHER to keep the breaker, not
on its timing mechanics. Any change to the anchor, the threshold, or the cooldown length is a separate
safeguard change needing its own sign-off + backtest.


### 2026-07-26 — Regime-keyed risk multiplier replaces VIX-scaled sizing + fail-open→fail-safe (#456 DoD(a), operator-ruled; SHIPPED BEHIND A FLAG, flag OFF — no live behavior change yet)

**Trigger**: operator ruling 2026-07-26 ("vix shouldn't be the thing that controls sizing, we have a full regime"), during a live Correcting stretch; the #450-premortem residual `vix=None` full-base-risk fail-open (`constants.py:35-36`, mislabeled "conservative" in a comment for over a year).

**Evidence**: `docs/analysis/456_regime_sizing_proposal_2026-07-26.md` — 43-trade closed cohort: Bull −0.35R (9/29 wins) vs non-Bull pooled −1.13R (1/14); traded-range VIX bands (15.0-22.2) don't separate outcomes (−0.52/−0.55/−0.62/−0.96R); candidate-pool 5d-positive rate monotone by regime (Bull 47.1% → Choppy 35.0% → Correcting 27.8% → Crisis 20%, n=2,567). N≥10 met for Bull (29) and pooled non-Bull (14); **Correcting (n=5) and Crisis (n=0) are STRUCTURAL PRIORS, not measurements — flagged as such per CHANGE_PROCESS rule 2, not evidence-backed at the same bar as Bull/Choppy.**

**Change**: `risk_pct = RISK_PCT × regime_risk_multiplier(label)` — Bull 1.0 / Choppy 0.75 / Correcting 0.5 / Crisis 0.25 / missing-stale-unrecognized 0.25 (stale = `regime_date` older than the last completed trading day before today). Removes `vix_scaled_risk_pct()` + the `qqq_ema_bullish` ×0.5 halve from all 3 sizing sites (order_manager.py ×2 real-money sites + the flag_detector.py HTF shadow). VIX now affects sizing only through the regime classifier (`regime.py`). Strategy × drawdown-tier composition (`entry_pipeline.py` post-spec_builder) is UNCHANGED — this change is upstream of it. New audit event `sizing_regime_fallback`. Full design in the "Position sizing — regime-keyed risk multiplier" section above.

**Feature flag**: `REGIME_SIZING_ENABLED` (env, default `false`). OFF = byte-identical to today (pinned numerically in `tests/test_regime_sizing.py` against the operator's own worked example: VIX 18.58 + bearish EMA → 0.4105× → $19.85/trade on $4,835 equity). ON = the mapping above. **This card ships the code with the flag OFF — flipping it live is a SEPARATE operator-signed action**, per CHANGE_PROCESS rule 5 (field-validate before live) — shadow-verify on paper ≥3 sessions including one label transition before flipping in the live account. Flip mechanics: `REGIME_SIZING_ENABLED=true` + `bash scripts/deploy.sh execution` (broker/ code — NOT the market-agent default scope).

**Anticipated effect once flipped**: in the CURRENT Correcting tape, risk/trade → 0.50× base (~$24 live) vs today's *effective* 0.41-0.48× (the VIX formula + the undocumented EMA halve) — a **+22% exposure increase at the sizing step**, already shown to and accepted by the operator (0.411x → 0.500x on $4,835 equity = $19.85 → $24.18/trade; note 28/43 historical trades were 20%-notional-capped, where risk_pct changes don't move shares proportionally — the delta is at the sizing-step level, not a uniform account-wide effect). Reasoning accepted: the 2% daily-loss limit and the tiered drawdown breaker are the backstop, not the per-trade risk_pct. On a Bull day: 1.0× vs today's ~0.85-0.95× (the VIX formula's permanent partial haircut disappears). On a missing/stale/unrecognized regime: 0.25× + a Telegram+audit fail-loud alert (today: 1.0×, silently, via the fail-open bug) — deduped once per ET day per `account_mode`.

**Reversion-flag**: REVERSAL of P19 (2026-05-14, `cc8f2e9`) VIX-scaled sizing + its None-fallback, and of the bearish-EMA halve it preserved. Why the prior was *wrong*, not just incomplete: (1) its None-fallback comment claimed "conservative" while returning FULL base risk — factually inverted, and it ran that way for every VIX-null day (277/365 pre-2026-03 regime rows had no VIX); (2) it keyed sizing on one classifier input whose traded dynamic range (VIX 15-22) left the formula effectively flat (0.64-0.98× band, never touching its own 0.25-0.5 floor half) while the composite regime label it ignored separated outcomes sharply on the SAME 43 trades (31% vs 7% win rate, Bull vs non-Bull); (3) it introduced a second, undocumented sizing axis (the `qqq_ema_bullish` halve) that appeared in no SSoT — the de-facto sizing policy was illegible even to this file. Rollback (either the flag OFF, which is instant and requires no code change, or a full revert): the three call sites restore `vix_scaled_risk_pct` + the halve; `constants.py` keeps `vix_scaled_risk_pct` in place (not deleted) so a flag-flip-back needs zero code change.

**Explicit revert triggers** (what would make us undo the LIVE flip, once flipped): (i) a regime-label outage class appears (repeated `sizing_regime_fallback` days) that the old VIX path would have sized normally through; (ii) 20+ further live/paper trades show Bull-labeled expectancy at or below non-Bull (the label loses its separation — the key is wrong); (iii) label flap produces operator-visible sizing incoherence (same setup, adjacent days, >2× size swing) that a follow-up hysteresis change can't cheaply fix; (iv) evidence the classifier's label lags a crash morning WORSE than yesterday's VIX did (the 2026 gap-day audit in the proposal §5 says the opposite today — 3 of 4 gap-≥1% mornings in the live-label window had a non-Bull label going in).

**Not shipped (operator forks, decided)**: (1) NO 9:31 SPY-gap guard — fires ~1×/13mo, not worth the complexity (operator). (2) Choppy set at 0.75× (map A), not 0.5× (map B) — B scores better on this thin sample but punishes the flappiest classifier boundary. (3) Ship-and-accrue on Correcting/Crisis rather than gating on a $0 backtest re-derivation first — **quarterly review 2026-08-01** (rides `kill_scale_bands_quarterly_review`) is the standing re-evaluation surface as the live cohort accrues.

**Known limitations carried forward** (see "Position sizing" section above for detail): staleness gate is weekend-only, no market-holiday calendar (~9 false-positive floor+alert mornings/yr, safe-direction); the fail-loud dedup has a bounded race under the ORB monitor's 5-way concurrency (a handful of duplicate Telegrams possible on the first fallback morning, never a sizing-correctness issue); the offline `backtester/engine.py` / `backtester/tracker.py` sizing copies are UNCHANGED (not one of the 3 identified sizing sites) and will diverge from live sizing if/when used for future regime-replay evidence work.

**Status**: SHIPPED 2026-07-26 flag OFF → **FLIPPED LIVE 2026-07-26 (operator: "flip it")**.

**⚠ CHANGE_PROCESS rule 5 DEVIATION — recorded, not skipped silently.** Rule 5 requires
"Field-validate before ship to live. Shadow phase or paper-only first," and the paragraph below
originally specified paper ≥3 sessions incl. one label transition. **That validation was not
achievable and the requirement was waived by the operator.** Measured 2026-07-26: there are **0
enabled strategies at `phase='paper'`** (`mi_strategies`: magna53=live, parabolic_short/shadow_orb_5m/
wick_fill=shadow, 9m_day2/fishhook_v3/flag_continuation=deprecated) and the last paper fill was
**2026-07-14**, 12 days prior. A paper-only flip would therefore have exercised nothing — it is a
no-op, not a validation, and waiting on it would have been waiting on an event that cannot occur.
An account_mode-gated two-stage flip (paper first, live second) was built and then reverted for
exactly this reason.

**Compensating controls the operator named when ruling** (2026-07-26, on being shown the +22%
risk/trade increase): the **2% daily-loss limit** and the **tiered drawdown breaker** — "we can adjust
and we have other protection if portfolio losses mount." Plus: the flip is instantly reversible with
no code change (`REGIME_SIZING_ENABLED=false` + redeploy), flag-OFF parity is numerically pinned by
test, and the first live exercise is a single ORB window that can be inspected before the next.

**Watch on first live use**: confirm an actual entry sizes at the regime multiplier (Correcting →
0.50× base), and that no `sizing_regime_fallback` alert fires — a fallback on a normal morning would
mean the staleness predicate is wrong in production despite passing the week-long date check. Tests: `tests/test_regime_sizing.py` (25 tests — pure-lookup table, flag-OFF numeric parity, all 4 regime levels fresh, staleness both directions incl. the weekend edge, unrecognized-label floor, fail-loud dedup incl. per-account_mode + next-day reset, both real sizing sites routing through the one shared resolver + threading the caller's `today` rather than an independent clock read, the HTF shadow site, and the briefing display line); full suite 3744 passed. `preflight_datetime_hygiene.py` + `preflight_no_silent_failures.py` both green (baseline unchanged). Advisor-reviewed pre-ship (caught + fixed the naive staleness predicate that would have floored+alerted every morning, and the `today`-threading gap); the fail-loud dedup SQL is untested against a real Postgres (mocked only, inherits `intraday_drawdown`'s precedent — see "Position sizing" section above) — flagged for the operator's call. Awaiting operator review of this SSoT + the flag name before any live flip; the flip itself requires its own shadow-verify (paper ≥3 sessions incl. one label transition) per CHANGE_PROCESS rule 5.

### 2026-07-24 — FL-2 daily-loss COVERAGE fix: realized losses attributed by CLOSE day, not `alert_date` (operator-signed; coverage-increasing; NO %-threshold change)

`_check_safeguards` daily-loss query: `WHERE alert_date = today` → `WHERE (closed_at AT TIME ZONE 'America/New_York')::date = today` (`live_tracker.py`). **Root cause:** the gate summed losses of trades *alerted* today, so a multi-day position (Day 2-5: SMA-trail / partial / time-stop) that stopped out **today** was invisible — its loss mis-attributed to the (prior) alert day. Correct when trades were same-day in/out; the gap opened silently when multi-day holds were added. **Unsafe direction** (under-counted today's realized losses → could allow new entries after a >2% day driven by held-position stop-outs; the drawdown breaker is EOD-cached at 16:12 + trips on −4%-from-peak, and #455 R4 is alert-only, so no intraday backstop covered this). **Correct-attribution** (each realized loss counted once, on the day it is realized): CLOSES the multi-day under-count hole (the safety win) **and** removes the old alert-day OVER-attribution — net more-*correct*, **not** uniformly tighter (some days count less: 5/21 old −$1505 → new −$643, since the position wasn't lost yet on its alert day). Cannot false-trip (every trip still maps to real realized losses ≥2%). **Backtest** (`mi_live_trades`, 40 closed trades / 28 loss-days): `closed_at` 100% populated (0 NULL); old vs new disagreed on **12/28** loss-days; days that read $0 under `alert_date` had real realized losses (6/24 −$1483, 5/26 −$862, 5/12 −$639); old also over-attributed on the alert day (6/22 −$1483 → correctly moves to the 6/24 close). Found in the FL-5 v1.0 doc reconcile; signed before the v1.0 declaration. **Reversion:** revert the WHERE clause to `alert_date = today` (single line). Pinned by `tests/test_daily_loss_close_day.py`.

### 2026-07-18 — #461: position-cap check→insert TOCTOU race closed (transactional cap check; NO cap-value change; operator-approved design)

**Trigger**: #461 (advisor-flagged during #436 fork B): `_check_safeguards` read the open-position count at entry STEP 2, but the trade row INSERT happened at STEP 6 — two separate, non-transactional DB round-trips with up to ~30 s of awaits between them (bar-fetch retry, fade guard, spec build). The ORB monitor deliberately runs up to 5 `submit_trade_entry` calls concurrently (`Semaphore(5)` + `gather`), plus overlapping bar-stream/cron triggers and the `EXECUTION_MODE=http` process split — so at cap−1, N concurrent candidates could ALL pass the check on the same stale count and ALL insert (worst alignment: cap+4). Design + concurrency proof (file:line-anchored): `docs/decisions/461_toctou_cap_design_2026-07-18.md`, **operator-approved 2026-07-18**.

**Evidence**: correctness fix to enforcement mechanics, not a threshold tune → no backtest applies (same class as #436). The race is proven by a race-reproduction test run against the PRE-fix code: 4 countable live rows + 3 concurrent entries past STEP 2 → **7 countable rows (cap+2)** pre-fix; **exactly 5** post-fix (`tests/test_461_cap_toctou_race.py`). Real-Postgres cross-connection serialization + commit-before-release + per-mode key isolation proven in `tests/test_461_cap_lock_real_pg.py` (APOLLO_TEST_DSN-gated, sibling of the #151 gate).

**Anticipated effect**: NONE on any uncontended morning (the lock is uncontended → no visible change; hold time = recount + insert + confirm ≈ single-digit ms, no external I/O inside the lock — the Alpaca submit stays post-commit). The ONLY observable difference: an entry that would previously have EXCEEDED the cap inside the race window now receives the byte-identical `block:max_positions: N/5 (mode=x)` skip (ledger `cap_blocked` mapping + #197 CAP+1 alert unchanged), plus a new observe-only `cap_recheck_blocked` audit event — a fired event in prod = a live race hit that the fix caught (this is the verify-live signal). Mechanics: STEP 2 stays the cheap early gate (full pipeline concurrency preserved — no re-creation of the TEAM 5/04 serial-stacking bug); STEP 6 wraps `pg_advisory_xact_lock(0x434150 "CAP", hashtext(account_mode))` → authoritative recount (per-mode + per-strategy #65, via the new shared `live_tracker.count_open_positions` helper — single SQL SoT with `_check_safeguards`, zero drift) → the existing INSERT → the auto-enter `status='confirmed'` flip, all in ONE transaction; the lock releases at commit so the next waiter's recount necessarily sees the row. Holds across coroutines, overlapping triggers, AND processes (the lock lives in Postgres — the #151 lesson). **Explicitly UNCHANGED (THE LINE)**: cap VALUE (5, and per-strategy caps from `mi_strategies`), counting vocabulary (`OPEN_POSITION_STATUSES`, #436 pending-confirmation exclusion), skip-reason vocabulary/formats, per-account-mode isolation (`hashtext('paper')` ≠ `hashtext('live')`; all counts mode-filtered), and the other safeguards (halt/daily-loss/breakers are NOT re-evaluated at insert time — deliberately out of scope, re-evaluating would change when they bind).

**Reversion-flag**: NEW (first concurrency-correctness change to this safeguard's enforcement; no prior decision reversed — the cap semantics are exactly what this file already specified).

**Status**: built 2026-07-18 on the #461 branch, pending operator diff review + deploy (`deploy.sh market-agent`). Tests: race-repro fails-pre-fix/passes-post-fix + per-strategy variant + duplicate-conflict no-lock-leak + paper⊥live isolation + #197 CAP+1 parity + #436 recheck-vocabulary pin (7 tests, `test_461_cap_toctou_race.py`); real-PG gate 3 tests (DSN-gated); full suite 3409 green. Verify-live: clean boot + preflight green, normal entries on the next multi-HIGH morning, and zero-or-explained `cap_recheck_blocked` events.

### 2026-07-11 — #436 fork B: exclude inert `pending_confirmation` proposals from the position cap (operator-signed)
**Change:** the "occupies a slot" vocabulary dropped `pending_confirmation` → `db.OPEN_POSITION_STATUSES = ('filled','order_placed','confirmed')`, applied at all four sites that share it (`get_open_position_count`, `live_tracker._check_safeguards` per-mode + per-strategy, `coverage_drift._fetch_open_db_trades`) via one shared constant so they cannot drift.
**Why (not just incomplete — the old count was wrong):** a staged-paper proposal (`phase='live'`, `live_real_enabled=False`) is **inert** — it holds no broker order and there is NO confirm path (buttons removed #364), so it can never become a position. Counting it as "open" let un-actioned proposals consume real cap slots. Evidence: the ABSI/FCEL/SNX/ACAD phantoms (6/24–6/26 ramp) ate 4/5 live slots and nearly blocked WULF on 7/6, and threw 32 `coverage_drift_detected` D3 events on 7/6. Root cause + full side-effect sweep: `docs/analysis/436_phantom_root_cause_2026-07-11.md`.
**Safety:** a real auto-entry flips `pending_confirmation → confirmed` in-process (microseconds), so it is counted the instant it becomes real — the cap is never under-counted for a genuine entry. The pre-existing (unrelated) check→insert TOCTOU race is unchanged by this and is tracked separately. No threshold changed (cap stays 5). Reversion: re-add `'pending_confirmation'` to `OPEN_POSITION_STATUSES`.
**Backtest:** N/A — this is a correctness fix to what counts as a position, not a threshold tune; the evidence is the phantom incident + the code proof that a proposal is un-submittable.

### 2026-06-20 — Live AUTO-ENTRY wired (real-money, operator-signed; START-SMALL launch)

**Trigger**: pre-launch hardening (6/20) found auto-entry for live was never wired —
`entry_pipeline.submit_trade_entry` auto-submitted only `account_mode='paper'`
(`if is_paper:`); every live entry fell through to a manual [Confirm] Telegram proposal
(5-min `CONFIRMATION_TIMEOUT_SEC` — constant removed 2026-07-03 with the #364 confirm-flow deletion; historical reference). That contradicted CLAUDE.md's dual-account table
(live + `live_real_enabled=True` → "real fills") and would have made Monday's
"real-money launch" silently require a manual tap per entry. Operator directed auto-entry
for the START-SMALL cutover ("with starting smaller $ we can just start with auto entry").

**Evidence**: operator decision + user-reviewed design (entry-mechanic, not a
threshold/detection change → no backtest applies). **Sizing/cap reasoned through with the
operator 2026-06-20**: START-SMALL = the **$5,000 account itself**, so
`position_size_multiplier=1.0` (full 1% risk/trade ≈ $50, often less under the 20% capital
cap) and **NO tight count cap** (`max_concurrent_positions=NULL` → shares global 5). A
low-WR (~25%) winner-driven strategy needs broad participation — a tight cap randomly
excludes potential winners (P(≥1 winner): 25%/44%/58% at 1/2/3 candidates) and **#197** is
our own evidence (the cap-blocked cohort beat the broad one: FTNT/FLNC/PCT). Risk is bounded
by per-trade size + the $5k account + 2% daily-loss + drawdown breaker, NOT by count;
worst correlated day ≈ (positions open) × 1% (rarely >3 fire in the ORB window) = small
absolute $ on $5k.

**Anticipated effect**: `_should_auto_enter(account_mode, live_real_enabled)` now gates the
funnel — paper → auto (unchanged); live + `live_real_enabled=True` → **AUTO-ENTER real
money** (NEW); live + `live_real_enabled=False` → staged-paper proposal (unchanged ramp).
Monday, MAGNA53 ORB entries auto-fire full-1% real money on the $5k account at ~9:31 with an
"AUTO-ENTERED" Telegram per fill instead of a manual proposal. ALL safeguards still gate it
(they run before the branch); `submit_entry` re-checks `/pause` (defense in depth). No
per-trade human gate remains — `/pause` + sizing + the $5k account + daily-loss are the
protections.

**Reversion-flag**: NEW (the live auto-entry path was previously unimplemented —
proposal-only). Rollback: `live_real_enabled=false` → back to the staged-paper proposal
(per-entry, no redeploy) · `/pause` · `phase=paper`.

**HARD-gate reaffirmation**: this makes `/pause` the ONLY per-trade kill for live (no
human-in-loop). The existing HARD gate stands and is now MORE load-bearing —
`live_real_enabled=TRUE` is not permitted until `/pause` (#345) is live + verified
(runbook step 5 verifies it before the first ORB window Monday).

**Status**: shipped (code) 2026-06-20 on main with `tests/test_entry_auto_enter.py` (4-case
truth table + live-requires-flag pin; full suite 1024 green). Advisor review pending
(overloaded) — operator-signed pre-deploy. Verify-live = first MAGNA53 auto-entry Monday
(AUTO-ENTERED Telegram + `per_strategy_sizing_applied` quarter-size + bracket has a stop leg).

### 2026-08-09 — Closed-trade cohort bias: entry-day floor PROPOSED then REMOVED; open-book reporting shipped

**Trigger**: operator observation — "winning trades take longer, e.g. I'd expect us to hold
PLTR for weeks if it really works out." Measured: paper winners hold 11.9d on average vs
0.5d for losers (live losers 0.1d), so the CLOSED cohort every strategy-health trigger reads
is loser-heavy by construction while winners are still open and uncounted — worst exactly
when a runner is developing. Full writeup:
`docs/analysis/kill_scale_band_closed_trade_bias_2026-08-09.md`.

**What shipped — open-book reporting only**: every band message states the open-position
count and days held alongside the closed-trade stats — REPORT ONLY, verified by test that it
cannot move the verdict (a cohort with open "winners" by hold-time produces an identical
band/reasons/numbers to the same cohort with an empty open book). No SIGNED threshold
(`_KILL_T20`, `_KILL_CUM_R`, `_REDUCE_T20`, `_REDUCE_STREAK`, `_SCALE_T40`,
`_SCALE_MIN_TRADES`) changed. Verified against prod: today's verdict is HOLD before and after
(n=17 < 20 sample floor either way).

**What was proposed and then REMOVED — the distinct-entry-day independence floor**:
initially shipped alongside the open-book change (`_DAY_FLOOR = 12`, requiring 12 distinct
entry days before strategy-health bands could fire, even once the 20-trade sample floor was
met). Operator called it arbitrary. Re-measured before commit and the number did not hold up:

- **It was never calibrated.** 12 was set equal to the LIVE cohort's own distinct-day count
  on the day it was written (17 trades / 12 distinct entry days, 2026-08-09) — a floor set to
  today's value can never bind against today's cohort, only against a smaller future one that
  the trade floor would already be catching.
- **The independence problem it targeted does not reproduce.** Across the fuller paper
  closed-trade history (33 trades), only 7 distinct entry days have more than one trade, and
  4 of those 7 mix a winner and a loser on the same day — there is no consistent within-day
  correlation to correct for. (Live cannot test this at all: it has zero closed winners in
  its entire 17-trade cohort, so no live day can be mixed by construction — that is not
  evidence either way, just an untestable cohort.)
- **The arithmetic makes any such floor moot on its own.** Normal cadence here runs ~1.3–1.4
  trades per entry day (live 17 trades / 12 days = 1.42/day; paper 33 trades / 25 days =
  1.32/day). A 20-trade cohort therefore already spans ~14 days by the time the sample floor
  clears — any day floor set below ~14 is inert by construction, and 12 is below that line.

So the honest outcome was removal, not a re-calibrated second number. `_DAY_FLOOR`, the
`entry_dates`/`distinct_entry_days` plumbing, and the "not independent enough to band" branch
are gone from `kill_scale_bands.py`; the open-book reporting (open-position count + days
held) stays, unchanged and unaffected by the removal.

**Reversion-flag**: the entry-day floor is a same-day removal of a same-day addition — it was
never live in production and no prior decision is being reversed. The mark-open-positions-to-
market alternative (separately considered for the open-book question) was explicitly ruled
OUT (see analysis doc) — not a partial adoption of it.

**Status**: open-book reporting shipped `agents/market_intelligence/kill_scale_bands.py`,
operator-approved via the analysis doc. Entry-day floor proposed, measured, and removed
pre-commit — never deployed. 20 tests (`tests/test_kill_scale_bands.py`), full suite green
(4880 passed, 7 skipped).

### 2026-06-19 — Manual real-money trading halt `/pause` added (#345, operator-requested)
New highest-priority runtime safeguard `manual_trading_halt` (`BLOCK_TRADING_PAUSED`):
a one-command operator kill switch for ALL new real-money entries. Motivation: the
only prior controls were per-strategy `/strategy disable` and the boot-read
`LIVE_TRADING_ENABLED` env (restart-gated, too slow). DB-backed
(`mi_safeguard_state`, mirrors the holistic-judge toggle), read per-entry in
`_check_safeguards` → instant, no redeploy. `/pause` halts, `/resume` lifts; both
read the state back and report the ACTUAL stored value. FAIL-SAFE: an unreadable flag
blocks the live path under a DISTINCT `INFRA_HALT_STATE_UNREADABLE` reason (consistent
with the sibling account-fetch read, which also fails closed). Scope: LIVE account
only (paper/shadow telemetry unaffected); blocks NEW entries, does NOT flatten open
positions (they keep resting broker stops). Advisor-reviewed (fail-direction,
read-back, exact-match routing to avoid the #260 cascade swallow, deploy
execution-first). 8 tests (`tests/test_trading_pause.py`). **HARD launch gate:
`live_real_enabled=TRUE` not permitted until this is live + verified.**

### 2026-06-12 — Kill/scale criteria bands SIGNED (#268b)

**Trigger**: launch runway DoD-1 (`docs/roadmap/launch-2026-06-22.md`) requires
kill/scale criteria SIGNED into this file before the 6/22 GO/NO-GO. Operator
standing decision 2026-06-11 ("#1 we wait — kill/scale until Phase B data");
Phase B completed 2026-06-12 05:43 UTC — the data arrived.

**Evidence**: #268 Phase B replay — 1,307 candidates graded+judged, 953
simulated, 12-month window. Healthy-year envelope quantified above (the bands
are set strictly outside it). Single 12-month pass, no error bars; recall and
geometry caveats documented in the section + analysis doc.

**Anticipated effect**: NONE in code — doc-only decision rules. Weekly
evaluation surface = Sunday digest. On sign-off, the heading flips DRAFT →
SIGNED and the bands become citable for the 6/22 GO/NO-GO evidence pack.

**Reversion-flag**: NEW (first kill/scale policy; no prior decision reversed).

**Status**: **SIGNED by operator 2026-06-12** (morning review, in-IDE read)
with two conditions, both incorporated into the section above: (1) standing
review — bands evaluated at every quarterly rule review + re-derived on P6
replay-regression divergence, never silently re-tuned; (2) explicit operator
override authority in either direction, always logged (change-log + audit row).
The bands are now citable for the 6/22 GO/NO-GO evidence pack. Closes #268.

---

### 2026-06-06 — #197 cap+1 game_changer slot SHADOW shipped; #198 closed obsolete

**Trigger**: should've-entered review (#196/#219) — game_changer/HIGH setups blocked
by the flat `max_concurrent_positions` cap (5) that went on to run (FTNT +16%, FLNC
+43% MFE, PCT +38%). Operator decision 2026-06-06 after reviewing the evidence cohort.

**Evidence** (read-only `scripts/shadow_cap_plus_one_197.py` / `mi_ep_missed_outcomes`
#199, all-history): the safeguard-blocked cohorts beat the broad HIGH cohort —
`cap_blocked` N=13 (+3.3% avg 5d / 50% win / +13.5% MFE) and `breaker_blocked` N=9
(+6.4% / 67% / +14.3%) vs `high_unentered` N=174 (−3.0% / 38%). The blocked cohort is
ALREADY 100% top-tier (it cleared every quality gate to reach the entry pipeline), so
the lever is a **slot policy**, not a quality filter. N=13/9 are at/below the N≥10 bar
(directional); cohort still ~50% losers (JMIA −20%) → sizing matters; first-order only.

**Anticipated effect**:
- **#197 — SHADOW only (no live behavior change).** Policy **(a): cap+1 for
  game_changer** — when a game_changer HIGH is `cap_blocked`, a cap+1 rule WOULD admit
  it in a 6th slot. Every `cap_blocked` decision is persisted permanently in the durable
  append-only ledger `mi_cap_plus_one_shadow` (written by `record_cap_plus_one_shadow`
  at the 5 PM refresh — telemetry-only, captures ALL qualities so a future
  game_changer→strong widen keeps full history; outcomes COALESCE-preserved after the
  source row rolls out of the 30d window). `scripts/shadow_cap_plus_one_197.py`
  (read-only; registered in the monthly backward-check sweep) reads the ledger and
  reports the policy-(a) cohort's forward outcome — a lossless record of bending the rule.
  **Promotion to a LIVE cap+1 is GATED**: N≥10 admitted-cohort (game_changer is rare + high-prior; operator 2026-06-06) + operator sign-off + a
  CHANGE_PROCESS change-log entry here. Until then `max_concurrent_positions` is
  unchanged at 5. (game_changer is narrow → slow accrual, by design.)
- **#198 — CLOSED as obsolete.** It proposed a conviction-override of the count-based
  `circuit_breaker`, which was then slated for removal — **that plan is CANCELLED (operator 2026-07-31, the breaker is KEPT)**, so
  #198's target still exists; it stays closed on its own merits below. The tiered breaker already solves #198's actual pain — it *sizes down*
  (REDUCE 0.5×) through normal-variance loss streaks instead of hard-blocking, so a
  great setup during a normal drawdown is admitted at reduced size, not killed. The
  only residual "override" target would be the −12% BLOCK catastrophic floor, and
  overriding *that* for one setup defeats the floor's purpose. No code change.

**Reversion-flag**: NEW (#197 shadow telemetry — no detection/safeguard logic changed,
observe-only). #198 closure is a scope decision, not a safeguard change.

**Status**: #197 shadow shipped 2026-06-06 (read-only, registered); promotion pending
N≥10 + sign-off. #198 closed 2026-06-06.

---


### 2026-06-04 — PDT lockout guard RETIRED (FINRA Rule 4210 / Alpaca intraday-margin framework)

**Trigger**: Alpaca operator email 2026-06-04 — "We have officially lifted the Pattern Day Trader rule and replaced it with the new intraday margin framework." FINRA retired the PDT rule; Alpaca confirmed the rollout on our account. This was exactly the gate recorded in memory `pdt_rule_4210_change_2026` ("confirm ALPACA's — not Fidelity's — rollout → relax `BLOCK_PDT_LOCKOUT_*` via CHANGE_PROCESS").

**Evidence**: regulatory change, broker-confirmed (not a backtest/threshold tune). Under the new framework: PDT designation gone regardless of day-trade count; the 4x-intraday-BP minimum equity drops $25K → $2K; the fields `pattern_day_trader`, `daytrade_count`, `last_daytrade_count`, `daytrading_buying_power`, `last_daytrading_buying_power` are deprecated — they return safe placeholders (`pattern_day_trader=false`, `daytrade_count=0`) now and are **removed from the API by 2026-07-06**. So the guard was already inert (can never fire on `false`/`0`) AND the prior direct `account.pattern_day_trader` read in `get_account()` would `AttributeError` after removal.

**Anticipated effect**: the PDT block (`BLOCK_PDT_LOCKOUT_ACTIVE` / `_IMMINENT`) + the `_emit_pdt_warning_once` headroom alert are removed from `live_tracker.py`; the guard never fires. No new Apollo-side day-trade gate replaces it — intraday-margin overextension is Alpaca's broker-side pre-trade check (rejects margin-deficit orders) + intraday margin calls. `/status`, `/account`, `/dryrun` drop the now-meaningless "Day-trades: 0/3" + "PDT flag" lines (buying_power stays, per Alpaca's field-migration guidance). `get_account()` no longer surfaces `pattern_day_trader`/`daytrade_count`. **Zero behavioral change on paper** (fields already 0/false); on live (post-6/22) no PDT throttle on a sub-$25K account.

**Reversion-flag**: REMOVAL of the PDT guard. NOT a reversal of a prior *decision* — the guard was correct for the pre-2026 regulatory regime; the regime itself changed. If a PDT-style rule were reinstated, re-add the guard against the (then-restored) fields. The `BLOCK_PDT_LOCKOUT_*` skip-reason constants + their `humanize()` labels are KEPT (not deleted) so historical `mi_live_trades` rows still render.

**Status**: shipped (code) 2026-06-04 as an **isolated commit**; **deploy HELD** to ride the #189 deploy after Track A's verifying scan — deploying earlier would `git pull` the held #189 grade change into prod (one-change-per-scan-cycle attribution). Hard removal deadline is 2026-07-06, ample margin. Verify on that deploy: clean boot + `/status` renders without PDT lines + a scan's `_check_safeguards` runs without the PDT block.

---

### 2026-06-03 — Promotion timing RESOLVED: arm BEFORE cutover (paper evidence sufficient)

**Trigger**: prepping #174 (the shadow→active flip), the SSoT-read surfaced a 3-way conflict — this file said ≥14d POST-cutover + paper-not-evidence; `data_gated_reviews.yaml::drawdown_breaker_promotion` recorded an advisor-2026-05-10 reversal (paper-OK + arm BEFORE cutover); the composite `live_cutover_decision` Step D said arm AT cutover. Unrankable from docs (this file was edited 5/18, after the claimed reversal, and still said post-cutover). Operator resolved as tie-breaker (participant in the 5/10 review).

**Evidence**: operator judgment 2026-06-03 — paper exists to validate the FULL system (incl the active-mode breaker) before real money. Plus paper shadow validated the full tier-machine: OK→WATCH→REDUCE (−8.95%, 5/22)→released→OK (5/29); multiple `*_released` events (recovery proven); one isolated `drawdown_check_unavailable` (5/19, not a cluster); 18 snapshots (5/08–6/02); trips justified (real −5 to −9% drawdowns).

**Anticipated effect**: breaker promotes shadow→active BEFORE the 6/22 cutover (on paper) so it's enforcing when real money goes live. Active phase will size-down (REDUCE 0.5×) / block (BLOCK 0×) paper entries during paper drawdowns — intended, and makes the Gate-3 paper cohort reflect the real (breaker-included) system. Currently OK (0% dd, peak $100,684 on 6/2) → no behavior change until the next drawdown.

**Reversion-flag**: REVERSAL of this file's "post-cutover / paper-not-evidence" Promotion-plan text (the pre-2026-05-10 plan). Why the prior was WRONG (not just incomplete): it would let real money trade the highest-risk learning-curve window with the safeguard DISARMED — defeating the safeguard's purpose exactly when most needed; and it treated paper as non-evidence when paper's whole purpose is to validate the full system (incl active-mode safeguards) pre-live. The 5/10 advisor review already reversed this; this file simply wasn't updated (stale SSoT).

**Status**: policy reconciled 2026-06-03. The env flip (`DRAWDOWN_BREAKER_PHASE=active`) was SHIPPED + VERIFIED 2026-06-03 (operator go): DRAWDOWN_BREAKER_PHASE=active added to prod .env, deploy.sh both GREEN (preflight exercised _check_safeguards with the active breaker + G6 replace-path validated live), confirmed container env=active, state=OK (no immediate behavior change), 4 open positions intact. Effectiveness tracked forward via data_gated_reviews::drawdown_breaker_active_effectiveness. Acceptance-gate readiness: 3/4 clearly met; trip-rate exceeds the literal "≤1×/quarter" but the trips were justified (real drawdowns) — operator confirms acceptability at flip-time.

---

### 2026-05-18 — Drawdown breaker: tiered redesign (OK/WATCH/REDUCE/BLOCK)

**Trigger**: User correctly flagged that the binary -5%/-2.5% breaker design was methodology-incompatible. For a 20-30% WR strategy, P(7 consecutive losses) = 13.3%, making a -7% drawdown statistically NORMAL variance. Hard-blocking on normal variance prevents the methodology from finding the winners that pay for losses. The whole strategy structurally cannot work under the original design.

**Evidence**: 2026-05-18 paper account state — peak $99,271 (5/08), current $93,255, drawdown -6.06% caused by CRMD/KLAR/CSCO/MRAM cumulative damage over 10 days. Under binary design: TRIPPED state, would have blocked entries for ~30 days waiting for peak to age out or equity to recover to -2.5% (= +$3,535 from current). Under tiered design: same drawdown lands in WATCH state (informational only, no sizing impact). The system continues to fish for winners that pay for losses.

**Anticipated effect**:
- Tier definitions: OK (1.0×), WATCH at -4% (1.0×, alert only), REDUCE at -7% (0.5×), BLOCK at -12% (0.0×).
- Trip-side: jump to deepest applicable tier in one snapshot.
- Release-side: step up one tier per evaluation, asymmetric hysteresis.
- Sizing composition: `final_shares = strategy_multiplier × drawdown_tier_multiplier × base_shares`. A 0.5× strategy × REDUCE (0.5×) = 0.25× during bleed weeks — methodology-correct conservative compounding. (Worked example was 9M Day 2, deleted 2026-08-02 / #515.)
- Audit events: tier-specific (`drawdown_watch_entered`, `drawdown_reduce_entered`, etc.) — no dual-emit since no production readers of legacy event names.

**Why tiered**:
- Daily loss limit (2%) is the same-day blow-up guard
- WATCH = telemetry tier (-4% to -7%): alerts but no trading change. Captures cumulative-bleed state for operator visibility.
- REDUCE = sizing tier (-7% to -12%): halves risk per trade. Strategy keeps fishing for winners but with reduced exposure. The methodology STILL operates.
- BLOCK = catastrophic tier (-12%+): rare; true emergency floor

**Reversion-flag**: REPLACEMENT of binary design (shipped 2026-05-08, #39). Legacy `DRAWDOWN_TRIP_PCT/RELEASE_PCT` constants kept as aliases for one cycle. Legacy `'TRIPPED'` state auto-migrates to REDUCE via `_next_state` + `get_tier_multiplier`. Rollback path: revert constants to binary values; ALLOWED_WRITERS unchanged; tiered code paths fall through to binary semantics via aliases.

**Promotion / live cutover impact**: this unblocks Gate 1 of live-cutover composite review. Under binary design, today's -6% would have blocked any live cutover for ~30 days. Under tiered: WATCH state, system trades normally at full size. Composite review can evaluate cleanly Friday.

**Status**: SHIPPED 2026-05-18. Live verification: today's -6.06% recomputes into WATCH state (informational); existing-position management unaffected; new entries (in shadow phase) continue at 1.0× sizing. Active-phase promotion still gated on 14d telemetry + acceptance gates.

---

### 2026-05-18 — Stop-ACK timeout watchdog: first real production catch (GOOGL #56)

**Field validation**: the stop-ACK timeout watchdog shipped 2026-05-17 (commit `8e8f6f3`) fired its first real case at 09:00:00 ET Monday 2026-05-18.

**Timeline** (UTC times in audit log → ET):
- 13:00:00 UTC (09:00 ET) — Watchdog scan detected GOOGL #56: `status='filled' AND filled_at NOT NULL AND stop_order_id IS NULL AND filled_at < NOW() - INTERVAL '30 seconds'`. Position had no broker stop entering Monday open.
- 13:00:00 UTC — `stop_ack_timeout_remediated` audit event. Fallback stop-market placed at `trade['orb_low']` = $379.43, order `b47256af-a252-4df9-865c-776e52fde847`.
- (Implicit) 09:35 ET — `morning_stop_refresh` ran. Read `trade["stop_price"]=$394.497` (the BE-level trailed stop from prior Day-2 management), called `update_stop()` to re-establish proper methodology stop above the conservative fallback.
- 20:45:00 UTC (16:45 ET) — Day-2 `update_open_positions_live` ran. `stop_update_started: $394.497 → $395.87` (slight SMA-trail bump). New stop `a16b3bbe-b105-4524-8800-bec219ad7cb6`.

**Why the stop_order_id was NULL Monday morning**: most likely Friday's DAY-TIF stop expired at 4:00 PM ET close (Alpaca DAY orders don't carry over weekends), and the weekend orphan-remediation didn't re-place — the normal 9:35 ET `morning_stop_refresh` would have re-established it, but for the 35 minutes between 9:00-9:35 ET the position would have been naked at broker. The 9:00 ET watchdog tick caught it.

**Concrete evidence**: position protected at $379.43 from 9:00 ET (well before market open at 9:30) instead of unprotected until 9:35 — 35 minutes of naked exposure eliminated. If GOOGL had gapped down hard at open, the methodology stop would have been re-established at the right level by 9:35 OR the fallback would have already stopped the position out. Either path is safe; no path leaves the position naked through market open.

**Operational outcome**: the watchdog did exactly what it was designed for. The MRAM-class silent-failure gate is now field-validated less than 48 hours after ship.

**Followup filed** (BACKLOG): investigate WHY GOOGL's stop_order_id went NULL between Friday close and Monday open — was it (a) Alpaca DAY TIF expiration as theorized, (b) weekend maintenance, or (c) some race with the 5:00 PM data-pull pipeline. Understanding the trigger informs whether to add a Friday-close stop-renewal job OR confirm the watchdog is sufficient on its own.

**Followup outcome (2026-05-18 investigation)**: Stops are placed via `place_stop_order` with `TimeInForce.GTC`, NOT DAY — so Friday close didn't expire d3b1850f. Audit log shows:
- Fri 16:45 ET: `stop_updated` placed d3b1850f at $394.50
- Fri 21:00 ET: `evening_position_backstop` ran sync_positions — quiet (stop ACTIVE)
- Sat/Sun: no scheduled jobs (mon-fri only)
- **14 container restarts** Sat 5:15 PM ET → Sun 12:11 PM ET (Track 1 deploy cycle)
- Mon 09:00 ET: watchdog catches stop_order_id NULL

Most-likely cause: during one of the Saturday restarts, Alpaca's WS dispatched a backlogged cancel/reject/expired event for d3b1850f. Pre-T1.5a (today), `trade_stream._handle_cancel_or_reject` nulled stop_order_id via inline `UPDATE mi_live_trades SET stop_order_id = NULL` WITHOUT any `log_audit_event` call — silent state mutation. That's why no audit trail.

**Going forward**: T1.5a's `set_stop_order_id` helper emits `stop_order_id_changed` audit event with `reason='cancel_or_reject_null'` for exactly this code path. If this recurs, full timeline will be in audit log.

**Verdict**: defense in depth sufficient. No additional code change needed.
1. Trigger (silent WS cancel during restart) — was silent pre-T1.5a, NOW audited
2. Watchdog catches NULL Monday 09:00 — already working
3. morning_stop_refresh re-establishes proper stop at 09:35 — already working

Closes the followup. Three-layer protection is in place.

---

### 2026-05-17 — Trade-state ownership refactor (T1.1/T1.2/T1.4) + Gate 5 G (column-write authority preflight)

**Trigger**: Five trade-state corruption bugs in May (CRMD/KLAR/ARM/BW/AIXI), same root cause every time — multiple writers to the same column with no ownership rule, last-write-wins by accident. Boot-time prepare validation (Gate 5 B, shipped 2026-05-14) catches type errors but not semantic-overwrite. Friday's Phase 1 audit (`docs/architecture/trade-state-ownership.md`) enumerated every writer per column + drafted ownership rules; today's Phase 2 work refactors three hot-path bug surfaces + ships the static-analysis gate.

**Three refactors shipped (commit chain T1.1 → T1.2 → T1.4):**

- **T1.1** — `trade_stream._process_entry_fill` no longer writes `stop_price` / `hard_stop`. Entry-fill is NOT the authorized writer; INSERT at `entry_pipeline._skip` sets the initial value, `update_stop()` owns trail. KLAR/ARM bug root cause. Cuts stop_price writers 7 → 4. Param count 6 → 5.

- **T1.2** — `live_tracker.update_open_positions_live` partial-fired branch no longer writes `stop_price`. `update_stop()` at the same call site is the authorized writer. When `update_stop()` failed (returning False + nulling stop_order_id per naked-position protocol), the wrapping write previously falsely reported a stop_price the broker no longer held. Cuts stop_price writers 4 → 3. Param count 4 → 3.

- **T1.4** — `live_tracker.update_open_positions_live` no-partial branch no longer writes `stop_price` / `total_pnl` / `partial_taken` / `remaining_shares`. Beyond the stop_price reason: in this branch `step.new_X == state[X]` (no change when no partial fires), so the "idempotent no-op write" was actually a LOST UPDATE hazard if a WS fill arrived concurrently between state-load and UPDATE. Cuts stop_price writers 3 → 2 effective (live_tracker close path at line 537 still writes NULL — T1.3 future-work). Param count 8 → 4.

**Gate 5 G ship (T1.5):**

`scripts/audit_column_writes.py check` mode + `ALLOWED_WRITERS` dict + `deploy.sh` step `[5c/5]` wire. Walks every UPDATE / INSERT site touching `mi_live_trades`, builds `(column, module.function)` pairs, fails the deploy on any pair not in `ALLOWED_WRITERS`. Output names the violation, the file/line, the function, the existing allowed set, and the two fix paths (add to allow-list OR refactor to authorized writer).

**Verification protocol passed**:
1. `check` mode on clean tree → OK, 47 sites verified clean.
2. Synthetic test: injected a `rogue_writer` function writing `stop_price` from `fake_violator.py` → check correctly flagged the violation + named the four legitimate writers. Test passed.

**Promotion**: Active on every deploy via `scripts/deploy.sh` step `[5c/5]`. Exit code 6 reserved for column-write authority failures.

**Friction by design**: adding a new writer requires updating `ALLOWED_WRITERS` in the same commit. Explicit ack of new co-ownership.

**Limitations** (per script docstring): regex-based parsing handles multiline UPDATEs but would miss dynamic SQL string-concat (none currently exist). Doesn't catch raw `conn.execute` with template strings. Acceptable for current codebase pattern.

**Future-work follow-ups filed**:
- T1.3 — `live_tracker.update_open_positions_live` close path (line 537) delegates to `finalize_full_exit` / `finalize_stop_fill`. Deferred today per drop priority (complex — WS-vs-fallback ownership for Alpaca-confirms-gone case).
- T1.5a — `set_stop_order_id` helper consolidates 12 solo writes into one authorized writer. Allow-list tightening (cosmetic per advisor 2026-05-17); not safety.

**Reversion-flag**: NEW for Gate 5 G. REFINEMENTs of 2026-05-14 KLAR/ARM fix (d6fa74c) and 2026-05-14 BW fix (c0fa67f) for T1.1/T1.2/T1.4 — the inline COALESCE / `partial_fired` skips remain as belt-and-suspenders; refactors remove the SECOND-WRITE pattern at source.

**Status**: shipped 2026-05-17. Closes Gate 5 G live-cutover blocker. Composite `live_cutover_decision` review evaluation continues per schedule (2026-05-22 earliest).

---

### 2026-05-17 — Stop-ACK timeout watchdog (silent-failure gate, sibling of Gate 5 A)

**Trigger**: Weekly review 2026-05-17 proposed a 30-sec stop-ACK timeout gate to close the gap that Gate 5 A doesn't cover. Gate 5 A (naked-position remediation, shipped 2026-05-14 from CRMD postmortem) handles the EXCEPTION case (entry-fill UPDATE raises). The silent case — entry UPDATE succeeds cleanly, but OTO bracket child stop-leg never ACKs from Alpaca OR its acceptance event is missed by WS handler — was not covered by any gate. This entry closes that gap.

**Note (2026-05-18 correction)**: the weekly review framed MRAM #120 (2026-05-11) as the trigger incident citing "phantom double-exit" with stop_order_id persisting NULL. That framing was incorrect — broker order history (`mi_live_orders` for trade_id=120) shows MRAM had stop `b59f5633` placed cleanly + filled, plus a legitimate Day-1 re-entry (entry #2 `f7d0cad4` filled at 13:50). The -$2,199 was real damage from two real stop-outs on a re-entered trade, not phantom. See BACKLOG entry 2026-05-18 + commit `de01238` for the revert. The watchdog's design rationale (silent vs exception class) stands; the specific MRAM justification was wrong.

**Evidence (revised)**: the field-validation evidence is today's GOOGL #56 catch (2026-05-18 09:00 ET). GOOGL had its broker stop silently nulled some time between Friday 4:45 PM ET (last `stop_updated` audit event) and Monday 9:00 AM ET (watchdog firing). Most likely cause: WS cancel/reject event for stop `d3b1850f` during Saturday's 14 Track 1 container restarts. Pre-T1.5a `_handle_cancel_or_reject` nulled stop_order_id without audit logging — silent state mutation. Watchdog detected the NULL state at 9:00 ET, placed fallback at orb_low ($379.43). morning_stop_refresh re-established proper trail at 9:35 ET. Position never naked through market open.

**Anticipated effect**: new scheduler job `_stop_ack_timeout_watchdog_job` runs every 30s during market hours (9:00-15:30 ET, mon-fri). Predicate: `status='filled' AND filled_at IS NOT NULL AND stop_order_id IS NULL AND filled_at < NOW() - INTERVAL '30 seconds'`. On detection: submits fallback stop-market at `trade['orb_low']` (matches Gate 5 A pattern), UPDATEs `mi_live_trades.stop_order_id` with fallback order ID, emits `stop_ack_timeout_remediated` audit event, sends "🛡 STOP-ACK TIMEOUT — REMEDIATED" Telegram. On fallback failure: escalates to CRITICAL with `stop_ack_remediation_failed` + double-burst Telegram. Dedup: one remediation attempt per (trade_id, day).

**Why "fallback stop" not "flatten"** (deviation from weekly review proposal): Gate 5 A precedent submits fallback stop, not flatten. The fallback approach is recoverable if real ACK arrives later (race with cancel). Flatten on transient ACK delay loses the trade entirely. Acceptable risk: position naked for 30-60s window (between fill and watchdog detection). Trade-off accepted because the alternative (flatten on every 30-sec-delayed ACK) would surface false-positives on normal Alpaca latency.

**Env flag**: `STOP_ACK_TIMEOUT_GATE_ENABLED=true` (default). Set false + docker compose restart to revert.

**Reversion-flag**: NEW. Sibling of Gate 5 D stuck-fill watchdog (which only catches `status='filling'` cases, not `status='filled' + stop_order_id NULL`).

**Status**: shipped 2026-05-17. **Field-validated 2026-05-18** by GOOGL #56 catch (see safeguards.md change log entry above this one). Continue monitoring `stop_ack_timeout_remediated` audit events; non-zero count = a real silent-failure case the gate caught.

---

### 2026-05-08 — Initial shadow ship

**Trigger**: 5/8 morning ORB blocked by 5-consecutive-loss count breaker (BSX 4/23 → AMD 5/07 streak). User flagged the breaker as methodology-blind + self-perpetuating. Two structural flaws documented in `constants.py:37-43`: (1) cooldown anchored to `latest_loss_at + 24h`, advancing with each new loss closing during cooldown — only a closed winner breaks it, but during cooldown no new entries fire, so only existing open winners can resolve it; (2) Pradeep methodology holds winners for days/weeks while losers stop fast in minutes/hours, so the trailing-N closed-trade window structurally over-weights losers.

**Evidence**: One streak (4/24-5/07) directly observed. Plan agent + advisor reviewed two design iterations: per-call vs. daily state machine (state machine chosen for audit-flood + ordering + hot-path reasons); stateless threshold check vs. state-aware hysteresis (state-aware chosen to eliminate `-5.1%/-4.9%/-5.1%` flap scenario). Backtesting against historical losing streaks deferred — equity-at-time including unrealized cannot be reconstructed from `mi_live_trades.total_pnl` alone.

**Anticipated effect**: Shadow ship emits `drawdown_breaker_tripped` / `drawdown_breaker_released` audit events on state transitions only. Zero impact on trading behavior during shadow. Active flip (env var) blocks new entries when state='TRIPPED'. Methodology-aware (Alpaca equity includes unrealized → open winners lift equity, prevent false trips). Self-clearing on recovery to within 2.5%. Magnitude-sensitive (5 small losses don't trip; 1 big loss can).

**Reversion-flag**: NEW. Replaces the count-based breaker (#5 above) which stays in place threshold=10 as backup until the drawdown breaker promotes and bakes for 30 days.

**Status**: shadow shipped 2026-05-08. Promotion gated on ≥14d post-live-cutover (live cutover earliest ~5/12) telemetry + acceptance gates above.
