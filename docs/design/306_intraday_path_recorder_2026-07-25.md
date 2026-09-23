# #306 — Intraday Path Recorder (LOG-ONLY shadow) — DESIGN + IMPLEMENTATION PLAN

**Date:** 2026-07-25 (PT) · **Status:** DESIGN — no code shipped by this card; a follow-on card executes §7.
**Parent evidence:** `docs/analysis/306_intraday_partial_analysis_2026-07-25.md` (the n=9 sweep that could not pick a trigger level) · `docs/analysis/503_zero_for_nine_forensic_2026-07-25.md`.
**Consumer:** `data_gated_reviews.yaml::exit_tune_cohort_review` (recurring at n=20/40/60/80/100 closed live trades).
**Rides #306. No new tracked tasks.**

⚖ **THE LINE:** everything below is LOG-ONLY. No order emission, no stop change, no exit-path change, no
strategy parameter. The one prod function this touches (`track_open_position_extremes`) is an
analytics writer; the one decision-adjacent consumer of its output is examined in §4 and shown
value-equivalent. Any future *rule* built on this evidence is CHANGE_PROCESS + operator sign-off.

---

## 1. Goal + scope

**Goal:** capture the minute-by-minute intraday price path of every filled live-table trade
(both account modes), reliably including trades that live and die in under 15 minutes, so the
operator's intraday partial-profit rule (sell ~1/3 at level L, stop to breakeven) can be evaluated
OFFLINE at every future n-gate — over any trigger level, all three bases (%, R-multiple,
ADR-multiple), and any character segmentation — without further production changes.

**Explicitly does NOT do:**
- Does not evaluate triggers, emit orders, move stops, or alert. No trigger level exists anywhere in this design.
- Does not subscribe to any websocket or touch the ORB `bar_stream` (money-path-adjacent; see §3).
- Does not change any schema (no new tables, no new columns — see §5).
- Does not choose the partial rule. That is the operator's, later, on the accumulated evidence.

**Why now:** today's verified finding — `track_open_position_extremes` (order_manager.py:3695)
feeds off `collector.get_minute_bars()` = Polygon `/v2/aggs` (collector.py:478), which on our
Starter plan is ~15–17 min delayed. A trade filled 09:31 and stopped 09:40 never has a single
in-hold bar visible while it is still open, so its path (and its `highest_price_seen`) is never
written. The 9-trade correlation in the parent analysis is exact; CRCL's real +1.62R MFE at
09:37 was invisible to the system.

**⚠ Root cause is TWO defects, not one.** The delay is defect #1. Defect #2 is that the poll
selects **currently-open positions only and never revisits**: even with a real-time data source,
a trade that fills 09:36 and stops 09:39 exists entirely between the 09:35 and 09:40 polls and
is never captured, and every trade loses its final ≤5 minutes of path. The second opinion
(external review) flagged the same hole independently, and it is the exact bug class caught in
#310 (`pivot_stop_shadow`'s `closed_at::date = today` predicate silently dropped 7 of 9 same-day
round trips). Fixing only the data source — the card's framing — still ghosts fast trades.
This design fixes both defects (§3, §4).

### Pre-step (named, Monday RTH — before executing §7)

