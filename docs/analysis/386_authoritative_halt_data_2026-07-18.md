# #386 — Authoritative trading-halt data vs the inferred RMV dead-data guard

**Date:** 2026-07-18 · **Status:** SHADOW BUILT (this branch) — live switch = operator decision
**Principle under test:** direct source beats inference. The guard is a detection/eligibility
criterion → any live change is THE LINE + CHANGE_PROCESS (operator signs; this doc only
measures).

**2026-09-12 UPDATE:** #386 (the design-audit task this doc was written under) is closed; the
live-path project is now tracked as **PLAN.md #488**. §7's S1 (entitlement probe) PASSED
2026-07-25 against SIP on a throwaway connection — operator-approved, see PLAN.md #488 for the
verdict. This build merged to main 2026-09-12 from branch `ba7533b` with `HALT_STATUS_CAPTURE_
ENABLED` still default OFF; S2 (flip the flag) remains an open operator decision. Everything
below is the ORIGINAL 2026-07-18 analysis, left as written.

---

## 1. The guard today (what would be replaced/augmented)

The RMV halt-floor — task card cites `03b95e5`; in this repo's history the halt-floor commit
is **`20c9c06`** ("#327/#54: RMV min-max → ratio-to-baseline (creator-confirmed) +
halt-floor") — lives in `agents/market_intelligence/flag_detector.py`:

- `_RMV_DEAD_NTR_FLOOR = 0.05` — flag_detector.py:402 (calibration comment 398-401: 0.05%
  sits under real ultra-tight coils PAYO 0.14% / NUVL 0.15%, above any genuinely halted
  3-bar stretch; Gemini-confirmed 2026-06-27).
- The branch — flag_detector.py:459-460 (inside `_compute_rmv`): if every recent-window
  (3-bar) NTR < floor → return **None** ("range-dead recent window (halt / frozen feed) — a
  void, not a coil"). None is deliberately NOT 0 — 0 would mint a phantom max-coil buy
  signal on dead data.
- **Data it reads:** DAILY bars from `mi_daily_closes` (Polygon grouped-daily ingest),
  fetched via `db.get_recent_daily_history` (db.py) in `run_flag_scan`
  (flag_detector.py:1004+). Granularity matters: the floor can only see **multi-day**
  deadness (T12-class regulatory halts, frozen feed, zero-tick zombies) — an intraday LULD
  pause leaves a real daily range and never trips it (see §5 expected-disagree classes).

**Who consumes the None verdict (detection/entry surfaces):**
1. `anticipation.is_entry_tight` (anticipation.py:897-905) — `rmv is None → False`: blocks
   the **#327 SHADOW consolidation-entry signal** (`ENTRY_RMV_MAX` gate, anticipation.py:860).
   Fail-safe direction: dead data can never *create* an entry.
2. `flag_detector` telemetry — rmv_5d/rmv_15d persisted NULL on `mi_flag_candidates`
   (flag_detector.py:973-974 on this branch; insert mapping :1711-1712). Not a stage gate
   (COILED uses range/vol/body tightness, not rmv).
3. `mi_structure_axis_shadow` (#330) — RMV-15 as structure component (db.py:1164 comment).

No **live-money** path reads RMV directly today (#327 entry-watch records, never submits) —
but the guard is still a detection criterion feeding operator-facing surfaces and the armed-
later #327 path, hence the shadow discipline.

## 2. Feed audit — who actually exposes an authoritative halt/LULD/T-status flag

### ✅ Alpaca — YES, via the market-data WebSocket `statuses` channel (the only real source in our stack)

Verified in the installed SDK (alpaca-py **0.43.2**, the version the container runs):

| What | Where (file:line, installed SDK) |
|---|---|
| `StockDataStream.subscribe_trading_statuses(handler, *symbols)` — "Subscribe to trading statuses (halts, resumes)"; `"*"` wildcard supported | `alpaca/data/live/stock.py:117-128` |
| `TradingStatus` model — symbol, timestamp, **status_code**, status_message, **reason_code** ("the tape-dependent code of the halt reason"), reason_message, tape | `alpaca/data/models/trades.py:82-101` |
| WS dispatch: message type `"s"` → `TradingStatus` | `alpaca/data/live/websocket.py:201, 251` |
| No REST equivalent — statuses exist ONLY on the stream (nothing in `alpaca/data/historical/stock.py`); capture must be real-time-accrued | grep-verified, 0 hits |

Weak REST sibling: `TradingClient` `Asset.status` (`active|inactive`) + `Asset.tradable`
(`alpaca/trading/models.py` Asset fields; `AssetStatus` enum = active/inactive only) —
**listing/tradability state, not a halt flag** (catches delistings/deficiencies, not T1/LUDP).
Recorded as a possible v1 enrichment, not the authority.

**Entitlement caveat (unverified until probed):** we run `ALPACA_DATA_FEED=iex` (free).
Alpaca documents the statuses channel on the standard stream endpoints, but whether OUR
iex-feed subscription carries it is an empirical question — and the SDK's failure mode for
an un-entitled channel is severe (§3). Hence the probe script + default-off flag.

### ❌ Polygon — nothing on our plan

`collector.py` endpoints in use: `/v2/aggs/grouped/...` (:201), `/v2/snapshot/locale/us/markets/stocks/tickers`
(:219, :898, :929), `/v3/reference/tickers` (:243, :274), `/v2/aggs/ticker/...` (:288, :311),
`/v2/reference/news` (:685). **None carries a halt/trading-status field** (grep `halt|luld|
trading_status` over collector.py: 0 hits; snapshot parsing `_extract_snapshot_price`
:875-883 reads lastTrade/day only). Polygon's LULD feed is a **WebSocket channel on the
Business tier** — we are on Starter (collector.py:8) with no Polygon WS in the codebase.
`/v3/reference/tickers` `active` = listing status only.

### ❌ FMP — nothing

`/stable/` endpoints in use: profile (:392), earnings (:416), income-statement (:129-164),
news (:476-483). No halt/status surface.

**Conclusion:** the authoritative flag = **Alpaca WS `statuses`**, and it must piggyback the
EXISTING stream — Alpaca allows one concurrent data-stream connection per account+feed, and
`bar_stream.py` (the real-money ORB entry trigger) owns it.

## 3. Two live-path risks found during design (why the capture defaults OFF)

1. **Un-entitled channel KILLS the shared stream.** `websocket.py::_run_forever` `return`s
   (terminates) on the "insufficient subscription" ValueError
   (`alpaca/data/live/websocket.py:352-356`). If iex lacks `statuses`, a blind subscribe
   would tear down the ORB bar stream → 3 retries → cron-fallback degradation of the
   real-money entry path. **Mitigation:** `scripts/probe_alpaca_statuses.py` proves the
   entitlement on a throwaway connection FIRST (run off-prod or while the prod stream is
   down); capture flag stays off until the probe passes.
2. **Boot-connect lifecycle change.** `_run_forever` idles until ANY handler is registered
   (`websocket.py:321-331`); today the stream connects at the first morning EP-candidate
   subscribe. A registered `statuses:"*"` handler makes it connect at boot and stay up all
   day. Benign (kills first-subscribe latency) but a live-stream behavior change → operator
   flips it, never a default. (Reconnect safety: `_send_subscribe_msg` re-sends ALL
   registered handlers on every (re)connect — websocket.py:344 — so the statuses
   subscription survives both SDK reconnects and bar_stream's outer retry loop with zero
   bar_stream changes.)

## 4. What was built (SHADOW-ONLY, this branch)

**No live-guard change: `_compute_rmv` is byte-identical.** Every new path is telemetry.

| Piece | File | Behavior |
|---|---|---|
| Entitlement probe | `scripts/probe_alpaca_statuses.py` | Standalone throwaway-connection probe; PASS/FAIL/INCONCLUSIVE verdicts; zero prod-code involvement |
| Authoritative capture | `agents/market_intelligence/broker/halt_status_shadow.py` | `subscribe_trading_statuses(…, "*")` → `mi_halt_status_events` (raw halt/resume events + codes + feed). **Env-gated `HALT_STATUS_CAPTURE_ENABLED`, default OFF** → module is a no-op in prod until the operator flips it. Writer swallows all errors (never raises into the stream dispatch loop) |
| Registration hook | `broker/bar_stream.py` (in `start_bar_stream`, own try/except) | One guarded call; inert with the flag off; cannot break the bar path |
| None-reason taxonomy | `flag_detector.rmv_none_reason` (pure sibling, right after `_compute_rmv`) | Separates the overloaded None: `insufficient_history` / `degenerate_close` / **`dead_floor`** / `zero_base`. Parity with `_compute_rmv` pinned by test (reason-None ⟺ rmv-not-None) |
| Nightly compare | `agents/market_intelligence/dead_data_guard_shadow.py` → `mi_dead_data_guard_shadow` | Piggybacks `_flag_scan_job` (scheduler.py, guarded; 17:25 ET). Cohort = scanned-with-NULL-rmv ∪ authoritatively-halted-in-window (5-cal-day trailing window ≈ the 3-trading-bar floor window). Row: rmv_15d, none_reason, `inferred_dead` (dead_floor/zero_base), `halted_authoritative`, halt_events_n, halt_codes, in_flag_universe, `agree`. Never raises |
| Tables | `db.py::initialize_schema` | `mi_halt_status_events`, `mi_dead_data_guard_shadow` (+4 accessors). Nothing on a detection/entry path reads either |
| Tests | `tests/test_386_dead_data_guard_shadow.py` | 11 tests: parity battery + branch classification + live-guard-untouched, flag-off inertness, wildcard registration, both event shapes, writer/job never-raise, 2×2 matrix + no-history row |

## 5. Shadow-compare plan (agreement measurement → operator-signed switch)

**Rollout (each step operator-visible):**
1. **Probe** (operator or off-prod run): `python scripts/probe_alpaca_statuses.py` against
   the prod feed (`iex`). FAIL → stop; the Alpaca route is closed on this plan (fallback
   options: §6). PASS → step 2.
2. **Operator flips `HALT_STATUS_CAPTURE_ENABLED=true`** (env change + market-agent
   restart). Verify-live: `mi_halt_status_events` accrues rows on the next halt day
   (halts occur near-daily market-wide with a `"*"` subscription); boot log shows
   "trading-statuses (*) capture registered".
3. **Accrue ≥ 20 trading days** of compare rows (auto — the nightly job runs already;
   it just writes `halted_authoritative=false` everywhere until capture is on, which
   is itself useful: it inventories what the floor trips on TODAY).
4. **Agreement readout** (one SQL, no new code):
   - Of rows with `none_reason='dead_floor'`: % with `halted_authoritative=true`
     (**precision of the inference as a halt detector**) — the remainder split into
     frozen-feed/zombie (the guard's OTHER legitimate target) via spot-check.
   - Of authoritative **multi-day** halts (halt codes without same-window resume, T12-class)
     on tickers with sufficient history: % where the floor tripped (**recall**).
   - **Expected-disagree classes, excluded from the verdict:** intraday LULD pauses
     (halt+resume same session — daily bars keep a real range; bucket by
     `halt_codes` LUDP/M) and halted names outside the flag universe
     (`in_flag_universe=false` — coverage telemetry, not guard error).
5. **Operator decision** on the measured matrix (see §7 for the fork).

**Decision-relevant threshold (proposed, operator may re-cut):** if ≥90% of multi-day
authoritative halts trip the floor AND the floor's non-halt trips are confirmed
frozen-feed/zombie (i.e., the heuristic is a *superset* of halts), the right live change is
**augment** (OR the authoritative flag in as a second, labeled reason) rather than
**replace** (the floor also catches feed-death, which no halt feed will ever flag).
Evidence-gated per CHANGE_PROCESS — N≥10 authoritative halt samples minimum before any
proposal.

## 6. If the Alpaca probe FAILS (fallbacks, unbuilt)

1. `sip` feed (Algo Trader Plus $99/mo) — statuses + `lulds` channel (SDK routes `"l"`
   msgs, websocket.py:251, though 0.43.2 exposes no public subscribe helper — raw-handler
   registration would be needed). Cost decision = operator.
2. Primary-source REST pull: Nasdaq Trade Halts (nasdaqtrader.com RSS, Tape C) + NYSE
   equivalents — free, authoritative, no WS/entitlement/connection-limit constraints; new
   external dependency outside the current 4-feed stack. Design-only for now.
3. Weak-REST enrichment: nightly `get_asset(ticker)` status/tradable on floor-tripped
   tickers only — catches delistings/zombies (likely a large share of trips), NOT halts.

## 7. Operator sign-offs required (nothing proceeds without them)

| # | Decision | Gate |
|---|---|---|
| S1 | Run/authorize the entitlement probe (off-prod window) | operational |
| S2 | Flip `HALT_STATUS_CAPTURE_ENABLED=true` after probe PASS (accepts the boot-connect lifecycle change, §3.2) | live-stream behavior |
| S3 | After ≥20 trading days + N≥10 authoritative halts: the live-guard fork — **augment** (floor OR authoritative flag, recommended per §5) vs **replace** vs **keep inference-only** | **THE LINE** — detection criterion; CHANGE_PROCESS entry in the setup SSoT + backtest of the agreement data; this doc's matrix is the evidence input |
| S4 | If probe FAILS: pick a §6 fallback (sip $99/mo vs primary-source REST vs weak-REST only) | cost / new-dependency |

**Merging this branch itself** = shadow-only (default-off capture + telemetry job) — safe
under the working rules' no-money default, but it touches `bar_stream.py`/`scheduler.py`
with guarded hooks, so it rides the normal deploy + review path, not a silent merge.

## 8. What this does not answer (added 2026-09-12, at merge)

**Population:** zero authoritative halt events exist yet (n=0) — `mi_halt_status_events` stays
empty until the operator flips `HALT_STATUS_CAPTURE_ENABLED` (S2) and a real halt occurs on a
captured ticker afterward. Every percentage quoted above (§5's agreement-readout plan, the ≥90%
decision threshold) is a PROPOSED measurement method, not a computed result — there is no real
data to run it against yet. This document is a design/feed-audit analysis, not an empirical
finding: it establishes WHAT to measure once capture accrues events, not what the agreement
actually is.

- **Whether the RMV floor and the authoritative flag actually agree in practice** — unanswered;
  needs real captured halts (S2 must be flipped first), which has not happened.
- **Whether the proposed ≥90% decision threshold (§5) is the right cut** — it is proposed, not
  backtested. CHANGE_PROCESS requires N≥10 authoritative halt samples before any live-guard
  change; the count today is 0.
- **Whether `iex` (the free default feed) also carries the `statuses` channel** — the S1 probe
  that PASSED 2026-07-25 ran against `sip` (the feed this account is actually entitled to via
  Algo Trader Plus), not `iex`. If the account's feed configuration ever changes, re-probe.
- **Anything about current EP/exit/sizing rules or the RMV floor's live behavior** — this
  document is entirely about a telemetry capture path; it changes no detection or trade logic
  (verified: `_compute_rmv`/`_ntr`/`_wilder_tr` byte-identical to main at merge time, 2026-09-12).
