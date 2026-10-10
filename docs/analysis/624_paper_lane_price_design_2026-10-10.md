# #624 — small-cap PAPER lane: price and design outline (2026-10-10)

**Answer: about $1.60 a month (range $1–$3), about 2.3 extra names graded a day. But under his "same as the
current EP" spec the lane would place roughly ONE paper order a month — small caps get no points for
trading liquidity in the live score. Real catalyst grades accrue (~48 a month); real fills barely do.**
Price and design only — nothing here is built, deployed or decided. Every change to entries, sizing,
scoring or safeguards below is written as HIS decision (THE LINE).

Raw pulls (prod, read-only, captured once): `scripts/probes/_624_paper_lane/q0–q6.sql` + `_out.txt` (session
`d30e3944`). Window: the last 30 scan days, **2026-08-28 → 2026-10-09**.

## 1. How many extra names a day

**Population:** every ticker-day in `mi_ep_scan_log` over those 30 days that the live scan rejected
ONLY for market cap — i.e. it passed the volume-pace gate, the 60-day cooldown, the extension guard,
the $1M dollar-volume floor and the ATR ceiling (`check_filters` checks cap LAST, so a cap reject has
passed the other two), then failed `mcap_too_small` (< $500M, `backtester/filters.py:MIN_MARKET_CAP`).

| measure | value |
|---|---|
| ticker-days rejected only for cap | **68** in 30 sessions (57 distinct tickers) |
| per day | **2.3 average**, 0 to 7 on a single day |
| already graded by live anyway | 0 of 68 (the cap read never flipped) |
| overlap with the existing shadow lane (`mi_lowcap_lane_signals`) | 2 of 68 — the shadow rule (gap ≥ 15% and top-10% volume) is far narrower than "same as live" |

- **This is a slight LOWER bound.** The 68 reached the cap check inside the top-20 graded list. On
  crowded mornings small caps sort last and die at the top-20 cut before the cap is read: the board
  exceeded 20 on only 2 of 30 days (09-17, 10-05), and of the 12 ticker-days cut there, the two
  small caps (SVRN $55M, SDEV) were blocked by other gates anyway. So the true count is ~2.3/day plus
  a little on crowded days.
- **Would they take slots from the live lane? Today, effectively no** — the board is usually far below
  20 (median day 5–7 names per tick). But the 68 DO sit in live top-20 slots today before the cap kills
  them; the lane must not change that ordering (see §4, invariant 4).

## 2. Cost per graded name

**Population:** all 225 live ticker-days that reached catalyst grading in the same 30 days, and every
model/search call logged in `api_usage` between 07:00 and 10:05 ET by the per-name callers.

| call (caller in `api_usage`) | calls | $ in window | per call (logged) | per call via `pricing_for` today |
|---|---|---|---|---|
| catalyst grade (`ep_catalyst_grade`, Sonnet) | 239 | 2.54 | $0.0106 | $0.0106 (sonnet-5-5, $2/$10) |
| news search (`perplexity_news_search`) | 301 | 1.88 | $0.0062 | per-request fee, reported by vendor |
| catalyst validate (`perplexity_catalyst_validate`) | 230 | 0.12 | $0.0005 | vendor-reported |
| grade judge (`ep_grade_judge`, Opus — only names near the bar) | 32 | 1.13 | $0.035 | $0.031 (opus-5-5, $4/$20) |
| earnings metrics (`catalyst_metrics_extractor`) | 47 | 1.04 | $0.022 | $0.022 |
| judge divergence (`judge_divergence`) | 29 | 0.42 | $0.015 | $0.015 |
| theme fit (`ep_theme_fit`) | 32 | 0.17 | $0.005 | $0.003 |
| catalyst type (`catalyst_type_classifier`, Haiku) | 33 | 0.08 | $0.002 | $0.002 |
| **total** | | **$7.38 / 225 names** | **$0.033 per graded name** | |

- Per-day spread of the per-name cost: median $0.031, middle half $0.025–$0.036, extremes $0.012–$0.072.
- `pricing_for` reproduces the logged per-call costs, so the logged figure is the price.
- **$0 extras:** the company profile and news fallbacks are yfinance (`get_fmp_profile` /
  `get_fmp_news` are yfinance under the old name), Polygon is a flat subscription, Alpaca and SEC are
  free. The position-management judge (`mgmt_judge`) reads the LIVE book only
  (`get_open_live_trades`, `account_mode='live'`) so paper positions cost nothing there. Paper fills
  are free.

## 3. One monthly number

**~$1.60 a month** = 2.3 names/day × 21 sessions × $0.033. **Range $1–$3** (1.5–3.5 names/day × the
middle-half per-name cost). Perplexity's per-request fee is most of the search line, so a busy small-cap
month moves it roughly linearly.

## 4. What the lane would actually produce — the fork for him

His spec: *"Everything should be same as current EP setup except market cap."* The live score
(`ep_rubric.SCORE_WEIGHTS["liquidity"]`) pays 7–15 points only to names trading **≥ $50M a day**
(20-day volume × prior close). 

