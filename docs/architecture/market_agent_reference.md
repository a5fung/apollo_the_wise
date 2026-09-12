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
```

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
  - **Any audit_wrap'd job with no handler of its own** (the stuck-fill / stop-ack naked-position watchdogs were the worst cases): `core.job_audit.audit_run`'s exception branch calls `record_job_failure` → `job_failed_error` audit row on EVERY failure + `notify_job_failure` Telegram once per job per 60 min (per-process pre-gate + `tg=1` audit-log lookback, restart-proof). Before this the only trace was an unwatched `mi_job_runs status='failed'` row. `notify_job_failure` now Markdown-escapes the error text and `notify_owner` re-sends plain text on a 400 (an odd `_` count used to drop the page silently).
  - **Polygon full-market snapshot 200-OK-but-EMPTY** (a detection blackout no exception can catch): guarded at the source in `collector.get_snapshot_all` → `polygon_snapshot_empty_error` row on every empty tick; Telegram "DETECTION IS BLIND" once 3 empties land within 1h (≈3 consecutive 5-min scans), then deduped for the window — via `llm_health.alert_endpoint_shape_anomaly` with the #501 `window_hours` / `sustained_count` / `telegram_text` overrides. Covers all 12 callers (EP scan, 5 flag scans, 9M, …). The exception path is NOT double-surfaced (`_polygon_get` already alerts).
  - **WS-outage backstops** `_check_fills_job` / `_stream_health_watchdog`: their handlers call `record_job_failure` with a consequence-first line (fills UNOBSERVED / a dead stream would stay dead), still swallow. Residual: `audit_wrap` still records such a run as `success`.
  - **15-min DB↔Alpaca reconcile losing a WHOLE account mode**: `order_manager.reconcile_all_modes` → `order_status_reconcile_mode_error` row per failure; Telegram "<MODE> ORDER RECONCILE DOWN" after 3 consecutive failures of the same mode (45 min at the 15-min cadence; 3 min on the 9:31–9:40 open-window variant), counter reset on the page and on that mode's next success (the `intraday_drawdown._consecutive_failures` pattern).
  - Tests drive the real paths and were mutation-checked RED: `tests/test_501_tier1_silent_failure_surfaces.py`.

### Telegram Formatting
- NEVER use pipe tables — Telegram can't render them. Use monospace code blocks.
- `send_telegram_message` in `briefing.py`. Returns False on failure (never raises).
- Escape dynamic strings before passing with Markdown mode.
- **An alert that carries machine text — SQL, JSON, a snake_case identifier, model prose — goes out on the HTML layer, converted ONCE at the send boundary: `send_telegram_message(md_to_html(text), parse_mode="HTML")` (`shared/telegram_format.py`; #647, 2026-09-12; the #121 migration path, `system_review.py` was the precedent).** Telegram's legacy-Markdown parser reads every bare `_` as an italic delimiter, so such a body 400s on its first send and reaches the operator only through the plain-text retry — 28 times in the 14 days to 2026-09-11, including the live OKTA exit-failure page and the catalyst-lattice revert SQL. Migrated so far: the EP alert (`send_ep_alert`), Full exit FAILED + Regime sizing FALLBACK (`order_manager`), auto-enter / proposal-send failed (`entry_pipeline`), ingest findings (`order_ingest._emit`), L1/L2 audit pages (`system_audit`), the catalyst-lattice monitor + JOB PRODUCED NOTHING (`health_checks`), the delayed-feed residual, the mgmt-judge digest, the monthly sweep digest, the LLM truncation check. `md_to_html` consumes the `\_`/`\*` that `_md_escape` emits, so an escaped builder migrates without edits. Remaining legacy surfaces: #121.
- The plain-text backstop (`_strip_markdown_markers`, Markdown mode only) keeps code-span and fence bodies VERBATIM and strips only word-bounded emphasis pairs — before #647 it delivered the revert SQL as `misafeguardstate`. On the HTML path the backstop strips tags and unescapes, so machine text survives there by construction.
- Skip-reason machine prefixes (`infra:subscribe_timeout: ...`) → run through `humanize()` before user display. DB keeps machine prefix; user sees prose.
- Reserve Telegram for terminal/actionable events. Self-healing/transient → `mi_audit_log` only.
