# Real-Time Detection Feed — Hybrid Polygon/Alpaca-SIP Design (2026-07-20)

**Status**: DESIGN ONLY — no code changed. Detection-criterion change → CHANGE_PROCESS + operator
sign-off gates every phase (§9). Nothing in this document is self-authorizing.

**Problem (measured, validated 2026-07-20)**: MAGNA53 EP detection reads intraday prices from
Polygon's bulk snapshot (`ep_detector.py:1579` → `collector.get_snapshot_all`, collector.py:211-226),
which on the Starter-class plan is **~15-17 min delayed** (measured: `min.c` ~17 min stale on
SPY/NVDA/AAPL/IREN/HUT while Alpaca SIP `latestTrade` was 0-6 s old). Stable pre-market gappers are
unaffected (a 15-min-old price shows the same gap), but **fast movers that cross the 10%
`MIN_GAP_PCT` floor inside the 9:31-9:44 ORB window are invisible until it is too late**. Case:
IREN 2026-07-20 — ~8-9% pre-market (below floor, silently dropped in the Pass-1 loop at
ep_detector.py:1626-1627), crossed 10% for real ~9:32-9:35, surfaced on the delayed feed at 9:50 →
`orb_out_of_window` (scheduler.py:944-996), no entry. Same-news HUT (11.5% pre-market, held) was
caught at 7:05 and entered.

**Chosen approach (operator-selected)**: HYBRID two-pass.
- **Pass 1** — keep the existing single Polygon bulk-snapshot call as the full-universe (~9,700
  ticker) screen, but admit candidates at a LOWER "superset" gap threshold so fast movers whose
  delayed gap is still under 10% are not dropped.
- **Pass 2** — for the Pass-1 superset (~dozens), fetch real-time prices from Alpaca SIP (already
  paid: Algo Trader Plus, 10k req/min, full consolidated tape — the same feed EXECUTION already
  uses via `broker/alpaca_client.py`), recompute the gap, and apply the REAL 10% floor + all
  downstream logic (scoring, `mi_ep_scan_log`, ORB decision) on the real-time gap.

**What this does NOT change (THE LINE)**: `MIN_GAP_PCT` stays 10.0 (ep_detector.py:90-91). The ORB
submission window stays 9:31-9:44 (scheduler.py:893). No scoring weight, safeguard, sizing, or
window semantic moves. This changes the FRESHNESS of the price/volume inputs only. The superset
threshold is an internal Pass-1 implementation detail whose output can never bypass the real floor.

---

## 1. Architecture overview

```
run_ep_scan (ep_detector.py:1466)
  │
  ├─ Pass 1 (UNCHANGED except gap threshold):
  │    get_snapshot_all() ..................... 1 Polygon call, ~9,700 tickers, DELAYED
  │    per-ticker filters (1587-1660):
  │      symbol/type/prev_close/prev_volume ... unchanged (1590-1612)
  │      gap_pct >= _pass1_gap_floor() ........ CHANGED: superset (e.g. 6%) when hybrid on,
  │                                             else MIN_GAP_PCT (10%)  [was line 1626]
  │    candidate dict gains: gap_pct_delayed, price_source='polygon_delayed'
  │
  ├─ Pass 2 (NEW, inserted between loop end 1660 and sort 1662):
  │    _apply_realtime_pass2(candidates, now_et)
  │      • 1-2 batched Alpaca SIP snapshot calls (superset only, ≤100 symbols/call)
  │      • reconcile prev_close (Polygon prevDay.c authoritative — §4)
  │      • rt_gap = (alpaca latest_trade.p − polygon prev_close) / prev_close
  │      • AUTHORITATIVE MODE ON:  c["gap_pct"] = rt_gap; re-apply MIN_GAP_PCT floor
  │        SHADOW MODE:            c["gap_pct"] stays delayed; rt logged alongside
  │      • optional volume refresh (own toggle — §3)
  │      • per-candidate fallback to delayed on any miss; NEVER raises (§6)
  │
  └─ everything downstream UNTOUCHED and automatically real-time:
       sort + rank_by_gap (1662-1664) · top-20 cap (1840) · RVOL@T gate (1857-1899)
       · _score_ep(gap_pct=c["gap_pct"]) (2916-2926) · _scan_row → mi_ep_scan_log
       (1802-1821, 3143-3146, 3232) · insert_ep_alert (3149-3171) · HIGH → ORB decision
       (scheduler.py:917-1010, window check 893)
```

The single design win: **every downstream consumer reads `c["gap_pct"]`**, so overwriting it at one
seam makes the real-time gap flow through scoring, the scan-log row, the alert row, and the ORB
decision with no other code changes.

Rejected alternative — Alpaca WebSocket streaming for detection: no full-market bulk stream is
practical for a 9,700-ticker universe on one connection, and the 5-min scan cadence doesn't need
sub-second data. The existing `bar_stream` stays what it is (ORB-candidate execution bars). Batched
REST snapshot is right-sized.

---

## 2. Q1 — Superset threshold for Pass 1

### The lag geometry

Let L = feed lag (~15-17 min, measured). At scan tick T, the delayed gap reflects the price at
T−L, so:

```
real_gap(T) = delayed_gap(T) + move(T−L → T)   [in gap-points, % of prev_close]
```

The superset margin M = 10% − superset_threshold must cover `move over the last L minutes` for the
fastest movers we intend to catch. Key structural fact: **during the 9:31-9:44 ORB window, the
delayed feed still shows ~9:14-9:29 prices — i.e., essentially the PRE-MARKET state.** The entire
opening surge is invisible. So the operative question is: *how far below 10% can a pre-market gap
sit and still plausibly cross 10% by 9:44 on the open surge?*