| population (30 days) | graded | reached HIGH (the order tier) |
|---|---|---|
| live names trading ≥ $100M/day | 77 | 27 |
| live names trading $50–100M/day | 34 | 3 |
| live names trading **under $50M/day** | 114 | **2 (~2%)** |
| the 68 small caps | 67 of 68 are **under $50M/day** | — |

- So under the identical score: **~48 real catalyst grades a month, but about one paper order a
  month** (68 × ~2%). His primary ask (real grades) is met; his second (real fills) barely is.
- **Fork (his decision — a scoring change is THE LINE, CHANGE_PROCESS + backtest + sign-off):**
  (a) keep the live score exactly → grades accrue, ~1 fill/month; outcomes for every graded name come
  from the existing replay walker (as the shadow lane does today), fills are a bonus; or
  (b) give the lane its own liquidity term → more paper fills, but it is then no longer "the same as
  EP" and needs its own evidence. Recommendation: (a) — it is his spec, it costs ~$1.60, and the
  replay walk gives ~48 outcomes a month with real grades without touching the score.

## 5. Design outline (not built)

**Invariant 0 — the one that blocks a naive "piggy back" (found while pricing):** the live order path
`broker/live_tracker.py::_HIGH_ALERT_SELECT_SQL` selects EVERY `score_tier='HIGH'` row in
`mi_ep_alerts` for today with **no source, strategy or account filter**, and
`process_new_alerts_live` submits each as `signal_type="magna53"` → the LIVE account. **If the lane
wrote its HIGH alerts through `insert_ep_alert` unchanged, a small-cap paper candidate would get a
real-money order.** The lane therefore writes to its OWN alerts table (or a distinct `source` AND a
filter added to that select, guarded by a test); a separate table is the safer default because no
existing live reader can see it. (A non-'live' `source` would already fall out of live cooldown and
"already today" via `LIVE_SOURCE_SQL`, but NOT out of the HIGH select.)

- **Strategy row:** a NEW `mi_strategies` row (e.g. `magna53_smallcap`, `signal_type` same name),
  `phase='paper'`, `live_real_enabled=false`, `position_size_multiplier=1.0` (his 09-04 sizing ruling),
  `max_concurrent_positions` set (its own slots). `resolve_account_mode_for_strategy` maps
  `phase='paper'` → `'paper'`. Keep the existing `magna53_lowcap` shadow row recording the P15 rule
  — it is a different rule and its forward record is the check on the history replay. (Reusing that
  row instead is his call.)
- **Where it runs:** after the live graded loop, detached (the `schedule_lowcap_lane_tick` pattern) —
  NEVER inside `for c in candidates[:SHORTLIST_SIZE]`; grading is sequential and an outage costs up to
  5s a name inside the ORB window. Input = the names the live loop rejected only for cap, plus small
  caps cut at the top-20 line on crowded mornings, ranked by the same pre-score, own cap of 20.
- **Same gates, same order, imported never restated:** volume pace, cooldown (60 days over the lane's
  own alerts AND live alerts), extension guard, $1M dollar-volume floor, ATR ceiling, then the cap
  test inverted (< $500M), catalyst grade, post-grade filters, judge, regime bar, score bar.
- **Cap read:** `check_filters(..., skip_mcap=True)` + a lane-local cap cache — never the live
  `_mcap_cache` (it pins None = PASS on a yfinance error; see `lowcap_lane.py` docstring).
- **Shared budgets the lane must not consume:** the per-tick theme-fit budget (`FitBudget`), the daily
  M&A-question budget (`ma_filter`), and `_catalyst_cache` (keyed by ticker; harmless today because
  live rejects on cap before reading it, but the lane should use its own cache so the live path stays
  byte-identical).
- **Entry:** a lane submitter reading only the lane's HIGH alerts, calling
  `submit_trade_entry(signal_type='magna53_smallcap', ...)` with the same ORB stop-buy, entry − 2R
  stop, 09:45 window and 10:00 cancel. `_check_safeguards('paper', 'magna53_smallcap')` is per-account,
  so the live position cap, daily loss limit and breakers are untouched.
- **Exits — a named build item, not a caveat:** MAGNA53 exits key on the literal signal type in at
  least three places — `rule_eras.PARTIAL_8R_SIGNAL_TYPES`, `order_manager._DEPTH_EXIT_STRATEGY`,
  `order_manager._ORB_R_FRAME_SIGNAL_TYPES` (plus labels in `sell_discipline.py`). Each must admit the
  lane's signal type, or the lane's paper positions run without the partial, the depth exit and the
  R frame.
- **Sizing on paper:** shares come from PAPER equity, so dollar sizes differ from live; the lane is read
  in R, never dollars.
