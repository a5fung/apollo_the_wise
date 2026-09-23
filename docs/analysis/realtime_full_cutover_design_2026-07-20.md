# Full Real-Time Cutover — Design + Execute-Ready Runbook (#490, 2026-07-20)

**Status**: DESIGN ONLY — no code changed. Implementation is GATED on the residual-data trigger
(operator-owned, §1.3). This document exists so that IF the `mi_ep_delayed_residual` dashboard shows
the hybrid isn't enough, the cutover executes with ZERO design delay. Detection-criterion change →
CHANGE_PROCESS + operator sign-off gates every phase (§8). Nothing here is self-authorizing (THE LINE).

**Companion**: `docs/analysis/realtime_detection_feed_design_2026-07-20.md` (the #489 hybrid design,
esp. §3 volume, §5 insertion seams, §14 replay results). This doc assumes that one and does not repeat it.

---

## 1. Where we stand today (verified in code, 2026-07-20)

### 1.1 Shipped and live
- **Hybrid Pass-1/Pass-2 is SHADOW-LIVE** (commit `4cc1f67`): `EP_RT_PASS2_ENABLED=true`, superset
  5% (`ep_detector.py:98-99`), `_pass1_gap_floor()` (`ep_detector.py:102-106`) widens the Pass-1 gap
  gate at `ep_detector.py:1722`; `_apply_realtime_pass2` (`ep_detector.py:1481-1559`) fetches
  real-time Alpaca snapshots for the superset via `collector.get_alpaca_snapshots_batch`
  (`collector.py:229-288`, batched ≤100, serial chunks, never-raises, live-validated), applies the
  0.5% prev_close cross-check (`:1525`), the 30pp sanity clamp (`:1533`), and re-applies the real
  10% `MIN_GAP_PCT` floor (`:1499-1508`) under the `ep_rt_gap_authoritative` runtime toggle
  (`db.py:3111-3140`, mi_safeguard_state overrides env, ~60s cache). Floor-flip events
  `ep_rt_floor_flip_up/down` (`:1546-1555`); degrade event `ep_rt_pass2_degraded` (`:1510-1516`).
- **Residual tracker deployed + verified**: `ep_delayed_residual.py` (EOD 16:35 ET,
  `scheduler.py:5082-5085`; job `scheduler.py:1078-1086`) writes `mi_ep_delayed_residual`
  (DDL `db.py:1037-1055`) — every QUALITY in-window (9:31-9:44) 10%-crosser the ~16-min delay missed,
  with `hybrid_caught` marking whether the 5% hybrid would have caught it. `hybrid_caught=false` =
  the structural residual. Dashboard seeded (commit `076bd60`); preliminary signal: missed crossers
  mostly faded → escalation urgency currently LOWER (caveated, small N).

### 1.2 Known deferred gaps (from the hybrid ship — the cutover build absorbs them)
- **G1 — scan-log per-row shadow columns not populated**: `mi_ep_scan_log` gained
  `gap_pct_rt / gap_pct_delayed / price_source / rt_price_age_s` (`db.py:1001-1004`) but the
  `log_ep_scan_candidates` INSERT was NOT extended (deferred in commit `95ff07d`); floor-flip audit
  events are the current signal.
- **G2 — volume refresh never shipped**: `c["today_volume"]` is still the DELAYED Polygon
  `day.v`/`min.av` (`ep_detector.py:1726`) feeding the RVOL@T gate (`ep_detector.py:1965-1970` →
  `minute_volume.py:225-282`). The §3 volume design (own toggle, minute-bar cumulative) exists on
  paper only.
- **G3 — `fwd_1d_pct`/`fwd_5d_pct` on `mi_ep_delayed_residual` have NO writer** (columns exist in
  the DDL; `grep` finds no populator — `outcome_tracker.py:205` has the idiom for `mi_ep_alerts`).
  The escalation trigger reads forward outcomes → this filler must ship (RT-1) or the dashboard
  can't answer "were the missed ones winners?".
- **G4 — no #489 entry in `docs/setups/magna53_ep.md` yet**: acceptable while everything is shadow
  (no criteria changed); the SSoT change-log entry is REQUIRED in the same commit as any
  authoritative flip / cutover code (§8).

### 1.3 The trigger (operator-owned; this doc just arms it)
Escalate to full real-time when the residual dashboard shows a **sustained material count of
quality misses with good forward outcomes** — e.g. over ≥15 trading days: `hybrid_caught=false`
rows averaging ≥1/day whose median `fwd_5d_pct` (or max-favorable) is meaningfully positive. The
threshold is the operator's call at review time; the preliminary "mostly faded" read (§1.1) means
no urgency today. This runbook is the pre-paid design so the decision→live latency is ~2-4 days of
build/shadow, not weeks.

