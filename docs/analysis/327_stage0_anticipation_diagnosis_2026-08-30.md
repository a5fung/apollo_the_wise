# #327 Stage 0 — why the #270 anticipation machine never settled an outcome, and whether a re-seed fixes it

**Date:** 2026-08-30 · **Task:** #327 (delayed-entry shadow), Stage 0 of the approved plan
(`~/.claude/plans/crystalline-waddling-charm.md`) · **Diagnosis only — no behaviour change, nothing
uncommented, nothing deployed.**

## The decision it serves

Whether the plan's Stage 1 ("re-seed the universe" of `agents/market_intelligence/anticipation.py`)
proceeds, is re-scoped, or the machine is declared unsalvageable for this purpose. The plan's own
words: *"Stage 0 can kill or reshape everything after it, and that is the point of putting it
first."*

## VERDICT: REBUILD (the watch lane), salvaging named parts. A re-seed does not suffice.

The zero-settled record has a mundane cause — **the machine ran for exactly one evaluation cycle,
ever, and was switched off three hours later** — so "re-seed and it will produce rows" is
technically true. But every decision-bearing layer of it answers a question the operator has since
ruled differently: the seed (phantom +40%), the confirm gate (re-gates +40% + SMA200 inside
`replay()`, which ADR 0013 and the golden test both freeze), the entry vocabulary (a day-1 ORB
construct he ruled out for day-2+ on 2026-08-29, plus a reclaim detector whose live semantics are
wrong on every day except the one it was replayed on offline), the management rule (+1R/+3R day-5
harvest vs his 08-30 M-none/M-trail arms), the settlement horizon (5 bars vs the plan's 20
sessions), the notification posture (loud vs his "Silent. Log only." ruling), and the table shape
(one overwriting row per name — the plan's per-fire trigger rows with ex-ante vectors cannot live
in it). Stages 2–3 of the plan already replace the entry and settlement layers; once the plan's own
new tables exist, nothing decision-bearing of this machine remains in the loop. Naming that
honestly: **this is a rebuild that reuses the plumbing, not a re-seed.** Detail in §5.

## Method / population

- **Code:** local checkout @ `17ad12a5` (matches prod server checkout family; LIVE_RULES generated
  2026-08-30 read first). Files: `anticipation.py` (1,405 lines, whole file),
  `scheduler.py:3614-3798, 5425-5447`, `db.py:2150-2260, 9541-9573, 10139-10290`,
  `scripts/_270_entry_replay.py`, ADR 0013, git history of all of the above.
- **Prod (read-only SELECT, captured once):** `mi_anticipation_lifecycle` all 19 rows all-time;
  `mi_job_runs` for the two job ids; `mi_daily_closes` 2026-05-01..2026-08-29 (83 sessions) for
  the gate-volume measurements; `mi_ep_scan_log` same window for the EP-scan comparison.
  Capture: `/Users/alvinfung/.claude/jobs/6b173ac9/tmp/stage0_prod_batch1.txt` (probe SQL:
  `stage0_q1.sql` beside it).

## 1. Why only 19 rows — BOTH causes, measured

**Cause 1 (dominant): the machine ran once.** Prod `mi_job_runs`: `anticipation_readiness` has
**exactly 1 run ever** (2026-06-16 17:35:00 ET); the 3b entry job (`delayed_ep_3b`, pre-rename id)
also **exactly 1 run** (2026-06-16 16:20:00 ET). All 19 rows carry `created_at` 2026-06-16
21:35:01–11 UTC — the single readiness tick — and `updated_at == created_at` on every row: never
touched since. Git: the readiness job was built 06-16 07:51 (`263c62dc`), 3b 08:08 (`d3ff281e`),
renamed 13:23 (`2e5f0a13`), **paused 17:41 PT = 20:41 ET the same day** (`97f9486f`, ADR 0013).
The 19 rows are one run's 25-day seed window. That is the entire operating history.

**Cause 2: the gate is as narrow as reported.** The seed (`db.py:9541-9573`) requires
`close ≥ 1.40×prev_close` AND `vol ≥ 3×ADV20-median` AND `close ≥ $5` AND `$vol ≥ $20M`. Measured
over 2026-05-01..08-29 (83 sessions, `mi_daily_closes`):

