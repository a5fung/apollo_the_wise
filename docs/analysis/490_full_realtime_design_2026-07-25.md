# #490 FULL Real-Time Detection — Design for Operator Sign-off (2026-07-25)

> # ✅ SIGNED BY THE OPERATOR — 2026-07-24 PT (session 7/24-25)
>
> **All six §11 forks ruled, aligned on the recommendations:**
> 1. **Design SIGNED** — §2 prev_close authority (Polygon `prevDay.c` sole denominator, date-keyed
>    Alpaca cross-check) + §3 tick-quality Q1-Q4 (incl. mandatory bar corroboration for any RT-only
>    admission, and replacing the 30pp clamp that would have rejected the NVVE +95% class) + §5
>    architecture. **Build RT-1.**
> 2. **9:43 tick — YES**, added at RT-3.
> 3. **Shadow duration — whichever is LONGER**: ≥10 trading days AND ≥5 residual-class catch days.
> 4. **Shadow surfacing — DIGEST ONLY** (upholds the 7/21 noise ruling; no per-catch Telegram).
> 5. **Batch — 100/call now**, probe 200 in RT-0 before adopting.
> 6. **§9.4 O-9 disposition APPROVED** — retire it as an escalation trigger + rebase its columns to
>    the cross basis, folded into RT-1.
>
> Still NOT authorized by this signature: the RT-3 authoritative flip, the RT-5 volume flip, and any
> deploy. Those remain separately operator-executed per the cutover ladder.

