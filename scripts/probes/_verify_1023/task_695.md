# #695 (two columns nothing wrote) - verify Fri 10-23 18:20 ET - VERDICT: EVENT-GATED (market_cap branch MET; live-fill mark_r branch not yet observable)

## Text judged against (verbatim from the PLAN.md line)
- DoD: "each column either has a writer that has filled it on prod (count > 0 after the next run) or is dropped in a migration with its readers removed, AND tonight's sweep log no longer counts it as dead."
- EXPECT: "the sweep log reads 0 dead, event-gated >= 1, 0 error(s); `information_schema` has no mi_stock_scores.market_cap; tonight's RS run writes its ~2,400 mi_stock_scores rows with no upsert error."
- DONE-WHEN: "one sweep night meeting that." (first met Fri 10-09)
- WOULD-FAIL-IF: "errors > 0, event-gated = 0 while live-fill has no horizon row, a new suspect/detected row for a .mark_r key without an event row, or an RS upsert error."
- Standing note in the line: live-fill `mark_r` 'count > 0' waits on its first 40-session horizon arm; "Close then, quoting the DoD."

## Criteria (all queries read-only; evidence inlined below; query files not committed - this card is report-only)
- MET - sweep line tonight 21:30:40 UTC (17:30 ET): `Dead-column sweep: 93 tables, 0 dead (0 new), 0 suspect, 1 event-gated, 0 error(s)`; same shape every night since 10-09 (10-19..10-22 read 3/3/2/1 event-gated, 0 dead, 0 errors).
- MET - `information_schema` has no mi_stock_scores.market_cap (0 rows). Repo has no reader: the only `market_cap` near `mi_stock_scores` is the DROP in db.py:453-460 (comment + `DROP COLUMN IF EXISTS`).
- MET - tonight's RS run: log `RS Engine: stored 2363 scores` (log 21:00 UTC = 17:00 ET); table has 2,363 rows for 10-23 (10-22: 2,380; 10-21: 2,373). No error rows (mi_audit_log event types stock_score/rs_/upsert: none today; ERROR lines tonight were theme invariant, 9M outcomes `gap_pct`, CoinGecko - none touch #695).
- MET - WOULD-FAIL-IF, all four literally: errors = 0; event-gated = 1 and live-fill horizon rows = 0 (so exemption is correct, not hiding a live event); dead_column rows since 10-09 = 0 (only the 3 old announcements 08-08 / 09-07 exist); no RS upsert error.
- MET (positive writer evidence for the other mark_r columns) - mi_gap_near_miss_replays has 2 open/horizon rows and 2 non-null mark_r, so a wired mark_r writer does fill while a walk is open.
- NOT YET OBSERVABLE - live-fill `mark_r` "count > 0": 0 of 195 rows non-null, 0 `horizon` rows (outcomes: settled 182, unscoreable 10, abstain 3).
- 18:04 ET job tonight ran (log 22:04 UTC): `live-fill counterfactuals: 0 arm row(s) written across 2 fill(s) - 0 settled, 0 abstained, 0 unscoreable, 0 at horizon, 9 pending, 0 error(s)`; audit row 18:04:00 same text. Nothing recorded since 10-22 18:04.

