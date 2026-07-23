# Entry Pipeline + Stop-Leg ID Capture

> SSoT for the single ORB-entry funnel + the stop-leg capture helper. Moved
> verbatim from CLAUDE.md 2026-07-16 (#417 doc-backfill) — update THIS file in
> the same commit as any pipeline change. The Telegram-on-terminal-failure
> contract + "never re-implement the stop-leg loop" stay inline in CLAUDE.md.

## Entry Pipeline

- **`broker/entry_pipeline.py::submit_trade_entry`** — single funnel for both MAGNA53 EP and 9M Day 2 entries. Strategy differences (stop source, sizing) inject via `spec_builder` callback. Pipeline owns: dedup → safeguards (cheap early gate) → bar-fetch retry → fade guard → spec build → per-strategy sizing multiplier → **atomic cap-recheck + DB insert (+ auto-enter confirm flip) in one transaction under a per-`account_mode` `pg_advisory_xact_lock` (#461, `_CAP_LOCK_NAMESPACE = 0x434150 "CAP"`; recount via the shared `live_tracker.count_open_positions` — closes the STEP-2→insert TOCTOU race; cap-blocked recheck returns the byte-identical `block:max_positions` / `block:strategy_position_cap` skip + a `cap_recheck_blocked` audit event; no external I/O inside the lock)** → Alpaca submit (post-commit) → audit log → Telegram. **Contract: every terminal failure Telegrams via `humanize()`.**
- `account_mode` resolved at safeguard step from `strategy.phase` via `resolve_account_mode_for_strategy()` and threaded through spec_builder, alpaca client calls, DB inserts, and Telegram surfaces. SpecBuilder type alias takes account_mode as 4th positional arg.
- Bounded action vocabulary: `ACTION_AUTO_ENTERED / PROPOSED / AUTO_ENTER_FAILED / PROPOSAL_SEND_FAILED / SKIPPED / BLOCKED`.
- Bounded skip-reason vocabulary in `broker/skip_reasons.py` — 38 constants across `filter:* / setup:* / block:* / infra:* / window:* / broker:*`. Aggregate via `split_part(skip_reason, ':', 1)`. `broker:*` (#500, 2026-07-23) = the BROKER killed an accepted entry (cancel/reject/expire) — written with a synthesized last-vs-trigger diagnosis by `order_manager.broker_terminal_reason` (WS `_handle_cancel_or_reject` + `check_fills` polling backup), never the pre-#500 bare `"cancelled"`.
- **#500 price-aware submit (2026-07-23, operator-signed)**: `order_manager.submit_entry` checks `get_latest_trade` before placing the order — price ≤ ORB high (or any data flake) → the stop-limit bracket, byte-identical; price > ORB high (today's order = guaranteed broker cancel, the ARWR 7/22 class) → `place_limit_buy_with_stop` at `latest×1.002`, same stop leg/COID/mode threading, bounded by `CHASE_RISK_INFLATION_CAP` (1.5× planned risk; beyond → `setup:chase_cap_exceeded` skip + Telegram via `humanize()`). The 5s retry re-decides the branch; `mi_live_orders` records the ACTUAL order type/limit. Detection, sizing, safeguards unchanged. SSoT: `docs/setups/magna53_ep.md` change log 2026-07-23.

## Stop-Leg ID Capture

- `alpaca_client.extract_stop_leg_id(order)` is the canonical helper — uses `stop_price` as primary signal, case-insensitive `"stop" in type_str` fallback. Robust against Python 3.11+ Enum stringification (`str(OrderType.STOP)` → `"OrderType.STOP"`).
- Used in: `place_bracket_order` (naked-order guard), `submit_entry`, `check_fills`, `attempt_day1_reentry`, `_process_entry_fill`. Never re-implement the loop.
- `_process_entry_fill` checks 3 sources before remediation: WS event legs, DB `stop_order_id`, REST refetch.