| gate (close-to-close gain, same $ floors) | ticker-days (n) | per session |
|---|---|---|
| ≥ 9% | 5,323 | 64 |
| ≥ 15% | 2,162 | 26 |
| ≥ 20% | 1,278 | 15 |
| ≥ 30% | 589 | 7 |
| **≥ 40% (the gate)** | **334** (309 after the 3×ADV20 leg) | **~3.7** |
| EP scan actually sees (`mi_ep_scan_log`, distinct ticker-days) | 3,266 | **39** |

The confirm layer (`replay()`) then re-gates: needs ≥30 bars (`scheduler.py:3648`), **SMA200
computable AND close > SMA200** (`anticipation.py:105-108`) — only 216 of the 309 have ≥200 prior
bars stored. Live outcome of the one run: **19 confirmed rows from a 17-trading-day window ≈ 1.1
per session — about 3% of the EP-scan population, and a different population** (extreme
close-to-close movers, not 9% open-gappers). At that rate the funnel produced 8 armed, **1 ready,
0 triggered per 25 days** — settled outcomes would have accrued at ~0/month even if never paused.

## 2. Why `entry_tactic` is NULL on every row — the entry layer was never reached, and never failed

Three stacked reasons, none a silent failure:

1. The only writer of tactic `anticipation` is `evaluate_candidate`'s mature-coil branch
   (`anticipation.py:594-600`: a coiled day with `base_run ≥ 3` inside the armed window). No name
   in the one run had one — a ≥40% mover printing three consecutive ≤12%-range quiet days above
   its gap-low within 15 sessions is rare by construction.
2. The only writers of `first5_break`/`gdl_reclaim` are in the 3b job
   (`scheduler.py:3744-3755` → `record_anticipation_3b_entry`, `db.py:10247-10261`). **The 3b job's
   single run was at 16:20 ET — 75 minutes BEFORE the readiness job's first-ever write at 17:35
   ET.** Its watch set (`get_anticipation_watch_set`, armed/ready/coiled rows) was empty by
   construction. The entry layer has examined zero names, ever.
3. Since 2026-06-16 20:41 ET, no writer exists at all (both `add_job` blocks commented out,
   `scheduler.py:5436-5447`).

(One premise correction: the table has no CHECK on `entry_tactic` — the
`anticipation | first5_break | gdl_reclaim` vocabulary is a comment on the column
(`db.py:2192`); the CHECK is on `state` only.)

## 3. The one `ready` row is MNTS itself — and it was 5 days stale at birth

`MNTS` gap 2026-05-26 (close 15.48, gap-day low 11.86, 79.8M shares) → armed 06-08 (low 11.80
undercut) → ready 06-11 (close 16.30 > gdl on 21.4M) — the machine's own calibration case,
**derived retroactively in the 06-16 batch run** from full bar history. What the bars did next:
06-12 close 11.95, 06-15 close 10.23 (back **below** the gap-day low), 06-16 close 9.31 — so at
the moment the row was first written 'ready', the set-up it described was already five sessions
old and invalidated. MNTS bled to 4.71 by 07-24 with no new high.