- IREN 7/20: pre-market 8-9%, crossed on a ~+1.5-2.5pp opening move. Margin needed: ~2pp.
- Typical in-play gappers put in +2-4pp in the first 10-15 min post-open. Margin 4pp covers this.
- A +5pp-in-15-min mover from a 5% pre-market base is possible but increasingly chase-class — the
  marginal value of margin beyond ~4-5pp decays while noise (candidates that will never cross)
  grows.

### Fan-out feasibility

Current 10% floor yields ~3-7 candidates/cycle (given). Gap-count distributions are roughly
log-linear in the threshold; a ~2× count per −2pp is the standard working estimate
(**ASSUMPTION — replay must confirm on our universe**):

| Pass-1 threshold | est. candidates/cycle | Alpaca snapshot calls (≤100 sym/call) |
|---|---|---|
| ≥ 8% | ~6-14 | 1 |
| ≥ 6% | ~12-30 | 1 |
| ≥ 5% | ~20-45 | 1 |
| ≥ 4% | ~35-80 | 1 |

Even ≥4% fits ONE batched call. Feasibility barely constrains the choice; the real costs of going
lower are (a) floor-flip noise near the boundary (rt spikes briefly kissing 10%), and (b) scan-log
/ audit volume. The scored cohort stays bounded regardless — the top-20 cap (ep_detector.py:1840)
and the authoritative 10% floor are unchanged.

### Recommendation

**Ship default `EP_PASS1_SUPERSET_GAP_PCT = 6.0` ⚠now 5.0** (env-overridable, same pattern as
`EP_MIN_GAP_PCT` at ep_detector.py:90-91), consulted only when the hybrid is enabled.

- 4pp margin covers every historical-class case we can name (IREN needed ~2pp) plus a comfortable
  buffer for a strong opening surge from a 6-8% pre-market base.
- Est. 12-30 Pass-2 symbols/cycle — one snapshot call.
- Refinement option (calibration outcome, not v1): a **two-level superset** — pre-9:30 ticks use a
  tighter value (e.g. 8%; pre-market tape moves slowly, lag matters less) and the 9:31/9:35/9:40
  ticks use the wide value (6% or 5%; this is where the lag blinds us). v1 keeps ONE knob for
  simplicity; the replay table below tells us whether the split earns its complexity.

### Calibration method (replay, before ship)

`mi_ep_scan_log` **cannot** calibrate this alone — the Pass-1 loop drops sub-10% names before any
logging (1626-1627), so the sub-floor population was never recorded. Reconstruct offline from
Polygon minute bars (a delayed feed is just a time-shifted read of the same tape):

1. Universe reduction: from grouped-daily (`collector.get_grouped_daily`), keep only tickers whose
   day's true max gap ≥4% vs prev close AND prev_close ≥ $5 AND prev_volume ≥ 50k (mirrors
   1605-1612) — a few hundred/day, feasible for minute-bar pulls (`collector.get_minute_bars`,
   collector.py:297; Polygon plan is call-unlimited).
2. For each scan tick τ ∈ {7:00, 7:05, …, 9:55} on each of 30-60 trading days:
   `delayed_gap(τ)` = last minute-close ≤ τ−16min vs prev close; `rt_gap(τ)` = last minute-close ≤ τ.
3. Metrics per candidate threshold s ∈ {5, 6, 7, 8}:
   - **Coverage**: of all tickers with `rt_gap ≥ 10%` at some tick in 9:31-9:44 while
     `delayed_gap < 10%` at that tick (the IREN class), what fraction had `delayed_gap ≥ s` (i.e.,
     Pass 1 would have admitted them)?
   - **Fan-out**: p50/p95 Pass-2 symbol count per tick.
   - **Flip-down count**: `delayed_gap ≥ 10 > rt_gap` — the *stale false-admit* class the fix also
     cleans (today these get scored on a phantom gap).
   - **Would-be-alert list**: every net-new admission, named, for operator review (§9).
4. Decision rule: choose the LARGEST s with ≥95% coverage of the in-window-crosser class, subject
   to p95 fan-out ≤ 100 symbols. Expected outcome ≈ 6%; ship what the table says.

**Honest residual**: a name at 3% pre-market that explodes to 11% by 9:40 is below any sane
superset and stays missed — Pass 1 is the only full-universe view and it is delayed; that bound is
inherent to the hybrid. The replay quantifies this residual class so the operator sees the true
coverage, not a claimed 100%.

---

## 3. Q2 — What Pass 2 fetches; the volume question

### Price (the primary fix)

One batched Alpaca snapshot call returns, per symbol (verified against installed alpaca-py 0.43.2:
`StockSnapshotRequest(symbol_or_symbols, feed, currency)` →
`StockHistoricalDataClient.get_stock_snapshot`; `Snapshot` model fields `latest_trade`,
`latest_quote`, `minute_bar`, `daily_bar`, `previous_daily_bar`):

- `latest_trade.price` + `.timestamp` → the real-time price. Precedence mirrors the intent of the
  Polygon chain (min.c → day.o → lastTrade.p, ep_detector.py:1617-1621) but the latest trade IS the
  freshest field pre- and post-open, so use it directly; `minute_bar.close` is the fallback.
- `previous_daily_bar.close` → used ONLY for the prev_close cross-check (§4), never as the gap
  denominator.
- `daily_bar` / `minute_bar` volumes → volume refresh (below).

Staleness/sanity on the rt price:
- A thin pre-market name may not have traded for 20+ min — a "stale" `latest_trade` is then still
  the truth (Polygon would eventually show the same trade). No freshness *requirement*; instead log
  `rt_price_age_s = now − latest_trade.timestamp` for observability.
- Sanity clamp: if `|rt_gap − delayed_gap| > 30pp`, treat the rt read as suspect (bad print /
  symbology mismatch), fall back to delayed for that ticker + emit `ep_rt_prev_close_mismatch`-style
  audit (§6). SIP latest-trade can include odd-lot/condition-coded prints that bars exclude —
  accepted risk at this tolerance (**ASSUMPTION — spot-check in shadow**).