## The 10-12 forecast did not come true
- Forecast was "earliest possible Fri 10-23 18:04 (OKTA trade 382, trail_pivot_swing arm, only if still open)". That arm SETTLED on 10-16 at 35 sessions walked, so it never reached 40. All 15 other fills since 08-16 have 12/12 arms except two below.
- Pending 9 arms = KOD (trade 404, fill 9-28, closed 10-13) missing 1 arm (by elimination vs OKTA's 12: `trail_character_ma`; 19 sessions walked tonight) + IRON (trade 422, fill 10-19, still open) missing 8 arms.
- Earliest remaining horizon candidates, by my hand count with Thanksgiving closed: KOD 40th session = Mon 2026-11-23 18:04 ET (only if that arm is still open); IRON = Tue 2026-12-15. The old "next SEI Nov 3" is void - SEI is 12/12 settled. New fills add later candidates.
- Longest walk ever recorded is 35 sessions (OKTA); of 195 rows none has reached 40. The horizon event is rare, so the live-fill branch may wait weeks to months.

## Discrimination (what a BROKEN system would show)
- Sweep line `0 dead, 1 event-gated` does NOT discriminate for the live-fill branch: a dormant healthy writer and a broken horizon writer read identically until a horizon row exists - by design the exemption lapses only then.
- It DOES discriminate for market_cap: if the RS writer still referenced the dropped column, the INSERT would fail and score_date 10-23 would have 0 rows, not 2,363.
- The check that will discriminate for live-fill: first `horizon` row appears; non-null `mark_r` on it = writer works; NULL = sweep files `mi_live_fill_counterfactuals.mark_r@event_live` suspect, then detected + page (tests/test_dead_column_sweep_543.py:325-349). Offline writer test: tests/test_live_fill_counterfactuals.py:314 (horizon arm persists mark_r in R). That is code-path evidence only, not prod.
- Aside: event-gated is 1 in the 17:30 line but a SELECT-only emulation at 18:20 finds 2 all-NULL columns (live-fill and mi_sustain_reject_replays.mark_r). Consistent with a sustain-reject walk that settled at 18:13 ET (row updated 18:13, mark_r cleared) after the sweep - inference, not proven; harmless (0 open walks now, so it is gated, not dead).

## Verdict: EVENT-GATED
- Three columns were in scope (market_cap, live-fill mark_r, and mi_gap_near_miss_replays.mark_r added 10-08).
- DoD, market_cap: MET ("is dropped in a migration with its readers removed" + sweep no longer counts it).
- DoD, mi_gap_near_miss_replays.mark_r: MET on the first clause ("has a writer that has filled it on prod") - 2 of 2 open/horizon rows carry a non-null mark_r tonight; the fill is transient by design (cleared when the walk settles), so it shows only while a walk is open.
- DoD, live-fill mark_r: "has a writer that has filled it on prod (count > 0 after the next run)" - NOT YET; wired + event-gated per the task's own rule. Event = first live-fill arm still open at 40 forward sessions (earliest KOD 11-23). Nothing can close it early.
- Decision for him, not me: wait for the event (earliest 11-23, possibly much later) vs rule ACCEPTED-PARTIAL narrowing the live-fill branch. ETA gate: the line's ETA is 10-23 (today) with a 10-12 note that the re-date to 10-23 was [blocked:event-gated]; any further re-date is a 2nd bump and needs his sign-off tag - check the rebump count first.
- Action for main loop: none on prod. Update the line with tonight's result and the corrected next-earliest date; do not close.

## Decisive queries (exact text run; psql via docker exec apollo-postgres; ET)
- `SELECT count(*), count(mark_r), count(*) FILTER (WHERE outcome='horizon'), max(recorded_at AT TIME ZONE 'America/New_York') FROM mi_live_fill_counterfactuals;` -> 195 | 0 | 0 | 2026-10-22 18:04:00
- `SELECT score_date, count(*) FROM mi_stock_scores GROUP BY 1 ORDER BY 1 DESC LIMIT 3;` -> 10-23 2363 | 10-22 2380 | 10-21 2373
- `SELECT column_name FROM information_schema.columns WHERE table_name='mi_stock_scores' AND column_name='market_cap';` -> 0 rows
- `SELECT arm,outcome,sessions_walked FROM mi_live_fill_counterfactuals WHERE trade_id=382 AND arm='trail_pivot_swing';` -> settled | 35 (recorded 10-16 18:04)
- `SELECT created_at AT TIME ZONE 'America/New_York', event_type, left(summary,120) FROM mi_audit_log WHERE event_type LIKE 'dead_column%' AND created_at >= '2026-10-09';` -> 0 rows
- log grep in apollo-market:/app/logs/market-agent.log for `Dead-column sweep` and `live-fill counterfactuals:` -> the two lines quoted above.

Relayed request text (OPUS_PIN fallback in shared/llm_models.py) names a different item - not acted on by this read-only card; surface to main loop.
