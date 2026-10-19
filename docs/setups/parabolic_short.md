# Parabolic Short

**Phase**: Shadow (telemetry-only). Promotion path: `telemetry_review` per `strategies/registry.py`; the SHORT-SIDE ladder (SHADOW → PAPER → live-reduced) is ADR 0020 §4 and starts with the forward shadow below.
**Origin**: Stamatoudis / Quallamaggie methodology — short the climax of a multi-week vertical run, expecting violent mean-reversion.
**Code**: `agents/market_intelligence/parabolic_detector.py` (the detector), `agents/market_intelligence/parabolic_short_shadow.py` (the short-side forward shadow, #314), scheduler 17:15 ET cron `parabolic_scan` (runs both). Tables: `mi_parabolic_candidates`, `mi_parabolic_exclusions`, `mi_parabolic_short_shadow`.

## Definition

A stock that has gone vertically up over weeks (parabolic) eventually exhausts and reverses. Entry on the first confirmed reversal candle after the blow-off top. Asymmetric R:R when timed: stop above the parabolic high, target is mean-reversion crash (often 50-80%+ retracement).

**The setup is short-side only.** Long-side base/breakout patterns (flag continuation, EP) share visual surface features (gap up, big volume, big range) with a parabolic climax candle but are NOT this setup — they belong in `flag_continuation.md` / `magna53_ep.md`.

## Universe / eligibility

- **Liquidity**: dollar volume ≥ $10M today (so the position can be entered + borrowed)
- **Security type**: CS/ADRC only, or unknown (rejects ETFs/funds via `mi_security_types`) — SQL pre-filter, `db.get_parabolic_universe`
- **Price**: close ≥ $5
- **Cap-tier prior-move thresholds** (Qullamaggie):
  - Large cap (≥ $10B): prior_move ≥ 50%
  - Mid cap ($2-10B): prior_move ≥ 100%
  - Small cap (< $2B): prior_move ≥ 200%
- **History**: ≥ 60 prior sessions (need history for SMA-50 + base anchor walk)
- Universe sourced from daily history via a permissive SQL pre-filter (false positives are fine —
  they hit the per-ticker compute and resolve to `unqualified`); per-ticker compute runs under
  `asyncio.Semaphore(10)` bounded concurrency (`_SCAN_CONCURRENCY`, parabolic_detector.py:37),
  not serial.

### HARD-GATE filter: M&A / one-shot-news exclusion (Perplexity)

Climax/anticipation candidates (not `watch` — no Telegram alert, no API spend justified) are run
through `_apply_exclusions` → `_news_check_for_exclusion` (parabolic_detector.py ~509): a Perplexity
query asks whether the move was driven by a buyout/acquisition/merger/take-private/FDA
approval/lawsuit ruling/earnings surprise in the last 30 days. A positive (`is_event_driven=true`)
verdict excludes the candidate from Telegram/alert (row persists with `excluded_reason` /
`excluded_source` / `excluded_detail` in `mi_parabolic_candidates`, so filtered names are still
reviewable). Verdicts cache in `mi_parabolic_exclusions` with a TTL so a repeat scan short-circuits
without another Perplexity call. Fail-open: any Perplexity error or unparseable verdict → do NOT
exclude (noise reducer, not a safety gate).

## Detection criteria (current)

The compute function (`compute_parabolic_metrics`, `parabolic_detector.py:198`) emits a stage per (ticker, scan_date):

### Qualifying gates (all required to enter watch tier)

1. **Liquidity**: today's `close × volume ≥ $10M`
2. **Prior move from base**: `(today_close / base_low) - 1 ≥ cap_tier_threshold`
   - `base_low` = first close ≤ SMA-20 walking back from today, within 60 sessions; or 60d-ago low if no touch
3. **Extension vs SMAs**: `today_close / SMA-50 ≥ 1.50`
4. **Velocity-delta** (parabolic curve, not linear): daily compound rate over 5d > 1.10× daily compound rate over 20d
   - Daily rates: `(1 + roc_n) ^ (1/n) − 1`
   - Threshold 1.10 holds names through 1-2 day pre-climax consolidation (CAR 4/20 had 1.11)

### Burst checklist (≥ 3 of 4 needed for BOTH anticipation and climax — same `burst_score >= _MIN_ANTICIPATION_SCORE` threshold; climax adds the 2 extra hard gates below, not a stricter burst count)

1. `days_up_streak ≥ 3` — consecutive close > prior close ending today
2. `gap_count_3d ≥ 2` — last 3 sessions where open > prior close × 1.01
3. `range_expansion_count_3d ≥ 2` — bar range > prior bar range
4. `vol_expansion_count_3d ≥ 2` — bar volume > prior bar volume

### Climax tier (final stage promotion)

`stage = 'climax'` requires all of:
- Burst score ≥ 3 of 4
- `gapped_today` (today open > yesterday close × 1.02)
- `climax_volume_flag` (today volume = max over last 20 sessions)
- **HARD gate 1**: `days_up_streak >= 3` (parabolic short = vertical multi-day acceleration into climax day; 1-2 up days means flat-base catalyst gap, not exhaustion)
- **HARD gate 2**: `not is_earnings_today` (earnings catalyst is fresh news, not climax exhaustion; AGL/XMTR 5/07 false-climax class)

### Stages

- `unqualified` — any qualifying gate fails. Persisted, no alert.
- `watch` — qualifying gates pass, burst < 3.
- `anticipation` — burst ≥ 3 but climax hard gates fail. Telegram watchlist.
- `climax` — burst ≥ 3 + climax hard gates pass. Telegram trigger candle.

## Short-side forward SHADOW (#314 — ADR 0020 §4, card B3)

**What it is**: the detector's `climax` rows become *episodes*; each is replayed from stored daily bars (`mi_daily_closes`) as the backside-confirmation short ADR 0020 §4 specifies, and the result is recorded in `mi_parabolic_short_shadow`. **No order, no position, no `mi_strategies` write, no sizing** — `risk_fraction` is a recorded number (`RISK_PCT / 2`), nothing is sized from it. The only broker reach is the read-only `execution_client.get_asset` (the #256 W1 facade; deploy gate 5j). B6 (the direction-aware trade lifecycle that the PAPER rung needs) is **not** part of this and is not started.

**Where it runs**: inside the existing 17:15 ET `parabolic_scan` job, after the scan (and its M&A / news exclusions). Isolated: a shadow crash pages on its own and the scan's digest still goes out; a scan crash does not stop open episodes from settling. Every run writes ONE `parabolic_short_shadow_run` audit row (so a quiet night is distinguishable from a night it did not run).

**The episode** (D0 = the climax-flagged scan date; every count is in TRADING rows of `mi_daily_closes`):

| Step | Rule | Source |
|---|---|---|
| Candidate | `stage='climax'` and NOT excluded (`excluded_reason IS NULL`) | detector + `_apply_exclusions` |
| Decide, once, on D0's night | no other episode open on the name (else `episode_already_open`) → market cap ≥ **$250M** else `filter:mcap_too_small` (unknown cap → `filter:mcap_unknown`) → borrow check (`shortable` AND `easy_to_borrow`, plus `active`/`tradable`) else a named `borrow:*` / `infra:*` reason → **armed**. A borrow READ that fails (`infra:`) writes **no row** while a later night can still arm it (retried; counted in the audit row's `deferred`) — the infra row lands only on the last window night | ADR §4 (J4 / J2, "no adds, ever") |
| Geometry recorded for EVERY decision (armed or rejected) | `climax_high`, `climax_low`, `prior_day_low` (= the level in force when the row is written: the climax day's low for an on-time arm, the LAST session's low for a late arm), `atr_14` (flag_detector's ATR, persisted), `stop_buffer = min(3% × climax_high, 0.5 × ATR14)`, `stop_price = climax_high + stop_buffer`, `limit_price` (stop-limit SHORT limit, `stop_limit_buy_price` mirrored), `risk_fraction` | ADR §4 + card B3 data prep |
| Arm window | sessions 1-3 after D0. A resting stop-limit SHORT at the **prior session's low** (it re-sets each session) | ADR §4 |
| Trigger | a session whose low reaches the level; the borrow check is **repeated**; `trigger` row (`triggered`, or `skipped` + reason and the episode closes) | ADR §4 |
| Invalidation | a session that **closes** above the climax high before a trigger → `outcome` `closed_untriggered / invalidated` | ADR §4 |
| Expiry | the 3rd session passing with no trigger → `closed_untriggered / expired_untriggered` | ADR §4 ("3 unarmed days", see Readings) |
| Management | cover **1/3** at the first flush (price one R below the entry); stop trails to the **prior session's high** daily (only ever down); **time stop** at the close of the 5th session held; no overnight hold into an earnings date; **no adds** | ADR §4 |
| Settlement | `outcome` row: `realized_r` (blended: 1/3 at +1R + 2/3 at the exit leg), `exit_leg_r`, `mfe_r`, `mae_r`, `sessions_held`, `flush_taken`, `reason` ∈ `stop / trail_stop / time_stop / earnings_exit` | card B3 |

**Daily-bar honesty** (a daily bar cannot order its own events — every choice is the conservative one, and the ambiguity is a flag, not a hidden assumption). The order is a DAY stop-limit SHORT, stop at the level, limit 0.5% (min $0.02) under it. A session whose low EQUALS the level triggers (a sell-stop fills on a print at its price). Fills, by `detail.kind` on the trigger row: **`intraday`** — the session opens above the level and trades down through it: fill AT the level. **`gap_open`** — it opens at/below the level but inside the limit: fill at the open. **`limit_recovery`** — it opens BELOW the limit: the opening print triggers the stop and the order rests as a limit SELL, which fills at the limit as soon as the session trades back up to it; a session HIGH at/above the limit is therefore a certain fill at the limit (the open is the first print, so the rise happened while the order was live; fixed 2026-10-17 — the first build recorded a no-fill here and re-armed lower). **No fill** only when the open is below the limit AND the high never gets back to it (the arm carries, the level re-sets to that session's low; counted in `gap_skips`). A gap above the stop exits at the open; when one bar could both stop the position out and take the flush, **the stop is assumed first**; a stop-out on the entry session itself exits at the stop and is flagged `entry_day_ambiguous` (the high may have come before the fill). Entry-session excursions: an `intraday` fill came on the way DOWN, so that session's high may predate it and is NOT counted in `mae_r` (a stop-out still floors `mae_r` at the stop distance); a `limit_recovery` fill came on the way UP, so that session's low sat under the limit BEFORE the fill — it gives no `mfe_r`, no flush credit, and sets `entry_day_ambiguous` if it reached the flush level (the flush is still credited on any later session).

**Readings of the ADR the build had to make** (none contradicts the text; each is a constant or one branch — change on the operator's word):
1. **"after 3 unarmed days"** → the arm lives for 3 SESSIONS after D0 and cancels if it has not triggered (armed or not). `ARM_WINDOW_SESSIONS = 3`.
2. **"the break of the prior day's low"** → literal and rolling: the level for each session is the PRIOR session's low (the stop trails the same way). The alternative — fixed at the climax day's low — is stricter on sessions 2-3 only.
3. **"hard time-stop 5 trading days"** → the entry session counts as session 1; exit at the close of the 5th. `TIME_STOP_SESSIONS = 5`.
4. **"first −1R-equivalent flush"** → price one R BELOW the entry (a favourable 1R move for a short): `entry − 1 × (stop − entry)`.
5. **"min(3%, 0.5×ATR14)"** → 3% of the climax high, in dollars, against 0.5 × ATR14, in dollars; the smaller buffer wins. No ATR → the 3% stands alone.
6. **Market cap unknown** → rejected (`filter:mcap_unknown`): the floor cannot be verified, and the floor exists to keep microcap squeezes out.
7. **"1R sized at half the long book's per-trade risk"** → `risk_fraction = constants.RISK_PCT × 0.5` recorded on the arm row. The regime-scaled resolver is NOT applied (the shadow sizes nothing).
8. **Borrow account** → `paper` (the shadow phase resolves to no account; the first real rung is PAPER). Recorded per row as `borrow_acct`.
9. **"no overnight holds through earnings dates"** → `earnings_calendar.is_earnings_day` probed for the day after each held session (and the next NYSE trading day - a Friday before a holiday Monday probes the Tuesday); an earnings print ON the session also exits one night early (the safe direction). A calendar that cannot answer does NOT force an exit — the unknown sessions are listed in the outcome row's `detail`. Limit: yfinance coverage.
10. **One decision per candidate, written once; a failed borrow READ is retried, not recorded** → rows are insert-once, so a row written the night a read failed would forfeit that climax for good although the arm window still has two nights. While a later night can arm the candidate (sessions since D0 < `ARM_WINDOW_SESSIONS − 1`), an `infra:borrow_check_failed` writes NO row, is counted under `deferred` in that night's `parabolic_short_shadow_run` audit row (not `errors` — that pages), and the candidate is retried; the late arm records the level in force. On the last window night the infra row is written. Never "assume easy to borrow". **Known limit:** if the borrow outage covers nights 0 and 1 AND the 17:15 run is missed on night 2, the candidate goes `stale` on night 3 and is dropped with no row at all (the `deferred` entries in the two audit rows are then the only trace) — a double fault, and the stale drop is the pre-existing behaviour for any missed night. **CHANGED 2026-10-17** (was: "no retries"). The TRIGGER-time borrow check is still one decision: a failed read there is a `skipped` trigger row + `trigger_skipped` outcome.
11. **"NO adds, ever" → one open episode per name** → a climax on a name that already has an armed episode with no outcome row (waiting OR held) is rejected `episode_already_open` (geometry recorded, no broker read). The step ADVANCES open episodes first and DECIDES candidates second (oldest climax first), so a prior episode that closes on tonight's own bar — e.g. the next day's climax closing above the prior climax high — no longer blocks. Added 2026-10-17 after the build let two back-to-back climax flags arm two episodes on one name (double-counted N, correlated outcomes).

**Reason vocabulary** (aggregate on `split_part(reason, ':', 1)`): `filter:mcap_too_small`, `filter:mcap_unknown`, `borrow:not_tradable`, `borrow:not_shortable`, `borrow:hard_to_borrow`, `borrow:asset_not_found`, `infra:borrow_check_failed`, `episode_already_open`, `invalidated_before_arm`; trigger kinds (`detail.kind`) `intraday`, `gap_open`, `limit_recovery`; outcomes `invalidated`, `expired_untriggered`, `stop`, `trail_stop`, `time_stop`, `earnings_exit`, `trigger_skipped`, `void_restated` (a split moved the bars under the frozen arm levels — no made-up R across two price scales), `void_replay_mismatch`, `void_bad_geometry`, `void_data_gap` (a 30-day backstop so no episode stays open forever).

**Reading the shadow** (the ladder rung is *N ≥ 30 triggered-and-settled episodes with positive expectancy*; each rung is its own CHANGE_PROCESS + operator sign-off, and PAPER is also blocked on B6):

```sql
-- the funnel: how many climax names reach each step, and why the rest fall out
SELECT row_kind, status, reason, count(*) FROM mi_parabolic_short_shadow GROUP BY 1,2,3 ORDER BY 1,2,4 DESC;
-- the rung's number: settled episodes, and what they paid (realized_r is the blended position R)
SELECT count(*) AS settled, avg(realized_r) AS mean_r, count(*) FILTER (WHERE realized_r > 0) AS winners,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY realized_r) AS median_r
  FROM mi_parabolic_short_shadow WHERE row_kind = 'outcome' AND status = 'settled';
```

## Stage transitions / hysteresis

None currently. Each scan_date computes stage independently from prior scans. Promotion/demotion fires immediately based on that day's data. (Flag continuation has hysteresis; parabolic doesn't.)

## Known limitations / open questions

1. **Pivot anchoring is unstable** (advisor flag 2026-05-08): pivot can walk forward on any new bar that beats prior pivot's high (even by 1¢). For a base making slow higher-highs in tight increments, pivot keeps moving and base never accumulates. The current band-tightening (5% → 2%) helps but isn't the principled fix. **Stable-anchor approach** (once pivot established, only move on strict break exceeding prior pivot's high by N%) is filed for next session. Note: this is `flag_continuation.md`'s issue too — both share the pivot logic.

2. ~~Earnings-day check has fail-soft inconsistency~~ — **resolved 2026-05-08**. All four sites (parabolic, EP boost, EP cooldown bypass, EP MODERATE→HIGH override) now treat yfinance error as "earnings day = True". Defensive direction at each site: parabolic suppresses climax, EP boost fires, cooldown bypasses, override promotes.

## Change log (newest first)

### 2026-10-18 — #704: the void-on-restatement guard reads the splits ingest's recorded verdict first (`db.stored_price_scale`); the data check stays as the catch-all

**Trigger**: the 10-17 /simplify altitude review — three consumers answered "did this split move the stored bars?" three ways; this
one used only the bars (`RESTATE_TOLERANCE` 0.5% on the climax high). His "Aligned, let's do these tmr" 10-17.

**Evidence**: `tests/test_parabolic_short_shadow.py` — a recorded forward and a recorded reverse split (bars restated) void the episode
`void_restated` with the factor in `detail.split_scale`; a recorded PHANTOM changes nothing (the episode runs to its normal
`time_stop`); a split still UNAPPLIED defers the episode (a `deferred` entry `split_unapplied`, NOT an `errors` entry — `errors`
pages) and the next night, once the 17:00 pull has decided, advances it. The ingest's recording is pinned in
`tests/test_split_refetch_covers_stored_history.py`.

**What**: in `_advance_episode`, before the existing check, `stored_price_scale(ticker, armed_on, trade_date)` (the window the arm
levels were frozen in): `1.0` → nothing moved, continue; `None` → wait (or, past the 30-day backstop, `void_data_gap`); anything else
→ `void_restated`. The `RESTATE_TOLERANCE` re-read of the climax high is KEPT behind it as the catch-all for a restatement the split
table never held (a corrected bar), so today's voids are a strict subset of tomorrow's. Back-fill: an outcome-NULL applied row reads
as a real split at the table's ratio - EXCEPT here: when every mover in the window is such a legacy row (`db.split_verdict_recorded`
False) the climax-high re-read decides, as it did before #704, so a legacy PHANTOM (written before the column, indistinguishable from
a real split by the table) does not void an open episode; a legacy row the re-read bears out still voids (`detail.legacy_split_scale`).
A recorded verdict is the ingest's own word and voids without the re-read; `skipped_no_data` is such a verdict and is NOT a phantom (it
is also what a failed Polygon fetch of a real split records, leaving a cliff the climax-high re-read cannot see), so it voids too.