### Volume — yes, it needs a real-time path, and there is a latent existing bug here

The RVOL@T gate's numerator is ALSO delayed, and in the ORB window this bites the same fast-mover
class *twice*:

- `today_volume` = Polygon `day.v` falling back to `min.av` (ep_detector.py:1630) — delayed ~15-17
  min like everything else in the snapshot.
- Post-open, the gate passes it as `today_session_vol` (1858-1861) into `compute_rvol_at_time`
  (minute_volume.py:225-282), which at 9:31-9:44 selects the **session anchor**: today's cumulative
  volume *from 9:30* vs the 20-day baseline cumulative *at this clock minute* (259-264). But the
  delayed `day.v` at 9:40 reflects the ~9:24 state — i.e., little-to-no session volume — while the
  baseline denominator already contains ~10 minutes of a normal day's densest tape. The numerator is
  structurally understated → `session_rvol < 1.0` false-rejects (`FILTER_SESSION_RVOL_TOO_LOW`,
  1871-1899) are plausible for exactly the in-window crossers Pass 2 exists to admit. The `min.av`
  fallback (pre-market-inclusive cumulative) softens this for big pre-market names but with
  wrong-anchor semantics. Same story for `projected_vol_multiple` (1643-1646): real
  `_minutes_since_open` divided into a stale cumulative → understated open-intensity.
- **I could not verify from code what Polygon's delayed `day.v` actually reads at 9:31-9:44 (0 vs
  pre-market-inclusive) — OPEN QUESTION for a live check.** Either way the value is ~15-17 min
  stale; only the *magnitude* of the distortion is unverified.

**Design**: Pass 2 refreshes volume, but the fix is **its own toggle, flipped separately from the
gap** (change isolation — the magna53 SSoT precedent of deploying grounded-grade and materiality
one cycle apart so each is verified alone):

- **Option A (free)**: use the snapshot's `daily_bar.volume`. Problem: Alpaca daily-bar
  extended-hours/pre-market inclusion semantics are **unverified** (OPEN QUESTION — verify live
  against known tape), and the session anchor needs cumulative-from-9:30 specifically.
- **Option B (recommended, +1 call, exact semantics)**: one batched multi-symbol
  `StockBarsRequest(symbol_or_symbols=[superset], timeframe=Minute, start=<4:00 or 9:30 ET>,
  end=now, feed=get_data_feed())` — the exact pattern of `get_minute_bars_window`
  (alpaca_client.py:700-744) but multi-symbol. Summing per symbol gives the *correct* pm-anchor
  (from 4:00) and session-anchor (from 9:30) cumulatives for `compute_rvol_at_time`, with no
  semantics guesswork. ~15 min × ~30 symbols ≈ 450 bars — one page.

In shadow (§9), Pass 2 computes rt volume via Option B and logs `(polygon_vol, alpaca_vol,
would_rvol_gate_flip)` without acting. The volume flip gate is separate: only after the shadow
shows the rt numerator is sane vs baselines AND quantifies how many false RVOL rejections the
delayed numerator causes. If the shadow shows ~0 effect, check the instrumentation before closing
(memory: shadow-zero-effect-check-instrumentation) — the acting population here is small by
construction.

**Gap-only would still be shippable**: the gap is the binary floor that creates the IREN miss; the
RVOL distortion *biases* but has the baseline-missing silent-pass fallback (minute_volume.py
docstring: no baseline → gate passes). Ship order: gap flip first, volume flip second, both
measured by the same shadow.

---

## 4. Q3 — prev_close consistency

`gap = (price − prev_close)/prev_close`. Pass 1 uses Polygon `prevDay.c` (ep_detector.py:1605);
Alpaca's snapshot carries `previous_daily_bar.close`. Two rules:

1. **One authoritative denominator: Polygon `prevDay.c`, for BOTH passes.**
   `rt_gap = (alpaca_latest_trade − polygon_prev_close) / polygon_prev_close`. Rationale:
   - Every downstream consumer already keys off it: the scan-log `prev_close` column (1808), ADV$
     math (1436-1437), the extension check against `mi_daily_closes` (1969-1977), 3-month momentum
     (2909-2913). Swapping denominators mid-pipeline would fork "prev_close" into two meanings.
   - The shadow's measured `rt_gap − delayed_gap` delta must isolate the NUMERATOR (price
     freshness). A mixed denominator conflates feed lag with reference disagreement and poisons the
     flip-gate evidence.
2. **Cross-check, fail-safe drop.** Pass 2 compares `alpaca previous_daily_bar.close` vs
   `polygon prevDay.c`. If they disagree by more than **0.5%** (tolerance for late prints /
   consolidated-close nuances; splits and symbology mismatches blow far past it):
   - emit `ep_rt_prev_close_mismatch` (audit row, deduped per ticker/day via the
     `_audit_dedupe_check` pattern), and
   - **do NOT apply the rt override for that ticker** — fall back to the delayed gap
     (`price_source='polygon_delayed_fallback'`). A mismatched reference is more dangerous than
     staleness: a split-day mismatch manufactures a phantom ±50% gap. Fail direction = today's
     behavior.

Notes: Polygon snapshot values are session-raw (not back-adjusted), as are Alpaca snapshot bars —
on non-split days they should agree to the cent (**ASSUMPTION — the shadow's mismatch-rate metric
verifies this empirically; flip gate requires <0.5% mismatch rate with all mismatches explained**).
Class-share symbology (BRK.B vs BRK-B) is moot: the Pass-1 loop already skips any ticker containing
`.` (ep_detector.py:1590).

---

## 5. Q4 — Code insertion design

### New fetcher — lives in `collector.py`, NOT in `broker/`