`scripts/probes/_306_latency_check.py` (read-only, ~30 lines): during market hours fetch SPY
1-min bars once from Polygon (`collector.get_minute_bars`, run in `apollo-market`) and once from
Alpaca (`StockBarsRequest`, `TimeFrame.Minute`, `feed=get_data_feed()` — both containers hold
Alpaca keys; run in `apollo-market` too so one `docker exec` covers both). Print `now_et` minus
newest bar timestamp for each.
- Expected: Polygon lag ≈ 15–17 min; Alpaca SIP lag ≤ ~1–2 min (prod `ALPACA_DATA_FEED=sip`
  verified on both containers; live SIP websocket confirmed PASS in the #488 entitlement probe).
- **If Polygon is NOT delayed:** the delay hypothesis was wrong, but the design stands unchanged —
  defect #2 (open-only selection) fully explains the sub-5-minute blindness and the Alpaca repoint
  is still the right source (real-time, consolidated, aligned with #490's ruled direction). Say so
  in the ship note.
- **If Alpaca minute bars are materially delayed (> ~3 min):** STOP — the design's premise fails;
  report back instead of shipping.

---

## 2. The design decision: record the PATH (confirmed, with two refinements)

The parent's lean — record minute bars, not trigger verdicts — is **correct**, and the external
second opinion concurs. Independent reasons, having actually pushed on it:

1. **Verdict-logging locks in guessed levels.** The n=9 analysis explicitly could not separate
   levels (live and paper cohorts prefer opposite ends of the range; NVCR's 2R ranking rides on
   half a cent). Any hardcoded level list is a bet the evidence refused to make, and re-testing a
   new level means a redeploy. Recorded paths make every level, basis, fraction, and stop
   destination a free offline query, including ones nobody has thought of yet.
2. **A live evaluator captures nothing decision-grade that bars lose** — with two honest
   exceptions, both handled by convention, not by finer data (§2a).
3. **Side-effect payoff:** the same fetch repairs `highest_price_seen`/`lowest_price_seen`
   for fast trades (§4) — the #503 forensic's MFE zeros were partly artifacts of this blindness.

### 2a. The challenges, answered

**Intra-minute tick sequence.** Genuinely lost: if one bar's high crosses trigger L and its low
crosses breakeven, ordering is unknowable from the bar. The answer is a **named, fixed sim
contract**, not tick recording. This design formalizes the parent probe's contract
(`scripts/probes/_306_intraday_partial_sim.py` docstring, "Sim contract") as **the convention
every consumer of this table MUST use**:

- **SC-1 (trigger scan window):** scan starts at the first bar with `t >= filled_at` — the fill
  bar itself is excluded, so an entry-minute spike can't self-trigger.
- **SC-2 (fill price):** a triggered partial fills **AT the trigger price L** — limit-at-level
  assumption, no credit above L. *(The second opinion proposed fill-at-bar-CLOSE/VWAP. Rejected:
  a sell limit at L cannot legally fill below L, so close/VWAP — which can sit below L in a bar
  whose high touched L — simulates an impossible fill and models a market-on-touch order instead.
  Fill-at-L is the correct conservative bound for the limit implementation, credits zero
  improvement, and is what the shipped n=9 numbers already used — changing convention now would
  make future sweeps incomparable with the baseline. Slippage sensitivity for a market-on-touch
  variant is an offline haircut (L − k·range proxy), not a recording change — `vwap` is stored
  per bar for exactly this.)*
- **SC-3 (BE stop):** first later bar with `open <= entry` fills at the OPEN (gap-through), else
  `low <= entry` fills AT entry.
- **SC-4 (same-bar ambiguity):** trigger bar also has `low <= entry` → resolved PESSIMISTICALLY
  (partial fills and remainder scratches that bar) and the occurrence is COUNTED. Empirically ≤2
  cases at only the lowest levels (2%/0.5R) on 41 trades.

Tick/quote-level recording is rejected: it needs a market-data stream consumer on the execution
container (the existing `trade_stream` is order updates, not market ticks; `bar_stream` is
entry-critical ORB machinery a shadow must not ride), for marginal precision the review's own
evaluator cannot consume. If the operator later flips the rule live, the live mechanism reads
live quotes at that point and its first weeks calibrate real slippage — a flip-time concern.

**Minute granularity on a 9-minute trade.** Sufficient, demonstrated: CRCL's whole life was 9
minutes and its +1.62R peak at 09:37 is fully visible in minute bars — that reconstruction IS the
parent analysis. A 9-minute trade yields 9 bars; the trigger question ("did price reach L before
exit, and did it then touch entry") is answerable per SC-1..4. Granularity was never the failure
mode; delay + selection were.

**The "gap-up / above a level in history" variant.** Path recording plus OFFLINE daily structure
answers it; nothing extra to record. Verified against how daily history is actually stored: the
gap-up-open variant (day ≥2 opens ≥G% above prior close) needs prior close + today's open — both
in the recorded path + `mi_daily_closes` (400d retention). As-of-fill structural levels (20d/52wk
highs, base lines) need up to 365d of pre-fill dailies: inside `mi_daily_closes` only while the
fill is ≤ ~1 month old (rolling window), and always available from Polygon's 5-year daily history —
which is exactly how the parent probe computed them (`_306_bars_raw.tsv` includes "daily bars per
ticker entry−400d"). The second opinion's "answerable offline" claim **holds, with the precision
that the durable source is Polygon refetch, not our rolling table.** Also note the analysis's §5
finding: pre-entry structure produced ZERO partials on this cohort for geometric reasons — this
variant is a complement at best, and costs the recorder nothing.

### 2b. The two refinements to the parent's lean

1. **The recorded table is the live-capture layer, not the eternal archive.** "Evaluable offline,
   forever, with no further production change" is true for trigger-fire/MFE questions on the
   recorded window. It is NOT true for (a) counterfactual extensions **beyond the exit day** — a
   BE-stop counterfactual on a winner can survive days past the real exit (paper cohort: scratches
   on day 8), and recording indefinitely past exit is unbounded scope — and (b) horizons beyond
   the 120-day prune (§5). Both are covered by Polygon refetch (complete after the fact; 5-year
   history; the probe's proven fetch path). The review method stays **hybrid-source by design**:
   recorded bars for fidelity where delay blinded us, vendor refetch for depth. Consequence: we
   deliberately record each involved trade's path through **16:00 of its fill/exit days only**
   (post-exit same-day context included — the HUT post-stop re-cross class), never further.
2. **Extremes repair is folded in, not left as a second job** (§4).

---

## 3. Cadence + granularity

**Chosen: 1-minute bars, polled every 5 minutes during RTH (the existing `*/5, hour="9-15"` slot),
window = full day-so-far, plus one 16:10 ET completion sweep.** Reasons, not guesses:

- **A 5-min poll of 1-min bars yields complete 1-min coverage** because each poll refetches the
  full `[09:30 ET, now]` window for its tickers and upserts with `ON CONFLICT DO NOTHING` —
  coverage is a property of the fetch window, not the poll frequency. A missed poll, a restart, or
  an Alpaca hiccup self-heals on the next poll. ≤390 bars/ticker/request — one API call per ticker
  per poll, far under Alpaca rate limits at our position counts (≤5/mode cap).
- **Polling faster adds nothing to the PATH** (the bars are identical whenever fetched, since the
  source is now real-time) — it would only freshen the extremes columns, which no consumer reads
  at minute latency (§4). Keeping the existing cron slot also means zero partition churn
  (`track_position_extremes` is already in `EXECUTION_OWNED_JOB_IDS`, scheduler.py:109).
- **Websocket/tick is not needed for log-only** (§2a) and would couple a shadow to entry-critical
  streams. It is the natural flip-time upgrade if the operator ever arms a live rule
  (`broker/bar_stream.py` already consumes an Alpaca bar stream for ORB candidates — reuse point
  named for that future card, nothing more).
- **The capture-completeness burden moves to SELECTION, not cadence** — the critical predicate:

  > Poll population = trades with `filled_at IS NOT NULL AND (status = 'filled' AND
  > remaining_shares > 0 OR closed_at >= <today 09:30 ET, tz-aware>)`.

  i.e. **open OR closed-today** — a trade that fills 09:36 and dies 09:39 is picked up by the
  09:40+ polls via its `closed_at`; every trade's final minutes are captured by construction. The
  bound is computed in Python with `ZoneInfo("America/New_York")` and compared as TIMESTAMPTZ —
  **no `closed_at::date` casting** (the #310 bug class; also the CLAUDE.md tz rule). Status
  vocabulary is deliberately NOT enumerated for the closed side (`closed_at IS NOT NULL` via the
  `>=` comparison is immune to vocabulary drift; prod today uses `closed`).
- **16:10 ET completion sweep** (one new job): the last `*/5` poll fires 15:55, so bars
  15:55–16:00 and any position closed in that window need one final pass. The sweep re-runs the
  same function with `sweep=True`, which (a) fetches the full `[09:30, 16:00]` day for today's
  population, and (b) for OPEN multi-day positions, checks per-day bar coverage since `filled_at`
  (bounded 30 days, the `backfill_position_extremes.py` cap) and refetches any prior day with
  < ~300 RTH bars — healing restart-day holes. 16:10 sits before the 16:15 post-EOD audit and
  clears the in-memory-buffer warning window concern (it writes DB only, but scheduling it off
  :00–:05 keeps it out of the EOD digest chain's way).

Granularity of the recorded row = the existing `mi_intraday_bars` shape (OHLCV + vwap), one row
per (ticker, minute).

---

## 4. `track_open_position_extremes`: IN SCOPE — subsumed, not merely repointed

The second opinion says "clearly in scope"; agreed, and one step further: **the path recorder IS
the refactored `track_open_position_extremes`** — same function name, same job id, same cron slot.
The body becomes: fetch Alpaca bars per ticker (one fetch) → upsert `mi_intraday_bars` → compute
per-trade extremes from the same in-memory bars → the existing monotonic `LEAST/GREATEST` UPDATE.

Why subsume rather than run two jobs or leave it on Polygon:
- **One fetch, one truth.** Two jobs polling two vendors for the same tickers would eventually
  disagree with each other (Polygon-delayed extremes vs Alpaca-fresh path) — the worst outcome for
  an evidence system.
- **Zero registry churn.** The writer-authorization maps (`scripts/audit_column_writes.py:150-151`,
  `scripts/preflight_db_updates.py:79`) authorize `order_manager.track_open_position_extremes` by
  name; keeping the name keeps them green. The job id keeps its `EXECUTION_OWNED_JOB_IDS` entry and
  its `misfire_grace_time=180`.
- **The closed-today inclusion fixes extremes too:** today the tail minutes of every trade (and the
  entirety of fast trades) never reach the columns. #503-class forensics read those columns.
- Polygon leaves this job entirely — aligned with #490's operator-ruled direction (real-time data
  when acting in real time).

**Correction to the tasking input (verify-against-code):** the claim "`highest_price_seen` is read
by NO decision path" is not accurate. The **time-stop scan** (scheduler.py:1240-1315) uses
`highest_price_seen excursion < +3%` to surface 9M Day 2 meanderer candidates, and the operator's
`/timestop` command (agent.py:2565) re-checks the same discriminator and then submits a real OPG
sell. So the columns gate an **operator-confirmed exit**. This does not block the repoint —
argued, not assumed: the time-stop population is holds ≥ 5 *trading days*, for which a 15-min
source delay is immaterial (every bar has long since been polled; both vendors serve the same
consolidated tape, so values are equal to the tick for that population). The sub-15-minute trades
whose values DO change are closed and can never re-enter the time-stop population. Net behavior
change to time-stop: none. **The ship note must still state this provenance change explicitly**
(an input to an operator-confirmed exit changes source) — THE-LINE hygiene, not a code gate.
The `giveback_floor` hook (exit_logic.py:78) references `highest_price_seen` only in a
future-tense docstring (live wiring "would use") and is default-OFF — unaffected today; if ever
armed it inherits *better* data.

**Two correctness clamps inside the merged function (state them in code comments):**
1. **Recording window ≠ extremes window.** Bars are recorded through 16:00 of the fill/exit day
   (post-exit context is wanted). Extremes must be computed ONLY over `filled_at <= t <= closed_at`
   (or `now` if open) — a post-stop-out pop must never contaminate `highest_price_seen` (HUT
   re-crossed its trigger after its stop-out; the analysis relied on that being excluded).
2. **Keep SC-1's boundary convention** — in-hold filter stays `t >= filled_ms` exactly as today
   (order_manager.py:3746-3751), so recorded extremes stay comparable with all prior values and
   with the sim contract.

---

## 5. Data volume + retention

Measured baseline (prod, read-only, 2026-07-25): `mi_intraday_bars` = 123,532 rows / 79 MB total
relation (~640 B/row incl. PK + ticker index), 347 tickers, spanning 2026-03-24→07-24. **Note the
card's premise is incomplete here:** `_persist_first_bar` writes one 9:30 bar per live entry, but
`backtester/intraday.py::_cache_bars` (line 101) already bulk-caches full-day Polygon minute bars
into this same table — full-day storage in this table is existing, proven practice, and the
recorder's write pattern (`executemany` + `ON CONFLICT (ticker, bar_time) DO NOTHING`) mirrors it.

Recorder ingest: ≤390 rows/ticker/day. Realistic book 1–3 concurrent positions → ~400–1,200
rows/day (~0.25–0.75 MB/day). Worst case (both modes at the 5-position cap, all distinct tickers,
10 tickers) → 3,900 rows/day ≈ 2.5 MB/day ≈ 300 MB per 120-day window — acceptable on Hetzner and
far below the table's existing backtester bursts.

**Retention: keep the existing 120-day prune unchanged** (db.py:6862). The n=60+ reviews will
outlive 120 days, but the recorded bars are a convenience/fidelity layer, not the archive: Polygon
serves the identical consolidated tape for 5 years after the fact, and the review probe already
fetches from it (§2b). Recorded-vs-refetched divergence risk is limited to cross-split adjustment
semantics (Polygon `adjusted=true` vs bars recorded pre-split) — a known, rare edge the review
handles by preferring refetch for any ticker with a corporate action in window. Raising the prune
to 400d (~×3 disk on this table, also retaining backtester bulk longer) buys nothing the refetch
doesn't already guarantee; rejected. No schema change of any kind: the considered `source` column
(provenance) and `adr20_at_fill` column (review convenience) are both rejected as YAGNI — ADR20
as-of-fill is computable offline from vendor dailies per the probe's frozen convention (§8).

---

## 6. Failure modes — every one fails SAFE (log-only, money path untouched)

| Failure | Behavior | Why safe |
|---|---|---|
| Alpaca fetch fails (one ticker) | per-ticker `try/except` logs warning, `continue` — other tickers proceed (current job's exact pattern, order_manager.py:3735-3739) | next poll refetches the full day; nothing partial persists wrongly |
| Alpaca fetch fails (all, e.g. outage) | every poll logs; 16:10 sweep still tries; coverage check emits `path_coverage_gap` audit event (`log_audit_event`, already imported in order_manager) | audit-log-only per Telegram discipline (transient → `mi_audit_log`); Polygon refetch recovers the day offline if ever needed |
| Partial data returned (missing minutes) | upsert what arrived; full-window refetch next poll fills holes; sweep's <300-bars/day check catches persistent gaps | idempotent upsert; gap is visible, not silent |
| Duplicate bars / re-covered minutes | PK `(ticker, bar_time)` + `ON CONFLICT DO NOTHING` | re-polling the same window is a no-op by construction |
| Position closes mid-poll | selection reads `closed_at` at query time; a close between SELECT and UPDATE just means extremes clamp at `closed_at` next poll (monotonic `LEAST/GREATEST` — a re-run can never loosen a value) | no lock needed; writes are monotonic and idempotent |
| Restart mid-day (deploy, crash) | no watermark state exists to lose — every poll refetches day-so-far; sweep heals multi-day holes for open positions | stateless-by-design |
| Job raises unexpectedly | wrapped in `audit_wrap` (existing registration); body also keeps per-ticker isolation | scheduler survives; audit row records it |
| Event-loop stall risk | the Alpaca SDK's `get_stock_bars` is synchronous; the current Polygon fetch is async aiohttp, so a naive swap would ADD blocking to the execution loop during RTH (incl. the ORB window). **Mandate `asyncio.to_thread(...)` around the SDK call** in the new helper | the execution event loop (trade_stream, entries) never blocks on this shadow |
| Feed entitlement regression (SIP → IEX fallback) | `get_data_feed()` reads env; recorder inherits; bars remain real-time but thin | system-wide setting, not recorder-owned; latency probe + coverage audit would surface it |
| Market holiday / no fills today | selection returns open multi-day rows only; Alpaca returns [] for the day; no writes | cheap no-op (current behavior too) |
| DB write fails | logged warning; poll retries in 5 min | idempotent |
| `LIVE_TRADING_ENABLED=false` | job gate returns immediately (existing gate, scheduler.py:1821-1823, kept) | no fills exist to record |

Non-effects, stated: no new writers to any money column (`stop_price`, `hard_stop`, orders);
extremes columns keep their exact writer set; both account modes recorded deliberately (matches
the current job — analytics, not trade-state mutation; the dual-account `account_mode`-filter
invariant governs trade STATE operations, and the per-`id` monotonic UPDATE mutates no state).

---

## 7. IMPLEMENTATION PLAN (for the executing Sonnet card — mechanical)

**Pre-step 0 — Monday RTH latency probe.** Create `scripts/probes/_306_latency_check.py` per §1.
Run: `ssh apollo@87.99.134.162 'docker exec apollo-market python -m scripts.probes._306_latency_check'`
during RTH. Record both lags in the ship note. STOP only if Alpaca lag > ~3 min.

**Step 1 — `broker/alpaca_client.py`: add `get_minute_bars_range()`.** New async helper next to
`get_minute_bars_window()` (line 700 — the existing Alpaca minute-window fetcher; reuse its
request shape and error contract):
```
async def get_minute_bars_range(ticker: str, start: datetime, end: datetime) -> list[dict]
```
- tz-aware ET datetimes in; `StockBarsRequest(symbol_or_symbols=ticker, timeframe=TimeFrame.Minute,
  start=start, end=end, feed=get_data_feed())`.
- **Wrap the sync SDK call: `bars = await asyncio.to_thread(client.get_stock_bars, request)`.**
- Return `[{"t_et": <tz-aware ET datetime>, "open","high","low","close","volume","vwap"}]`;
  `[]` on any exception with `logger.error` (mirror lines 739-744).
- Do NOT modify `get_first_bar` / `_persist_first_bar` / `get_minute_bars_window`.

**Step 2 — `broker/alpaca_client.py`: add `persist_intraday_bars(ticker, bars)`.** Batch upsert:
`executemany` of the exact SQL at `_persist_first_bar` (lines 637-641), `ON CONFLICT (ticker,
bar_time) DO NOTHING`. Errors logged, never raised (mirror `_persist_first_bar`'s contract).
Leave `_persist_first_bar` untouched (entry-path adjacent — do not refactor it to call this).

**Step 3 — `broker/order_manager.py`: rewrite the body of `track_open_position_extremes(sweep: bool = False)`.**
Keep the name and signature-compatibility (new kwarg defaults False). New body:
1. `today_open_et = datetime.now(_ET).replace(hour=9, minute=30, second=0, microsecond=0)`
   (`_ET` already module-level ZoneInfo).
2. SELECT `id, ticker, filled_at, closed_at` FROM `mi_live_trades` WHERE
   `filled_at IS NOT NULL AND ((status = 'filled' AND remaining_shares > 0) OR closed_at >= $1)`
   with `$1 = today_open_et`. **No `::date` casts anywhere.**
3. Group by ticker. Per ticker (per-ticker try/except, `continue` on failure — preserve current
   isolation): `bars = await alpaca.get_minute_bars_range(ticker, today_open_et, now_et)`
   (module already imports `alpaca_client as alpaca` — verify; else match existing import style).
   Skip ticker if `[]`.
4. `await alpaca.persist_intraday_bars(ticker, bars)` — the PATH write (all fetched bars,
   including post-exit same-day bars).
5. Extremes per trade of that ticker: filter `filled_at <= bar.t_et` AND
   (`closed_at is None or bar.t_et <= closed_at`); skip if empty; `period_low/period_high` =
   min(low)/max(high); append `(trade_id, low, high)`.
6. Existing monotonic UPDATE unchanged (lines 3762-3768: `LEAST/GREATEST` with COALESCE).
7. `if sweep:` additionally — (a) re-fetch with `end = 16:00 ET` for today's population (already
   covered by 3 if `now > 16:00`, which it is at 16:10 — so no extra code beyond running the
   normal body); (b) for each OPEN trade with `filled_at < today_open_et`: count recorded bars per
   prior trading day (`SELECT (bar_time AT TIME ZONE 'America/New_York')::date AS d, count(*)
   FROM mi_intraday_bars WHERE ticker=$1 AND bar_time >= $filled_at GROUP BY 1` — AT TIME ZONE
   before the date cast, per CLAUDE.md); for any day `< 300` bars and within a 30-day bound
   (`backfill_position_extremes.py` cap), fetch that full day via `get_minute_bars_range` and
   upsert; (c) if a gap persists after refetch, `await log_audit_event("path_coverage_gap",
   f"{ticker} {day}: {n}/390 bars", ...)` — audit-only, no Telegram.
8. Rewrite the docstring: Alpaca-SIP-sourced path recorder + extremes maintainer; note the
   recording-vs-extremes window distinction (§4 clamp #1) and the open-OR-closed-today predicate
   rationale (#310 class). Remove all Polygon references. Delete the now-unused
   `collector.get_minute_bars` import (keep `et_today` only if still used).

**Step 4 — `scheduler.py`:**
1. Update `_track_open_position_extremes_job` docstring (lines 1812-1832) — Alpaca, path+extremes;
   keep the `LIVE_TRADING_ENABLED` gate.
2. Update the registration comment block (lines 5317-5321).
3. New job function `_position_path_eod_sweep_job()` — same gate, calls
   `track_open_position_extremes(sweep=True)`.
4. Register: `CronTrigger(hour=16, minute=10, day_of_week="mon-fri",
   timezone="America/New_York")`, `id="position_path_eod_sweep"`, `misfire_grace_time=600`,
   `audit_wrap(..., "position_path_eod_sweep")`.
5. **Add `"position_path_eod_sweep"` to `EXECUTION_OWNED_JOB_IDS`** (line ~111) — the partition
   guard fail-louds at split-role boot on any registered-but-unclassified job, and this job needs
   the execution container. `track_position_extremes` is already in the set — no change for it.

**Step 5 — registries sanity (no expected diff, verify):** run
`python scripts/audit_column_writes.py` and `python scripts/preflight_db_updates.py` locally —
the writer name `order_manager.track_open_position_extremes` is unchanged, so both must stay
green. If either flags, STOP and reconcile rather than editing the registry silently.

**Step 6 — tests** (new file `tests/test_track_position_extremes_paths.py`; mock the DB pool +
`alpaca_client` fetch like the existing broker-job tests — see `tests/test_500_price_aware_entry.py`
for the mocking idiom; there is currently NO test covering this function, so this is net-new
coverage):
1. **Selection predicate:** open trade included; trade closed today 09:39 ET included; trade
   closed yesterday 19:59 ET excluded; trade closed today-after-20:00-ET-UTC-rollover still
   included (the #310 regression — build the timestamps so `closed_at::date` in UTC would get it
   wrong, and assert our predicate gets it right).
2. **Fast-trade capture:** fill 09:36 / close 09:39, poll "runs" at 09:40 → bars persisted, extremes
   updated from the 3 in-hold bars.
3. **Recording ≠ extremes window:** post-`closed_at` bar with a higher high is persisted to
   `mi_intraday_bars` but does NOT enter `highest_price_seen`.
4. **SC-1 boundary preserved:** bar at exactly `filled_at` included in-hold (`t >= filled_ms`).
5. **Monotonicity:** second run with narrower bars never loosens stored extremes (LEAST/GREATEST
   semantics — assert via captured SQL params or a fake conn).
6. **Per-ticker isolation:** fetch raising for ticker A still processes ticker B.
7. **Idempotency:** same bars twice → `persist_intraday_bars` called with ON CONFLICT SQL (assert
   SQL contains `DO NOTHING`); no exception.
8. **Sweep gap-heal:** open multi-day trade with a 120-bar prior day → sweep fetches that day;
   persistent gap → `log_audit_event("path_coverage_gap", ...)` called; no Telegram call.
9. **Gate:** `LIVE_TRADING_ENABLED=false` → job body never queries.

**Step 7 — deploy + verify-live ("done" definition).**
- Scopes: `bash scripts/deploy.sh market-agent` AND `bash scripts/deploy.sh execution` (broker/* +
  scheduler.py → deploy.sh's ownership map flags both; the 7/23 #500 mis-scope memory applies).
  **Deploy outside 9:25–10:05 ET and 16:00–17:00 ET** (deploy-timing memory).
- Verify-live next market day (task status `deployed`, ETA = verify date, per CLAUDE.md):
  1. `SELECT count(*), min(bar_time), max(bar_time) FROM mi_intraday_bars WHERE ticker = '<open
     position>' AND bar_time >= <today 13:30 UTC>` — expect a growing full-day spread (not just
     the 09:30 bar), max within ~6 min of the last poll.
  2. If any trade closed intraday that day: its bars exist through 16:00 and its
     `highest_price_seen != entry seed`; extremes ≤ in-hold max (clamp check).
  3. `position_path_eod_sweep` ran at 16:10 (mi_job_runs / audit row) with no
     `path_coverage_gap` events on a healthy day.
  4. Ship note includes: latency-probe numbers (pre-step), and the time-stop provenance note (§4).
- Update the #306 PLAN.md line status per session protocol. **No SSoT setup-file change is
  required** (no detection criterion or safeguard touched); the design doc (this file) is the
  recorder's reference.

Estimated diff: ~60 lines alpaca_client, ~80 lines order_manager (mostly replacement), ~30 lines
scheduler, ~250 lines tests, 1 probe script. No schema change, no new table, no migration.

---

## 8. Evidence produced, mapped to `exit_tune_cohort_review` (n=20/40/60/80/100)

What each review run gets that today's n=9 did not have:

| Review need (YAML items a–d) | Served by |
|---|---|
| (a) per-trade forensic: true MFE-before-exit, exit reason, hold | `highest/lowest_price_seen` now correct for ALL trades incl. sub-10-min holds (extremes clamped to hold window); minute path in `mi_intraday_bars` for exact peak timing |
| (b) intraday partial sweep, any L over %, R, ADR bases | recorded paths (≤120d old) joined in SQL, or the probe's Polygon refetch for older/beyond-exit-day extensions — same consolidated tape; sim contract SC-1..4 (§2a) is the fixed convention, so runs stay comparable across n-gates |
| (c) character segmentation | **ADR20 as-of-fill** computed offline per the probe's frozen convention (mean (high−low)/close over the 20 sessions ending the day BEFORE fill — `flag_detector`'s sourced-range convention, `_HTF_MIN_ADR_PCT` companion at flag_detector.py:724-727); continuous ADR-multiple basis is the primary frame per analysis §4, tiers populate as triggered-n grows |
| (d) holding-period distribution | unchanged source (`filled_at`/`closed_at`); minute paths add time-to-peak (min→peak) per trade |
| gap-up / structural variant (§5 of analysis) | recorded path (open of each day) + daily structure from Polygon refetch / `mi_daily_closes` (§2a) |
| BE-scratch counterfactuals extending past real exit | Polygon refetch (explicit, by design — §2b refinement 1) |

**Contradiction found and reported (verify-against-prose rule):**
`data_gated_reviews.yaml::exit_tune_cohort_review` item (c) instructs "reuse
`pivot_analysis.character_profile`, do NOT invent a parallel taxonomy." Verified against code
(pivot_analysis.py:56): `character_profile()` profiles **MA-respect personality** (home MA,
undercut p80, pullback episode durations) for TRAIL placement — it contains no run-rate/velocity
axis and is the wrong tool for fast/slow segmentation, exactly as the parent analysis §4 already
established. The right key is ADR20 (above). The YAML's prose should be corrected to "segment by
ADR20 per the 306 analysis convention; `character_profile` remains trail-side" — **a one-line
`data_gated_reviews.yaml` edit that is prod config and therefore NOT made by this design card;
flag it into the next session CLOSE / the executing card's commit for operator visibility.**
(The "no parallel taxonomy" instinct in that line survives: ADR20 is an existing convention, not
a new taxonomy.)

**What this shadow does NOT provide (honest gaps, all pre-accepted):** intra-minute ordering
(convention SC-4, counted), real partial fill prices (unknowable without orders; SC-2 bound;
calibrated in the first live weeks IF the operator ever arms a rule), regime interaction at scale
(analysis §6.5 — needs cohort accumulation, which is the entire point of the recurring review),
and per-segment trigger levels before ~20 *triggered* trades per tier (analysis §4).
