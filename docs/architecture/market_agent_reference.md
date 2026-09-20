# Market agent — build & ops reference

**Owner doc for the mechanical how-to that used to live in `CLAUDE.md`.** Moved out 2026-09-07
(#626): `CLAUDE.md` is loaded into every session, so it must carry only what has to be in front of
you *before you know you need it* — THE LINE, the report format, the session ritual, the timezone
rule. Step-by-step build instructions are things you look up when you are already doing the task,
so they belong here and are linked from there.

**Nothing was rewritten in the move.** These sections are verbatim; the same rules apply, and the
same tests still enforce them (`tests/test_execute_task_routing.py` freezes the routing cascade,
`preflight_datetime_hygiene.py` bans naive datetimes, the pre-commit hooks below gate the rest).

## Running Locally
```bash
bash start.sh          # Terminal 1 — orchestrator + Postgres + Redis
bash start_market.sh   # Terminal 2 — market agent
# Verify: /agents in Telegram — all green
```

## Architecture
```
User (Telegram)
      │
Apollo Orchestrator (port 8000)   ← claude-sonnet-4-6, tool-use loop
      │  POST /task  +  X-Apollo-Secret header
      ▼
Market Intelligence agent (Docker, :8006)
      │
PostgreSQL (pgvector) + Redis
```
**Key rule:** Only the market agent is exposed as a sub-agent. All trading/market features live inside it.
**`agents/market_intelligence/db.py` is the single source of truth for every DB query + the schema** — add queries there, never inline in a caller.

## Adding an Orchestrator Tool
1. Tool schema → `core/router.py` → `get_orchestrator_tools()`
2. Dispatch → `core/orchestrator.py` → `_dispatch_tool()`
3. Handler → inline in orchestrator OR delegate to market agent's `execute_task()`

## Adding a Telegram slash command (`/foo`)
Three places must be updated **in the same commit** or the command is hidden from operators:
1. **Handler** in `agents/market_intelligence/agent.py` — `_handle_foo_query(self, request)` method.
2. **Dispatch** in `agent.py` — entry in the command-to-handler dict (e.g. `"/foo": self._handle_foo_query`).
3. **Bot command list** in `channels/telegram.py::_register_commands` — `BotCommand("foo", "<short description>")`. This is what makes the command appear in the Telegram `/` menu (six commands missed this in May 2026 and were invisible).

## Market Agent Routing (`execute_task`)
Order matters — first match wins:
1. watchlist / 2. theme engine rerun / 3. refresh / 4. history
5. EP outcomes ("ep outcome", "ep performance", "ep returns", "ep results")
5a. **9M EP outcomes** ("9m outcome", "9m performance", "9m result", "sugar outcome") — before 9M query
5b. **9M trades** ("9m trade", "9m position", "trade 9m", "show 9m trade")
5c. **9M EP query** ("9m ep", "sugar baby", "sugar babies", "nine million", "show 9m", bare "9m")
5d. **Continuation flag** ("/flags", "coiled", "tightening flag", bare "flags") — see _handle_flag_query
5e. **/setup TICKER** — reverse-lookup detector chronology across ~10 detector tables
6. EP ("ep", "episodic", "gap", "pivot", "gapper")
7. journal add ("journal:", "log trade") / journal query ("show journal", "my journal")
8. theme ("theme", "sector", "industry") — before regime/RS
9. regime / 10. RS/score / 11. briefing / 12. pullback / 13. fundamentals
14. screener / 15. audit log ("audit log", "show logs", "show errors") / 16. weekly review ("weekly review", "system review", "self audit") / 17. /audit topic ("audit <topic>") / 18. fallback

## Ticker Extraction
```python
re.findall(r'\b([A-Z]{2,5})\b', request.task.upper())
```
Common English words live in the shared `_PREPOSITION_SKIP` frozenset (`agent.py`) — add new ones THERE (one place). Each ticker-extraction site extends it: `_PREPOSITION_SKIP | {site-specific command words}` (e.g. `{"RS","SCORE"}` in `_handle_single_score`). #260 (2026-06-10) deduped the former three hand-synced copies into this base; `tests/test_execute_task_routing.py` freezes the routing cascade.

## When to extract a shared helper — wait for a third PERMANENT consumer

**The convention, operator-ruled 2026-09-16** (this is where #239 went when it was closed as a
convention rather than a task — a rule with no end state does not belong on the board with a date):

> **Do not extract duplicated logic into a shared helper until a THIRD consumer needs it — and
> count only PERMANENT consumers.** A one-off script under `scripts/` is a throwaway and does not
> count toward the three, however many of them there are.

**The case it was written from.** `scripts/_wave_a_grade_inflation_check.py` and
`scripts/probes/verify_monday_firstfire.py` both compute the same trailing baseline — per-day
`game_changer` / HIGH counts over the prior ~9 days from `mi_ep_alerts` — to answer "are we
suddenly grading more generously than usual". A 2026-06-28 review flagged the duplication as real
and deferred the extraction anyway, because two throwaways are not a reason to build plumbing. Re-run
2026-09-16: still exactly two consumers, still both `scripts/`, **zero permanent**.

⚠ **This is deliberately NOT mechanised, and that is a judgement not an omission.** A test greping
for that SQL shape would be a guard over a condition a real third consumer would probably never
trip — a different column alias, `catalyst_quality IN (...)`, or a `TIER_RANK` comparison all read
as new code while computing the same thing. A gate that cannot fire is worse than a written rule,
because it also tells you it is watching.

**Also settled, and not to be re-litigated:** unifying the `_emit_shadow_row` envelope is a WON'T-DO.
Provenance is intra-grade while the tape and Perplexity reads are post-grade; one envelope over both
hides exactly the context difference a reader needs. (#239 part (b).)

## Pre-commit hooks (one-time setup per clone)
After fresh clone, activate the local pre-commit gates:
```bash
git config core.hooksPath .githooks
```
Currently enforces:
- **pre-commit — YAML dupe-key check** on `data_gated_reviews.yaml` (mirrors deploy.sh `[5e/5]`; catches the 2026-05-24 SNDK class bug at `git commit` time instead of at deploy or runtime), plus the PLAN.md single-SoT gate (Gate 2) + CLAUDE.md size ceiling (Gate 3).
- **pre-push — full `python -m pytest tests/ -q`** (mirrors CI), runs only when the pushed commits touch Python, blocks the push on failure. Added 2026-06-17 after a subset-only local test run shipped a CI-breaking regression (the downgrade-digest mock). Bypass an emergency push with `git push --no-verify`.

Pre-commit gates are vanilla shell + fast (<1s); the pre-push test gate is ~30s (Python pushes only). Bypass with `--no-verify` only if you really know what you're doing.

## Required Env Vars
```
TELEGRAM_BOT_TOKEN, TELEGRAM_ALLOWED_USER_IDS
ANTHROPIC_API_KEY, POLYGON_API_KEY, FMP_API_KEY, PERPLEXITY_API_KEY

# Dual-account Alpaca (#66, 2026-05-10) — required when ENABLE_LIVE_MODE=true
ENABLE_LIVE_MODE=true       # false = dev/single-account opt-out (paper only)
ALPACA_PAPER_API_KEY, ALPACA_PAPER_SECRET_KEY     # paper-api.alpaca.markets
ALPACA_LIVE_API_KEY, ALPACA_LIVE_SECRET_KEY       # api.alpaca.markets

# Legacy (deprecated; remapped to ALPACA_PAPER_* at boot for one cycle):
ALPACA_API_KEY, ALPACA_SECRET_KEY, ALPACA_PAPER=true

LIVE_TRADING_ENABLED=false  # Master kill switch — disables ALL submits
ALPACA_DATA_FEED=iex        # "sip" only when Algo Trader Plus ($99/mo) active
POSTGRES_PASSWORD, REDIS_PASSWORD, INTERNAL_API_SECRET, TRADINGVIEW_WEBHOOK_SECRET

# Methodology calibration overrides
REVENUE_STAGE_MIN_USD=0.01  # is_revenue_stage threshold; PROVISIONAL OPERATOR PIN
                             # (code default $5M). History + re-eval cadence:
                             # CHANGELOG + #55 (quarterly sweep Feb/May/Aug/Nov 1st).

# #672 missed-job recovery — OPERATOR FLIP, default OFF. A re-run of a missed job
# HOLDS every Telegram it would have sent (the summary page names them); set to 1
# to deliver them instead, each prefixed "⏪ LATE RE-RUN — <job> for <slot>".
APOLLO_RECOVERY_SEND_LATE=0
# #672 — set to 1 to deploy the sweep READ-ONLY: every pass plans and the boot
# pass writes its heartbeat row + one page naming what it WOULD re-run, but nothing
# executes and nothing is written to mi_job_runs. Unset to enable.
APOLLO_RECOVERY_DRY_RUN=0
```

## Missed-job recovery (#672, 2026-09-20) — `agents/market_intelligence/job_recovery.py`

A daily intelligence job that should have run and did not is **re-run from the ledger**, with the
market date pinned to the day it was due. Why the ledger and not APScheduler's miss event: the
in-memory jobstore **forgets a past slot at boot** (no `EVENT_JOB_MISSED` — measured), which is exactly
the shape 2026-09-18 had. Three triggers, one function: boot (+120 s), every 30 min (`:20/:50`), and
right after the miss listener records a burst. Population **derived** from the running scheduler —
fires at most daily · not `EXECUTION_OWNED_JOB_IDS` (THE LINE) · not paused · audit-wrapped. A slot is
re-run only while **no market session has opened since it** and it was not itself inside 09:30–16:00;
otherwise it is recorded `unrecoverable` and named for hand recovery. Each re-run executes the
registered callable through `audit_wrap` inside `shared.dates.pinned_recovery()` (a ContextVar —
`et_today()` answers the slot's date for that task only; every binding is checked before the run and
the run is REFUSED if one still reads the clock), records `mi_job_runs.scheduled_for = slot`, is
bounded at 3× its p95, capped at 3 attempts per slot, and never runs 09:25–10:05 ET. Telegrams are
held at the httpx layer (`shared/telegram_hold.py`). Exercise / verify: `scripts/probes/_672_exercise_recovery.py simulate`
(off-prod) and `... dry-run` (in the container, read-only). Pin-completeness is gated by
`scripts/check_job_date_sources.py` (`# recovery-clock-ok:` escape).

---

## Moved from CLAUDE.md 2026-09-07 (#626) — detail, unchanged

`CLAUDE.md` keeps the one-line rule for each of these; the mechanism lives here.

### 9M EP Detection (Parallel Track)
- **No LLM** — pure quantitative virgin 9M detection (Pradeep Bonde). **Every threshold, the gate list, the Sugar Baby definition and stop placement live in `docs/setups/ninem.md` — read it before touching any of them.**
- **Intraday and EOD use identical filters** — any divergence creates phantom sugar babies.
- **Stop = prior day's low** (breakout day's low), NOT ORB low or ATR-based.
- **Tables**: `mi_9m_ep_alerts` (intraday), `mi_9m_day2_candidates` (EOD), `mi_sugar_babies_cohort` (the persistent Pradeep cohort)
- **Anticipation cadence carve-out**: silent anticipations hit DB/audit only; Telegram only when gap ≥ 10% OR proj_vol ≥ 25M.
- Do NOT import from `ep_detector.py` — use `collector.get_snapshot_all()` directly in `ninem_detector.py`

### Self-Audit System (L1/L2/L3)
- **L1** invariant breach (hard SQL guard fails) → immediate Telegram + audit row.
- **L2** anomaly (metric outside 30d trimmed median ± 3 MAD OR > 5× median) → immediate Telegram with Sonnet hypothesis.
- **L3** drift (band transition) → audit row only, surfaces in Sunday weekly digest.
- Jobs: `_post_eod_audit_job` 16:15 ET, `_post_nightly_audit_job` 17:30 ET, `_baseline_refresh_job` 02:00 ET.
- On-demand: `/audit <topic>` (cooldowns/themes/skips/positions/feed/9m/all).
- Cold-start tiers: `sample_n < 7` → hardcoded `_COLD_START_CEILINGS` only. `7 ≤ n < 14` → L3 only. `≥ 14` → full L2.
- Sonnet hypothesis call gets last 5 CLAUDE.md change headers + last 10 distinct audit event types as context.

### Error Alerting
- Silent failures in theme engine write to `mi_audit_log`: `validation_error`, `assignment_error`, `discovery_error`, plus `validation_rate_limited` / `anthropic_rate_limited` for 429s.
- After nightly run: if any `*_error` events in last 2h → immediate Telegram alert.
- Morning briefing: 3-bucket banner (🔴 errors / 🟠 rate-limited / 🟡 parse errors).
- Telegram: `show errors 7d` pulls all error events for the period.
- **Safety-net self-surfacing (#501 Tier-1, 2026-09-10 — the four money-path nets that could die silently; SoT for the findings: `docs/analysis/silent_failure_taxonomy_2026-07-23.md` F1–F4).** Every event name below contains `error` so the nightly `%error%` sweep + `show errors` see it with no extra wiring; every Telegram is deduped; nothing here changes strategy, safeguards, sizing or trade state.
  - **Any audit_wrap'd job with no handler of its own** (the stuck-fill / stop-ack naked-position watchdogs were the worst cases): `core.job_audit.audit_run`'s exception branch calls `record_job_failure` → `job_failed_error` audit row on EVERY failure + `notify_job_failure` Telegram once per job per 60 min (per-process pre-gate + `tg=1` audit-log lookback, restart-proof). Before this the only trace was an unwatched `mi_job_runs status='failed'` row. `notify_job_failure` now Markdown-escapes the error text and `notify_owner` re-sends plain text on a 400 (an odd `_` count used to drop the page silently). **Sound (#635, operator-approved 2026-09-13):** every `notify_owner` page is silent (`disable_notification`) EXCEPT the death page of a job in `core/notifications.LOUD_FAILURE_JOBS` — the stop-ack + stuck-fill watchdogs, the 15-min coverage detector, the three bare-window coverage slots and the two L1 naked_position checks. Rule: loud iff the job's death removes the last DETECTION of a bare live position; repair jobs stay silent because a live detector catches their result, and every alert the detectors EMIT already buzzes (`send_telegram_message` sends no `disable_notification`). Telegram's on/off bit is the only sound lever the Bot API has.
  - **Polygon full-market snapshot 200-OK-but-EMPTY** (a detection blackout no exception can catch): guarded at the source in `collector.get_snapshot_all` → `polygon_snapshot_empty_error` row on every empty tick; Telegram "DETECTION IS BLIND" once 3 empties land within 1h (≈3 consecutive 5-min scans), then deduped for the window — via `llm_health.alert_endpoint_shape_anomaly` with the #501 `window_hours` / `sustained_count` / `telegram_text` overrides. Covers all 12 callers (EP scan, 5 flag scans, 9M, …). The exception path is NOT double-surfaced (`_polygon_get` already alerts).
  - **WS-outage backstops** `_check_fills_job` / `_stream_health_watchdog`: their handlers call `record_job_failure` with a consequence-first line (fills UNOBSERVED / a dead stream would stay dead), still swallow. Residual: `audit_wrap` still records such a run as `success`.
  - **15-min DB↔Alpaca reconcile losing a WHOLE account mode**: `order_manager.reconcile_all_modes` → `order_status_reconcile_mode_error` row per failure; Telegram "<MODE> ORDER RECONCILE DOWN" after 3 consecutive failures of the same mode (45 min at the 15-min cadence; 3 min on the 9:31–9:40 open-window variant), counter reset on the page and on that mode's next success (the `intraday_drawdown._consecutive_failures` pattern).
  - Tests drive the real paths and were mutation-checked RED: `tests/test_501_tier1_silent_failure_surfaces.py`.

### `_sdk` thread-pool telemetry (#664, 2026-09-18)

Every broker call goes through `broker/alpaca_client._sdk()` = `asyncio.wait_for(asyncio.to_thread(fn), timeout)`, so each one borrows a thread from the loop's DEFAULT executor — `min(32, cpus+4)` = **7 threads on apollo-execution** (3 CPUs), shared with every other `to_thread` caller in that process. Seven concurrent hangs would make a STOP placement queue rather than fail fast. `broker/sdk_pool_telemetry.py` measures that instead of arguing it from the ceiling — **instrumentation only**: no timeout, executor or call-path change (a dedicated executor for writes is an execution-path change and the operator's call, THE LINE).

- **What is recorded, per call, in memory (no I/O on the call path):** the real slot wait (measured on the worker thread), whether the call was `queued` (no free thread at submit — the discriminating signal; an idle pool still shows ~0.1 ms of handoff), the depth at start, the executor's own work-queue size (`backlog`, the only cross-user signal — `get_minute_bars_range`, `bar_stream`, `twitter`, `earnings_calendar`, `correlation_engine` bypass `_sdk`), and for a caller that timed out how long its thread kept the slot past the budget (`overrun_s`).
- **⚠ The 30s/45s bounds the CALLER, not the slot.** alpaca-py's REST client (`alpaca/common/rest.py`, 0.43.x) passes NO HTTP timeout to `requests`, so a hung socket holds a worker thread until TCP gives up; a 429 additionally sleeps 3s×3 retries on the thread. `overrun_max_s` is the number that shows this; changing it is not this telemetry's job.
- **Rows:** `sdk_pool_rollup` — one per 5-minute interval with any call, written by the execution-owned `sdk_pool_rollup` job (every 5 min, every day; not `audit_wrap`'d, same reasoning as `telegram_poll_watchdog`). `detail` JSON: `calls`, `max_depth`, `pool_max`, `queued_calls`, `wait_max_ms`, `wait_mean_ms`, `wait_hist_ms`, `run_max_ms`, `timeouts`, `overruns`, `overrun_max_s`, `max_backlog`, `by_fn`, `queued_samples` (≤20 per-call records of the calls that waited), `record_errors`, `service_role`. `sdk_pool_saturated` — additionally, when any call in the interval had no free thread. Nothing reads either row to act.
- **Reading it — the day's maximum against the pool:**
  ```sql
  SELECT date_trunc('hour', created_at AT TIME ZONE 'America/New_York') AS hr_et,
         SUM((detail::json->>'calls')::int)            AS calls,
         MAX((detail::json->>'max_depth')::int)        AS depth_max,
         MAX((detail::json->>'pool_max')::int)         AS pool,
         SUM((detail::json->>'queued_calls')::int)     AS waited_for_a_thread,
         MAX((detail::json->>'wait_max_ms')::float)    AS wait_max_ms,
         SUM((detail::json->>'timeouts')::int)         AS caller_timeouts,
         MAX((detail::json->>'overrun_max_s')::float)  AS thread_outlived_budget_max_s,
         SUM((detail::json->>'record_errors')::int)    AS recorder_errors
    FROM mi_audit_log
   WHERE event_type = 'sdk_pool_rollup'
     AND (created_at AT TIME ZONE 'America/New_York')::date = CURRENT_DATE
   GROUP BY 1 ORDER BY 1;
  ```
- **A quiet pool is not a dead recorder:** `position_coverage_check` calls the broker every 15 min 09:31–15:55 ET, so every market-hours interval MUST produce a rollup with `calls > 0`. A market-hours gap, or `record_errors > 0`, is a defect in the telemetry, never evidence the pool was idle. Tests: `tests/test_sdk_offload_464.py` (8 concurrent calls into a 7-wide pool → the eighth records a `queued` wait; the recorder cannot throw into the call), `tests/test_sdk_pool_telemetry.py`.

### Telegram Formatting
- NEVER use pipe tables — Telegram can't render them. Use monospace code blocks.
- `send_telegram_message` in `briefing.py`. Returns False on failure (never raises).
- **THE DEFAULT IS SAFE (#652, 2026-09-19; the `"Markdown"` opt-in folded into it #675, 2026-09-20): a caller that passes NO `parse_mode` writes legacy Markdown as always and `send_telegram_message` converts it ONCE at the boundary (`md_to_html`) and sends HTML — a bare `_` in a table name, a revert-SQL column, a ticker or a verdict like `TRAIL_TIGHTEN` can no longer 400 the message.** The default is a SENTINEL, not the string "HTML": an explicit `parse_mode="HTML"` is passed through untouched (never converted twice — 32 of 44 real explicit-HTML bodies would be mangled), an explicit `parse_mode="Markdown"` is CONVERTED the same as the default (#675 — the three `scheduler._backup_health_check_job` sites that were its last production callers had already migrated to the default by 2026-09-19, one after a LIVE 400 on `"pg_dump is current"`; the legacy chunker/fallback path it used is deleted, not "chunked and backstopped exactly as before" anymore), `parse_mode=None` is plain text, not converted. A long HTML message is split by `chunk_html`, which closes every tag open at the seam and reopens it in the next chunk; plain text (mode=None) uses `_chunk_plain` (not tag-aware — deliberately, since plain prose may contain a bare `<word>` that isn't a real tag). `md_to_html` mirrors the legacy fence rule (drops a language token and ONE newline after the opening ```), so a code block opens on its first line — before this the L1/L2 pages' drill SQL rendered with a blank first line. Evidence: `docs/analysis/telegram_html_default_flip_render_check_2026-09-18.md` (732 real bodies: 266 that failed the first send render under HTML, 0 regress the other way) and `scripts/probes/_675_render_check_baseline_2026-09-20.txt` (same corpus, re-run before the #675 change: still 0 regress). A 400 on the default path writes `telegram_markdown_fallback` with `mode=HTML(default)` in the detail — that row is the verify-live observable. ⚠ `edit_telegram_message` keeps its own `"Markdown"` default (one caller, `scheduler.py` HUD edit); `core/notifications.notify_owner`, `broker/telegram_confirm.send_trade_proposal` and `channels/telegram._send_chunk` each carry their OWN httpx sender on legacy Markdown and are NOT covered by this default — #675 left all three exactly as found.
- Escaping dynamic strings (`_md_escape`) is still correct on the default path: `md_to_html` consumes the `\_`/`\*` it emits.
- **Before #652 (2026-09-12 → 2026-09-19) an alert carrying machine text had to opt into the HTML layer BY HAND: `send_telegram_message(md_to_html(text), parse_mode="HTML")` (`shared/telegram_format.py`; #647; the #121 migration path, `system_review.py` was the precedent). That call shape is still valid and still passed through untouched, but it is no longer required — the bare call does the same thing now.** Telegram's legacy-Markdown parser reads every bare `_` as an italic delimiter, so such a body 400s on its first send and reaches the operator only through the plain-text retry — 28 times in the 14 days to 2026-09-11, including the live OKTA exit-failure page and the catalyst-lattice revert SQL. Migrated so far: the EP alert (`send_ep_alert`), Full exit FAILED + Regime sizing FALLBACK (`order_manager`), auto-enter / proposal-send failed (`entry_pipeline`), ingest findings (`order_ingest._emit`), L1/L2 audit pages (`system_audit`), the catalyst-lattice monitor + JOB PRODUCED NOTHING (`health_checks`), the delayed-feed residual, the mgmt-judge digest, the monthly sweep digest, the LLM truncation check. `md_to_html` consumes the `\_`/`\*` that `_md_escape` emits, so an escaped builder migrates without edits. Remaining legacy surfaces after #652/#675: none — every explicit `"Markdown"` opt-in now converts too.
- The plain-text backstop (`_strip_markdown_markers`) is unreachable from `send_telegram_message` after #675 (nothing sets `mode == "Markdown"` anymore) but is kept: `scripts/probes/_652_render_check.py` imports it as the legacy-fallback emulator, and `tests/test_briefing_markdown_fallback.py` / `tests/test_647_machine_text_alerts_on_html_layer.py` pin its own behavior directly. On the HTML path the live backstop strips tags and unescapes, so machine text survives there by construction.
- Skip-reason machine prefixes (`infra:subscribe_timeout: ...`) → run through `humanize()` before user display. DB keeps machine prefix; user sees prose.
- Reserve Telegram for terminal/actionable events. Self-healing/transient → `mi_audit_log` only.