Boundary precedent: intelligence code stays broker-import-free
(execution_client.py:286-300 — `get_data_feed_name` lives on the facade precisely so intelligence
can resolve the feed without a broker import), and collector.py **already** imports the alpaca-py
data SDK directly with paper credentials for `get_alpaca_news` (collector.py:521-580: NewsClient,
`ALPACA_PAPER_API_KEY` fallback chain, sync call via `run_in_executor`, returns `[]` on any
failure, never raises). Mirror that exactly:

```python
# collector.py (NEW — sketch, not code to ship)
async def get_alpaca_snapshots_batch(tickers: list[str]) -> dict[str, dict]:
    """Real-time SIP snapshots for a bounded symbol list (EP Pass 2).
    Batches at <=100 symbols/call. Returns {ticker: {price, price_ts,
    prev_close, day_volume, minute_volume, ...}}. {} / missing tickers on
    failure — NEVER raises (Pass-2 caller degrades per §6)."""
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockSnapshotRequest
    from alpaca.data.enums import DataFeed
    from agents.market_intelligence.execution_client import get_data_feed_name
    feed = DataFeed.SIP if get_data_feed_name() == "sip" else DataFeed.IEX
    # module-level client singleton, paper creds (same chain as get_alpaca_news)
    # per batch: asyncio.wait_for(loop.run_in_executor(None, client.get_stock_snapshot, req),
    #                             timeout=EP_RT_BATCH_TIMEOUT_S)  # 4s, 1 retry
```

(Optionally also `get_alpaca_minute_volume_batch(tickers, anchor_start_et)` for the Option-B volume
path — same file, same idioms, multi-symbol `StockBarsRequest`.)

tz discipline: all timestamp handling via `ZoneInfo("America/New_York")` (`_ET` is already at
collector.py top); no naive `datetime.now()` — deploy gate `[5h/7]` enforces this.

### `run_ep_scan` changes (ep_detector.py)

**(a) Pass-1 threshold seam** — line 1626 becomes:

```python
if gap_pct < _pass1_gap_floor():   # MIN_GAP_PCT when hybrid off; superset when on
    continue
```

with `_pass1_gap_floor()` reading `EP_RT_PASS2_ENABLED` + `EP_PASS1_SUPERSET_GAP_PCT` (module
constants, env-overridable — the exact `EP_MIN_GAP_PCT` pattern at 87-91). The candidate dict
(1648-1658) gains `"gap_pct_delayed": round(gap_pct, 2)` and `"price_source": "polygon_delayed"`.
All OTHER Pass-1 filters (symbol/type 1590-1603, prev_close 1605-1607, prev_volume 1610-1612) run
unchanged BEFORE the gap check, so the superset widens only the gap gate.

**(b) Pass-2 block** — inserted between the loop end (1660) and the sort (1662), so the sort,
`rank_by_gap` (1663-1664), and the top-20 cap (1840) all operate on the authoritative gap:

```python
candidates = await _apply_realtime_pass2(candidates, now_et)   # NEW
candidates.sort(key=lambda c: c["gap_pct"], reverse=True)      # 1662, unchanged
```

`_apply_realtime_pass2` (new function in ep_detector.py, wholly wrapped — §6):

1. If `EP_RT_PASS2_ENABLED` is false → return candidates unchanged (byte-identical today-path).
2. `snaps_rt = await get_alpaca_snapshots_batch([c["ticker"] for c in candidates])`.
3. Per candidate with a usable rt read: prev_close cross-check (§4) → `rt_gap` → set
   `c["gap_pct_rt"]`, `c["rt_price_age_s"]`, `c["prev_close_alpaca"]`.
4. `authoritative = await get_runtime_toggle("ep_rt_gap_authoritative", "EP_RT_GAP_AUTHORITATIVE", default=False)`
   (db.py:3077-3106 — mi_safeguard_state row overrides env, 60s cache, fails open to the env value;
   env default false → any toggle-read failure degrades to shadow, i.e. today's behavior).
   - **ON**: `c["gap_pct"] = c["gap_pct_rt"]`, `c["price_source"] = "alpaca_sip"`.
   - **OFF (shadow)**: `c["gap_pct"]` stays delayed; rt fields ride along for logging only.
5. Volume refresh under its own `ep_rt_volume_authoritative` toggle (§3): recompute
   `c["today_volume"]`, `rel_volume`, `projected_vol_multiple` from the rt cumulative; in shadow,
   log-only fields (`today_volume_rt`).
6. **Re-apply the REAL floor to the authoritative gap**: drop every candidate with
   `c["gap_pct"] < MIN_GAP_PCT`. In shadow mode the authoritative gap is the delayed one, so all
   superset-only admissions (delayed < 10%) are dropped here → **the live cohort in shadow is
   byte-identical to today's**, and `rank_by_gap`/top-20 are unchanged. Post-flip, this same line
   is what drops rt-confirmed-below-10 names (the stale-false-admit cleanup).
7. Floor-flip logging (both modes): where delayed and rt disagree about the 10% floor, append a
   scan-log row via the existing `_log_filtered`/`_scan_row` machinery (1802-1826) with
   `filter_reason` like `rt_floor_flip: rt 10.8% vs delayed 8.9% (shadow — not admitted)` /
   `below 10% floor on rt gap (delayed 10.4%)`, and emit `ep_rt_floor_flip_up` /
   `ep_rt_floor_flip_down` audit events (deduped per ticker/day). Log ONLY the flip class — not the
   whole superset — to keep `mi_ep_scan_log` volume sane (~0-5 rows/tick, vs 10-40 if we logged
   every superset name every tick).

**(c) Downstream flow — already correct with zero changes**:
- `_score_ep(gap_pct=c["gap_pct"], …)` (2916-2926) scores the rt gap.
- `_scan_row` (1802-1821) writes `c.get("gap_pct")` → the logged gap is the DECIDED gap; new
  nullable columns (§8) carry `gap_pct_rt` / `gap_pct_delayed` / `price_source` / `rt_price_age_s`
  so both readings are always auditable.
- `insert_ep_alert` (3149-3171) persists the rt gap on the alert row.
- The scheduler's HIGH→ORB decision (scheduler.py:917-1010) reads `score_tier` off the returned
  results — computed from the rt gap. The window check itself (893: `hour == 9 and minute < 45`) is
  untouched. IREN-class timeline post-flip: real cross ~9:32-9:35 → caught at the 9:35 or 9:40 tick
  → `within_orb_window` true → `new_highs_post_open` → `trigger_orb_entry` (1002-1004). In-window.
- The gap-dependent per-candidate logic that runs between Pass 2 and scoring — cooldown bypass
  `gap_pct >= 15` (1913), `_is_cooldown_resetup` (1943), earnings override `gap_pct >= 10` (2946),
  tape-conviction shadow (3034) — all read `c["gap_pct"]` and therefore all operate on the
  authoritative value automatically. This is correct: those thresholds should see the real gap.

**Residual timing gap (surfaced, not silently accepted)**: the scan cadence is */5 (scheduler.py
cron 4998-5011: 7:00-9:55 every 5 min, plus the 9:31 tick at 5015-5021). A cross at 9:41-9:44 is
first seen by the 9:45 tick, where `within_orb_window` is already false → still
`WINDOW_OUT_OF_ORB`. Effective new coverage = crossers visible by the 9:31/9:35/9:40 ticks.
**Operator fork (not pre-decided here)**: add a 9:43 (or 9:42+9:44) scan tick to shrink the blind
tail vs accept it. Costs one more scan cycle; entry-timing adjacent → operator's call at sign-off.

---

## 6. Q5 — Failure handling (critical)

Principles: the scan must NEVER break; degraded = **exactly today's behavior** (delayed data, 10%
floor); degraded must be LOUD-but-deduped, never silent.

