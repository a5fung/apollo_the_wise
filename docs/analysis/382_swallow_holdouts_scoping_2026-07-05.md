# #382 — Money/Trade-Path Swallow Holdouts: Scoping Report

**Date**: 2026-07-05
**Scope**: The ~13 (true count: **14**) broad+silent `except` sites in
money/trade-path code that #381's remediation deliberately deferred, per
`scripts/preflight_no_silent_failures.py`'s own "money" classification bucket.
**Status**: READ-ONLY scoping. No code changed. Each site below gets a
proposed disposition; nothing is applied here — that's a separate,
operator-gated pass per file (THE LINE / CLAUDE.md).

## How sites were found

`scripts/preflight_no_silent_failures.py` statically AST-walks
`agents/ core/ channels/ shared/` for `except` handlers that are (a) broad
(`except:` / `except Exception` / `except BaseException`, or a tuple
containing one) AND (b) silent (body has neither a `raise` nor a call to a
name in `LOUD_NAMES` — logging/audit/Telegram/humanize/etc.), and that lack a
`# loud-ok:` escape comment. It carries a 95-site baseline
(`scripts/no_silent_failures_baseline.json`) as a ratchet — new swallows fail
CI, existing ones are tracked debt.

Its own `PATH_CLASS` bucketing tags a site **"money"** by substring match on
the relative path: `broker/`, `entry_pipeline`, `order_manager`,
`trade_stream`, `live_tracker`, `execution_client`, `alpaca_client`. Running
that exact classifier against the current baseline (not re-deriving it by
hand, to stay consistent with what CI actually gates on) gives:

```
MONEY class count: 14  (of 95 total baseline sites)
agents/market_intelligence/broker/bar_stream.py:120
agents/market_intelligence/broker/bar_stream.py:177
agents/market_intelligence/broker/entry_pipeline.py:88
agents/market_intelligence/broker/entry_pipeline.py:219
agents/market_intelligence/broker/entry_pipeline.py:267
agents/market_intelligence/broker/entry_pipeline.py:348
agents/market_intelligence/broker/entry_pipeline.py:397
agents/market_intelligence/broker/entry_pipeline.py:457
agents/market_intelligence/broker/entry_pipeline.py:473
agents/market_intelligence/broker/gap_through_telemetry.py:270
agents/market_intelligence/broker/live_tracker.py:297
agents/market_intelligence/broker/live_tracker.py:334
agents/market_intelligence/broker/trade_stream.py:171
agents/market_intelligence/broker/trade_stream.py:291
```

**Count discrepancy vs. the ~13 expected**: true count is **14**, not 13 —
one more than expected, from `bar_stream.py` (2 sites) which the task's
example file list didn't name explicitly but which the classifier's own
`broker/` substring rule correctly buckets as money-path (it owns the
WebSocket subscribe/unsubscribe path that feeds `entry_pipeline` at 9:31 ET).

**Confirmed clean (checked, not just absent from the list)**: the other
broker/execution files the task named — `order_manager.py` (27 broad excepts,
0 silent), `alpaca_client.py` (18 broad excepts, 0 silent), `exit_logic.py`
(0 broad excepts), `telegram_confirm.py` (3 broad excepts, 0 silent),
`drawdown_breaker.py`, `shadow_orb_tracker.py`, `orb_extension_shadow.py`
(0 silent each), `execution_routes.py` (1 broad except, 0 silent), and
`execution_client.py` (1 broad-and-would-be-silent except, but it already
carries a `# loud-ok:` escape at line 138) — all have **zero** open swallow
violations under the same classifier. Notably, **`order_manager.py`
(stop-leg capture, fill processing, replace-order) and `alpaca_client.py`
(the actual Alpaca REST/order calls) are both already fully clean** — the
never-naked-stop machinery itself carries no open holdouts under #382's scope.

## Headline finding: 12 of the 14 sites wrap a call that provably cannot raise

`agents/market_intelligence/db.py:8302`, `log_audit_event()`, is documented
and implemented as never-raising:

```python
async def log_audit_event(event_type: str, summary: str, detail: str = "") -> None:
    """... Never raises — safe to call from anywhere. ..."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO mi_audit_log (event_type, summary, detail) VALUES ($1, $2, $3)",
                event_type, summary[:500], detail[:8000],
            )
    except Exception as e:
        logger.warning(f"audit log write failed ({event_type}): {e}")
```

