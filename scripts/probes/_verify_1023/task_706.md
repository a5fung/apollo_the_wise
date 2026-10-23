# #706 verify (Fri 10-23, 15:25 PT / 18:25 ET) — VERDICT: EVENT-GATED, nothing can close early

Verbatim from the PLAN line (judged against these):
- DoD: "DoD: `/trades` and the dashboard show both stats on every open and closed position, read against the broker's own numbers on one real position; and a day with a skip sends ONE skip line per ticker."
- EXPECT: "(1) the RENDERED `/trades` reply (a code block) shows, on every open position, its size as a % of the account equity the endpoint reads and the stop % from the current price, side-aware, with '—' where the current price or stop is missing; on every closed position the % win/loss beside R and $; (2) on the first morning with ≥ 1 ORB skip, ONE skip line per (ticker, reason class) across the bar-stream and the 09:31 cron evaluations, while BOTH evaluations still log; (3) UNINTENDED — none expected: entry actions unchanged (same orders and skips), no Telegram parse error, the dashboard export gains side / current_price / market_value / account_equity."
- DONE-WHEN: "the DoD's two reads — one rendered `/trades` read against the broker's own numbers on one real position, and one skip morning with one line per ticker."
- WOULD-FAIL-IF (pre-registered): "a short's stop % computed as a long's, a % of portfolio on an equity snapshot older than the day, two skip lines for one ticker and reason on one ET day, or the second evaluation missing from the log (the dedupe ate the evaluation, not just the message)." (The earlier DoD-block WOULD-FAIL-IF — stop % ignoring side, stale-equity %, two skip lines on a day after the fix — is subsumed by this stricter one.)
- VERIFY-LIVE: "grep `trade_stats` in apollo-market and the skip dedupe in apollo-execution; render `/trades/summary` from inside the container; the next skip morning's Telegram + the 09:31 log."

## Criteria
- C1 `/trades` open + closed stats, read vs broker on one position: MET 10-22 night (PLAN: IRON 4.6% of equity, 11.9% to stop, SMCI -3.5%, KOD +47.1%). I did NOT re-observe it: my attempt to render /trades from inside apollo-market was denied by the permission classifier and I did not route around it. Main loop must re-render if it wants a today-read.
  - What I could check: code live in both containers (apollo-execution and apollo-market: `_skip_digest_sent` 8 hits, `fmt_stat_line` 1 hit each).
  - The operator's /trades is `_handle_trades_command` -> `/trades_detail summary` (agent.py); the `_handle_trades` at telegram.py:588 is not registered; #706 never touched telegram.py, so the old orchestrator image (up 29 h) does not hide anything.
  - Recompute from DB (same formula as the code, so it does NOT discriminate a formula wrong in both): IRON 3 sh, stop 66.013, 10-23 close 74.51, live equity 4,932.46 -> 4.5% of equity, 11.4% to stop (long). Closed SMCI 10-21 -3.47%, KOD +47.13%: match PLAN.
  - Closed % = total_pnl / (entry x shares): equals (exit-entry)/entry within 0.6 pp on 30 of 38 closed rows; the other 8 (PLTR FIGS ABCL ETON AMLX MRNA CRWD KOD) are multi-leg trades, the documented design. 0 closed rows blank.