1. **Fetcher never raises** (`get_alpaca_snapshots_batch`): per-batch
   `asyncio.wait_for(run_in_executor(...), timeout=4s)` + 1 retry; total Pass-2 wall-clock hard
   ceiling ~10-12 s worst case (§7); any batch failure → those symbols absent from the result.
2. **Per-ticker fallback**: candidate missing from the rt result (or prev_close mismatch, or
   sanity-clamp trip) → keep the delayed gap, `price_source='polygon_delayed_fallback'`. Visible in
   every scan-log row; no per-ticker alert.
3. **Superset admissions REQUIRE rt confirmation**: with the authoritative toggle ON, a candidate
   whose delayed gap < `MIN_GAP_PCT` and whose rt read failed is **DROPPED** at the floor step —
   the superset is only ever valid paired with a real-time confirmation. (Without this rule, a
   fetch outage would silently admit 6-10% delayed-gap names — a detection loosening nobody
   approved.) Names with delayed ≥ 10% proceed on the delayed value exactly as today.
4. **Whole-scan degradation**: if the entire Pass-2 batch fails on a tick (timeout/auth/outage):
   - `log_audit_event("ep_rt_pass2_degraded", f"EP scan tick ran on DELAYED data — {err}",
     json{tick_et, superset_count, error_class, authoritative})` — one durable row per degraded
     tick (audit-only per the Telegram-reserve rule; it's self-healing/transient at tick
     granularity).
   - `maybe_alert_api_failure("alpaca", e, context="ep_rt_snapshot")` — the established #370
     input-side idiom (alpaca_client.py:266-267, collector.py:88-89): immediate Telegram, deduped
     per error-class ~6h, so a SUSTAINED outage is loud without per-tick spam. We KNOW detection
     ran delayed; the operator knows within one dedup window.
   - The L2 anomaly layer picks up `ep_rt_pass2_degraded` event-count spikes automatically (new
     event types enter the 30d baseline machinery); the weekly review sees it via event counts.
5. **Outer belt**: the entire `_apply_realtime_pass2` body is wrapped so any UNEXPECTED exception
   logs + returns the candidates with delayed values intact (after applying the plain
   `MIN_GAP_PCT` floor). The existing `ep_scan_failed` handler (scheduler.py:1012-1040) remains the
   last-resort backstop, but Pass 2 must never be what trips it.
6. **Fail directions, stated**: authoritative-toggle read failure → env (default off) → shadow →
   today's behavior. rt fetch failure → delayed + audit + deduped alert. prev_close mismatch →
   delayed for that ticker. Every failure path converges on the pre-change system.

---

## 7. Q6 — Latency budget

- Cadence: */5 ticks 7:00-9:55 + the 9:31 tick (scheduler.py:4998-5021); scan stops at 10:00
  (5045-5052). ORB-critical ticks: 9:31/9:35/9:40 — a HIGH surfacing there must clear the
  `minute < 45` check (893), which is evaluated AFTER `run_ep_scan` returns.
- Pass-2 cost: ceil(N/100) snapshot calls; N ≈ 12-30 at the 6% superset → **1 call**, ~0.2-0.5 s
  typical (+1 optional multi-symbol bars call for Option-B volume, similar cost). Worst case with
  timeouts/retry: 2 batches × (4 s + retry) ≈ 10-12 s hard ceiling, then degrade (§6).
- Rate limit: ≤3 calls / 5-min tick vs 10,000 req/min plan — ~0.006% of quota. No contention with
  execution-path calls (`get_first_bar` etc. — same 10k/min pool, similarly tiny).
- Perspective: Pass 2 runs BEFORE the scoring loop, whose per-candidate LLM/FMP calls (gather at
  2173-2186, judged post-loop) already dominate scan wall-clock by orders of magnitude. The
  existing code already worries about serial 4s adds near the 9:45 cutoff
  (`_in_orb_cutoff`, 2743-2750) — a bounded ≤1 s typical / ≤12 s worst-case, once per scan (not per
  candidate), is comfortably inside the budget. **Confirmed: 1-2 batched calls fit.**