**Anticipated effect**: none on a night with no split. An episode with a recorded phantom is unchanged (it never voided before
either), and so is one whose only movers are legacy phantoms (the review of this change caught that the first draft voided those). A real split now voids by the table even if the re-read were within 0.5% (a 51:50 style split). Shadow telemetry only — no
arm, trigger, stop or sizing rule moved, no order path.

**Reversion-flag**: NEW; not a detection-criterion change. **Status**: DEPLOYED 2026-10-18 (server 25fabf93; `deploy.sh both` + `execution`); verify on the first split night per
#704's PLAN line (ETA 10-23). EXPECT / DONE-WHEN / WOULD-FAIL-IF: CHANGELOG 2026-10-18 (#704).

### 2026-10-18 — DEPLOYED and verified (status superseding the 10-17 entries below)

**Trigger**: the 10-17 entries below carried a build-time status; the OPEN drift check (live_rules) flagged them as the doc's latest word.

**Evidence**: deployed 2026-10-17 22:35 ET as 963a735e (`deploy.sh both`, then `deploy.sh execution` back to back, exit 0), and the
/simplify pass redeployed 2026-10-18 00:25 ET as 61974034. Verified in prod both times: `mi_parabolic_short_shadow` exists, and the facade
borrow read from apollo-market returns AAPL `shortable` + `easy_to_borrow`. Climax baseline read at deploy: 0 non-excluded climax
candidates in the last 30 days, so a night with no arm row is the expected reading until a climax appears.