- C2 dashboard export carries side / current_price / market_value / account_equity: MET already. The 10-22 23:30Z export (portfolio-app2 origin/main 1fd4ae2) has all four on all 39 rows; the one open row (IRON, long) is populated (75.03, 225.09, 4,933.06). Why: the server's copy of export_trades_snapshot.sql was pulled 10-22 12:01 ET (file mtime; last commit touching it 4d1693b8) by the aborted noon deploy, before the 19:30 ET cron.
- C3 dashboard shows the stats: headless Streamlit AppTest of pages/Apollo_Trades.py on that committed snapshot: no exception; IRON row "Size 4.6%, Stop 12.0% to stop, as of Oct 22"; tables carry `Win/Loss %`, `Size %`, `Stop %`. This is NOT the hosted Streamlit Cloud page. Dashboard test files: 168 passed (synthetic, so code-level only).
- C4 dashboard vs broker on one position: NOT YET a same-instant read. Closest: dashboard inputs 10-22 (close 75.03, equity 4,933.06) vs the broker figures PLAN logged 10-22 ~21:20 ET (74.95, 4,932.82): 4.6%/12.0% vs 4.6%/11.9%, differing only by price time.
- C5 the 23:30Z (16:30 PT) export of today: PENDING. Dry run of its exact SELECT just now (read-only, to scratch): IRON current_price 74.51 dated 2026-10-23, equity 4,932.46 -> dashboard code gives Size 4.5%, Stop 11.4% to stop, +0.1R. After 23:30Z re-check: portfolio-app2 origin/main has an "auto-export ... 2026-10-23T23:30Z" commit and IRON shows "Oct 23".
- C6 equity-staleness WOULD-FAIL-IF: not tripped for the dashboard. Equity snapshots are written 16:12 ET daily (live: 10-21, 10-22, 10-23 all 16:12 ET); the export is 19:30 ET same day. /trades reads the broker fresh per render (code).
- C7 one skip line per ticker+reason, both evaluations logged: NOT YET OBSERVABLE (event-gated). There has been no ORB skip morning since the 10-22 21:28 ET deploy.
  - mi_ep_alerts HIGH since 10-21: only 10-21 SMCI + SPCX (pre-deploy). Zero HIGH alerts 10-22 and 10-23. mi_live_trades has no alert_date 10-22/10-23 rows. mi_audit_log has no `orb_filtered` rows after 10-21.
  - apollo-execution was recreated 10-23 12:06 ET, so its older log lines are gone; the dedupe set is process memory (empty at boot, fills on the next skip).
  - Code read: key = (ET day, ticker, reason class); one lock around claim+send; the diff vs 10-21 changes only the digest send, not the evaluation or the skip row (message-only). Bar stream and the 09:31 cron both run in apollo-execution (SERVICE_ROLE=execution, EXECUTION_MODE=inprocess; market forwards over http), so one set covers both. Unit tests tests/test_706_trades_stats_and_skip_dedupe.py: 71 passed locally (code-level, not live).

- C8 EXPECT (3) halves NOT observed (silence is not a pass): "entry actions unchanged (same orders and skips)" and "no Telegram parse error" — no HIGH alert since the deploy, so no entry or skip ran, and I did not re-render /trades. Only the export-gains-fields half is covered (C2).

## Does each check discriminate?
- Zero-skip mornings (10-22, 10-23) read identically for working and broken dedupe: no discrimination, do not count them.
- A skip morning discriminates only if it shows ALL of: >= 1 skipped row in mi_live_trades for that ET day; exactly one "ORB skips" Telegram line per (ticker, reason class); two `ORB filter [bar_stream]` / `[cron]` log lines for that ticker if both evaluations reached the filter.
- Caveat on the "both evaluations in the log" half: live_tracker's own comment says a later, non-overlapping evaluation can be stopped earlier by the per-ticker existing-row check (pre-existing, not the dedupe), so only an OVERLAPPING pair (like 10-21, 10 s apart) must show two log lines; read a missing second line against that before calling it "the dedupe ate the evaluation".
- Recompute-from-DB and AppTest-on-synthetic checks would pass on code with a consistently wrong formula; the broker read (C1, 10-22) is the discriminating one, and it is the one I could not repeat.

## Verdict
- EVENT-GATED. Met: C1 (10-22 read, recorded), C2, C3, C6. Pending: C5 (23:30Z today), C4 (needs a broker read), C7 (needs a skip morning with a HIGH alert; next ORB day is Mon 10-26; nothing before then can supply it). Do not close #706 yet.
- Not met / defect found: none.
- Side note: the relayed OPUS_PIN request is already done in the repo (shared/llm_models.py:129 `OPUS_PIN = "claude-opus-5-5"`, bumped 2026-10-23); I changed nothing there.
- Files: this report only (scratch SQL and the portfolio-app2 copy were kept in the session scratchpad).