- Scoring-load note: the superset does NOT widen the scored cohort (floor still 10%, top-20 cap at
  1840); it changes composition only by (a) genuine rt crossers — the target class, ~0-2/day — and
  (b) near-floor flips. FMP/LLM call budget unchanged in expectation.

---

## 8. Schema & event additions

`mi_ep_scan_log` — nullable schema-evolution columns, exactly the established idiom
(db.py:992-998 `ALTER TABLE … ADD COLUMN IF NOT EXISTS`), appended to the
`log_ep_scan_candidates` INSERT (db.py:6201-6225) and `_scan_row` (ep_detector.py:1802-1821):

| column | meaning |
|---|---|
| `gap_pct_rt FLOAT` | Pass-2 real-time gap (NULL when Pass 2 off/failed) |
| `gap_pct_delayed FLOAT` | Pass-1 Polygon gap (always set when hybrid on) |
| `price_source TEXT` | `polygon_delayed` \| `alpaca_sip` \| `polygon_delayed_fallback` |
| `rt_price_age_s FLOAT` | now − latest_trade.timestamp at fetch |
| `prev_close_alpaca FLOAT` | cross-check value (§4) |
| `today_volume_rt BIGINT` | Option-B rt cumulative (volume shadow) |

Existing `gap_pct` column KEEPS its meaning = **the authoritative/decided gap** (delayed in shadow,
rt after the flip) — every existing consumer and outcome-join reads it unchanged.

Audit events (all via `log_audit_event`, ep_detector import at line 56; deduped per ticker/day via
the `_audit_dedupe_check` pattern): `ep_rt_floor_flip_up` (rt≥10>delayed — the IREN class; in
shadow = "would have alerted"), `ep_rt_floor_flip_down` (delayed≥10>rt — stale false-admit),
`ep_rt_prev_close_mismatch`, `ep_rt_pass2_degraded` (per-tick, not per-ticker).

No new table needed: the per-tick rt-vs-delayed record lives in `mi_ep_scan_log` (which already has
per-tick rows + `scan_time_et`), and divergences are audit events — lighter than a
`mi_theme_axis_shadow`-style table (db.py:1110-1157) and joins directly against outcomes. If the
operator wants latest-state-per-day rollups, the `DISTINCT ON` pattern (db.py:6230-6250) already
serves it.

Config surface:
- `EP_RT_PASS2_ENABLED` (env, default `false`; set `true` at Phase-1 deploy) — master: fetch +
  shadow-log.
- `EP_PASS1_SUPERSET_GAP_PCT` (env, default `6.0`; consulted only when Pass 2 enabled).
- `ep_rt_gap_authoritative` runtime toggle / `EP_RT_GAP_AUTHORITATIVE` env (default false) — the
  operator's flip; instant, no deploy (mi_safeguard_state row, ~60s cache lag).
- `ep_rt_volume_authoritative` / `EP_RT_VOLUME_AUTHORITATIVE` (default false) — separate volume
  flip.

Deploy scope: `agents/market_intelligence/` (ep_detector, collector, db, minute-volume seam) →
`bash scripts/deploy.sh market-agent`.

---

## 9. Q7 — Scope: 9M and other consumers of `get_snapshot_all`

**Recommendation: NO real-time treatment for 9M now.** Justification:

- 9M gates are far from the lag's bite: gap ≥ 3% OR intraday gain ≥ 4% (ninem_detector.py:46-63)
  — a 15-min lag rarely flips a 3% threshold decisively the way it flips a 10% floor with a
  9:31-9:44 deadline attached.
- 9M has no in-window entry deadline anymore: 9M as a tradeable ENTRY is deprecated (operator,
  2026-07-16 — Day-2 strategy deprecated); what still runs is condition/cohort detection
  (sugar-baby accrual), whose EOD confirmation path reads settled data where 15 min is immaterial,
  and whose intraday alerts are informational, not order-driving.
- Real money is the priority axis: MAGNA53 EP feeds the ORB order path; 9M does not.
- If a future review shows the 9M intraday alert cadence missing fast movers *worth knowing about*,
  the Pass-2 helper (`get_alpaca_snapshots_batch`) is generic and reusable — a small follow-on,
  filed then with evidence, not built now.

Other `get_snapshot_all` consumers (premarket SPY/QQQ snapshot, overnight watchlist,
`get_premarket_snapshot` at collector.py:885-913): index-level/briefing uses where 15-min staleness
is cosmetic. Out of scope.

---

## 10. Q8 — Rollout: CHANGE_PROCESS, shadow-first, flip gate (THE LINE)

This changes what's detected → what's entered → **real money**. Per CHANGE_PROCESS
(docs/setups/CHANGE_PROCESS.md): SSoT read (done — magna53_ep.md read in full for this design),
change-log entry in `docs/setups/magna53_ep.md` **in the same commit** as the code, evidence before
threshold changes, HARD-gate list review by the operator (rule 3 — the agent does NOT classify the
would-be-alert list), field-validation before live. Reversion-flag: **NEW** (no prior change to the
detection data source; MIN_GAP_PCT itself is untouched — the 2026-05-17 R2 10% decision is
*preserved*, now enforced on truthful data).

### Phase 0 — offline replay (before any deploy)
The §2 calibration replay. Deliverables (docs/analysis/ table, the `476_optionA_backtest` idiom):
superset threshold table; count of historical in-window crossers ("how many IRENs") over 30-60
days; flip-down (stale false-admit) count; the named would-be-alert list for operator review — with
the honest note that if the replay shows ~only-IREN in the window, the operator sees that BEFORE
more build (rigor-before-spend).

### Phase 1 — SHADOW (deployed, N ≥ 10 trading days)
`EP_RT_PASS2_ENABLED=true`, both authoritative toggles OFF. Live behavior byte-identical (§5 step
6 guarantees the shadow cohort == today's cohort). Accrues per tick (~36 ticks/day → 360+ ticks
over 10 days): both gaps + delta on every candidate row; floor-flip events both directions;
prev_close mismatch rate; rt fetch health; volume deltas + would-RVOL-flip counts.