- **What it records:** every graded name (grade, judge verdict, score, every gate's value) into the
  lane table whether or not it reaches HIGH; HIGH names also get a real paper order in `mi_live_trades`
  (`account_mode='paper'`, `signal_type='magna53_smallcap'`); the nightly replay walker scores every
  graded name's bracket so outcomes exist for the ~47 a month that never get an order.
- **How its tail rate is read:** share of graded names (and, separately, of paper fills) reaching ≥ 3R,
  by catalyst grade (strong / game-changer vs routine vs none), as a distribution with an interval —
  the #624 DoD. The registry's median gate (`_eval_unpaired_r`) is wrong for a tail lane (PLAN #624);
  set `min_median_r: null` as the shadow row did.
- **The three dual-account invariants:** (1) mode-bound client order ids via `make_client_order_id`
  at the lane's submit site (comes free through `submit_trade_entry`); (2) cross-account event
  rejection in `trade_stream._verify_event_account_mode` before any DB write (unchanged, covers paper);
  (3) every new query carries `account_mode` — resolved from the strategy row, never a bare `'paper'`
  literal (deploy gate `[5o/7]`).
- **Tests the build needs:** live byte-identity with the lane on / off / raising (the existing
  `tests/test_624_lowcap_lane.py` pattern, on a board where a live name IS admitted); a test that a
  lane HIGH can never appear in `_HIGH_ALERT_SELECT_SQL`; a test that the lane's submit resolves
  `'paper'` and fails closed on any other phase.

## 6. Decisions for him

- **Price OK?** ~$1.60/month (range $1–$3).
- **Fork (a)/(b) in §4:** identical score → ~1 paper fill a month, grades ~48/month; or a lane-only
  liquidity term → more fills but a scoring change (THE LINE).
- **Touches the live lane?** The live scan, score, slots and safeguards stay unchanged. The one live-path
  edit risk is the HIGH-alert select (§5 invariant 0) — a separate lane table avoids editing it at all.
- **New strategy row vs reuse `magna53_lowcap`:** recommendation new row; reuse is his call.

## Review corrections (2026-10-10, independent review; supersede the text above where they differ)

| # | Correction |
|---|---|
| 1 | The live order step RE-CHECKS market cap (`live_tracker.py:660`, `check_filters`), so a small-cap row in the live alert table normally does not become a real-money order; but a FAILED cap lookup lets a name through (`filters.py:259`), and about one skipped row a day would land in the live trade book. A separate alerts table is still the right call — for that reason, not the one stated above. |
| 2 | The exits list is hand-picked. The `magna53` strategy row carries `profit_trigger_r = 8.0` and `breakeven_arm_r = 3.0`; a new row left empty falls back to the global settings (+2R partial, no breakeven arm — `db.py:5112-5118`, `get_strategy_exit_overrides`). Copy 8.0 / 3.0 onto the lane row, and rule each of the ~13 non-test `"magna53"` literals in or out (e.g. `live_fill_counterfactuals.py:146`, `cross_strategy_allocator.py:182`, `agent.py:4385-4444`). |
| 3 | The live order step's "already traded today" check has no `account_mode` filter (`live_tracker.py:652`): a lane paper trade on the same stock and day would make live MAGNA53 skip it. Filter by account (approved 10-10) with a test. |
| 4 | "About one paper fill a month" counts HIGH grades, not fills (prod, same 30 sessions: 32 stock-days graded HIGH → 23 HIGH alerts → 12 orders → 10 fills). Read the lane's tail rate from the replay outcomes, not from fills. |
| 5 | Both low-liquidity HIGHs (PHVS 09-08, KOD 09-28) scored 90 only through the game-changer conviction floor (`liquidity 0`). Under option (a) every game-changer small cap reaches HIGH and routine ones never do. |
| 6 | The "2 of 114 reach HIGH" rate is a likely LOWER bound (float is blank on all 68 small caps; 31 of 66 low-liquidity live names with a float get the +5 small-float points). |
| 7 | Monthly cost range from its own method: about $0.80–$2.70 (1.5 × 21 × $0.025 to 3.5 × 21 × $0.036), not $1–$3. |
| 8 | Two safeguard-adjacent decisions for him: the lane's position-cap value (unset = it shares the paper account's overall cap, `dual_account.md:22`) and how the lane is stopped (`/pause` and `LIVE_TRADING_ENABLED` cover the live path only). |
| 9 | The `_mcap_cache` failed-lookup claim is out of date since 09-05; the build touches execution-loaded modules (deploy `execution` too); check the paper account works before the first lane order (the paper book has had no trades in 60 days); state the lane's Telegram policy. |

## What this does not answer

- Whether small-cap catalysts behave like large-cap ones once graded — only the lane's own trades can say (n = 0 today).
- Fill quality on names trading under $50M a day: 67 of the 68 turned-away stock-days are in that band, and no fill or spread data exists for them on paper yet.
- The cost on busy mornings: the 68 stock-days (n = 30 sessions, 08-28 → 10-09) slightly undercount, because a few small caps are cut at the top-20 shortlist before their cap is checked.
