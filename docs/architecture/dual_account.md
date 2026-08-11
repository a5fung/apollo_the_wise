# Dual-Account Architecture (#66, 2026-05-10)

> SSoT for the two-Alpaca-account routing layer. Moved verbatim from CLAUDE.md
> 2026-07-16 (#417 doc-backfill) — update THIS file in the same commit as any
> code change (stale SSoT is worse than none). The 3 correctness invariants
> stay inline in CLAUDE.md; everything here is the full detail.

**One Apollo container, two Alpaca accounts** (paper + live), routed per-strategy via `mi_strategies.phase`:

| phase | live_real_enabled | account_mode | Submit destination |
|---|---|---|---|
| shadow | – | (n/a) | No submit; audit telemetry only |
| paper | – | paper | Alpaca paper account (real fills, fake $) |
| live | False | live | 🟡 STAGED-PAPER Telegram proposal; no auto-submit |
| live | True | live | Alpaca live account (real fills, real $) |

**Key components:**
- `constants.resolve_account_mode_for_strategy(strategy)` — SSoT mode resolver. Pre-dual-account global `current_account_mode()` kept for non-trade contexts (`/status`, boot audit).
- `alpaca_client.get_trading_client(account_mode)` — per-mode TradingClient singletons, independent HTTP sessions (no shared pool). Every wrapper accepts optional `account_mode`.
- `alpaca_client.make_client_order_id(account_mode, strategy_id, ticker)` — strict mode-bound `apollo_{mode}_{strategy}_{ticker}_{ms_epoch}` format. **Required at every order submission site** to prevent cross-account COID collisions.
- `trade_stream.py` — two TradingStream instances (one per mode), each handler closure-bound to its account_mode. `_dispatch_trade_event` runs `_verify_event_account_mode` before any DB mutation; mismatches drop the event + emit `cross_account_event_rejected` audit (defense in depth even with mode-bound COIDs).
- `_check_safeguards(account_mode, signal_type)` — per-mode isolated (paper at-cap doesn't constrain live). Per-strategy `max_concurrent_positions` enforced WITHIN per-mode envelope. NULL = share global cap.
- `sync_positions()` iterates `['paper','live']` (or `['paper']` if `ENABLE_LIVE_MODE=false`) — runs `_sync_positions_for_mode(account_mode)` per mode. Each mode's mi_live_trades query carries `AND account_mode = $1`.
- `account_equity_snapshot_job` (16:12 ET) iterates both modes; drawdown breaker state per mode (`mi_safeguard_state` PK = `(safeguard, account_mode)`).

**Boot bootstrap** (`agent.py::_bootstrap_alpaca_credentials`):
- `ENABLE_LIVE_MODE=true` (default): hard-requires `ALPACA_PAPER_API_KEY/SECRET` AND `ALPACA_LIVE_API_KEY/SECRET`. Boot-blocks if either pair missing.
- `ENABLE_LIVE_MODE=false`: only `ALPACA_PAPER_*` required. Strategies at `phase='live'` blocked. Dev / single-account opt-out.
- Legacy `ALPACA_API_KEY`→paper remap still in code (`legacy_alpaca_creds_fallback` audit; was "one cycle only" from 5/10 — removable).
- Post-init `verify_dual_account_clients()` smoke-tests both accounts, emits `dual_account_boot_verified` (success) or `dual_account_boot_failed` (per-mode error detail).

**Per-strategy sizing/cap** (#65, two mi_strategies columns):
- `position_size_multiplier NUMERIC DEFAULT 1.0` — applied in entry_pipeline AFTER spec_builder so it covers every builder uniformly — `prepare_orb_order` and `prepare_prior_day_low_orb_order` (renamed from `prepare_9m_day2_orb_order` 2026-08-02, #515). Multiplies shares; recomputes position_size + risk_dollars.
- `max_concurrent_positions INT NULL` — per-strategy slot cap. NULL = share global `MAX_CONCURRENT_LIVE_POSITIONS`. Use case: a newly promoted strategy starts at multiplier=0.5 + cap=2. (The original worked example was 9M Day 2; that strategy was DELETED 2026-08-02, #515 — no strategy is currently promoting, and every live row sits at multiplier=1.0.)

**The 3 correctness invariants (the safety backbone — never relax any):**
1. Mode-bound client order IDs at every submission site.
2. Cross-account event rejection before any DB mutation.
3. `account_mode` filter on every trade query.

## Account-mode / phase literals & graduation (2026-08-11)

**The rot class:** a query hardcoding `account_mode = 'paper'` (or `'live'`, or a
`phase = '...'`) is correct the day it ships and silently stops matching reality the day
the strategy's `mi_strategies.phase` changes. Known case: `db.py::get_flag_universe`
path (c) pinned `'paper'` on 2026-05-17; MAGNA53 graduated to live 2026-06-22; the
mechanism ran dark ~7 weeks (17 live R3 rows invisible vs 1 paper) and nothing said so.
Fixed 2026-08-11 by dropping the filter (a ticker's chart doesn't care which book
recorded the stop-out). Same day, a latent sibling was found and fixed:
`live_tracker.process_new_alerts_live` inserted `check_filters` skip rows without
`account_mode`, defaulting to `current_account_mode()` = `'paper'` on prod (the legacy
`ALPACA_PAPER=true` env) — armed but never fired (zero `filter:*` rows in prod history).

**The rule:** never hardcode an account-mode or phase literal in production SQL without a
reviewed escape on the literal's line — `# mode-ok: <reason>` (Python side) or
`-- mode-ok: <reason>` (inside a SQL string). Prefer, in order: resolve the mode
dynamically (`resolve_account_mode_for_strategy`), drop the filter when the question is
mode-independent, and only then pin with an annotation.

**Enforcement, two halves (one scanner — `scripts/preflight_account_mode_literals.py`):**
1. **Deploy gate `[5o/7]`** — fails the deploy on any unannotated
   `account_mode|phase = '<paper|live|shadow|deprecated>'` literal in
   `agents/ core/ channels/ shared/` (docstrings/comments exempt; `backtester/`,
   `scripts/`, `tests/` out of scope). This keeps the pin INVENTORY complete.
2. **Nightly runtime sweep** — `health_checks.run_account_mode_graduation_sweep`
   (scheduler `_post_nightly_audit_job`). Silent on a healthy day. Announces:
   - **Phase transition** (the graduation itself): any diff in the `mi_strategies`
     phase map vs the audit-log snapshot (`strategy_phase_snapshot`) → one Telegram
     with the transition(s) + the full pinned-literal inventory as the review
     checklist. The snapshot advancing is the dedupe (once per transition).
   - **Dormant pinned book**: an `mi_live_trades` book with ≥30 lifetime rows, no new
     row in 21+ days while another book moves, AND ≥1 query still pinned to it → one
     Telegram, once per (table, mode) EVER (`account_mode_book_dormant` audit rows are
     the dedupe — the dead-column sweep pattern).

**Known deliberate non-filters (do NOT "fix" these):**
- The five `mi_safeguard_state` runtime toggles keyed `(<name>, "paper")`
  (`_JUDGE_TOGGLE`, `_COMPOSITE_TOGGLE`, `_SUBTHEME_ARM_TOGGLE`, `_LANE2_V2_TOGGLE`,
  `_THEME_BIRTH_GATE_TOGGLE`, db.py) — `"paper"` there is a fixed NAMESPACE key in the
  `(safeguard, account_mode)` PK, always read and written through the same module
  constant. It never filters trade data; a graduation cannot rot it. Confusing, not
  broken. (`_MANUAL_HALT = ("manual_trading_halt", "live")` is the same shape and IS
  meaningfully live: `/pause` is the real-money halt; its read sites gate on
  `account_mode == "live"` explicitly.)
- `_seed_strategies_registry`'s `"phase": "paper"` seed default — `ON CONFLICT DO
  NOTHING`; a fresh DB deliberately starts paper (the 2026-05-13 lesson), prod rows
  untouched.
- `current_account_mode()` reads the legacy `ALPACA_PAPER` env (`true` on prod →
  `'paper'`). It is a LABEL/fallback resolver only; every trade-bound write/read must
  thread an explicit mode (#444). Any new writer defaulting through it will put rows in
  the dormant paper book — the graduation sweep's dormant-book check is the backstop.