Every argument type issue, DB/pool failure, or query error is caught and
`logger.warning`'d **inside** `log_audit_event` itself. 12 of the 14 flagged
sites do nothing but `try: await log_audit_event(...) / except Exception: pass`
around this call — i.e. they wrap an already-self-protecting, already-loud
function in a second, redundant, *silent* shell. The AST scanner can't see
this (no interprocedural analysis) and correctly flags the local shape, but
functionally these 12 `except: pass` bodies are **unreachable dead code** —
under normal operation they can never fire, and if `log_audit_event` is ever
changed to actually raise, that's a deliberate future decision, not something
this holdout list should pre-empt.

Only **2 of the 14** wrap something that can genuinely raise:
`gap_through_telemetry.py:270` (a raw `conn.fetchval` DB read) and
`trade_stream.py:171` (`await stream.close()`, a WebSocket SDK call). Both are
best-effort/cosmetic paths with their own docstring-stated "failures don't
block X" contract — see per-site detail below.

**Net result: 0 of the 14 sites need a control-flow change.** None gate a
real trade decision on whether the wrapped call succeeds — the actual
trade-state action (DB insert, Alpaca submit, Telegram alert) either already
happened before the try, or fires unconditionally right after it, in every
one of the 14. Batch-2 (control-flow changes) is empty for this holdout set.

## Highest-stakes site (invariant-adjacent)

