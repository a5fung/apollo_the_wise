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

## Deploy gate [5p/7] — replay-everything CI (ADR 0022 §3 L4, #313 / #302, 2026-10-14)

**Regressions block DEPLOYS, never trades.** `scripts/deploy.sh` runs `scripts/preflight_ci_status_gate.py`
(host-side, stdlib) **before the image build** — a block stops the deploy from starting. It reads
`/home/apollo/backups/ci_status/<job>.json` (`{job, status: green|red, asof (ET), detail}`), the files the
in-container regression jobs write through the market-agent bind mount (`/app/ci_status`, writer module
`agents/market_intelligence/ci_status.py`).

| Reading | market-agent / both / execution | orchestrator |
|---|---|---|
| red, ≤ 7 days old | **BLOCK — `exit 21`** | pass (never blocked, M4f) |
| red, > 7 days old (stale) | WARN | WARN |
| green ≤ 7d · green > 7d | pass · WARN (job may be dead) | same |
| file missing / unreadable | WARN, never block (a missing `judge_eval` / `entry_sim` prints `(not built)`, information) | same |

Jobs the gate expects (ADR 0022 §3): `selection_replay` (**live** — the Sunday `weekly_system_review`
writes it, live account only; red iff live realized expectancy sits >0.3R under the +0.95R #268b
calibration at n≥50, M3f; a missing file is the one `MISSING WARN` that matters — the writer is dark),
`judge_eval` and `entry_sim` (**not built** — missing prints `(not built)` on every deploy, information
not a WARN; the ADR's §3 says what each would need). The gate's block exit code is **3**; deploy.sh maps
only 3 to `exit 21` — a crash in the gate prints `CI GATE ERROR — not blocking` and the deploy continues.
Override, **operator only**, LOUD: `CI_OVERRIDE="<reason>" bash scripts/deploy.sh <scope>` →
banner + `logs/ci_override.log` line + `mi_audit_log` row `ci_override_deploy` (relayed via
`scripts/log_judge_envelope_change.py` into the running container).

**First deploy of this change — one-time pre-step.** The host dir must be owned by `apollo` (uid 1000, the
container user) or the Sunday writer cannot write; docker creates a missing bind source root-owned. The
[5p/7] block `mkdir -p`s it and warns loudly unless it is writable, but the deploy that SHIPS the block runs
the pre-merge `deploy.sh` (bash keeps the old inode across `git pull`), so it prints no `[5p/7]` at all.
Therefore, as `apollo` on the host: `mkdir -p /home/apollo/backups/ci_status` BEFORE `bash scripts/deploy.sh
both` (the compose edit is all-service scope); if it already exists root-owned, `sudo chown apollo:apollo` it.
Then `deploy.sh execution` (clears the #324 drift warning) is the first run of the gate: expect
`selection_replay MISSING WARN` + two `(not built)` lines until Sunday's 08:00 ET review writes the file.

## Required Env Vars
```
TELEGRAM_BOT_TOKEN, TELEGRAM_ALLOWED_USER_IDS
TELEGRAM_PAPER_CHAT_ID      # OPTIONAL (#699, 2026-10-11). The "Apollo Paper" group's chat id (negative number):
                            # paper-tagged alerts go there instead of the main chat. Unset = everything goes to the
                            # main chat, exactly as before. All three prod containers read ../.env via env_file, so
                            # no compose edit - but env_file is read at container CREATE: set it, then recreate.
ANTHROPIC_API_KEY, POLYGON_API_KEY, FMP_API_KEY, PERPLEXITY_API_KEY
COINGECKO_API_KEY           # free Demo key (100/min, 10k/month; we use ~4.6k). Required since
                            # 2026-09-29: CoinGecko refuses keyless data calls (403) — crypto ingest died on it.

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
- `_ladder_watchdog_job` 16:17 ET mon-fri (#312, ADR 0022 L2, **DARK**): the four signed demotion triggers per enabled paper/live strategy on its own book → ONE `ladder_demotion_shadow` audit row; no phase/sizing/order write exists in `ladder_watchdog.py`, no Telegram. Owner doc: `docs/architecture/dual_account.md` §"Demotion".
- `_breakout_v1_list_job` 17:55 ET mon-fri (breakout v1 PAPER phase 1, 2026-10-29; **LIST + GRADE only, no orders**): tonight's names passing every v1 gate (`breakout_v1.py`, PURE) → `mi_breakout_v1_list` + ONE `breakout_v1_list_run` audit row + ONE paper-chat message only when the list is non-empty; `/bgrade` writes `mi_breakout_v1_grades`. Fails open after 600 s (`breakout_v1_list_error`). Owner doc: `docs/setups/consolidation_breakout.md`.
- `_consolidation_breakout_shadow_job` 17:48 ET mon-fri (#702 P6, **SHADOW**, SILENT): last night's watch rows that broke out get their entry rows, tonight's watch list is built, every open entry is walked over the 15 exit arms → four `mi_consolidation_breakout_*` tables + ONE `consolidation_breakout_shadow_run` audit row; no order path, no strategy row, no Telegram on a normal night (a crash propagates to `audit_wrap`'s one page). 17:50 was taken (`exit_path_shadow`, `chart_axis_shadow`). Owner doc: `docs/setups/consolidation_breakout.md`.
- `_parabolic_scan_job` 17:15 ET mon-fri (existing job; **#314, ADR 0020 card B3 adds a SHADOW step to it, no new job id**): scan → `run_parabolic_short_shadow` → ONE digest. The shadow step arms tonight's non-excluded climax candidates ($250M floor, then `execution_client.get_asset` for `shortable AND easy_to_borrow`) and advances every open episode from stored daily bars → `mi_parabolic_short_shadow` (arm / trigger / outcome rows) + ONE `parabolic_short_shadow_run` audit row per run; no order path, no strategy row; a crash pages on its own (`notify_job_failure("parabolic_short_shadow")`) and the digest still goes out; the digest gains ONE line only when something armed / triggered / settled. The only broker reach is the read-only `get_asset` (cross-listed in `execution_client._CROSS_FNS`, served by apollo-execution at `/exec/get_asset`). Owner doc: `docs/setups/parabolic_short.md`.
- On-demand: `/audit <topic>` (cooldowns/themes/skips/positions/feed/9m/job_runs/all) — and, since #691, `/audit <check>` for any monthly-sweep check (see §Monthly backward-check sweep below).
- Cold-start tiers: `sample_n < 7` → hardcoded `_COLD_START_CEILINGS` only. `7 ≤ n < 14` → L3 only. `≥ 14` → full L2.
- Sonnet hypothesis call gets last 5 CLAUDE.md change headers + last 10 distinct audit event types as context.

### Monthly backward-check sweep & `/audit <check>` (#691, 2026-10-03)

`agents/market_intelligence/quarterly_review.py` (job `monthly_backward_check_sweep`, 1st of the
month 18:00 ET, scheduler.py) runs every script in `QUARTERLY_BACKWARD_CHECK_SCRIPTS` as
`python -m <module>` and sends ONE decision-first digest (#513): NEEDS YOUR CALL / FAILED TO RUN /
✅ done / ⏳ waiting / 👀 review. **That list is the roster's SSoT — no second roster anywhere.**

- **Classification is by the scripts' OWN verdict phrases** — `_NEEDS_YOU` / `_CONCLUDED` /
  `_WAITING` in `quarterly_review.py`, case-sensitive substrings over the script's FULL stdout (not
  the 25-line summary: #88's and #94's verdicts sit after 40+ lines). **Contract for a registered
  script: in EVERY branch it can reach, print a verdict line containing a phrase in one of those
  lists.** Unreadable output lands in 👀 "review" — never in a green bucket. A marker may not span a
  line break (the script's wrap decides) and must not occur in always-printed boilerplate.
- **`tests/test_691_monthly_sweep_cleanup.py` enforces it:** it runs each registered script's REAL
  `main()` against a fake DB pool, once per verdict branch (`SCENARIOS`), and fails on any
  "review", on a bucket different from the pinned one, and on a registered script with no scenario
  (population derived from the roster, both directions). Adding a check = add the roster entry, the
  verdict phrases, and its scenarios, or the build fails.
- **Table-only monitors** (#50, #53, #77 had no verdict line): #50 prints its own docstring matrix
  applied to the numbers it already computes (`$0-$5M` band positive-edge, N>=10 → NO-SHIP; band
  stopped paying → NEEDS YOUR CALL; thin → ACCRUING). #53 and #77 have no numeric rule and the
  operator already closed them, so they print `VERDICT: INFORMATIONAL` — the standing ruling plus
  the current reading, never a computed all-clear (empty cohort = ACCRUING). Deciding to give them
  a numeric regime-flip alarm is the operator's call, not a classifier change.
- **The M&A accuracy review always asks** (its `HARD-gate` banner prints every run): the filter list
  is the operator's to judge, and an empty month is indistinguishable from a broken audit feed.
- **Retired from the roster (script kept, runnable by hand):** #223 SIP replay (2026-08-11) and
  #54 9M Day-2 stop/ATR (2026-10-03, the 9M setup is gone).
- **`/audit <check>` — stored, read-only.** `run_quarterly_sweep` writes ONE `mi_audit_log` row per
  check per run (`event_type='backward_check_output'`, summary `"<check> | exit=<n> | <bucket>"`,
  detail = the script's stdout, capped 24k chars; a failed run stores its stderr tail). The check name
  is the module tail (`check_topic`), e.g. `mna_filter_accuracy_review`, `_b88_mna_filter_path_b_fp_rate`,
  `news_source_quality`; the topics are DERIVED from the roster (`sweep_topics()`), and
  `system_audit.run_topic_audit` answers them with the newest row — it NEVER re-runs a script. Until a
  check has run once on code with the store, the reply says "No stored run … first run is <date>"
  (never "Unknown audit topic"). A wrong topic lists every valid one. A hand-run
  `python -m agents.market_intelligence.quarterly_review` runs + stores + prints the digest without
  Telegram. The event name ends in `_output` on purpose: the nightly `%error%` / `%\_failed%` sweeps
  and `show errors` must not count a stored table as an incident.
- **Deploy scope:** `quarterly_review.py`, `judge_review.py`, `system_audit.py`, `scripts/`, `docs/` =
  market-agent ONLY (none is in `scripts/exec_loaded_modules.txt`). `/audit` is already registered in
  all three places (handler, dispatch dict, `BotCommand`), so `channels/telegram.py` and the
  orchestrator are untouched.
- **Judge footer (monthly judge review):** states what it counts — graded rows whose stored evidence
  carried an SEC filing or Benzinga wire — and makes no claim about what the judge was shown.

### Weekly review message — what prints and what only stores (#700, 2026-10-11)
Owner of the rules: `agents/market_intelligence/system_review.py` (`_assemble_report`); decision table and
rationale: `docs/design/weekly_review_noise_700.md` (a finding, not an owner). Operator 2026-10-11: *"even if
something doesnt need me, if it's informative it can still include so don't need to remove everthing but
remove noise as much as possible."* Presentation only - every metric is computed and stored as before.
- **Four rules.** (1) INFORMATIVE prints, compact: a result with its conclusion, a number that moved, a first-ever
  event, a new section's readout (#486, #313), a live-money P&L fact. (2) UNCHANGED since last week becomes one
  phrase on the head's checked line (`unchanged since last week: bands HOLD · winner capture 19%`), the block goes to
  the full text. (3) REPEATED rows become one line per type and disposition. (4) UNVERIFIED is never a finding: the
  job checks the narrator's "anomalies to verify" against the record (`verify_narrative_anomalies`: names an audit
  type with no live row, every identifier resolves in the AUDIT-ERROR record, no ticker from the week) - settled
  ones are one line, the rest are MINE ("To verify (mine, Monday)" + a head count under Needs me). Only
  `silent_audit_error_window` may settle from the L1/L2 footprint; any other L1 invariant / L2 anomaly keeps the
  bullet mine, and "settled" never covers an impact claim written in prose.
- **Where the full text lives.** `mi_system_reviews.metrics.report` = `full_md` (every section uncompacted),
  `head_md` / `fold_md` (as sent), `snapshot` (what next week compares against - categorical states and event keys
  only, never a windowed count), `changes` (one `{section, shown, why}` per change-only section), `suppressed`.
  Print it with `scripts/probes/_700_review_noise/preview.py --full`. There is no Telegram command for it.
- **"Last week" is the row dated at or before `window_start`** (`get_latest_system_review(..., on_or_before=)`), not
  the newest row - an on-demand `weekly review` upserts a row dated that day. A missing or unreadable prior makes
  every change-only section PRINT (`why: "no prior"`); it never hides one.
- **Event-keyed sections** (setup review, replay-regression) print only the week a trade closed - a loser or
  post-mortem in the window, a partial-taken winner closed in it, or the live closed-trade count
  (`snapshot.live_closed_n`) differing from last week's (no stored count: print); the early-window
  drift line is dropped once the cohort reaches the band floor (the bands own the number). A compaction that raises
  falls back to the section's full text.
- **Adding a section:** give it a full renderer (stored) and, if it repeats, a `_<section>_message` sibling and a
  change predicate with a `report.changes` entry; a field it compares against next week goes in `snapshot` only if the
  raw metrics do not already hold it.

### Error Alerting
- Silent failures in theme engine write to `mi_audit_log`: `validation_error`, `assignment_error`, `discovery_error`, plus `validation_rate_limited` / `anthropic_rate_limited` for 429s.
- After nightly run: if any `*_error` events in last 2h → immediate Telegram alert.
- Morning briefing: 3-bucket banner (🔴 errors / 🟠 rate-limited / 🟡 parse errors).
- Telegram: `show errors 7d` pulls all error events for the period.
- **Safety-net self-surfacing (#501 Tier-1, 2026-09-10 — the four money-path nets that could die silently; SoT for the findings: `docs/analysis/silent_failure_taxonomy_2026-07-23.md` F1–F4).** Every event name below contains `error` so the nightly `%error%` sweep + `show errors` see it with no extra wiring; every Telegram is deduped; nothing here changes strategy, safeguards, sizing or trade state.
  - **Any audit_wrap'd job with no handler of its own** (the stuck-fill / stop-ack naked-position watchdogs were the worst cases): `core.job_audit.audit_run`'s exception branch calls `record_job_failure` → `job_failed_error` audit row on EVERY failure + `notify_job_failure` Telegram once per job per 60 min (per-process pre-gate + `tg=1` audit-log lookback, restart-proof). Before this the only trace was an unwatched `mi_job_runs status='failed'` row. `notify_job_failure` builds the error text as HTML (`error_html`: `esc()`, backtick-quoted identifiers as `<code>`) and `notify_owner` re-sends plain text on a 400 (an odd `_` count used to drop the page silently). **Sound (#635, operator-approved 2026-09-13):** every `notify_owner` page is silent (`disable_notification`) EXCEPT the death page of a job in `core/notifications.LOUD_FAILURE_JOBS` — the stop-ack + stuck-fill watchdogs, the 15-min coverage detector, the three bare-window coverage slots and the two L1 naked_position checks. Rule: loud iff the job's death removes the last DETECTION of a bare live position; repair jobs stay silent because a live detector catches their result, and every alert the detectors EMIT already buzzes (`send_telegram_message` sends no `disable_notification`). Telegram's on/off bit is the only sound lever the Bot API has.
  - **Polygon full-market snapshot 200-OK-but-EMPTY** (a detection blackout no exception can catch): guarded at the source in `collector.get_snapshot_all` → `polygon_snapshot_empty_error` row on every empty tick; Telegram "DETECTION IS BLIND" once 3 empties land within 1h (≈3 consecutive 5-min scans), then deduped for the window — via `llm_health.alert_endpoint_shape_anomaly` with the #501 `window_hours` / `sustained_count` / `telegram_text` overrides. Covers all 12 callers (EP scan, 5 flag scans, 9M, …). The exception path is NOT double-surfaced (`_polygon_get` already alerts).
  - **WS-outage backstops** `_check_fills_job` / `_stream_health_watchdog`: their handlers call `record_job_failure` with a consequence-first line (fills UNOBSERVED / a dead stream would stay dead), still swallow. Residual: `audit_wrap` still records such a run as `success`.
  - **15-min DB↔Alpaca reconcile losing a WHOLE account mode**: `order_manager.reconcile_all_modes` → `order_status_reconcile_mode_error` row per failure; Telegram "<MODE> ORDER RECONCILE DOWN" after 3 consecutive failures of the same mode (45 min at the 15-min cadence; 3 min on the 9:31–9:40 open-window variant), counter reset on the page and on that mode's next success (the `intraday_drawdown._consecutive_failures` pattern).
  - Tests drive the real paths and were mutation-checked RED: `tests/test_501_tier1_silent_failure_surfaces.py`.
- **Tier 2/3 (#635, 2026-09-30 — F5-F13 of the same taxonomy; observability only).**
  - **A `*_failed` event can no longer be silent (F5, the RED-3b class).** `scheduler._check_nightly_silent_errors` also queries `NIGHTLY_SWEEP_FAILED_LIKE` (`%\_failed%`) and lists each event that has no page of its own as a backtick-fenced NAME × COUNT (never the row summary — Markdown-400 hazard; a noisy night collapses to one line per name, capped at 6), minus `NIGHTLY_SWEEP_FAILED_ALLOWLIST` = the events whose every emit site already Telegrams in the same function. `tests/test_v1_honesty_monitoring.py` DERIVES the emitter population by AST (`tests/_audit_emitters.py`), feeds each name through the real sweep, and fails if an allowlisted event stops paging next to its audit row. `show errors` lists `*_failed` rows too (the digest sends him there). A NEW audit-only event should still be named `*_error` (its summary is shown; a `_failed` one is only counted).
  - **Money-path swallows that were log-only (F6, F8-F12 — all audit-row additions inside an existing `except`/guard; every test asserts the original control flow is unchanged).** All six events end `_error`, so the nightly sweep shows their summary line: `ep_repoll_upgrade_error` (the cached-ticker late-source re-poll raised — was `logger.debug`; distinct from `live_enriched_grade_failed`, which #543's grading-health ratio counts), `ep_candidate_parse_error` (a tick dropped ≥ `max(50, 1% of the snapshot)` rows in the per-ticker candidate build, raised rows AND rows with `prev_close` 0 / no `prevDay` key counted together with the split in the detail — **threshold un-baselined**, and a thin/just-listed ticker legitimately has `prevDay.c == 0`, so tune from the first rows; audit only), `drawdown_breaker_read_error` (`read_breaker_state` read `OK` because the DB errored — **the fail-open direction is operator-ruled and unchanged**; audit + one Telegram/mode/hour with caller-neutral text, dispatched as a background task so the entry path is never delayed), `partial_fill_close_error` (closing a <$500 partial fill raised while the row is marked closed anyway — audit + a Telegram per occurrence; both the WS and polling paths; **fire-and-forget** — `order_manager.schedule_partial_fill_close_alert` — so a 15-30s Telegram cannot hold the `status='closed'` write), `stuck_pending_new_alert_error` (F12 — the stuck-order watchdog `_maybe_alert_stuck_pending_new` raised in its own DB/Telegram step and only logged; audit every failure + one Telegram/mode/hour, background task so the reconcile loop is never delayed), `trade_stream_sdk_shape_error` (alpaca-py changed `_run_forever`, no WS fill stream — audit every trip, Telegram once per process per mode). F7 (9M volume default) is DEAD with the 9M scan.
  - **Nightly state-change alerts (F13):** step 8 is `scheduler._state_alerts_step`; a failure still does not stop the pull but now calls `record_job_failure("nightly_state_alerts", ...)`. Deliberately NOT `failures.append` — that would skip `log_job_run(nightly_data_pull)` and make `check_missed_jobs` re-run the whole pull at the next evening restart.

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
- **THE DEFAULT IS SAFE (#652, 2026-09-19; the `"Markdown"` opt-in folded into it #675, 2026-09-20): a caller that passes NO `parse_mode` writes legacy Markdown as always and `send_telegram_message` converts it ONCE at the boundary (`md_to_html`) and sends HTML — a bare `_` in a table name, a revert-SQL column, a ticker or a verdict like `TRAIL_TIGHTEN` can no longer 400 the message.** The default is a SENTINEL, not the string "HTML": an explicit `parse_mode="HTML"` is passed through untouched (never converted twice — 32 of 44 real explicit-HTML bodies would be mangled), an explicit `parse_mode="Markdown"` is CONVERTED the same as the default (#675 — the three `scheduler._backup_health_check_job` sites that were its last production callers had already migrated to the default by 2026-09-19, one after a LIVE 400 on `"pg_dump is current"`; the legacy chunker/fallback path it used is deleted, not "chunked and backstopped exactly as before" anymore), `parse_mode=None` is plain text, not converted. A long HTML message is split by `chunk_html`, which closes every tag open at the seam and reopens it in the next chunk; plain text (mode=None) uses `_chunk_plain` (not tag-aware — deliberately, since plain prose may contain a bare `<word>` that isn't a real tag). `md_to_html` mirrors the legacy fence rule (drops a language token and ONE newline after the opening ```), so a code block opens on its first line — before this the L1/L2 pages' drill SQL rendered with a blank first line. Evidence: `docs/analysis/telegram_html_default_flip_render_check_2026-09-18.md` (732 real bodies: 266 that failed the first send render under HTML, 0 regress the other way) and `scripts/probes/_675_render_check_baseline_2026-09-20.txt` (same corpus, re-run before the #675 change: still 0 regress). A 400 on the default path writes `telegram_markdown_fallback` with `mode=HTML(default)` in the detail — that row is the verify-live observable. ⚠ The default above covers only senders that go THROUGH `send_telegram_message`. Senders with their own client (python-telegram-bot in `channels/`, raw Bot-API POSTs in `core/notifications.notify_owner`, `broker/telegram_confirm.send_trade_proposal`, `briefing.edit_telegram_message`, `charts`) were left on `parse_mode=Markdown` by #652/#675 and were migrated by #121 (2026-10-01) — see the DIRECT-BOT SENDERS bullet below.
- **PAPER-ALERT CHAT (#699, 2026-10-11) — ONE switch in the single sender.** `send_telegram_message` sends a message to env `TELEGRAM_PAPER_CHAT_ID` when ALL of: no explicit `chat_id` was passed · the env var is set to a number · the text STARTS with the paper tag, derived from `constants.mode_prefix("paper")` (`constants.is_paper_message` / `paper_chat_id_for`; leading whitespace, `<b>`-style tags and a Markdown opener are skipped, so a pre-converted `parse_mode="HTML"` body such as `order_ingest._emit`'s routes the same). If the paper send fails it falls back to the main chat (WARNING `Telegram paper chat … send failed — falling back`, plus the usual `telegram_send_failed` audit row naming the chat) — never dropped; a multi-chunk message that fails part-way re-sends from its first chunk to the main chat, so the main chat may repeat chunks the paper chat already showed. Live-tagged (`💰 LIVE-$ `) and untagged system alerts, an explicit `chat_id`, interactive command replies (`channels/telegram.py`, `agent.py`) and an unset var are unchanged byte for byte. ⚠ **The tag is only as good as the caller's mode - and the tag now picks the CHAT** (review of #699, 2026-10-11, fixed before the deploy): a bare `mode_prefix()` / `mode_prefix(None)` resolves through `current_account_mode()`, which is `paper` in EVERY prod container (`ALPACA_PAPER=true`, `account_mode_active` boot rows 2026-10-11), so a live-relevant alert wearing it would have moved from "right chat, wrong label" to the WRONG chat. Hence: `bar_stream._run_stream` (stream failure, serves both books) says `constants.BOTH_BOOKS_TAG` (`⚠️ MIXED live+paper `, the same constant `order_manager._cleanup_cancel_label` returns); `entry_pipeline._skip` labels with the owning strategy's resolved `_skip_mode`; and a FAILED strategy-mode lookup (`resolve_strategy_mode_nonfatal` -> None, fail-open by design) renders `constants.strategy_mode_prefix(None)` = `UNRESOLVED_MODE_TAG` (`⚠️ MODE UNKNOWN `, main chat) instead of guessing paper - at the `live_tracker` ORB-crash page and skip digest, the `ep_detector` catalyst-downgrade ping, the `scheduler` out-of-window HIGH + skip-row-write-FAILED pages, the `entry_pipeline` skip/CAP+1 pages and the `bar_stream` subscribe-failure page. Pinned by `tests/test_699_paper_chat_routing.py::test_bare_default_label_sites_are_pinned` (only the interactive `/dryrun` reply is left bare) and the DERIVED `test_a_function_that_looks_a_strategy_mode_up_never_uses_the_guessing_prefix` (any function calling the fail-open resolver may not call `mode_prefix`). `telegram_confirm.send_trade_proposal` builds a `mode_prefix` header but bypasses the sender; it is reached ONLY for a live strategy that is not armed (`entry_pipeline._should_auto_enter` is True for every paper strategy), whose header is the untagged STAGED-PAPER banner, so it is not routed - the same test pins that reachability so a change that makes it reachable for paper fails the build. Staging reads `.env.staging` and never sets the var. Probes (`scripts/probes/_699_paper_chat/`): `dryrun_routing.py --require-env` (sends nothing; pre-check (i) resolves the container's REAL env and demands the signed id `-5382801675`, half (ii) proves the code) and `live_routing_check.py` (SENDS exactly one paper-tagged test message through the real sender; refuses unless the real env resolves to the signed id; a human then looks in Apollo Paper and the main chat). ⚠ **If paper alerts reappear in the MAIN chat with `telegram_send_failed` audit rows naming the paper chat, the group id has probably MIGRATED:** a basic Telegram group (id without the `-100` prefix) is silently upgraded to a supergroup with a NEW id when some group settings change (history visibility, admin rights, a public link), and every send to the old id then 400s. Nothing is lost (each alert falls back to the main chat; the nightly `%_failed` audit sweep reports it), but each paper alert first costs a failed send (up to 15 s on a timeout) and writes 2-3 audit rows. Fix: put the new id (the 400's `migrate_to_chat_id`, or the bot's `getChat`) in `TELEGRAM_PAPER_CHAT_ID` in the server `.env` and recreate the containers.
- Escaping dynamic strings (`_md_escape`) is still correct on the default path: `md_to_html` consumes the `\_`/`\*` it emits.
- **Before #652 (2026-09-12 → 2026-09-19) an alert carrying machine text had to opt into the HTML layer BY HAND: `send_telegram_message(md_to_html(text), parse_mode="HTML")` (`shared/telegram_format.py`; #647; the #121 migration path, `system_review.py` was the precedent). That call shape is still valid and still passed through untouched, but it is no longer required — the bare call does the same thing now.** Telegram's legacy-Markdown parser reads every bare `_` as an italic delimiter, so such a body 400s on its first send and reaches the operator only through the plain-text retry — 28 times in the 14 days to 2026-09-11, including the live OKTA exit-failure page and the catalyst-lattice revert SQL. Migrated so far: the EP alert (`send_ep_alert`), Full exit FAILED + Regime sizing FALLBACK (`order_manager`), auto-enter / proposal-send failed (`entry_pipeline`), ingest findings (`order_ingest._emit`), L1/L2 audit pages (`system_audit`), the catalyst-lattice monitor + JOB PRODUCED NOTHING (`health_checks`), the delayed-feed residual, the mgmt-judge digest, the monthly sweep digest, the LLM truncation check. `md_to_html` consumes the `\_`/`\*` that `_md_escape` emits, so an escaped builder migrates without edits. Remaining legacy surfaces after #652/#675: the senders that bypass `send_telegram_message` — see the next bullet.
- **DIRECT-BOT SENDERS ON THE HTML LAYER (#121, 2026-10-01; deliberately NOT a list — it is DERIVED).** Every send in `agents/ core/ channels/ shared/` is found by structure (the canonical sender · python-telegram-bot `reply_text` / `send_message` / `edit_message_text` · any function naming `api.telegram.org/bot…/sendMessage|editMessageText`) by `scripts/telegram_send_census.py` (`python scripts/telegram_send_census.py` prints the table, `--legacy` the failures) PLUS every non-comment line of a `*.sh` under `infra/` and `scripts/` that names `api.telegram.org/bot…` (the host-cron pages - backup failed, service DOWN, disk HIGH, restore-check FAILED - all go out through ONE curl, `infra/ops_lib.sh::telegram_alert`, which the Python-only census could not see and which kept `parse_mode=Markdown` until the #121 review caught it 2026-10-01; it is now HTML with `&`/`<`/`>` escaped in bash and a plain-text retry on any non-2xx). `tests/test_telegram_no_legacy_markdown_sends.py` FAILS THE BUILD on any `"Markdown"` / `"MarkdownV2"` constant (IN ANY CASE - Telegram accepts `"markdown"`), `ParseMode.MARKDOWN[_V2]`, `.reply_markdown()` or a shell `parse_mode=Markdown` outside its allowlist (today: only `send_telegram_message`'s own `parse_mode == "Markdown"` fold), and on a plain send whose literal text carries Markdown syntax. THE PATTERN for a sender with its own client: convert legacy Markdown ONCE at the boundary (`md_to_html`), send `parse_mode="HTML"`, and on a rejection retry with `shared.telegram_format.to_plain` (tags out, entities unescaped — it cannot touch an identifier; the old `re.sub(r"[*_`\[\]]", "", text)` retries deleted every underscore). A long reply is converted FIRST and split SECOND (`chunk_html`) — the HTML is longer than the Markdown it came from, so splitting the Markdown at 4000 can put a chunk over 4096 and a blind seam inside a `<pre>` 400s both halves. Free text the operator types (the assistant's name and persona) is built with `tf.b()/tf.esc()`, never interpolated into Markdown. Migrated: `channels/telegram.py` (every slash command and drill-down button, the LLM reply path, `send_message`; its private `_md_to_html` is now the shared one), `core/notifications.notify_owner` (every job-failure page; `notify_job_failure` builds its HTML directly - a Markdown round trip mangled backtick-quoted identifiers into `\<code>rs\_rank\</code>` and ate the closing `_` after a trailing backslash - and passes `html=True` so `notify_owner` sends it as-is; `md_escape` is deleted), `broker/telegram_confirm.send_trade_proposal`, `briefing.edit_telegram_message` (the hourly /hud refresh — the pinned message's first send is HTML too, so the two halves must not flip layers), `friday_watchlist._send_with_keyboard` (now delegates to `send_telegram_message(reply_markup=…)` — it was a second sender with no chunking) and the `charts` link fallback. PLAIN BY DESIGN (no parse_mode, not legacy Markdown): `agent.py::_send_plain_with_keyboard` (/why, /setup, /trade — dynamic prose routinely unbalances markup), `TelegramChannel.send_plain_message`, `/memory`, `webhooks.py` test + enrichment, and the bare error strings. `md_to_html` also renders CommonMark `**bold**` as bold (the orchestrator prompt tells Claude to write `**Action required:**`; the single-star rule alone printed stray asterisks) — a CONVERTER change that reaches every `send_telegram_message` caller. DEPLOY SCOPES (all three services): `channels/` = orchestrator; `core/notifications.py` = orchestrator + market + execution (the market image COPYs it); `briefing.py` and `broker/telegram_confirm.py` = market + **execution** (both on `exec_loaded_modules.txt`; silent-dark without `deploy.sh execution`); `shared/telegram_format.py` = all three; `charts`/`friday_watchlist` = market-agent.
- The plain-text backstop (`_strip_markdown_markers`) is unreachable from `send_telegram_message` after #675 (nothing sets `mode == "Markdown"` anymore) but is kept: `scripts/probes/_652_render_check.py` imports it as the legacy-fallback emulator, and `tests/test_briefing_markdown_fallback.py` / `tests/test_647_machine_text_alerts_on_html_layer.py` pin its own behavior directly. On the HTML path the live backstop strips tags and unescapes, so machine text survives there by construction.
- Skip-reason machine prefixes (`infra:subscribe_timeout: ...`) → run through `humanize()` before user display. DB keeps machine prefix; user sees prose.
- Reserve Telegram for terminal/actionable events. Self-healing/transient → `mi_audit_log` only.