### Flip gate (ALL required; operator sign-off on the packet; agent recommends, operator rules)
1. rt fetch health: ≥99% of ticks non-degraded over the window.
2. prev_close mismatch rate < 0.5% of candidate-checks, every mismatch explained (splits etc.).
3. Sanity: pre-market delta distribution centered ~0 for stable names (a fat median = the rt read
   is broken, not the thesis); no unexplained |delta| > 30pp events.
4. `ep_rt_floor_flip_up` review: the operator reviews the named would-have-alerted list
   (CHANGE_PROCESS rule 3 — HARD-gate list review; agent must not self-classify it as clean).
5. `ep_rt_floor_flip_down` review: confirms the rt path *removes* stale phantom-gap admits (a
   bonus safety improvement, and evidence the rt value is the truthful one).
6. Volume flip additionally requires: rt session-cumulative sane vs `mi_minute_volume_curves`
   baselines; count + named list of RVOL-gate decisions that would change.

### Phase 2 — authoritative flip (gap first; volume separately later)
Operator flips `ep_rt_gap_authoritative` via the mi_safeguard_state row (instant, no deploy).
PLAN.md task goes `deployed` with ETA = next market day; **verify-live** = scan-log rows show
`price_source='alpaca_sip'` on a real scan tick + the first floor-flip case handled end-to-end
(row + event + correct admit/drop) — the operator-facing surface, not just DB data. Instant revert
= toggle off (~60s), full delayed path preserved untouched; env `EP_RT_PASS2_ENABLED=false` is the
deeper kill (removes the fetch entirely).

### Post-flip validation
- 2-week check: join `mi_ep_scan_log` rt columns → alert/entry outcomes; count (a) entries that
  exist only because of rt (the IREN class — did they behave like the HUT class or like chase?),
  (b) alerts suppressed by rt flip-down, (c) degraded ticks. Feed the magna53 change-log entry's
  "shipped + validated against N live sessions" status.
- The SSoT (`docs/setups/magna53_ep.md`) gains a "Detection data source" paragraph (Polygon
  delayed universe screen + Alpaca SIP rt confirm) in the same commit as the code — plus this
  file's change-log entry.

---

## 11. Explicit assumptions & open questions (verify against prod / live API)

**Assumptions (design proceeds on these; each is flagged where used):**
- A1. Polygon delay is uniform ~15-17 min across the snapshot's `min`/`day`/`lastTrade` fields
  (measured for `min.c`; assumed for `day.v`/`min.av`).
- A2. Gap-count ~2× per −2pp threshold (the §2 fan-out table) — replay confirms before the
  threshold is fixed.
- A3. Alpaca SIP `latest_trade` is a faithful "current price" for gap purposes (odd-lot /
  condition-coded prints acceptable at the 30pp sanity clamp) — shadow spot-checks.
- A4. Polygon `prevDay.c` ≡ Alpaca `previous_daily_bar.close` on non-split days — shadow measures
  the actual mismatch rate (flip gate #2).
- A5. alpaca-py 0.43.2's `get_stock_snapshot` accepts ~100-symbol batches in one request (verified
  the request/model shapes locally; the practical batch ceiling is an HTTP-level detail — verify
  with one live call).

**Open questions (could NOT be verified from code — need prod / live API):**
- O1. What does delayed Polygon `day.v` actually read at 9:31-9:44 — zero session volume or
  pre-market-inclusive via `min.av` fallback? Determines how severe the §3 latent RVOL distortion
  already is.
- O2. Alpaca snapshot `daily_bar` semantics pre-9:30 and its volume's extended-hours inclusion
  (decides Option A vs B for volume; B recommended precisely because it sidesteps this).
- O3. Actual candidate counts at 5/6/7/8% on OUR universe (replay, Phase 0).
- O4. Whether `misfire_grace_time`/job overlap policy on the `ep_scan` cron interacts with a
  worst-case +12 s Pass-2 (a 9:40 tick finishing by ~9:43 is still in-window; confirm no
  coalescing surprise).
- O5. The 9:41-9:44 blind tail (§5 residual): does the operator want the extra 9:43 tick? (Fork
  surfaced, not pre-decided.)
- O6. Whether Alpaca snapshot returns entries for every Polygon-listed symbol in the superset
  (symbology coverage) — shadow's `polygon_delayed_fallback` rate measures it directly.

---

## 12. Summary of new/changed surfaces

| Surface | Change |
|---|---|
| `collector.py` | NEW `get_alpaca_snapshots_batch` (+ optional minute-volume batch), get_alpaca_news idioms |
| `ep_detector.py` | `_pass1_gap_floor()` seam at 1626; NEW `_apply_realtime_pass2` between 1660 and 1662; candidate dict rt fields |
| `db.py` | `mi_ep_scan_log` +6 nullable columns; `log_ep_scan_candidates` INSERT extended |
| `docs/setups/magna53_ep.md` | change-log entry + detection-data-source paragraph (same commit) |
| Env / toggles | `EP_RT_PASS2_ENABLED`, `EP_PASS1_SUPERSET_GAP_PCT`, `ep_rt_gap_authoritative`, `ep_rt_volume_authoritative` |
| Audit events | `ep_rt_floor_flip_up/_down`, `ep_rt_prev_close_mismatch`, `ep_rt_pass2_degraded` |
| Untouched | `MIN_GAP_PCT=10.0 ⚠now 9.0`, ORB window 9:31-9:44, `_score_ep` weights, all safeguards, scheduler crons (unless O5 fork approved) |

---

## 13. Verification (Opus, 2026-07-20 — checked before operator review)