| Site | Why it's called out separately |
|---|---|
| `trade_stream.py:291` — `_verify_event_account_mode()` | This is the **cross-account contamination guard** — the function that keeps a paper-stream WebSocket event from mutating a live trade row (or vice versa), described in the module docstring as "load-bearing defense in depth." The swallow at line 291 only wraps the `cross_account_event_rejected` **audit-log write** (dead code per the finding above — `logger.error` already fires unconditionally one line earlier, and the caller's `return False` / event-drop happens regardless of whether this write succeeds). So the safety behavior itself is *not* at risk from this specific swallow — but because of its proximity to the invariant, its remediation comment should be unusually explicit (see per-site table), and any future touch to this function should get the #151-style paper-account exercise, not just a code review. |

No site in this holdout set touches stop-leg capture (`extract_stop_leg_id`),
`sync_positions()`, or `_process_entry_fill()` directly — those live in
`order_manager.py` / `alpaca_client.py`, both confirmed clean above.

## Summary table

| # | File:line | Enclosing fn | Wraps | Failure class | Nearby telemetry | Blast radius if silent | Proposed remediation | Risk | Batch |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `bar_stream.py:120` | `_run_stream` | `log_audit_event("bar_stream_disconnect")` | (dead — see above) | `logger.error` fires unconditionally 2 lines above; terminal-retry Telegram fires separately | Loses only the `bar_stream_disconnect` audit DB row on a self-healing retry; already in container logs | `# loud-ok`: never-raises annotation | LOW | 1 |
| 2 | `bar_stream.py:177` | `_record_subscribe_failure` | `log_audit_event("orb_subscribe_failed")` | (dead) | Caller (`subscribe_ep_candidate`) already `logger.error`'d before calling this helper; a Telegram alert follows 2 lines later (own try/except, logs on failure) | Loses only the `orb_subscribe_failed` audit row (used by `/why`) | `# loud-ok` annotation | LOW | 1 |
| 3 | `entry_pipeline.py:88` | `fetch_orb_bar_with_retry` | `log_audit_event("orb_bar_miss")` | (dead) | `logger.info` fires immediately above | Loses only the mid-retry informational audit row | `# loud-ok` annotation | LOW | 1 |
| 4 | `entry_pipeline.py:219` | `submit_trade_entry._skip()` | `log_audit_event(audit_event)` | (dead) | A Telegram skip/block alert always follows a few lines later (its own try/except is loud) | Loses the audit row for whichever skip/block reason fired — this is the single most-travelled of the 12 dead sites (every skip/block/fade path in the pipeline routes through `_skip()`) | `# loud-ok` annotation | LOW | 1 |
| 5 | `entry_pipeline.py:267` | `submit_trade_entry` (duplicate check) | `log_audit_event("orb_duplicate")` | (dead) | None in this branch (deliberately no Telegram — "already handled once"); only a `logger.debug` a few lines above | Loses the `orb_duplicate` audit row; the underlying trade row already exists from a prior, fully-telemetered pass | `# loud-ok` annotation | LOW | 1 |
| 6 | `entry_pipeline.py:348` | `submit_trade_entry` (post-bar-fetch) | `log_audit_event("orb_bar_fetched")` | (dead) | None nearby beyond the general pipeline flow | Loses the descriptive OHLC-of-ORB-bar record used for `/why` reconstruction; pipeline proceeds identically either way | `# loud-ok` annotation | LOW | 1 |
| 7 | `entry_pipeline.py:397` | `submit_trade_entry` (composite sizing) | `log_audit_event("per_strategy_sizing_applied")` | (dead) | None nearby | Loses the audit record of a real sizing decision, but the sizing math (`order_spec["shares"]` etc.) was already mutated above this block — unaffected | `# loud-ok` annotation | LOW | 1 |
| 8 | `entry_pipeline.py:457` | `submit_trade_entry` (auto-enter, submit failed) | `log_audit_event("orb_order_failed")` | (dead) | `logger.error` fires immediately above; an **unconditional** Telegram alert fires immediately after (not gated on this try) | Loses only the `orb_order_failed` audit row; operator is still alerted | `# loud-ok` annotation | LOW | 1 |
| 9 | `entry_pipeline.py:473` | `submit_trade_entry` (auto-enter, success) | `log_audit_event("orb_order_placed")` | (dead) | Trade already durably in `mi_live_trades` + submitted to Alpaca *before* this line; a success Telegram fires unconditionally after | Loses only a supplementary audit row for an already-durable (DB + Alpaca + Telegram) real entry | `# loud-ok` annotation | LOW | 1 |
| 10 | `gap_through_telemetry.py:270` | `reclassify_orb_cancellations_eod` | raw `conn.fetchval(...)` — prior classification label lookup | **Real** (DB read can genuinely fail) | None — but function docstring: "AUDIT-ONLY... Read + telemetry only — never mutates trade state" | Loses only a decorative "(was intraday X)" annotation on an EOD retrospective reclassification record; the classification + audit write happen regardless | Add `logger.debug(...)` on the exception (cheap visibility into DB flakiness) | LOW | 1 |
| 11 | `live_tracker.py:297` | `process_new_alerts_live` | `log_audit_event("orb_triggered")` | (dead) | `logger.info` fires immediately above | Loses only the `orb_triggered` batch-summary audit row | `# loud-ok` annotation | LOW | 1 |
| 12 | `live_tracker.py:334` | `process_new_alerts_live._process_alert` | `log_audit_event("orb_filtered")` | (dead) | `logger.info` fires immediately above; the actual skip is already durably recorded via `_insert_skipped_trade()` (uncaught, i.e. NOT swallowed) a few lines earlier | Loses only the supplementary `orb_filtered` audit row; the skip itself is already durable in `mi_live_trades` | `# loud-ok` annotation | LOW | 1 |
| 13 | `trade_stream.py:171` | `stop_trade_stream` | `await stream.close()` | **Real** (WebSocket SDK close can raise) | None — shutdown-path cleanup, container is exiting regardless | A stream fails to close cleanly during shutdown; no live-trading consequence since the process is terminating anyway | Add `logger.debug(...)` on the exception (diagnostic-only, no behavior change) | LOW | 1 |
| 14 | `trade_stream.py:291` | `_verify_event_account_mode` | `log_audit_event("cross_account_event_rejected")` | (dead) | `logger.error(CROSS_ACCOUNT_EVENT_REJECTED...)` fires unconditionally one line above; `return False` (event dropped) happens regardless of this write's outcome | Loses only the audit-log row for an already-logged, already-enforced cross-account rejection — see "highest-stakes" note above for why this gets called out despite being dead code | `# loud-ok` annotation (write it extra-explicit given the invariant proximity) | LOW | 1 |

## Per-site detail (full context read, not just the line)

- **bar_stream.py:120 / 177** — Both sit in the WebSocket subscribe/reconnect
  path that feeds the 9:31 ET ORB entry trigger. Both wrap
  `log_audit_event(...)` preceded (120) or followed (177) by an unconditional
  loud call (`logger.error` / Telegram). Minor caveat: both try-bodies also
  contain an inline `from agents.market_intelligence.db import
  log_audit_event` import statement — in a catastrophically broken deploy an
  `ImportError` here is theoretically possible, but the module is already
  imported successfully elsewhere in the same running process by this point,
  so this doesn't change the practical "dead code" conclusion.
- **entry_pipeline.py** (7 sites) — This file is the single funnel for every
  ORB bracket entry (MAGNA53 + 9M Day 2). All 7 sites are
  `log_audit_event(...)`-wrapping and none gate the actual state mutation:
  the DB insert into `mi_live_trades` (line ~402), the Alpaca submit
  (`submit_entry`, line 445), and every terminal Telegram (`_skip`'s alert,
  the auto-enter-failed alert, the success alert, the proposal-failed alert)
  are all **outside** these try blocks and unconditioned on their outcome.
  `_skip()` (site #4) is the highest-traffic of the seven since it's the
  shared helper for every skip/block/fade branch, but its own risk profile
  is identical to the others — dead code around a non-raising call.
- **gap_through_telemetry.py:270** — Inside the EOD reclassification job
  (`reclassify_orb_cancellations_eod`), which the module docstring explicitly
  scopes as "Read + telemetry only — never mutates trade state." The wrapped
  `conn.fetchval` is a genuine DB call that could fail, but its only use is a
  cosmetic "(was intraday clean_miss)" annotation on a corrected audit record;
  the corrected classification + its `log_audit_event` write happen either
  way, a few lines later, unconditioned on `prior`.
- **live_tracker.py:297 / 334** — Both in `process_new_alerts_live`, the 9:31
  AM ORB monitor. Both wrap `log_audit_event`; both have an unconditional
  `logger.info` immediately above. Site 334's actual skip-state write
  (`_insert_skipped_trade`, DB row with `skip_reason`) happens a few lines
  *before* this try and is NOT itself wrapped — so the real skip is durable
  regardless of whether the `orb_filtered` audit-log echo succeeds.
- **trade_stream.py:171 / 291** — 171 is inside `stop_trade_stream()`
  (container shutdown), closing each per-mode WebSocket; a real but
  zero-live-trading-consequence swallow since the process exits regardless.
  291 is inside `_verify_event_account_mode()` — see "highest-stakes" above.

## Proposed batches

**Batch-1 — telemetry-only / annotation-only (all 14; safe to ship together
in one small PR, zero behavior change):**
- **12 sites** get a `# loud-ok: log_audit_event() never raises — it
  self-catches and logs internally (db.py:8302); <site-specific one-liner
  on what's already loud nearby>` comment on the `except` line. This is a
  pure-comment change (satisfies the gate's own documented escape hatch for
  "a fallback-of-the-fallback where even the alert can fail" — here the alert
  literally cannot fail). No runtime behavior changes at all.
- **2 sites** (`gap_through_telemetry.py:270`, `trade_stream.py:171`) get a
  one-line `logger.debug(...)` added inside the except body — these wrap
  genuinely-fallible calls with currently zero visibility if they fire; a
  debug log is free diagnostic value with no control-flow change.

**Batch-2 — control-flow changes: NONE.** No site in this holdout set
requires narrowing the except type, re-raising, or otherwise changing what
happens on failure. Every one of the 14 already lets its surrounding
function proceed identically whether the wrapped call succeeds or fails —
that's precisely why they were safe to defer out of #381 in the first
place, and why, on inspection, none of them turn out to need the #151-style
"exercise against real paper Alpaca before relying on a cron" discipline.
The only site worth a heavier hand on the *comment* (not the code) is
`trade_stream.py:291`, given its proximity to the cross-account invariant.

## Sequencing

1. Ship Batch-1 as one commit/PR touching all 14 sites (comment-only for 12,
   one-line `logger.debug` add for 2). Run
   `python scripts/preflight_no_silent_failures.py --update-baseline`
   afterward to shrink the baseline from 95 → 81 (confirms real reduction,
   per the ratchet's own rule against burying swallows — here they're
   resolved, not buried, since each carries a verified justification).
2. No Batch-2 pass is needed for this holdout set. If a future audit of
   `order_manager.py` / `alpaca_client.py` (both currently zero-violation)
   ever finds a *new* swallow introduced there, that would be the first
   genuine candidate for a control-flow-level (#151-disciplined) review in
   the money path — nothing in the current 14 rises to that bar.
3. Optional (not required, low priority): consider whether the 12
   dead-code shells around `log_audit_event()` are worth deleting outright
   (not just annotating) in a later cleanup pass — purely a
   simplify/readability call, not a #382 gate concern, and NOT recommended
   to bundle with this ship (keep the diff minimal and reviewable).