**Status**: SIGNED 2026-07-24 → RT-1 dark build authorized. No code changed by this doc. Detection-criterion change on the money path (THE LINE):
every authority flip is operator-executed; CHANGE_PROCESS gates every phase; nothing here is
self-authorizing. This doc **supersedes** `realtime_full_cutover_design_2026-07-20.md` (the Option-A
runbook — its architecture is inherited, its evidence base and prev_close/tick-quality design are
replaced by what was measured 7/24-25) and treats `realtime_detection_feed_design_2026-07-20.md`
(the #489 hybrid) as the shipped substrate. The operator has already ruled full-RT the priority
("there isn't a rational reason to not use real-time data when we are trading real-time"), so the
old O-9 escalation trigger is no longer the gate — §9.4 disposes of it.

**One-line architecture**: keep the Polygon delayed snapshot as universe substrate + reference +
fallback; overlay real-time Alpaca SIP prices on the full ~3,325-ticker reduced universe at every
scan tick; Polygon `prevDay.c` stays the sole gap denominator; new tick-quality + prev_close
date-keying + halt-quarantine guards make a single RT print safe to decide on; shadow → operator
flip via runtime toggle; 5-rung named rollback.

---

## 1. What was measured 2026-07-21..25 (prod, read-only) — and what it changes

### 1.1 Feasibility measurements (confirm the 7/20 plan, with better numbers)

| # | Measurement | Value | Design consequence |
|---|---|---|---|
| M1 | `_rt_miss_watchdog` fetches the FULL ~3,325-symbol RT universe every in-window tick, in prod, today (`ep_detector.py:1575-1642`) | ~34 serial Alpaca calls (fetcher chunks at 100, `collector.py:253`) | #490 Pass-0 is already running in observe mode; the build extends a live path |
| M2 | Watchdog end-to-end latency (prod `ep_rt_live_miss` `created_at` vs tick minute: 09:31:04, 09:35:03, 09:40:02, 09:40:06…) | **2-6 s** for Polygon Pass-1 + Pass-2 + full-universe fetch + extension SQL + `check_filters` | The 7/20 doc's biggest open (O-7/A-2, "wall-clock unbenchmarked") is answered by prod data: full-RT fits the tick with an order of magnitude to spare |
| M3 | `ep_rt_live_miss` fires: 8 in 4 days (7/21-24), all liquid real names (AEHR, HAS, LMT, URI, RNG, BAH, SSNC, DLR), all passing the mechanical gates | ~2/day, no junk | The false-positive base rate of RT-vs-delayed crossers **in-window** is clean. ⚠ Scope caveat §1.3-C7: "all in-window" is BY CONSTRUCTION (the watchdog only runs 09:31-09:44) — pre-open RT quality is NOT yet measured, and §2's bug censors the pre-open shadow. The shadow phase (§8) closes this. |
| M4 | `ep_rt_pass2_degraded`: **0 all-time**; prod env verified 7/25: `ALPACA_DATA_FEED=sip`, `EP_RT_PASS2_ENABLED=true`, superset 5.0 | Alpaca fetch health is clean at Pass-2 scale | Failure ladder inherits proven rungs |
| M5 | `mi_ep_scan_log` shadow columns (G1): 1,008 rows last 5d, **0** with `gap_pct_rt`/`price_source` | The 7/20 doc's G1 gap is still open | G1 is REQUIRED RT-1 scope — the shadow gates (§8) need per-row evidence, floor-flip audit events alone under-resolve |

### 1.2 THE key constraint: 190 `ep_rt_prev_close_mismatch` events — root cause PROVEN

4 days of events (7/21-24): 190 total, **189 pre-open**, 74 clustered at the 07:00 tick (the rest
trickle as new tickers enter the superset — per-ticker/day dedupe), 18 events >10% disagreement,
worst 88.8%. Prod join run 7/25 against `mi_daily_closes`:

> **All 190/190 mismatch events have the Alpaca `previous_daily_bar.close` equal (to the cent) to
> the T-2 close — the close of the day BEFORE the prior trading day. 0/190 match the T-1 close.**

So Alpaca's pre-open `previous_daily_bar` is not "noisy" or "unsettled" — it is deterministically
the **wrong day**. Pre-open, Alpaca has no bar for today yet: `daily_bar` still holds YESTERDAY's
completed bar and `previous_daily_bar` holds T-2. Around the open, today's bar begins and both
fields roll forward one day. The magnitudes (up to 88.8%) are just the prior day's move — a gapper
that ran hard yesterday shows a huge T-1 vs T-2 difference.

**Consequence A (design)**: the pre-open constraint is fully solvable with *date-keyed field
selection* (§2) — no vendor is "wrong", the field semantics are window-dependent.

**Consequence B (today's hybrid is pre-open-blind — found bug)**: the Pass-2 cross-check
(`ep_detector.py:1530-1535`) `continue`s on >0.5% disagreement → pre-open, EVERY superset candidate
whose prior day moved >0.5% (most gappers) silently loses its RT read and falls back to delayed.
Fail direction is safe (= today's behavior; no money impact, authority is off), but the pre-open
shadow evidence is heavily censored — visible in the floor-flip counts: `ep_rt_floor_flip_up` 29
RTH vs **2** pre-open; `flip_down` 13 vs 3. The date-keying fix ships in RT-1 regardless of the
cutover, and re-arms real pre-open mismatch detection.

### 1.3 Contradictions found (register / prior docs vs code+prod — per the verify-claims rule)

- **C1 — `ep_rt_gap_clamped` does not exist.** No emitter anywhere in the repo; the 30pp sanity
  clamp (`ep_detector.py:1538-1539`) silently `continue`s. "Zero clamp events all-time" is
  **vacuous** — clamps are invisible. Worse, §3.4 shows the clamp itself is wrong for full-RT.
- **C2 — the extension check does NOT inherit snapshot staleness.** The #490 register says
  "volume, RVOL, $-volume and the extension check all inherit it." Code: the extension gate
  (`ep_detector.py:2205-2210`) computes `(prev_close − MIN(close over ~5d)) / MIN` from settled
  `mi_daily_closes` — deliberately PRE-GAP, no intraday price involved (same in the watchdog,
  :1623-1626). Volume/RVOL/$-vol claims are correct; extension needs **no change** (§6.3).
- **C3 — the O-9 auto-evaluator runs on the known-wrong basis.** `backfill_residual_outcomes`
  (`ep_delayed_residual.py:181-218`) stamps `fwd_1d/5d_pct` vs `baseline_close` = the day CLOSE
  (after the intraday move), and `evaluate_o9_escalation` (:221-238) reads exactly those columns —
  the 16:35 job re-evaluates daily on the flawed metric and will keep Telegram-implying "not
  triggered" against the operator's escalate ruling. The 7/20 "validated: median fwd-5d −11% →
  faders, outcome bar carries it" conclusion rested on this basis. Disposition in §9.4.
- **C4 — G1 still unpopulated** (M5) — the 7/20 doc listed it deferred; it still is.
- **C5 — Pass-2 authority would produce incoherent rows**: `_apply_realtime_pass2` overwrites
  `gap_pct` under authority but NOT `current_price` — an authoritative rt gap would ship alongside
  a delayed price in the alert/scan-log row. Coherence fix folded into RT-1 (§6.4).
- **C6 — minor drift**: 7/20-doc line numbers have moved (`_apply_realtime_pass2` now 1486-1567,
  Pass-1 gap floor :1844); the `ep_scan` cron is `hour="7-9", minute="*/5"` + a 9:31 job — i.e.
  ticks include BOTH 9:30 and 9:31, 37 ticks/day total.
- **C7 — "8 fires ALL in-window" is a code gate, not a data property** (M3 caveat): the watchdog
  returns unless 09:31 ≤ now ≤ 09:44 (`ep_detector.py:1588`).

---

## 2. Deliverable 1 — prev_close AUTHORITY (highest-risk element)

**DECISION: Polygon snapshot `prevDay.c` remains the SOLE gap denominator, in every window,
for every path (delayed Pass-1, RT overlay, Pass-2).** Alpaca's prev-close field is used ONLY as a
cross-check, and the cross-check becomes **date-keyed**, not field-hardcoded.

Why Polygon stays the denominator (unchanged from #489 §4, re-affirmed against the new data):
1. It is **settled prior-day data** — a 15-min-delayed feed's yesterday equals a real-time feed's
   yesterday. The staleness problem #490 fixes lives entirely in the NUMERATOR.
2. Every downstream consumer already keys off it (scan-log `prev_close`, ADV$ math, extension
   check, 3-month momentum). Forking the denominator forks the meaning of "gap" mid-pipeline.
3. The shadow's rt-vs-delayed delta must isolate price freshness; a mixed denominator conflates
   feed lag with reference disagreement.
4. The 190-event cluster **vindicates** this rule: because Alpaca was never the denominator, 4 days
   of wrong-day prev_closes contaminated NOTHING — the guard held. Full-RT keeps that property.

### 2.1 The cross-check, redesigned (fixes the pre-open constraint)

The scan already knows the previous trading date (`prev_close_date` arg / `last_trading_day()`).
The fetcher (§5.1) additionally returns `daily_bar.timestamp/close` and
`previous_daily_bar.timestamp/close`. Cross-check rule, per ticker, any window:

```
alpaca_ref = the bar (daily_bar OR previous_daily_bar) whose bar-date == prev trading date
  — pre-open that selects daily_bar (holds T-1; proven by 190/190 T-2 matches on the OTHER field)
  — post-rollover it selects previous_daily_bar (today's semantics, already validated in RTH)
if alpaca_ref exists and |alpaca_ref − polygon_prevDay.c| / polygon > 0.5%:
    → ticker degrades to delayed gap (exactly today's fail direction) + ep_rt_prev_close_mismatch
if alpaca_ref does not exist (new listing, Alpaca data gap, neither date matches):
    → NO cross-check available: keep Polygon denominator, stamp prev_close_verified=false,
      and any RT-ONLY admission of this ticker additionally requires guard Q3 (§3.3)
```

No clock heuristic, no "is it 9:31 yet" branch — the date does the selection, so the rollover
moment (which is Alpaca-internal and not guaranteed to be exactly 9:30:00) can't bite. Expected
post-fix mismatch rate: ~0 pre-open (the 190 all become clean daily_bar matches) and <0.5% RTH
(the #489 live sample measured ~99% agreement). **A fat post-fix rate is a real data-quality stop
signal again** — the metric regains meaning.

### 2.2 Corporate-action (split) guard — the failure class the 0.5% check really exists for

A split/reverse-split effective TODAY is the one case where "settled yesterday" itself is
ambiguous between vendors and can manufacture a phantom ±50%+ gap. Don't depend on Alpaca fields
for it: one Polygon reference call per morning (`/v3/reference/splits?execution_date=<today>`,
~7:00, cached for the day; Polygon Starter includes reference endpoints). Any universe ticker with
a split effective today → `corporate_action_hold`: **no RT-only admission that day** (delayed-path
semantics + audit event `ep_rt_corp_action_hold`). Cost ≈ one skipped-RT day for a handful of
tickers/year; benefit: the catastrophic-denominator class is excluded by construction. If the
reference call fails: fall back to the 0.5% cross-check alone (today's protection level, loud via
the degrade event).

### 2.3 Tertiary reference (analysis only)

`mi_daily_closes` (internal, nightly, adjusted) is the third opinion — used in the RT-2 shadow
packet to measure 3-way agreement rates (it is how the T-2 proof was run), NOT in the hot path.

---

## 3. Deliverable 2 — TICK-QUALITY GUARDS (single-print safety)

A consolidated 15-min-late snapshot averages away bad prints; a single SIP `latest_trade` does
not. Concrete, measurable guards — all thresholds env-tunable, all rejections LOUD:

The fetcher gains `latest_quote` extraction: `{bid_price, ask_price, bid_size, ask_size, ts}`
(alpaca-py `Snapshot.latest_quote`; same object, zero extra calls).

- **Q1 — NBBO band.** A quote is *valid* if `bid > 0 AND ask > bid` (rejects one-sided, zero, and
  crossed/locked markets — the phantom-cross print vector). The rt price is accepted only if
  within `[bid − max(0.5%·mid, $0.01), ask + max(0.5%·mid, $0.01)]`. Outside the band → the print
  is rejected (likely late-reported, condition-coded, or off-exchange odd print); fall through to
  fresh `minute_bar.close`, else delayed. Band width `EP_RT_QBAND_PCT=0.5` (env).
- **Q2 — freshness pairing.** The band is only authoritative when the quote is fresh: age ≤ 300 s
  pre-open (thin tape quotes update slowly; a stale-but-sane pre-market quote is still the truth)
  / ≤ 30 s RTH. Stale quote → Q1 skipped → Q3 becomes mandatory for admission.
- **Q3 — bar corroboration, REQUIRED for every RT-ONLY admission.** (Extends the shipped
  never-loosen rule `ep_detector.py:1504-1513`.) A candidate admitted only because of its RT price
  (delayed gap below the floor/superset) must ALSO show: `minute_bar` present, `volume > 0`,
  bar age ≤ 10 min, and bar-close gap ≥ `MIN_GAP_PCT − 0.5`pp. Consolidated minute bars exclude
  most condition-coded prints per SIP aggregation rules — a phantom print cannot mint a qualifying
  bar with volume behind it. This is the single strongest guard: **no name enters the scored
  cohort on one print alone.**
- **Q4 — replace the 30pp delta clamp (universe path) with an absolute insanity bound.** The
  shipped clamp (|rt − delayed| > 30pp → silently keep delayed, C1) is calibrated for the Pass-2
  population (delayed ≥5%, so a 30pp delta implies rt ≥35% — rare). At universe scale, delayed can
  be ~0% while rt is legitimately +40-95% — **the clamp structurally rejects exactly the NVVE
  (+95.3% from cross) / TRAX class the cutover exists to catch.** New rule for rt-priced tickers:
  hard-reject only `rt_gap > 200%` or price outside `[0.25×, 4×] prev_close` UNLESS Q1 AND Q3 both
  pass (a real +100% mover has a real NBBO and real printed bars). The Pass-2 delayed-fallback
  population keeps the existing clamp (its calibration there is fine).
- **Every guard rejection emits `ep_rt_tick_quality_reject`** with a reason enum
  (`no_quote | crossed_quote | outside_band | stale_quote | no_bar_confirm | insane_gap`), deduped
  per ticker/day — the C1 silent-clamp lesson mechanized. Shadow phase (§8) reports the per-reason
  reject-rate distribution + the NAMED list of any rejected would-be candidate for operator review
  (CHANGE_PROCESS rule 3 — the agent does not classify the list).

Accepted risk, stated: odd-lot prints *inside* the NBBO band pass Q1 — an in-band odd lot is a
fine price signal for a 10%-floor decision (it cannot move the gap materially by construction of
the band). Measured anyway in shadow via the latest_trade-vs-minute_bar disagreement distribution.

---

## 4. Deliverable 3 — HALT / SSR

Verified: **no halt or SSR handling exists anywhere in detection today** (repo-wide grep; the only
"halt" hits are the unrelated `/pause` trading halt and an anticipation-outcome edge case).

- **SSR: no code, by argument.** Reg SHO Rule 201 restricts SHORT sales below the bid after a −10%
  day. MAGNA53 entries are long-only stop-limit BUYS — legally and mechanically unaffected. SSR
  names are prior-day −10% decliners, near-disjoint from the gap-UP EP class. Cost of modeling it:
  a data feed + state we'd never act on. Revisit only if a short setup ever routes through this
  pipeline. (Stated so the scope-out is a decision, not an omission.)
- **Halts: heuristic quarantine in v1; no halt feed integrated (honest bound).** The detection
  risk is a LULD/news halt freezing `latest_trade` at a stale price — the gap reads frozen-high
  while the name can't trade, or resumes violently. Rule: a ticker is `halt_suspect` at a tick
  when (RTH) its `latest_trade` age > 90 s AND its quote is invalid-or-stale (Q1/Q2 fail), for a
  name that had a fresh print earlier in the same session (per-day in-memory map — distinguishes
  "halted mid-morning" from "just thin"). A halt_suspect ticker **cannot be RT-only admitted that
  tick** (delayed-fallback semantics; audit `ep_rt_halt_suspect`, deduped). It re-admits naturally
  at the next 5-min tick once prints/quotes refresh — post-resume entry then still passes the
  normal ORB mechanics, which are the real backstop (stop-buy only fills on strength through the
  ORB high; 10:00 ET unfilled-cancel; broker-side LULD rejects are the known #475 adjacent class,
  entry-side not detection-side). Shadow counts `halt_suspect` flags; if the class proves material
  the fork "integrate a real halt feed" goes to the operator with data — not silently pre-built.

---

## 5. Architecture + Deliverable 4 — RATE-LIMIT & LATENCY BUDGET

### 5.1 Overlay architecture (inherited from the 7/20 doc §2.1, unchanged in shape)

Polygon `get_snapshot_all()` stays: universe enumeration + `prevDay.c/.v` reference + delayed
price chain (per-ticker fallback). New Pass-0 (`EP_RT_UNIVERSE_ENABLED`): build the RT universe
from the existing non-gap Pass-1 filters (symbol/type via `mi_security_types`, prev_close ≥ $5,
prev_vol ≥ 50k — all prior-day/reference data, so the reduction introduces **zero blind spot**;
verified 7/20, re-verified against `ep_detector.py:1803-1830` where `_rt_universe` is already
built this way for the watchdog), fetch `get_alpaca_snapshots_batch(rt_universe)`, overlay
per-ticker: `price = rt if usable else delayed chain`. RT-priced tickers face `MIN_GAP_PCT`
directly; delayed-fallback tickers keep the hybrid superset floor (a fetch gap degrades a ticker
to today's hybrid, never to blind). Pass-2 accepts the pre-fetched map (no second fetch) and
remains the one place applying the cross-check + floor. The watchdog's separate fetch collapses
into Pass-0 (one universe fetch per tick, not two).

### 5.2 The budget (numbers)

| quantity | value | basis |
|---|---|---|
| RT universe | 3,325 | measured in prod 7/20 (CS/ADRC ∩ close ≥$5 ∩ vol ≥50k) |
| Calls/tick | 34 @ 100/batch (today's fetcher) or **17 @ 200/batch** (200 validated live 7/20) | `collector.py:253`; O-3 |
| Ticks/day | 37 (7:00-9:55 */5 incl. 9:30, + 9:31) | `scheduler.py` crons, C6 |
| Calls/day | ~630-1,260 | above |
| Rate-limit burst | ≤34 calls in a few seconds ≈ **0.3% of 10k req/min** (Algo Trader Plus, already paid) | no contention with execution-path calls (same tiny order) |
| Wall-clock, measured | **2-6 s end-to-end today, serial** (M2 — includes Polygon Pass-1 + DB work) | prod `ep_rt_live_miss` timestamps |
| Wall-clock budget | typical ≤5 s; hard total budget `EP_RT_UNIVERSE_TIMEOUT_S=15` → degrade | per-batch `wait_for` 4 s + 1 retry exists (`collector.py:257-266`); add optional concurrency 5 (`Semaphore`) as margin, default serial = today's proven behavior |
| ORB-critical ticks | 9:31/9:35/9:40 must return before the `minute < 45` check (`scheduler.py:897`) | +2-6 s leaves the 9:40 tick finishing ≈ as today; a worst-case 15 s degrade at 9:40:15 still completes as the hybrid does now. `misfire_grace_time=300`, `max_instances` default 1 — a 15 s overrun cannot skip/coalesce a */5 tick |

### 5.3 Partial-failure semantics (per-ticker fallback ladder — every rung a validated behavior)

1. **Per-ticker miss** (symbology gap ~5% measured, malformed, tick-quality reject, halt_suspect,
   corp-action hold) → that ticker runs the HYBRID path: superset floor + cross-checked Pass-2 rt
   if available, else delayed gap. Stamped `price_source` per row (G1 columns).
2. **Batch failure** (one 100/200-symbol chunk times out twice) → those symbols degrade per rung 1;
   the rest stay RT. Per-tick audit `ep_rt_universe_degraded` {batches_failed, symbols_missing}.
3. **Whole-fetch failure / total budget breach** → the tick runs EXACTLY today's shadow-hybrid +
   `maybe_alert_api_failure("alpaca", e, context="ep_rt_universe")` (the #370 deduped-Telegram
   idiom) — a sustained outage is loud within one dedup window, per-tick blips are audit-only.
4. **Toggle-read failure** → env default (off) → shadow (`db.py:3086-3114` fail-open-to-env).
5. **The never-loosen rule extends**: an RT-ONLY admission REQUIRES a live rt read passing Q1-Q4 —
   a fetch miss can drop a would-be catch (fail-safe, = today's miss) but can never admit a name
   no feed confirmed.
6. **Outer belt**: Pass-0 block wholly wrapped; unexpected exception → hybrid path;
   `ep_scan_failed` (`scheduler.py:1031`) stays the last resort.

---

## 6. Deliverable 7 — the other stale inputs: volume/RVOL, $-volume, extension

- **6.1 Volume/RVOL: IN SCOPE — co-requisite, separate flip.** The flat-premarket class has large
  real session volume the delayed `day.v`/`min.av` (`ep_detector.py:1848`) hasn't seen; the RVOL@T
  session anchor then false-rejects (`session_rvol_too_low`) exactly the names the RT gap admits
  (liquid names have baselines — no silent no-baseline pass). Fix as designed 7/20 §2.4: one
  batched multi-symbol minute-bars call on the **candidate cohort only** (≤~50 syms), summed into
  pm-anchor (04:00) + session-anchor (09:30) cumulatives for `compute_rvol_at_time`. Own toggle
  `ep_rt_volume_authoritative` (change isolation), shadow logs
  `(vol_delayed, vol_rt, would_rvol_gate_flip)` + the named flip list. Ship order: gap flip first,
  volume flip ≥3 market days later.
- **6.2 $-volume / ADV**: ADV is settled prior-day data (no change); today's $-vol follows the 6.1
  volume refresh automatically.
- **6.3 Extension check: NO CHANGE — it was never stale** (C2). It reads `prev_close` vs settled
  `mi_daily_closes` MIN — deliberately pre-gap. Stated so nobody "fixes" it into a live-price
  extension check, which would be a criteria change nobody asked for.
- **6.4 `current_price` coherence (C5)**: under authority, the overlay/Pass-2 must also set
  `c["current_price"] = rt_price` so the alert row, scan-log row, and Telegram render the price
  the decision actually used. Mechanical companion to the gap authority, not a criteria change.

---

## 7. Deliverable 6 — the delayed Polygon path: RETAINED. Why:

1. **It is the failure ladder.** Every rung of §5.3 lands on it; removal converts "degrade to
   yesterday's validated behavior" into "blind tick". As the continuously-exercised fallback
   population it also cannot rot unnoticed.
2. **It is the universe.** Enumeration + `prevDay.c/.v` reference come from the one bulk call;
   Alpaca has no equivalent single-call full-market snapshot on our plan shape.
3. **$0 marginal**: Polygon Starter is retained anyway for grouped-daily (RS universe), minute-bar
   history (residual tracker, backtests), reference/splits (§2.2), security types.
4. **It is the cross-check**: post-flip, `ep_rt_floor_flip_*` rates invert into a permanent
   two-feed data-quality alarm (delayed≈rt within lag geometry; a divergence spike = a feed broke).
5. The **superset floor stays at 5.0** post-flip — it now governs only the delayed-FALLBACK
   population (rung-1 tickers keep hybrid-grade coverage instead of 10%-floor-blind).

Not chosen: Polygon real-time upgrade (Option B, ~$199/mo) stays the pre-approved pivot if shadow
gates fail (coverage <99% liquid-universe, or p95 wall-clock >5 s, or sustained fetch instability)
— unchanged from 7/20 §7, with its known cons (billing-cycle rollback, cross-vendor tape split).

---

## 8. Deliverable 5 — SHADOW → AUTHORITATIVE cutover (named rollback, runtime toggle)

### RT-1 — build + dark deploy (flags off = byte-identical; `deploy.sh market-agent`)
All of: Pass-0 overlay + concurrency option; **date-keyed prev_close cross-check (§2.1 — ships as
a bug fix regardless of cutover)**; split guard (§2.2); tick-quality guards Q1-Q4 + reject events
(§3); halt quarantine (§4); **G1 scan-log population** (`gap_pct_rt/gap_pct_delayed/price_source/
rt_price_age_s` threaded into `log_ep_scan_candidates` — the shadow gates below read them);
`ep_rt_universe_catch` shadow events (rt ≥10 > delayed, not admitted, no LLM spend);
volume shadow (§6.1); `current_price` coherence (§6.4); **cross-basis residual columns** (§9.4);
freeze tests: flags-off byte-identical. Env: `EP_RT_UNIVERSE_ENABLED` (master, default false),
`EP_RT_UNIVERSE_CONCURRENCY=1`, `EP_RT_UNIVERSE_TIMEOUT_S=15`, guard thresholds. Runtime toggles
(`mi_safeguard_state`, ~60 s, no deploy): `ep_rt_universe_authoritative`,
`ep_rt_volume_authoritative` (both default off). SSoT: shadow note only (no criteria change yet).

### RT-2 — shadow validation (≥10 trading days, OR ≥5 residual-class catch days — operator's pick)
Daily proof-join (piggybacks the 16:35 residual job): every `mi_ep_delayed_residual`
`hybrid_caught=false` row on a shadow day must have a same-day in-window `ep_rt_universe_catch`.
**Gate (ALL, operator signs the packet):**
1. Residual-capture ≥95%, every miss explained (symbology/timing/bug — named).
2. Fetch health ≥99% ticks non-degraded; per-ticker fallback <2% on the candidate cohort;
   wall-clock p95 ≤5 s.
3. Post-fix prev_close mismatch ~0 pre-open and <0.5% RTH, every event explained (§2.1) — a fat
   rate is a STOP.
4. Tick-quality reject rate <1% with the per-reason distribution + NAMED rejected-candidate list
   reviewed by the operator (rule 3; agent does not classify).
5. Pre-open floor-flip evidence RE-MEASURED post-C3-fix (the censored data of §1.2-B cannot be the
   sign-off basis): pre-open rt-vs-delayed delta distribution centered ~0 for stable names.
6. The NAMED would-have-caught list (shadow catches) reviewed by the operator (rule 3).
7. Volume shadow: rt cumulatives sane vs `mi_minute_volume_curves`; named would-flip list.
8. ~0 shadow catches → check the instrumentation before concluding (memory:
   shadow-zero-effect-check-instrumentation) — the residual dashboard says the class exists.

### RT-3 — authoritative GAP flip (operator-executed; instant; no deploy)
`mi_safeguard_state` upsert `ep_rt_universe_authoritative='on'` (~60 s cache). Same session:
`ep_rt_gap_authoritative` on (it then governs only the delayed-fallback population). Same-commit
paperwork: `docs/setups/magna53_ep.md` change-log entry (data source: "Polygon delayed reference +
Alpaca SIP real-time universe overlay"; Reversion-flag NEW — MIN_GAP_PCT itself untouched, the
2026-05-17 R2 10% decision is preserved and now enforced on truthful data), PLAN #490 →
`deployed`, ETA = next market day.

### RT-4 — VERIFY-LIVE (the operator-facing surface, not DB rows)
(1) scan-log rows carry `price_source='alpaca_sip_universe'` on a real tick; (2) first rt-only
catch end-to-end: Telegram HIGH fires + an ORB decision row exists (entry or honest skip) —
event-gated wait if no qualifying day, never closed on "deployed"; (3) the residual EOD job
INVERTS into the standing verifier: post-cutover `missed_total` trends → ~0, and any
`hybrid_caught=false` row with no same-day live alert = regression alarm; (4) 2-week watch:
rt-only entries' outcomes, degraded ticks, reject-list review.

### RT-5 — VOLUME flip (operator; ≥3 market days after RT-3; instant; own SSoT line + verify-live)

### Rollback — 5 rungs, each instant + independent; layers ADD, never replace
| rung | action | lands on | latency |
|---|---|---|---|
| R1 | `ep_rt_volume_authoritative` off (SQL) | rt gap, delayed volume | ~60 s |
| R2 | `ep_rt_universe_authoritative` off (SQL) | #489 hybrid (Pass-2 authority if on) | ~60 s |
| R3 | `ep_rt_gap_authoritative` off (SQL) | fully-delayed original cohort | ~60 s |
| R4 | `EP_RT_UNIVERSE_ENABLED=false` (env) | universe fetch dormant; pure hybrid | one restart |
| R5 | `EP_RT_PASS2_ENABLED=false` (env) | byte-identical pre-#489 system | one restart |

---

## 9. Evidence pack for sign-off (recomputed per the #490 DATA WARNING)

### 9.1 The cost of the delay, cross-basis (`cross_px = prev_close × (1 + rt_gap/100)`)
All-time `mi_ep_delayed_residual` (7/09-7/24): 114 delay-missed in-window crossers; 47
`hybrid_caught=false` (the class only full-RT catches). Medians, residual class: cross→close
**−0.6%**, cross→high **+3.4%**. With settled fwd outcomes (last 21d, n=18): median fwd-5d
close-basis −10.5% vs cross-basis −15.6%; median cross→close −2.8%, cross→high +3.5%.

### 9.2 The tail (why medians are not the story — presented, NOT self-classified)
Top intraday-from-cross, all residual-class: NVVE 7/10 **+31.8% cross→close / +95.3% cross→high**;
CLRO 7/15 +5.3%/+32.6%; AEHR 7/21 +13.8%/+14.6% (hybrid-caught); RNG 7/24 +6.8%/+10.7%; QMCO,
OTLY, MXL +2-5% to close. The distribution is the EP shape itself: most crossers fade by the
close, a fat right tail carries. Neither cross→close nor cross→high is ORB-entry P&L — the honest
per-trade measure still needs the exit ladder (stop at ORB low, partials day 3-5). The operator's
escalation ruling stands on the tail + the principle; this section exists so the sign-off sees the
measured base rates too (CHANGE_PROCESS rule 3 — the operator classifies, and rule 1's N≥10 is
met: 47 residual cases).

### 9.3 What full-RT would have done differently, per prod events (4 days)
8 in-window residual crossers (M3) become scoreable candidates at their cross tick; 31
`ep_rt_floor_flip_up` (superset class — hybrid Pass-2 already sees these; RTH-dominant, pre-open
censored per §1.2-B); 16 `ep_rt_floor_flip_down` = stale phantom-gap admits the rt floor would
correctly drop (a selectivity IMPROVEMENT that ships with the same flip).

### 9.4 O-9 evaluator disposition + the cross-basis columns (RT-1 scope, no-money)
Both new columns are derivable in SQL from existing columns — no new data needed:
`cross_to_close_pct = (baseline_close/cross_px − 1)×100`,
`cross_to_high_pct = ((prev_close×(1+day_high_gap/100))/cross_px − 1)×100`; backfill all rows.
The C3-flawed `fwd_1d/5d_pct` writers are re-based to cross_px in the same change (the columns
keep their names, the basis becomes honest), and `evaluate_o9_escalation` — whose purpose
(escalate-to-#490) the operator's ruling has consumed — is **retired as a trigger and re-pointed
as the RT-4 regression monitor** (post-cutover it should read ~0 misses; any sustained nonzero =
the overlay is leaking). It must not keep Telegramming "not triggered" on a dead basis against a
decided question.

---

## 10. CHANGE_PROCESS / THE LINE compliance map

- **SSoT read**: `magna53_ep.md` read in full 7/25 (incl. the 7/24 FL-5 reconcile + #500 entry);
  this change touches DATA SOURCE freshness only — `MIN_GAP_PCT=10.0`, ORB window 9:31-9:44,
  scoring weights, safeguards, sizing: ALL untouched.
- **Reversion-flag**: NEW (first change to the detection data source; extends #489's shipped
  shadow architecture; preserves the 2026-05-17 R2 gap-floor decision on truthful data).
- **Evidence**: §9 (N=47 residual class, prod-measured, cross-basis per the DATA WARNING) + the
  RT-2 shadow packet before any flip (rule 1, rule 5).
- **HARD-gate lists** (rule 3): three NAMED lists go to the operator at RT-2 — would-have-caught,
  tick-quality-rejected, RVOL-would-flip. The agent classifies none of them.
- **Same-commit SSoT** (rule 6): magna53_ep.md change-log entries at RT-1 (shadow note), RT-3
  (authority), RT-5 (volume) — including the still-owed #489 catch-up note (G4).
- **Operator-executed flips only**: RT-3/RT-5 SQL runs on the operator's word; the agent never
  self-flips (THE LINE). Every failure path converges on a previously-validated behavior.
- **No new tracked tasks**: every item above is #490 build scope (RT-1..RT-5), incl. the C3/G1
  fixes and the cross-basis columns — nothing filed separately (board at ceiling).

## 11. Operator decisions requested (forks — not pre-decided)

1. **Sign the design** (§2 prev_close authority + §3 guard thresholds + §5 architecture), or amend.
2. **9:43 tick** (the 9:41-9:44 cadence blind tail — one cron line + one scan's LLM budget;
   full-RT makes it fully effective for the first time). Rec: add it at RT-3. Operator's call.
3. **Shadow duration**: 10 trading days vs event-gated ≥5 residual-catch days. Rec: event-gated
   with a 10-day floor.
4. **Shadow-catch surfacing during RT-2**: audit-only + the existing 10:00 digest (the 7/21
   noise ruling), or per-catch Telegram. Rec: digest only.
5. **Batch size**: 200/call (validated once, halves calls) vs 100 (4 days proven). Rec: 100 +
   concurrency 5; probe 200 in RT-0.
6. **§9.4 O-9 disposition** (retire-as-trigger + rebase columns) — approval to fold into RT-1.

## 12. Assumptions & opens (each verified where possible; rest pinned to a phase)

- **A1** Pre-open `daily_bar` = T-1 close. Evidence: 190/190 `previous_daily_bar`=T-2 implies the
  window shift; direct confirmation = one Monday 7:00 probe reading both bars' timestamps (RT-0,
  five minutes). The date-keyed rule (§2.1) is correct under either rollover timing.
- **A2** `Snapshot.latest_quote` populated for the liquid universe pre-market (alpaca-py 0.43.2
  model field exists; population rate measured in shadow — Q2's stale-quote path covers gaps).
- **A3** 200-symbol batches stable at 17-call scale (one live 200-sym call validated 7/20; RT-0
  probes a full universe pass at 200).
- **O1** Whether Alpaca ever rolls `daily_bar` early/late vs 9:30 in ways that leave BOTH bars
  date-mismatched transiently → §2.1 already fails safe (no cross-check → Q3-required).
- **O2** Halt-suspect base rate (shadow-measured; drives the "real halt feed" fork, §4).
- **O3** Pre-open RT false-positive rate — unmeasured today (C7 + §1.2-B censoring); RT-2 gate 5
  is the measurement.