Verified against the actual code + a live API spot-check (design proceeds vetted):
- **Reuse patterns exist**: `get_alpaca_news` (collector.py:521, alpaca-py `NewsClient`, paper-cred chain, never-raises) and `get_data_feed_name` (execution_client.py:286). The fetcher can mirror them. ✓
- **Volume-delay finding CONFIRMED (design-critical)**: ep_detector.py:1630 sources `today_volume` from the DELAYED snapshot `day.v`/`min.av`; :1862 passes it into the RVOL@T gate as `today_session_vol`. So the RVOL numerator is ~15-min stale in the 9:31-9:44 window → false `session_rvol_too_low` skips for exactly the fast-mover class the gap fix admits. §3 is real; gap-only would not fully fix IREN's class. ✓
- **A5 batch ceiling**: a single 100-symbol Alpaca SIP snapshot call returns HTTP 200. Caveat: **95/100 symbols returned** — ~5% Alpaca-vs-Polygon symbology gap (obscure names); handled by the §6 per-ticker `polygon_delayed_fallback`, and O6's shadow fallback-rate is the real measurement (matters because superset-only admits require RT confirm → a missing symbol drops a sub-10% candidate). ✓ / flagged
- **A4 prev_close agreement**: 94/95 agreed within 0.5% (~99%); the lone mismatch (LBO, 1.23%) is exactly the case §4 drops to the delayed gap. Fail-safe validated on a live sample (not just asserted). ✓
- **O2 daily_bar volume**: intraday `daily_bar.v` read `None` → validates the §3 choice of Option B (multi-symbol minute-bar sum) over Option A (daily_bar). ✓

Open questions **O1** (delayed `day.v` window severity), **O3** (fan-out on our universe), **O5** (9:41-44 tail fork) correctly deferred to the Phase-0 replay + Phase-1 shadow — they need historical/accrued data, not a live spot-check. No claim in this design was left unverified where verification was possible today.

---

## 14. Phase-0 replay results + operator decisions (2026-07-20)

Replay `scripts/probes/_489_realtime_replay.py` — 25 trading days (2026-06-11 → 07-17), common-stock/ADR
universe (mirrors the `mi_security_types` CS/ADRC gate) + $5M prior-day dollar-volume liquidity proxy
(for the mcap≥$500M / ADV$≥$1M gates) + prev_close≥$5 + prev_vol≥50k, LAG=16min.

- **156 QUALITY in-window crossers missed by the delay (~6.2/day)** — real liquid EP-class names
  (CPNG, INTC, SMCI, WDC, JBLU, NTLA, ENVX, RGTI/QBTS/QUBT, AEHR, OUST…), NOT junk. The bug costs real
  trades. (Raw unfiltered was 497/~20-per-day — inflated by warrants/ETFs the real scan excludes; the
  CS+liquidity filter strips that.)
- **Hybrid coverage by superset** (fraction of the 156 the delayed Pass-1 admits AND Pass-2 confirms at
  an in-window tick — accounts for the delayed feed catching up by 9:40):

  | superset | catches | fan-out/tick p50 / p95 |
  |---|---|---|
  | **5%** | 86/156 = **55%** | 11 / 47 |
  | 6% | 68/156 = 44% | 9 / 36 |
  | 7% | 41/156 = 26% | 8 / 22 |
  | 8% | 19/156 = 12% | 6 / 19 |

- **The structural residual (~45% at 5%)**: names near ~0% (often negative) on the delayed feed at the
  moment they really cross 10% — flat pre-market, exploding after the open. The delayed Pass-1 screen is
  blind to them at ANY superset. The hybrid catches the pre-market-gapper (IREN) class; it structurally
  CANNOT catch the explode-from-flat class. This confirms the §2 "honest residual" and quantifies it.

### Operator decisions (2026-07-20 — locked)
1. **`EP_PASS1_SUPERSET_GAP_PCT = 5.0`** (was Fable's 6.0). Catches 55% of quality misses; p95 fan-out
   47 = one Alpaca batch call.
2. **Ship the hybrid** — cheap, catches the majority-catchable IREN class; accept the residual FOR NOW.
3. **TRACK THE RESIDUAL (mandatory — a first-class deliverable, not optional).** The escalation to a full
   real-time universe is a DATA-DRIVEN decision, so we must instrument the exact cost of the residual.

### 14a. Residual tracker — new component (`mi_ep_delayed_residual`)
An **EOD telemetry job** (post-close ~16:30 ET; reuses the `_489_realtime_replay` delayed-vs-rt logic on
THAT day's minute bars, one day, cheap):
- For every in-window (9:31-9:44) 10%-crosser that the 5% hybrid did NOT catch (delayed <5% at the
  cross) → insert a `mi_ep_delayed_residual` row: `ticker, date, cross_tick_et, rt_gap, delayed_gap`.
- **EP-quality flag**: was it a real EP that would have traded? Join `mi_ep_alerts`/catalyst/news +
  the would-be `_score_ep` grade at the rt gap → `was_ep_quality` (had catalyst + would-grade-HIGH) vs
  `momentum_spike` (no catalyst). Only `was_ep_quality=true` is a real missed TRADE.
- **Forward outcome ("what happens after")**: fwd_1d / fwd_5d / max-favorable return via the existing
  outcome-join (`mi_daily_closes`), populated a few days later — so we see whether the missed EPs were
  winners (real cost) or would-be-losers (no loss).
- **Weekly digest line**: "Delayed-feed residual: N in-window crossers beyond the hybrid this week; M
  were quality EPs; median fwd-5d = X%." This is the escalation dashboard.
- **Escalation trigger (operator-owned)**: a sustained material count of quality EPs missed WITH good
  forward outcomes → move to a FULL real-time universe dataset (full-Alpaca-universe batched snapshots,
  or Polygon real-time). Until then, cheap hybrid + honest instrumentation.

This residual tracker is **independent of the gap/volume flip** — it runs EOD read-only, needs no live
authority, and can (and should) ship EARLY, even during Phase-1 shadow, so we're measuring the residual
from day one. It is the operator's "we absolutely must track it."