**Anticipated effect**: none — a status record. The first 17:15 ET run under the shadow is Mon 10-19.

**Reversion-flag**: none.

**Status**: deployed (61974034), awaiting its first real climax episode (#314's DONE-WHEN).

### 2026-10-17 (evening) — /simplify pass: the earnings probe's "next session" is the NYSE calendar's (no detector or threshold change)

The no-overnight-through-earnings probe asked about the day after a held session and "the next weekday"; it now asks about the next NYSE
TRADING day (`trading_calendar.get_market_status`, the calendar `job_recovery._session_opens_on` counts sessions on), so a session before a
holiday Monday probes the Tuesday instead of the closed Monday. Shadow-only (no order, no money); weekends are skipped before the calendar call
(`get_market_status` fails open and would read a Saturday as a trading day), so a calendar error falls back to the plain next weekday, the old behaviour
(test pinned: Friday -> Monday with the calendar library down). Also: the row-params helper is shared with the consolidation-breakout
writers (`db._row_params`). **Reversion-flag**: NEW.

### 2026-10-17 — #314 review round: the stop-limit fill model, one open episode per name, a borrow-read retry (same shadow, before first deploy)

**Trigger**: a review of the unpushed B3 build (seven findings) — one MAJOR (the stop-limit SHORT fill model), six minor. No operator rule changed; this corrects the recorder against ADR 0020 §4's own order ("stop-limit SHORT at prior-day low, limit offset per the existing stop_limit convention") and its "NO adds, ever".

**Evidence**: not a threshold change — no detector criterion and none of the eight ADR-registered constants moved (`check_gate_provenance` green). Reproduced on synthetic bars before the fix: `trigger_fill(140, open 139 / high 141 / low 130)` returned a no-fill although a resting limit sell at 139.30 is certain to have filled on the way back up; two back-to-back climax flags armed two episodes on one name. The tests that locked the old no-fill in were rewritten, not loosened. Mutation-checked (13 new hand-made mutants of the module, all killed).

**What changed**: (1) `limit_recovery` fill (open below the limit, high ≥ limit → fill at the limit) — only a high that never reaches the limit is a no-fill; the entry session of that fill credits no flush / MFE and flags `entry_day_ambiguous`. (2) `episode_already_open` — advance-then-decide, oldest climax first. (3) A failed borrow read at the arm writes no row until the last window night (reading #10 CHANGED from "no retries"); this also heals a deploy gap where the intelligence side runs before the execution route exists. (4) An `intraday` fill's entry-session high no longer feeds `mae_r`. (5) A late arm records the level in force. 

**Anticipated effect**: shadow-only (no order, no money). Episodes whose entry session opens under the limit now enter (at the limit) instead of re-arming lower, so the cohort's entries sit slightly higher and its early-session risk is measured from them; `mae_r` on `intraday` entries reads lower than the first build would have; a name never carries two open episodes; one transient borrow-read failure no longer costs a climax. The funnel query still reads as documented; `deferred` is a new key in the audit row's JSON.

**Reversion-flag**: NEW behaviour on an undeployed recorder — nothing is reverted. Reading #10 (no retries) is the one documented reading this changes.

**Status**: built 2026-10-17 (at build time not yet deployed) — ✅ Confirmed in production 2026-10-17 22:35 ET (963a735e), see the 2026-10-18 entry. The SQL-layer tests (`tests/test_parabolic_short_shadow_pg.py`) need a throwaway Postgres and were not re-run in this round; the round adds no SQL (it reuses `get_parabolic_short_open_episodes`).

### 2026-10-17 — #314: the short-side forward SHADOW (ADR 0020 §4, card B3) — arm / trigger / outcome rows, no orders

**Trigger**: operator "Ok" 2026-10-17 to the recommendation to build card B3 now (the EP-first hold was lifted the same day: other setups may go to shadow on their own evidence; live stays his sign-off). ADR 0020 §4 specifies the short mechanics; the detector has accrued climax rows since 2026-05-01 but nothing recorded what the signed short would have done.

**Evidence**: not a threshold change — NO detection criterion, gate or constant of the detector moved (`compute_parabolic_metrics`, the exclusions and every `_*` threshold are byte-identical). Every number of the new module is ADR 0020 §4 (operator-signed 2026-07-05, Gemini amendments adopted) and is cited verbatim in `scripts/gate_provenance_registry.py` (8 entries). Backtest N/A: CHANGE_PROCESS rule 1 governs threshold changes; this is a recorder, and its output IS the forward evidence the ladder's first rung reads. Verified on synthetic bars (`tests/test_parabolic_short_shadow.py`, mutation-checked: 20 of 21 hand-made mutants killed; the 21st — letting the trailing stop move UP — is an equivalent mutant: a prior-session high at/above the live stop would already have stopped the position out) — NOT yet on live data.

**Anticipated effect**: `mi_parabolic_short_shadow` gains one `arm` row per non-excluded climax candidate on the night it is flagged (armed, or rejected with a named reason), a `trigger` row when the prior-day-low break occurs, and one `outcome` row per episode; ONE `parabolic_short_shadow_run` audit row every 17:15 ET run; ONE extra line in the existing parabolic digest only on a night something armed / triggered / settled. The sample rate is UNKNOWN until the first month: the funnel query above says how many climax names survive the $250M floor and the borrow gate — if it is a trickle, the ladder's N ≥ 30 rung is far off and that is itself the finding to bring to the operator.

**Reversion-flag**: NEW (no prior short-side mechanics; ADR 0020 §4 is the first spec).

**Status**: shipped, awaiting field validation — built 2026-10-17; ✅ Confirmed in production 2026-10-17 22:35 ET (963a735e), see the 2026-10-18 entry. Deploy needs the execution step (`/exec/get_asset` lives on apollo-execution). Open readings of the ADR are listed in the section above for the operator to confirm or change; none blocks the shadow.

### 2026-07-24 — FL-5 reconcile: doc synced to code

Four stale items corrected (no code change): (a) the Burst-checklist header claimed "all 4" burst
items needed for climax — code's climax gate uses the SAME `burst_score >= 3` threshold as
anticipation (`_MIN_ANTICIPATION_SCORE=3`) plus 2 SEPARATE hard gates (days_up_streak, earnings);
the doc's own "Climax tier" section already had this right, only the checklist header contradicted
it — header corrected; (b) cron time "17:25" → **17:15** ET (`scheduler.py` line 5370); (c)
"per-ticker compute serially" → `asyncio.Semaphore(10)` bounded concurrency (`_SCAN_CONCURRENCY`);
(d) added the undocumented universe gates (close ≥ $5, CS/ADRC-only, ≥60 prior sessions —
`db.get_parabolic_universe`) and the Perplexity-based M&A/one-shot-news exclusion
(`_news_check_for_exclusion`, parabolic_detector.py ~509) as a documented HARD-GATE filter (was
entirely undocumented, in violation of the CLAUDE.md hard-gate filter-list rule).

### 2026-05-08 (session 2) — Aligned `is_earnings_day` fail-soft direction across all 4 sites

**Trigger**: Advisor flag 2026-05-08 — three sites (parabolic, EP boost, EP cooldown bypass) had different exception-handling directions (False at all three meant: parabolic permissive / EP boost restrictive / EP cooldown restrictive). Inconsistent and harder to reason about under outage.

**Evidence**: Logical (correctness alignment, no quantified backtest needed).

**Anticipated effect**: on yfinance error, all 4 sites now `treat as earnings day = True`. Direction at each site is the most defensive: parabolic SUPPRESSES climax (no false signal on outage), EP boost FIRES (real EP not missed), cooldown BYPASSES (real fresh signal not blocked), MODERATE→HIGH override PROMOTES (real EP reaches HIGH tier).

**Reversion-flag**: REFINEMENT of the four prior earnings-day check ships.

**Status**: shipped.

### 2026-05-08 — Tightened `_PIVOT_HIGH_BAND` 5% → 2%

**Trigger**: VECO 5/6 went TIGHTENING → unqualified the day before its +25% breakout. Investigation surfaced that pivot logic picked a high-volume DOWN day (5/5, high $52.16) over the actual period max-high day (4/24, high $53.43) because 5/5 had 3.0M volume vs 4/24's 1.5M, and 5/5 was within 5% of max ($52.16 / $53.43 = 97.6%, 2.4% below).

**Evidence**: 30d backtest of 6 pivot-shift cases in qualified candidates: COHU, AMSC, CORZ, FROG, TSHA all had new-pivot 2.6-4.9% off period max — all 5 would be blocked by 2% band. SGML new-pivot 1.2% off max — would still move (legitimate). 5 of 6 cases addressed.

**Anticipated effect**: fewer pivot resets on high-volume non-near-max-high bars; bases accumulate longer; some genuine blow-off shooting-stars >2% off max may be missed (rare — typical shooting star is <1% off max).

**Reversion-flag**: NEW (no prior change to `_PIVOT_HIGH_BAND`).

**Status**: shipped (commit 42993e1), awaiting 5/8+ field validation.

### 2026-05-08 — Restored `days_up_streak >= 3` HARD gate (after same-day reversal)

**Trigger**: User clarified VECO is a long flag/EP setup, not a parabolic short. The original gate's intent — block flat-base earnings gaps — is correct. The earlier same-day revert was based on agent misclassifying VECO.

**Evidence**: User's framing: parabolic short methodology requires multi-day vertical acceleration into climax day; 1-2 up days going in is a flat-base catalyst gap by definition. Re-reviewing the 30d backtest filter list (AGL, AMD, ARM, VECO, OGN, INTC) with this lens, all 6 are flat-base catalyst gaps — not false negatives. The 38% filter rate is correct.

**Reversion-flag**: REVERSAL of same-day revert. Prior reasoning was wrong: agent classified VECO as "correctly flagged climax" without trader-judgment ground truth. Lesson logged in CHANGE_PROCESS.md rule #3: HARD gate filter lists require user sign-off.

**Status**: shipped (commit 80f2535).

### 2026-05-08 — (REVERTED same day) Removed `days_up_streak >= 3` HARD gate

**Trigger**: 30d backtest showed 38% climax filter rate (6 of 16). Agent assessed VECO as a false-negative (Pradeep textbook setup wrongly filtered) → softened the gate.

**Evidence**: 30d backtest filter list, agent classification (without user review).

**Reversion-flag**: REVERTED SAME DAY (commit 035ad85 → 80f2535).

**Status**: reverted.

### 2026-05-08 — Tightened `is_earnings_day` window from ±1 day to {yesterday, today}

**Trigger**: Earnings on `scan_date + 1` cannot have produced today's gap; matching them was over-permissive. Sympathy plays + earnings later in the week could trigger false-positive boost candidates.

**Evidence**: Logical (no quantified backtest — pure correctness fix).

**Reversion-flag**: REFINEMENT of the original ±1 day window from CLAUDE.md 2026-05-05.

**Status**: shipped (commit 035ad85). Not parabolic-specific (also affects EP boost + EP cooldown bypass).

### 2026-05-08 — Added `is_earnings_today` HARD gate for climax tier

**Trigger**: AGL 5/7 (560% prior_move, days_up=2) and XMTR 5/7 (113% prior_move, days_up=3) — both gapped on earnings from tight 3-week bases. Structurally not parabolic shorts (catalyst-driven gaps, not exhaustion).

**Evidence**: 2 case studies (AGL + XMTR). Backtest not run pre-deploy (process gap noted). User's framing endorsed the methodological reasoning.

**Anticipated effect**: earnings-day climaxes filtered. ~14 names per 30d are catalyst='routine' with earnings-boost-eligible structure; subset of those that also pass parabolic gates would have been false climaxes. Exact filter rate not measured pre-deploy.

**Reversion-flag**: NEW.

**Status**: shipped (commit f5d1977). Combined with days_up gate above.

### 2026-05-01 — Initial ship (Stage 1 telemetry, 17:15 ET cron)

**Trigger**: TI1 in `project_trading_ideas_backlog.md`. Implementation per `~/.claude/plans/shiny-mapping-locket.md`.

**Evidence**: Backfill against historical CAR 4/2026 (2 climaxes 4/7, 4/21 matching Mario's tweet timing), GME 1/2021 (3 anticipations during squeeze), NVDA 3/2024 (correctly rejected — not parabolic).

**Status**: shipped (commit per CLAUDE.md). Phase=shadow; no entry pipeline.