**PINNED + WIRED 2026-07-20 (operator):** the bar is **≥5** `hybrid_caught=false` residual misses
over the last ~15 trading days **AND** their **median `fwd_5d_pct` ≥ +8%** (real winners, not faders;
5 not 10 — EPs are rare). No longer a review-time debate — it AUTO-EVALUATES daily:
`ep_delayed_residual.evaluate_o9_escalation()` runs inside `_delayed_residual_job` (16:35 ET), fed by
the new **G3** writer `backfill_residual_outcomes()` (stamps `fwd_1d/5d_pct` on settled misses), and
🚨-Telegrams "O-9 MET → execute cutover" the day both cross (7-day deduped). **Validated 7/20:**
count=15 but median fwd-5d **−11%** (faders) → **NOT triggered** — the outcome bar carries it; the delay
is missing losers, not winners. O9_MIN_MISSES=5 / O9_MEDIAN_FWD5D_MIN=8.0 (`ep_delayed_residual.py`).

### 1.4 The structural blind spot being removed
Phase-0 replay (#489 §14): the 5% hybrid catches ~55% (86/156) of delay-missed quality in-window
crossers. The other ~45% show DELAYED gap ~0% (often negative) at the moment they truly cross 10% —
flat pre-market, exploding post-open. Pass-1 (`ep_detector.py:1722`) is the only full-universe view
and it is delayed, so NO superset admits them. Removing the ceiling requires the Pass-1 gap itself
to be computed from a real-time price.

---

## 2. Option A — full-Alpaca real-time universe (RECOMMENDED)

### 2.1 Architecture: OVERLAY, don't replace

Do **not** drop `get_snapshot_all()` (`collector.py:211-226`). Keep the one Polygon call as the
**reference substrate** and overlay real-time Alpaca prices on top:

```
run_ep_scan (ep_detector.py:1562)
  ├─ get_snapshot_all() ................ 1 Polygon call, UNCHANGED — supplies universe enumeration,
  │                                      prevDay.c / prevDay.v (yesterday = settled, delay-immaterial),
  │                                      delayed price chain (per-ticker fallback), delayed volume
  ├─ NEW Pass-0 rt-universe fetch (EP_RT_UNIVERSE_ENABLED):
  │     rt_universe = [t for t, snap in snapshots.items() if <non-gap filters pass>]
  │                                      # exactly the existing checks at 1686-1708:
  │                                      # len≤5 / not _SKIP_TICKERS / no "." (1686)
  │                                      # CS/ADRC via mi_security_types (1688-1699)
  │                                      # prevDay.c ≥ $5 (1701-1703, MIN_PREV_CLOSE ep_detector.py:108)
  │                                      # prevDay.v ≥ 50k (1706-1708, MIN_PREV_DAY_VOLUME :110)
  │     rt_snaps = await get_alpaca_snapshots_batch(rt_universe, concurrency=EP_RT_UNIVERSE_CONCURRENCY)
  ├─ Pass-1 loop (1683-1758): price = rt_snaps[t]["price"] if usable else delayed chain (1713-1719)
  │     gap floor: rt-priced ticker → MIN_GAP_PCT directly (no superset needed — the price is true)
  │                delayed-fallback ticker → _pass1_gap_floor() (hybrid behavior PRESERVED for the
  │                fallback population — a fetch gap degrades a ticker to today's hybrid, not to blind)
  ├─ _apply_realtime_pass2(candidates, now_et, snaps=rt_snaps) ... reuse, no second fetch: Pass-2
  │     stays the ONE place doing the prev_close cross-check + 30pp clamp + floor re-application
  └─ downstream untouched (sort 1766, top-20 1943, RVOL gate 1947-2002, _score_ep, scan-log, ORB)
```

**Why every non-gap Pass-1 filter is computable without real-time data**: they all read
*prior-day* fields (`prevDay.c`, `prevDay.v`) or static reference (`mi_security_types`) — a
15-min-delayed feed's yesterday-data is identical to a real-time feed's yesterday-data. So the
reduced universe = "every ticker that could pass Pass-1 if its gap qualified" — **zero blind spot
introduced by the reduction**; any excluded ticker fails Pass-1 regardless of price.

### 2.2 Universe size + call budget + latency (the numbers)

| quantity | value | basis |
|---|---|---|
| Full Polygon snapshot | ~9,700 tickers | measured (CLAUDE.md, RS universe) |
| ∩ CS/ADRC (`mi_security_types`) | ~5,000-6,000 **EST** | typical US common-stock+ADR count — **O-1: exact N = one prod query** |
| ∩ prev_close ≥ $5 ∩ prev_vol ≥ 50k | **N ≈ 2,500-4,000 EST** | planning number **4,000** (conservative-high) |
| Alpaca snapshot calls/tick | **ceil(N/100) = 25-40** | batch ≤100 validated live (#489 §13); O-3: larger batches may cut this 2-5× |
| Calls/day | ~37 ticks × 40 ≈ **1,480** | crons `scheduler.py:5013-5033`: 7:00-9:55 */5 (36) + 9:31 |
| Rate-limit headroom | 40 calls burst ≈ **0.4%** of 10,000 req/min | Algo Trader Plus, already paid; no contention with execution-path calls (same tiny order of magnitude) |
| Wall-clock, typical | **~1.5-3 s** per tick | 40 calls / concurrency 10 = 4 waves × ~0.3-0.8 s/call (**A-2: per-call latency unbenchmarked — RT-0 probe measures**) |
| Wall-clock, hard ceiling | **≤15 s**, then degrade | per-wave `asyncio.wait_for` 4 s + 1 retry (existing fetcher idiom `collector.py:257-266`) under a total budget; on breach → hybrid path (§2.5) |

**ORB-critical timing**: the 9:31/9:35/9:40 ticks must produce a HIGH before the `minute < 45`
window check (`scheduler.py:894`), which is evaluated AFTER `run_ep_scan` returns. Today's scan
wall-clock is dominated by the per-candidate LLM/FMP scoring loop (`ep_detector.py:1943` onward),
not the fetch; adding ~2-3 s typical (vs. Pass-2's current ~0.3-0.5 s) leaves the 9:40 tick
finishing scoring on the same schedule ±3 s. Worst case (+15 s then degrade) still clears: a 9:40
tick degraded at 9:40:15 runs the hybrid path and completes as today. **O-7: measure current
`run_ep_scan` prod wall-clock before the flip** (belt: the near-cutoff guard `_in_orb_cutoff`
already exists at `ep_detector.py:2850`). **O-8**: `ep_scan` cron has `misfire_grace_time=300` and
APScheduler default `max_instances=1` — a worst-case overrun into the next */5 tick would SKIP that
tick; +15 s cannot cause this (scan total ≪ 5 min), but confirm no coalescing surprise in prod logs.

### 2.3 Gap computation from Alpaca fields (reuse, not reinvent)

Identical to shipped Pass-2 (`ep_detector.py:1518-1545`): `rt_gap = (alpaca latest_trade.price −
polygon prevDay.c) / prevDay.c` — **Polygon prev_close stays the SOLE denominator** (#489 §4
rationale unchanged: one authoritative reference, isolates the numerator). The fetcher already
returns `price` (latest_trade → minute_bar fallback), `price_ts`, `prev_close`
(`previous_daily_bar.close`, cross-check only) — `collector.py:269-285`. The cross-check (0.5%)
and 30pp clamp apply per-ticker in the SAME code path (Pass-2, now fed the pre-fetched map).
A ticker failing either degrades to its delayed gap — exactly today's semantics.

### 2.4 Volume — the co-requisite fix (G2 ships WITH the cutover)

The newly-caught flat-premarket class has *large real session volume the delayed feed hasn't seen
yet* — the RVOL@T numerator (`c["today_volume"]`, delayed, `ep_detector.py:1726` → `:1965-1970`)
UNDERSTATES them at 9:31-9:44 → `session_rvol` false-rejects (`ep_detector.py:1984-2002`) would
silently kill the very admissions the cutover exists to create (baseline-holding liquid names do
NOT get the silent no-baseline pass of `minute_volume.py:266-272`). Therefore the deferred #489 §3
Option-B volume path is **REQUIRED scope here, not optional**:

- New `collector.get_alpaca_minute_cum_volumes(tickers, run_date)` — ONE batched multi-symbol
  `StockBarsRequest(timeframe=Minute, start=4:00 ET, end=now, feed=get_data_feed())`, the exact
  single-symbol pattern of `alpaca_client.get_minute_bars_window` (`alpaca_client.py:700-744`) made
  multi-symbol, living in `collector.py` per the intelligence/broker boundary precedent. Applied to
  the **candidate cohort only** (≤ ~20-50 symbols — bounded), summed per symbol into pm-anchor
  (from 4:00) and session-anchor (from 9:30) cumulatives for `compute_rvol_at_time`
  (`minute_volume.py:259-264` picks the anchor).
- Own toggle `ep_rt_volume_authoritative` / `EP_RT_VOLUME_AUTHORITATIVE` (default off), flipped
  SEPARATELY from the gap (change isolation — same reason as #489 §3). Shadow logs
  `(today_volume_delayed, today_volume_rt, would_rvol_gate_flip)`.

### 2.5 Failure ladder (every rung converges on a previously-validated behavior)

1. Per-ticker rt miss (symbology gap, malformed) → that ticker runs the HYBRID path (superset floor
   + Pass-2 attempt via the same map → delayed fallback). Stamped `price_source`.
2. Partial batch failure → those ~100 symbols degrade per rung 1; the rest are rt. Audit
   `ep_rt_universe_degraded` (per-tick, deduped) with `batches_failed / symbols_missing`.
3. Whole universe fetch fails / total budget breached → tick runs EXACTLY today's shadow-hybrid,
   plus `maybe_alert_api_failure("alpaca", e, context="ep_rt_universe")` (deduped ~6h Telegram —
   the #370 idiom, `alpaca_client.py:266-267`) so a sustained outage is loud.
4. Authoritative-toggle read failure → env default (off) → shadow (`db.py:3128-3138` fail-open-to-env).
5. **Superset-only and rt-only admissions REQUIRE an rt read under authority** — the shipped rule
   (`ep_detector.py:1499-1508`) extends unchanged: a fetch miss must never loosen detection.
6. Outer belt: universe-fetch block wholly wrapped; unexpected exception → hybrid path. The
   `ep_scan_failed` backstop (`scheduler.py:1028`) remains last-resort.

### 2.6 Is Polygon still needed? YES — and the plan stays

Grouped daily (RS universe + residual replay, `collector.py:193-208`), minute-bar history
(residual tracker `ep_delayed_residual.py:92`, backtests), security types, prev_close reference,
ADV — all *daily/reference* data where the 15-min delay is immaterial. Option A moves only
**intraday price freshness** (and cohort volume) to Alpaca. Polygon Starter is retained; nothing
is cancelled. (This is also the honest framing of Option A's cost: $0 marginal, not "$29 saved".)

---

## 3. Option B — Polygon real-time plan upgrade (the paid escape hatch)

- **Cost**: real-time US stocks (consolidated SIP, snapshot endpoint included) is the
  **Advanced-class plan, ~$199/mo (≈$2.4k/yr) as of my knowledge cutoff**; Developer-class (~$79/mo)
  remained 15-min delayed. **O-2: verify current pricing/tiering at polygon.io — pricing changes;
  do not act on my figure.**
- **Code delta**: essentially ZERO required. `get_snapshot_all()` hits the same endpoint; with a
  real-time entitlement the same fields are simply fresh. Optional cleanups after verification:
  set `EP_PASS1_SUPERSET_GAP_PCT=10.0 ⚠now 5.0 ⚠now 5.0` (kills the now-pointless widened fan-out; `_pass1_gap_floor`
  then ≡ MIN_GAP_PCT) and keep Pass-2 as a two-feed cross-check (floor-flips → ~0 by construction;
  a nonzero rate becomes a data-quality alarm) or set `EP_RT_PASS2_ENABLED=false` to retire it.
- **Also fixed for free**: `today_volume` freshness (day.v real-time → the G2 RVOL distortion
  largely vanishes without new code), and every OTHER `get_snapshot_all` consumer (9M intraday
  detection, premarket/overnight snapshots `collector.py:947-1058`) goes real-time in one stroke.
- **Cons**: recurring $ for data that duplicates the already-paid Alpaca SIP; the freshness claim
  still needs its own live re-measurement post-upgrade (the original staleness measurement rerun);
  **rollback is a billing action on a plan cycle, not a 60-second toggle**; deepens single-vendor
  coupling of detection to Polygon while execution reads Alpaca (two tapes that can disagree at
  the second scale).

---

## 4. Recommendation: **Option A**, with B as the pre-approved pivot

1. **$0 vs ~$2.4k/yr** for largely duplicate data (Alpaca SIP already paid and already trusted by
   the execution path).
2. **A extends a LIVE-VALIDATED path** — `get_alpaca_snapshots_batch` is in production today with
   its failure ladder proven (never-raises, per-ticker fallback, degrade events). Option A is
   "the same fetcher, bigger list + concurrency", not a new architecture. B's real-time claim
   requires post-payment validation and its rollback is slow.
3. **Same-tape alignment**: the gap that triggers an ORB bracket is computed from the SAME
   consolidated tape the order fills on. Under B, detection (Polygon RT) and execution (Alpaca)
   read different vendors' views of the tape.
4. **Instant-revert at every layer** (§6 rollback ladder) — a property THE LINE work demands and B
   cannot offer for its core change.
5. The latency/call budget fits with an order of magnitude to spare (§2.2).

**Honest counter-weights**: B is operationally simpler (1 call, no concurrency code, no coverage
gaps), fixes ALL delayed consumers at once, and adds zero maintained code. **Hybrid-of-options
ruling**: if RT-0/RT-2 gates FAIL (coverage <99% on the liquid universe, or p95 wall-clock >5 s, or
sustained fetch instability in shadow), **pivot to B without redesign** — §7 is its runbook. The
$199/mo also buys 9M/premarket freshness the operator may independently want someday; that is a
separate spend decision, not this one (9M scope-out rationale: #489 §9, unchanged).

---

## 5. THE CUTOVER RUNBOOK — Option A (execute with zero design delay)

> Trigger: operator invokes this after the §1.3 residual evidence. Every flip is operator-executed.
> Deploy scope throughout: `bash scripts/deploy.sh market-agent` (files under
> `agents/market_intelligence/`). tz: all new datetimes via `_ET`/`ZoneInfo` (deploy gate [5h/7]).

### RT-0 — Preflight probes (read-only; ~half a day; no deploy)
1. **Exact N** (prod psql):
   ```sql
   -- rt-universe size = tickers passing every non-gap Pass-1 filter
   SELECT COUNT(*) FROM mi_security_types st
   JOIN mi_daily_closes dc ON dc.ticker = st.ticker AND dc.trade_date = <last_trading_day>
   WHERE st.security_type IN ('CS','ADRC') AND dc.close >= 5 AND dc.volume >= 50000
     AND LENGTH(st.ticker) <= 5 AND st.ticker NOT LIKE '%.%';
   ```
   (Or read the scan's own log line "security_types loaded — X stock", `ep_detector.py:1607-1611`,
   + one probe pass over a saved snapshot.)
2. **Live probe** `scripts/probes/_490_rt_universe_probe.py` (the `_489_realtime_replay.py` idiom):
   at 2-3 market-hours ticks, fetch the FULL reduced universe via `get_alpaca_snapshots_batch`
   with a temporary concurrency wrapper; measure per-call latency, total wall-clock at
   concurrency ∈ {5, 10, 20}, coverage = symbols returned / requested, and the named missing list.
   Optionally test batch sizes >100 (O-3).
3. **Prod env check**: confirm `ALPACA_DATA_FEED=sip` in the market-agent container
   (`collector.py:249` falls back to IEX if unset — an IEX-only rt price is a thin-tape read and
   would degrade BOTH the current Pass-2 and this cutover; **check this TODAY regardless, O-4**).

**GATE RT-0 (operator reviews numbers)**: coverage ≥99% on the reduced universe; p95 total
wall-clock ≤5 s at the chosen concurrency; N within 2× of the planning number. FAIL → pivot to §7.

### RT-1 — Build + dark deploy (1 day; behavior byte-identical, flags off)
Code (all pattern-matching existing seams):
1. `collector.get_alpaca_snapshots_batch(..., concurrency: int = 1)` — parallelize the existing
   chunk loop (`collector.py:253-267`) via `asyncio.gather` + `Semaphore`; default 1 preserves
   current behavior exactly.
2. `run_ep_scan`: Pass-0 block after `get_snapshot_all()` (`ep_detector.py:1675`) behind
   `EP_RT_UNIVERSE_ENABLED` (env, default false): build `rt_universe` (§2.1 filters), fetch
   `rt_snaps`. In the loop, overlay price per §2.1; stamp `price_source='alpaca_sip_universe'`.
   **Shadow semantics** (`ep_rt_universe_authoritative` off): decided gap/cohort byte-identical to
   the hybrid; where `rt_gap ≥ 10 > delayed_gap` and delayed `< _pass1_gap_floor()` (the class the
   hybrid CANNOT see) emit `ep_rt_universe_catch` audit event (deduped per ticker/day via
   `_audit_dedupe_check`, `ep_detector.py:207`) + a `_log_filtered` scan-log row
   ("rt_universe_catch (shadow — not admitted)"). Do NOT score/alert shadow catches (no cohort
   change, no LLM spend).
3. `_apply_realtime_pass2(candidates, now_et, snaps=None)` — accept the pre-fetched map; skip the
   refetch when provided. Cross-check/clamp/floor logic unchanged.
4. **G1**: extend the `log_ep_scan_candidates` INSERT with the 4 shadow columns (db.py:1001-1004).
5. **G2**: `collector.get_alpaca_minute_cum_volumes` + cohort volume refresh under
   `ep_rt_volume_authoritative` (shadow: log-only fields + would-flip counts) — §2.4.
6. **G3**: residual fwd-outcome filler — extend the EOD residual job (or the outcome_tracker
   sweep, `outcome_tracker.py:205` idiom) to backfill `fwd_1d_pct`/`fwd_5d_pct` from
   `mi_daily_closes`.
7. New env: `EP_RT_UNIVERSE_ENABLED`, `EP_RT_UNIVERSE_CONCURRENCY` (default 10),
   `EP_RT_UNIVERSE_TIMEOUT_S` (total budget, default 15). New toggles:
   `ep_rt_universe_authoritative`, `ep_rt_volume_authoritative` (both default off).
8. Tests freeze: flags-off = byte-identical (`tests/test_execute_task_routing.py` pattern; extend
   the 3 existing #489 freeze tests).

Deploy dark (`EP_RT_UNIVERSE_ENABLED=false`) → verify boot green → set
`EP_RT_UNIVERSE_ENABLED=true` (shadow) next off-hours restart. **SSoT**: no criteria change yet →
G4 note only; the change-log entry lands at RT-3.

### RT-2 — Shadow validation (≥10 trading days, or event-gated on ≥5 residual-class days)
The PROOF join, run daily (piggyback the residual EOD job's audit line):
- **Residual-capture rate**: every `mi_ep_delayed_residual` row with `hybrid_caught=false` on a
  shadow day MUST have a matching same-day `ep_rt_universe_catch` event at an in-window tick.
  Target **≥95%** (misses explained: symbology gap vs timing vs bug).
- Fetch health: ≥99% ticks with zero `ep_rt_universe_degraded`; per-ticker fallback rate <2% on
  the candidate cohort; wall-clock p95 within the RT-0 measurement.
- Volume shadow: rt cumulatives sane vs `mi_minute_volume_curves` baselines; named list + count of
  RVOL-gate decisions that would flip (expect: un-rejecting the flat-premarket class).
- prev_close mismatch + 30pp clamp rates at universe scale (~0.5%/~0 expected; a fat rate = stop).
- If shadow reads ~0 catches: **check the instrumentation before concluding**
  (memory: shadow-zero-effect-check-instrumentation) — the residual dashboard says the class
  exists; zero shadow catches more likely means a logging/coverage artifact.

**GATE RT-2 (operator sign-off on the packet)**: all metrics above + the operator reviews the
NAMED would-have-caught list (CHANGE_PROCESS rule 4 — HARD-gate list review; the agent does not
classify it clean). Plus the RT-3 fork decision: with rt Pass-1 authoritative, the 9:41-9:44
blind tail remains a CADENCE gap (ticks 9:31/35/40, `scheduler.py:5013-5033`) — add a 9:43 tick
(one cron line) or accept; operator's call (it was O5 in #489; real-time data now makes that tick
fully effective).

### RT-3 — Authoritative GAP flip (operator; instant; no deploy)
```sql
INSERT INTO mi_safeguard_state (safeguard, account_mode, state, last_transition_at, updated_at)
VALUES ('ep_rt_universe_authoritative', 'global', 'on', NOW(), NOW())
ON CONFLICT (safeguard, account_mode) DO UPDATE SET state = EXCLUDED.state, updated_at = NOW();
```
(~60 s cache, `db.py:3111-3140`.) From this tick: rt-priced tickers are admitted on
`rt_gap ≥ MIN_GAP_PCT` at Pass-1; scoring, `mi_ep_scan_log.gap_pct`, alerts, and the ORB decision
(`scheduler.py:894, 936-943, 1002-1011`) all read the rt gap — the flat-premarket class becomes
in-window catchable. `ep_rt_gap_authoritative` (Pass-2) should be flipped ON in the same session
if it wasn't already — it now governs only the delayed-fallback population.
**Same-commit paperwork**: `docs/setups/magna53_ep.md` change-log entry (data source: "Polygon
delayed reference + Alpaca SIP real-time universe overlay"; reversion-flag NEW; #489+#490 evidence
chain) + PLAN.md task → `deployed`, ETA = next market day.

### RT-4 — VERIFY-LIVE (next market day; the operator-facing surface, not just DB)
1. `mi_ep_scan_log` rows show `price_source='alpaca_sip_universe'` on a real tick (DB sanity).
2. **The surface**: first rt-only catch end-to-end — Telegram HIGH alert fires + the ORB decision
   row exists (entry or an honest skip reason), traced through `_ep_scan_job`
   (`scheduler.py:862-1011`). An event-gated wait if no qualifying day occurs immediately —
   never close on "deployed".
3. The residual EOD job now INVERTS into the standing verifier: post-cutover
   `missed_total` (`ep_delayed_residual.py:154`) should trend → ~0; any `hybrid_caught=false` row
   whose ticker got NO live alert that day = regression alarm (optional `caught_live` join column).
4. Watch 2 weeks: rt-only entries' outcomes (IREN-class or chase?), degraded-tick count, RVOL
   would-flip evidence → feeds RT-5 and the SSoT "validated" note.

### RT-5 — VOLUME flip (operator; ≥3 market days after RT-3; instant)
Same mi_safeguard_state INSERT for `ep_rt_volume_authoritative` after the RT-2 volume evidence +
RT-4 observation window. Separate flip = separate blast radius (change isolation). SSoT change-log
line + verify-live: one candidate's RVOL gate decision computed from rt cumulative in prod logs.

---

## 6. Rollback (each rung instant + independent; layers ADD, never replace)

| rung | action | lands on | latency |
|---|---|---|---|
| R1 | `ep_rt_volume_authoritative` → off (SQL) | rt gap, delayed volume | ~60 s |
| R2 | `ep_rt_universe_authoritative` → off (SQL) | the #489 HYBRID (Pass-2 authoritative if on; else shadow) | ~60 s |
| R3 | `ep_rt_gap_authoritative` → off (SQL) | hybrid in shadow = **fully-delayed original cohort** | ~60 s |
| R4 | `EP_RT_UNIVERSE_ENABLED=false` (env + restart) | universe fetch code dormant; pure hybrid | one restart |
| R5 | `EP_RT_PASS2_ENABLED=false` (env + restart) | byte-identical pre-#489 system | one restart |

The delayed Polygon path is never removed from the code — it IS the per-ticker fallback, exercised
continuously (fallback population), so the rollback target can't rot unnoticed.

---

## 7. Option B pivot runbook (if RT-0/RT-2 gates fail, or operator prefers paying for simplicity)

1. Upgrade the Polygon plan (verify current real-time tier + price first — O-2). No code deploy.
2. **Freshness verification** (same measurement that found the 15-17 min lag): compare snapshot
   `min.c` timestamps vs Alpaca `latest_trade` on SPY/NVDA + 3 movers across 3 ticks; require
   staleness ≤60 s.
3. Shadow proof reuses the SAME machinery: with fresh Polygon data, `ep_rt_floor_flip_up/down`
   rates collapse toward 0 (delayed≈rt) — watch 5 days; the residual EOD job should show
   in-window crossers now visible to Pass-1 (its LAG_MIN=16 replay still measures what the OLD
   feed would have missed, i.e. it verifies the upgrade's value directly).
4. Then (operator, one commit + SSoT entry): `EP_PASS1_SUPERSET_GAP_PCT=10.0 ⚠now 5.0`; keep Pass-2 as a
   permanent two-feed cross-check (recommended) or retire via `EP_RT_PASS2_ENABLED=false`.
5. Rollback: superset back to 5.0 (env) restores the hybrid instantly; the PLAN downgrade itself
   is a billing-cycle action — schedule detection-critical days accordingly (the known weak spot).

---

## 8. CHANGE_PROCESS / THE LINE compliance

- Detection data source feeds real-money ORB entries → every authority flip is **operator-executed**
  (RT-3/RT-5 SQL run by/for the operator on their word, never agent-initiated). `MIN_GAP_PCT=10.0 ⚠now 9.0`
  (`ep_detector.py:90-91`), the ORB window (`scheduler.py:894`), scoring weights, safeguards: ALL
  untouched — this changes input freshness only, and the shipped never-loosen rule
  (`ep_detector.py:1499-1508`) extends to the universe path.
- SSoT: `docs/setups/magna53_ep.md` change-log entry in the SAME commit as RT-1 code (shadow note)
  and RT-3/RT-5 flips (criteria-relevant), incl. the G4 catch-up for #489. Reversion-flag: NEW.
- HARD-gate list review (CHANGE_PROCESS rule 4): the RT-2 named would-have-caught list is the
  operator's to classify.
- Evidence rule: the flip is gated on the residual dashboard (real outcomes), not a single case.
- Burndown/PLAN: this design fulfils #490; implementation tasks are filed only when the operator
  pulls the trigger (backlog-growth honesty).

---

## 9. Assumptions (A-*) and open questions (O-*) — for the operator to verify

**Assumptions:**
- **A-1** Reduced universe N ≈ 2,500-4,000 (planning number 4,000). Basis: filter arithmetic, not a
  prod count.
- **A-2** Per-100-symbol snapshot call ≈ 0.3-0.8 s. Basis: one live call returned HTTP 200 (#489
  §13) but was NOT timed. RT-0 measures.
- **A-3** Alpaca symbology coverage ≥99% on the LIQUID universe (measured 95/100 on a list
  including obscure names; the misses skewed obscure). RT-0 measures the real rate + named list.
- **A-4** Concurrency 10 triggers no Alpaca-side throttling beyond the documented 10k req/min.
- **A-5** Polygon `prevDay.*` on the delayed snapshot is settled prior-day data (delay-immaterial).
- **A-6** Alpaca latest_trade includes pre-market SIP prints (it does for the Pass-2 population
  today; universe-scale thin names may simply have no prints — that IS the truth, handled).

**Open questions:**
- **O-1** Exact N (RT-0 SQL above).
- **O-2** Current Polygon real-time plan name/price — my ~$199/mo (Advanced-class) is
  knowledge-cutoff data; verify before weighing B.
- **O-3** Does the Alpaca snapshot endpoint accept >100 symbols/request? (Would cut calls 2-5×;
  100 is validated, larger is untested.)
- **O-4** Is `ALPACA_DATA_FEED=sip` set in the PROD market-agent env? (`collector.py:249` silently
  falls back to IEX — materially thinner tape for detection. Worth checking today, independent of
  the cutover.)
- **O-5** Confirm nothing else populates `mi_ep_delayed_residual.fwd_*` (repo grep says no writer;
  prod cron list should confirm) — G3 filler is required scope.
- **O-6** The 9:41-9:44 cadence tail: add the 9:43 tick? (Operator fork at RT-2 gate; real-time
  data makes it fully effective, cost = one cron line + one more scan's LLM budget.)
- **O-7** Current `run_ep_scan` wall-clock at the 9:31/9:40 ticks in prod (headroom check before
  RT-3).
- **O-8** APScheduler overlap behavior on a worst-case +15 s tick (expect: none; confirm in logs).
- **O-9** Escalation threshold itself (§1.3) — operator picks the residual count/outcome bar at
  review time; the preliminary "mostly faded" read argues for patience.

---

## 10. Surface summary

| surface | change (all RT-1 unless noted) |
|---|---|
| `collector.py` | `get_alpaca_snapshots_batch(+concurrency)`; NEW `get_alpaca_minute_cum_volumes` |
| `ep_detector.py` | Pass-0 rt-universe fetch + price overlay in the 1683-1758 loop; `_apply_realtime_pass2(+snaps)`; cohort volume refresh seam at the RVOL gate |
| `db.py` | extend `log_ep_scan_candidates` INSERT (G1); optional `caught_live` on residual table |
| `ep_delayed_residual.py` | fwd-outcome filler (G3); post-cutover verifier framing (RT-4) |
| `scheduler.py` | (only if O-6 approved) 9:43 tick cron |
| env/toggles | `EP_RT_UNIVERSE_ENABLED`, `EP_RT_UNIVERSE_CONCURRENCY`, `EP_RT_UNIVERSE_TIMEOUT_S`; toggles `ep_rt_universe_authoritative`, `ep_rt_volume_authoritative` |
| audit events | `ep_rt_universe_catch`, `ep_rt_universe_degraded` (+ existing `ep_rt_*` family) |
| SSoT | `docs/setups/magna53_ep.md` change-log entries at RT-1/RT-3/RT-5 (+ G4 catch-up) |
| untouched | `MIN_GAP_PCT`, ORB window, scoring weights, safeguards, Polygon plan (Option A) |

---

## Verification (Opus, 2026-07-20 — checked before operator review)

Load-bearing claims verified against code + prod + live API:
- **Architectural insight CONFIRMED**: every Pass-1 filter before the gap check (ep_detector.py:1686-1708) reads prior-day/reference data only — symbol type/`_SKIP_TICKERS`, `mi_security_types` (`_non_stock_tickers`/`_known_stock_tickers`), `prevDay.c`, `prevDay.v`. Only the current price needs real-time → the reduced RT universe is computable from delayed data with ZERO introduced blind spot. Option A's foundation holds.
- **O-1 universe N = 3,325** (measured: `mi_security_types` CS/ADRC ∩ latest `mi_daily_closes` close≥$5 ∧ volume≥50k). Inside Fable's 2,500-4,000 plan.
- **O-3 Alpaca accepts >100 symbols/call**: a live 200-symbol snapshot returned HTTP 200 (190/200 — ~5% symbology gap → per-ticker delayed fallback). At 200/call the whole universe = **~17 calls/tick** (~0.2% of the 10k req/min plan); Fable's latency/budget numbers hold with margin to spare.
- **O-2 Polygon real-time cost = $199/mo Advanced** (vs Starter $29 = **+$170/mo**, ~$2k/yr) — confirms Option A's $0 cost advantage; Option B stays the pre-approved pivot.
- **O-4 prod ALPACA_DATA_FEED=sip CONFIRMED** (both containers; `get_alpaca_snapshots_batch` returned real-time SIP 0-6s earlier today) — the current Pass-2 is NOT silently on IEX. Fable's "check this regardless" cleared.
- **O-5 no recurring fwd-outcome writer** — correct (only a one-off backfill ran today); G3 is required cutover scope.

VERDICT: Option A feasibility + the cutover runbook are sound. Recommendation stands (Option A $0 overlay; Option B = pre-approved billing-cycle pivot). Remaining open items are operator FORKS (O-6 9:43 tick, O-9 the escalation threshold), not correctness gaps.
