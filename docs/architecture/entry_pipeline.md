# Entry Pipeline + Stop-Leg ID Capture

> SSoT for the single ORB-entry funnel + the stop-leg capture helper. Moved
> verbatim from CLAUDE.md 2026-07-16 (#417 doc-backfill) — update THIS file in
> the same commit as any pipeline change. The Telegram-on-terminal-failure
> contract + "never re-implement the stop-leg loop" stay inline in CLAUDE.md.

## Entry Pipeline

- **`broker/entry_pipeline.py::submit_trade_entry`** — single funnel for both MAGNA53 EP and 9M Day 2 entries. Strategy differences (stop source, sizing) inject via `spec_builder` callback. Pipeline owns: dedup → safeguards (cheap early gate) → bar-fetch retry → fade guard → spec build → per-strategy sizing multiplier → **atomic cap-recheck + DB insert (+ auto-enter confirm flip) in one transaction under a per-`account_mode` `pg_advisory_xact_lock` (#461, `_CAP_LOCK_NAMESPACE = 0x434150 "CAP"`; recount via the shared `live_tracker.count_open_positions` — closes the STEP-2→insert TOCTOU race; cap-blocked recheck returns the byte-identical `block:max_positions` / `block:strategy_position_cap` skip + a `cap_recheck_blocked` audit event; no external I/O inside the lock)** → Alpaca submit (post-commit) → audit log → Telegram. **Contract: every terminal failure Telegrams via `humanize()`.**
- `account_mode` resolved at safeguard step from `strategy.phase` via `resolve_account_mode_for_strategy()` and threaded through spec_builder, alpaca client calls, DB inserts, and Telegram surfaces. SpecBuilder type alias takes account_mode as 4th positional arg.
- Bounded action vocabulary: `ACTION_AUTO_ENTERED / PROPOSED / AUTO_ENTER_FAILED / PROPOSAL_SEND_FAILED / SKIPPED / BLOCKED`.
- Bounded skip-reason vocabulary in `broker/skip_reasons.py` — 19 constants across `filter:* / setup:* / block:* / infra:* / window:*`. Aggregate via `split_part(skip_reason, ':', 1)`. New: `block:strategy_position_cap` for per-strategy slot limit (#65).

## Stop-Leg ID Capture

- `alpaca_client.extract_stop_leg_id(order)` is the canonical helper — uses `stop_price` as primary signal, case-insensitive `"stop" in type_str` fallback. Robust against Python 3.11+ Enum stringification (`str(OrderType.STOP)` → `"OrderType.STOP"`).
- Used in: `place_bracket_order` (naked-order guard), `submit_entry`, `check_fills`, `attempt_day1_reentry`, `_process_entry_fill`. Never re-implement the loop.
- `_process_entry_fill` checks 3 sources before remediation: WS event legs, DB `stop_order_id`, REST refetch.
