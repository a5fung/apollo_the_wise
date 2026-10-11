# #700 — the 2026-10-11 review rendered BY HAND under docs/design/weekly_review_noise_700.md

Real content from the stored row (q1_reviews.out) and the render-time inputs (q3_render_inputs.out).
STEADY STATE = the prior row carries raw metrics + a snapshot (every week from 10-25 on).
Numbers marked ~ are computed from the capture by `live_cohort_1011.py`, not read from the sent message.

<<<HEAD>>>
🧠 *Weekly review — Oct 4–11* · regime Choppy
*Needs me (2):*
• 1 data-gated review(s) ripe — I run each and bring you only its result (listed below)
• 2 observations from this week's narrative to verify Monday, 1 more already settled by the record — ⚠️ block below
_Also checked — reviews: 1 ripe (above), 56 still accruing · errors: 40 rows, 0 open · promotions: 0 ready, 5 accruing, 1 held by ruling · crypto: live, gates clean · spend: $13.66 of $150 · themes: 30d n=14, 79% engine-judge agree · 30d LLM $45 vs live P&L $+17 on 6 · unchanged since last week: bands HOLD · winner capture 19%._
<<<FOLD>>>
📅 *Reviews ready* (1) — data-gated thresholds flipped; I run each and bring you only its result:
• *Ranking rule — RUNNING out-of-sample read (converted 2026-08-18 from a single 2026-10-15 gate)* · written 2026-08-16, 2 rule changes since (latest 2026-09-06) — re-check the question against the live rule — RUNNING READ — fires again every session a new out-of-sample alert_date lands, from the first one.

⚪ *Errors logged (7d)* — 40 rows, 0 open
• ep_candidate_parse_error ×38 — quiet: all Wed 10-07 07:00–09:55 ET, none since (4d) · 139–150 of ~13.2k snapshot rows dropped (prev_close 0/missing)
• judge_divergence_check_failed ×1 — quiet: Tue 10-06 09:55 ET, none since (4d) · TLN: 2nd-model call failed/timed out
• stop_coverage_repair_failed ×1 — quiet: Tue 10-06 09:35 ET, none since (4d) · KO: place coverage stop (target 3) failed

📈 *Strategy promotion* — none ready · changed since last week:
• magna53_smallcap: new on the ladder (paper → live) — need 30 closed (have 0)

✅ *Working*
• The CEG loss stayed small and defined. It lost `-$58.95` on about `$58` of actual risk against `$77` planned, roughly -1R. The stop at `281.29` sat about 1.9 ATR away. The postmortem says the setup showed no momentum (day-1 close `299.59` was below the `300.94` entry). That is one trade, so it illustrates the loss cap and says nothing about expectancy.
• The judge layer ran cleanly: `judged` 10 of 10, `fallbacks` 0, `judge_driven` 10 (4 demotes, 0 promotes).
• `audit_errors.open_total` = 0 of 40 total. Every type is dispositioned `quiet`, and the last event was 10-07.

⚠️ *To verify (mine, Monday)* — observations from the narrative, not findings
• `cooldowns.triggered_this_week` = 81 (active 117), versus 38 (active 71) last week. `theme_churn.total_high_churn_pairs` = 20, the same as prior weeks, and this week's top pairs are all Appalachian Natural Gas names at 2 adds / 2 removes. The cause is unknown. It may be a designed mechanism or a known-in-flight task.
• Stop-coverage telemetry: `stop_coverage_repair_failed` count 1 (KO, 10-06, quiet). Separately, the CEG postmortem narrative says the broker-side stop shows `EXPIRED` with a null `stop_order_id`. That comes from the narrative, not from `audit_errors`. It may be designed behaviour, so check it against broker and audit ground truth.
• settled by the record: ep_candidate_parse_error ×38 — every row quiet since Wed 10-07 (errors above)

🔁 *Last week:* The `silent_audit_error_window` invariant persisted at 1, `theme_churn` stayed at 20 pairs, and `cooldowns.triggered_this_week` rose from 38 to 81. The 09-29 theme-pipeline error events did not recur, and the new `audit_errors` types are different ones.