- **Did the code look?** No — 3b detects only on TODAY's minute bars, the row didn't exist until
  06-16 evening (after that day's 16:20 3b run), and the machine was off by 20:41 ET. Zero
  examinations.
- **Would the entry condition have occurred had it looked on time?** Yes, 06-12: the open (13.94)
  was above the gdl, so `detect_gdl_reclaim` fires on the first RTH minute bar
  (`anticipation.py:1324-1332`) and a first-5-min break was likely. Entry ≈ 13.9–14.4, stop 11.86
  → stopped by 06-15 (low 10.11). **The machine's own tactics on its own template stock produce a
  loser, and settlement would have worked** (bars present, window ripe). The zero-settled record
  is an operating-history fact, not a settlement bug — but the trade behind the one ready row was
  a loss either way.

## 4. The "one-block uncomment" — compiles, but is NOT safe, and is not the fix

**Mechanically still true.** Verified against current code: both job functions intact; ids still
in `INTELLIGENCE_OWNED_JOB_IDS` (`scheduler.py:146`); `audit_wrap` imported (`core.job_audit`);
`collector.get_minute_bars` (`collector.py:565`), `SOURCE_ANTICIPATION_REENTRY`
(`stocks_in_play_sources.py:37`), all db helpers present; the table is registered in the
detector-liveness roster (`health_checks.py:1529`). It would run.

**Behaviorally unsafe on four counts:**

1. It resumes the exact phantom +40% universe the pause exists to stop (ADR 0013 §3).
2. It resumes **Telegram pushes** (ARMED transitions `scheduler.py:3695-3701`, 3b entry alerts
   `:3789-3796`) — the approved plan's ruling is *"Silent. Log only."*
3. **Stale-state mistiming:** armed/coiled/ready rows have no expiry path (`replay()`'s EXPIRED
   only exits WATCHED, `anticipation.py:117-123`), so the 8 June armed rows re-enter the 3b watch
   set immediately; any of them trading above its gap-day low today mints a `triggered` entry on
   the first session — a "reclaim" months after the arming context died.
4. **Retroactive derivation:** the readiness re-run re-derives each June row over 340 days of
   bars (`get_anticipation_ohlcv`, `db.py:10139`), minting back-dated ready/triggered states and
   even immediately-settleable outcomes from hindsight — the opposite of live accrual. ADR 0013's
   required archive of the 19 phantom rows (#297) was never done; they are still in the table.

## 5. The settlement path — one bounded abstain, one unbounded

- Tactic `anticipation`: **bounded.** `settle_row` abstains under 5 forward bars but
  `SETTLE_DEGRADE_DAYS=21` forces a degraded settle (`anticipation.py:470-476`). Cannot stick.
- Tactics `first5_break`/`gdl_reclaim`: **unbounded abstain, three ways** — the 3b fill-sim
  (`scheduler.py:3760-3786`) must later re-fetch the trigger day's minute bars and re-run the
  detector; if the fetch returns <6 bars, or the detector re-run returns None on revised data, or
  the sim returns None, the row is skipped **with no degrade clock, forever**. The readiness job
  deliberately skips minute-tactic rows (`scheduler.py:3643-3645`), so nothing else can ever
  settle them. This is precisely the "gate that can never ripen" class the two
  `anticipation_270_*` review entries were flagged for on 2026-08-15.
- **Stale attribution to correct while here:** `health_checks.py:1440` and
  `data_gated_reviews.yaml:232-239` both attribute the table's deadness to "the #270 pin rejects
  every candidate." That pin (`coil_pin_reject_reason`) belongs to Family-A's LIVE
  `_consolidation_readiness_job` writing `mi_anticipation_consolidation`; the Family-B lifecycle
  table is dead because **its writers are unregistered**. Two standing surfaces mis-state the
  root cause.
- `settle_entry_shadow` (`anticipation.py:1121-1180`, the Family-A #327 shadow) is fine: a
  definitive capture/stop settles regardless of window; only genuinely-open rows abstain.

## 6. Why "re-seed" cannot be Stage 1 as scoped — the defect ledger

| # | defect | where | class |
|---|---|---|---|
| D1 | +40% phantom seed (1 stock, never signed) | `db.py:9560` | design gap (ADR 0013, known) |
| D2 | confirm layer re-gates GAP=0.40 + close>SMA200 + 3×ADV20 — a new seed SQL changes nothing; `replay()` is pinned byte-identical by the golden test (funnel 62→30→16, `tests/test_anticipation_golden.py:52-60`) and ADR 0013 Phase-1 correction #1 rules it untouched as the Family-B artifact | `anticipation.py:31-34, 105-108` | design constraint |
| D3 | SMA200 requirement silently drops 33% of a re-seeded 9% universe (3,566 of 5,323 ticker-days have ≥200 stored bars; n=5,323) — correlated with recent IPOs, the tiny-cap cohort the setup was born from | `anticipation.py:105` | design gap |
| D4 | 3b detectors assume "today is the reclaim day": no recency predicate on the watch set (`db.py:10233-10245`), no prior-day context in the detectors; `detect_gdl_reclaim` fires on the first minute bar above the gdl — including the 9:30 open, months later. Correct only on the one session the offline replay chose; wrong on every other. Inherited faithfully from `scripts/_270_entry_replay.py:73-82` — a context mismatch, not a port bug | `anticipation.py:1307-1332`, `scheduler.py:3733-3749` | design gap |
| D5 | armed/coiled/ready rows never expire → zombie watch set grows monotonically | `anticipation.py:117-123, 558-563` | design gap |
| D6 | `first5_break` is an opening-range day-1 construct — operator ruling 2026-08-29: *"day 2 shouldn't use any ORB entry."* The entry vocabulary encodes rejected methodology | `anticipation.py:1307-1321` | superseded methodology |
| D7 | unbounded abstain for minute tactics (§5) | `scheduler.py:3760-3786` | bug |
| D8 | management/settlement = +1R/+3R ½/½ day-5 harvest over a 5-bar horizon — vs the operator's 08-30 arms (M-none 20-session / M-trail SMA10-20) and the plan's 20-session windows. Even when it settles, it answers a different question | `anticipation.py:421-424` | superseded methodology |
| D9 | loud Telegram on ARMED + entries vs the plan's "Silent. Log only." | `scheduler.py:3695-3701, 3789-3796` | superseded ruling |
| D10 | one overwriting row per (ticker, gap_day) — no per-fire trigger rows, no ex-ante decision vector, no screen-membership stamp, no rung-version stamp. The plan's `mi_delayed_entry_trigger` cannot live in this table | `db.py:2181-2236, 10166` | design gap |
| D11 | `polygon_to_rth_minutes` hardcodes UTC−4 — the RTH filter shifts one hour every EST winter; tz-aware-but-wrong-offset, invisible to the datetime-hygiene gate | `anticipation.py:1290-1296` | bug |
| D12 | root-cause mis-stated on two standing surfaces (§5) | `health_checks.py:1440`, `data_gated_reviews.yaml:232-239` | doc rot |
| D13 | re-registration without first archiving the 19 rows mints retroactive hindsight outcomes (§4) | operational | hazard |

**The structural point above all of them:** the machine IS a selective funnel — WATCHED requires
the gap, ARMED requires the undercut, READY requires the reclaim. The plan's approved population
ruling is the opposite shape: *"Every EP the scan sees... Record everything, label nothing."* A
funnel keyed on the undercut structurally excludes the never-pulled-back names that the
pivot-proximity study showed carry the best outcomes. You cannot re-seed a funnel into a
record-everything lane; **the funnel is the machine.**

## 7. What to salvage, what to freeze

**Reuse in the rebuild** (all pure, all tested): `simulate`/`settle_row`/`daily_path` (the harvest
core, golden-pinned), the structural-abstain rule, `db_rows_to_bars`/`get_anticipation_ohlcv`,
`polygon_to_rth_minutes` (after a ZoneInfo fix for D11) + `build_mixed_path` for minute-resolution
rungs, the UPSERT/state-map/watch-set SQL patterns, the golden-test discipline, the
detector-liveness registration, the job scaffolding (`audit_wrap` + one-digest shape).

**Freeze untouched:** `replay()`/`evaluate_candidate`/`mi_anticipation_lifecycle` stay the
Family-B artifact exactly as ADR 0013 ruled; the 19 phantom rows get the #297 archive before any
re-registration is ever considered. Do not modify `anticipation.py`'s machine for #327 at all —
the plan's architecture section already points at the right templates (`ep_shortlist_shadow.py`,
`exit_path_shadow.py`) and its own new tables.

**Stage 1 re-scope:** the new lane's seed is the EP scan population read from `mi_ep_scan_log`
(39 distinct ticker-days/session measured; n=3,266 over 83 sessions) — no new admission gate,
per the population ruling. Row volume at 20 forward sessions ≈ 780 open watch rows steady-state,
~16k watch rows/month — consistent with the plan's ~14k sizing.

## What this does not answer

- **Why each individual seed the one run rejected was rejected** — the confirm layer's 20-day-mean
  ADV vs the seed's 45-day-median divergence was not replayed per name (n=1 run, 19 confirmed
  rows; the ~1.1/session confirmed rate rests on that single run).
- **The MNTS 06-12 counterfactual is daily-bar grade** — minute bars were not fetched ($0
  constraint). The open printing above the gdl makes a same-morning fire near-certain, not proven.
- **Polygon minute-bar retention** for the D7 stuck path was inferred from code, not tested
  against the API.
- **Whether any of the 8 armed June rows would fire today** on uncomment — asserted from the
  detector logic, not simulated per name.
- Nothing here measures whether the delayed-entry TACTICS pay — that is the shadow's job
  (Stages 1-5), and this document deliberately produces no R numbers for them.

## ⚖ THE LINE

Diagnosis only. Nothing was uncommented, changed, or deployed; no strategy, entry/exit
discipline, sizing, or safeguard was touched. The verdict (rebuild the lane, freeze the Family-B
machine) re-scopes Stage 1 of a plan the operator approved; the rebuild itself still runs through
his sign-off at every gated point the plan names, and every tactic it will measure remains his
call.