📉 *Drift — band moves this week*
• cooldowns per day: band 1→2 — 20 a day vs a typical 5 (3 moves this week)
• active theme count: band 2→1 — 123 vs a typical 118 (3 moves this week)
📄 Docs: 1 dated claim nothing can verify — docs/setups/magna53_ep.md:675 (mine to re-check)

🧪 *Setup review — entry/stop geometry (90d)* — a trade closed this week
magna53/live n=31 W=9/31 $2.41 · exits: 25/31 stop_hit · peak +1.27R -> real -1.00R · stop/ADR 0.85 · eras: A n=9 · B n=10 · C n=7 · D n=5
   ⚠ 5 peak(s) unreadable (fast exit, recorder blind <10m)

*🔁 Replay-regression* (live R-dist vs #268b calibration):
  live (n=34): exp -0.14R · win 26% · avgW +2.14R · avgL -0.96R · [running maxDD 13.1R · streak 1/14]
  rule eras: under the current rules (since 2026-09-06): 5 trades · older rules: 29 trades — current rules exp +0.85R · older rules exp -0.31R

❌ *Losers post-mortem (1 trade · $-59)*
• `CEG` 2026-10-06 $-59 · the 5-min ORB would have blocked it (range 5.7% > 1.5× ATR)

⚖️ *Holistic judge:* graded 10 of 10 alerts — 0 up, 4 down, 6 held · 0 fell back to our score · fire axes seen on 7, none on 3

🚨 *Should've-entered gaps (30d)* — 2 new this week, 6 carried from last week (full table: full text)
```
tckr  date   peak    5d   src  reason
EROC  10/06  +14%     —    —   Cooldown
VST   10/06  +11%     —   SRC  Window missed
```
_📡 Strong-catalyst MODERATE caps (60d, n=14): 2 capped for want of a direct source, 12 had one — a judge call, not a gap._
🔍 Biggest movers we scored out (7d): DNA +46% peak (score below 50) · PICS +35% (score below 50) · SVRN +28% (outside top 20)

🪙 *Crypto RS — LIVE*: gates clean (last week: 1 crypto_ingest_error) · 7/7 ingests, 0 errors · 342 coins, 27 watchlist all resolved · stables in but alts not rotating 4 of the last 7 days

🔍 *Judge 2nd-opinion (#301, claude-sonnet-5-5):* 0/5 disagreed (0%) with the HIGH-tier judge verdict this week

🧩 *Theme read, engine vs judge (#486)*
This week (n=6): engine and judge agree on 4 of 6 (67%) — both saw a theme 2 · judge only 1 · engine only 1 · neither 2
Last 30 days to Oct 11 (n=14): agree on 11 of 14 (79%) — both 4 · judge only 2 · engine only 1 · neither 7
Judge saw a theme the engine did not — 2 in the last 30 days, both new to this list:
• AAOI 10-09 — theme known, excluded (stage Nascent)
• AKAM 09-25 — no theme row at all
_Counts 14 of 22 judge-graded alerts; definitions and the 8 left out: full text._

💸 *LLM spend vs realised P&L (#313) — last 30 days, Sep 12 – Oct 11*
LLM spend $45.33 across 5,623 calls · top: eval_519_option_a $9.22 · perplexity_news_search $8.09 · theme_assignment $7.21
Judge-named callers $2.59 (6% of spend): judge_robustness_eval $0.90 · ep_grade_judge $0.71 · mgmt_judge $0.42
Live book (real money): $+17 over 6 closed trades (3 winners)
<<<END>>>

## First run (Sun 10-18, prior row = 10-11 with raw metrics but NO snapshot) — these print ONCE in addition
<<<FIRST_RUN_EXTRA>>>
*🎚️ Kill/scale bands* (live-money, #268b):
🟢 *Kill/scale band: HOLD* — No change
  n=34 · t20=+0.42R · t40=n/a · streak=1 · cum=-4.7R
  within bands
  📖 open book (NOT in the verdict above): 3 position(s) — KOD 11d, PENG 2d, HUM 0d
  rule eras: under the current rules (since 2026-09-06): 5 trades · older rules: 29 trades — the t20 window holds 5 current, 15 older
<<<END>>>
(crypto, MFE, promotions and gaps compare against the prior row's RAW metrics, which every stored row has — so they
already read as changed/unchanged on 10-18; only the band block and the #486 queue, which live in the snapshot, print once.)
