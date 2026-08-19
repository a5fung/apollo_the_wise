# MAGNA53 EP — Episodic Pivot

> 📜 **THE PRINCIPLES (P1-P10) + THE GOAL live in `docs/roadmap/ep_profitability_program.md` § THE PRINCIPLES.** Read them before any analysis, card or proposal here — they are the operator's own rules, in precedence order, and they govern this document. Cite by name (P1, P2…). ⚖ THE LINE sits above all of them.


**Phase**: Live (paper). Production-active.
**Origin**: Pradeep Bonde Episodic Pivot methodology + Marios Stamatoudis adaptation.
**Code**: `agents/market_intelligence/ep_detector.py`, scheduler 7:00–10:00 ET cron every 5 min.

## Definition

A liquid stock gaps significantly on a real catalyst (earnings, FDA, M&A, major news), with confirming volume and structural fitness (not extended, not in cooldown). The gap signals new information has changed the stock's fair value; entry on opening-range breakout (ORB) the same morning.

**Stop and sizing (operator-signed 2026-08-16 — see change log):** the protective stop sits at
**`entry − 2R`, where `R = entry − ORB low`** (equivalently `2·ORB_low − ORB_high`). The ORB low
still **defines R**; it is no longer the exit. Position size **halves by the sizing formula itself**
(`shares = risk_dollars / stop_distance` — the distance doubled), so **dollar risk per trade is
unchanged**. 🔴 The +2R partial target does **not** move: 1/3 still comes off at the ORIGINAL
`entry + 2·(entry − ORB_low)` price (`order_manager.profit_target_r_per_share` pins the frame).
Pre-2026-08-16 the stop was the ORB low itself.
⚠ **Built, NOT yet deployed** — the running image still places the ORB-low stop until the next
market-agent + execution deploy; delete this line at verify-live.

This is the canonical Apollo entry strategy — the highest-volume, highest-conviction setup type.

## Universe / eligibility

- **Price**: prev_close ≥ $5
- **Liquidity**: pre-market dollar volume sufficient (relative + absolute floor — see PM volume gate)
- **Universe**: ~9,700 stocks via Polygon grouped daily
- **Cooldown**: 60-day cooldown after any prior EP alert, with carve-out for fresh earnings (see below)
- **Extension**: skip if prev_close is ≥ 50% above the MIN(close) of the last ~5 trading days (already extended pre-gap → chase risk). `MAX_EXTENSION_PCT=50.0` (ep_detector.py:99); MIN, not a single 5-days-ago point. [Corrected 2026-07-18 — was mis-transcribed at doc creation as "≤ 1.50× SMA-10", a rule that has never existed in code (see #481 + change log); the live criterion is unchanged.]

## Detection criteria (current)

EP detection runs every 5 min from 7:00 AM to 10:00 AM ET. Each scan tick evaluates candidates against:

### Filters (any failure → skip)

**Pre-grade** (candidate scan, before catalyst classification runs):
1. **Gap floor**: `gap_pct ≥ MIN_GAP_PCT` (9.0% hard floor, env `EP_MIN_GAP_PCT`; was 10.0% — see 2026-08-19 change log entry) — applied building the candidate list itself (ep_detector.py ~1567). No regime-dependent variant exists in code — ADR 0003's Phase-1 recommendation of "10% (or 12% in elevated regimes)" only ever shipped as a flat number; that regime branch was never built.
2. **Pre-market volume**: relative gate — `pm_rvol ≥ MIN_PM_RVOL` (1.0× session-anchored RVOL@T)
3. **EP cooldown**: skip if alerted within last 60 days, UNLESS `gap_pct ≥ 15% AND is_earnings_day` (fresh earnings catalyst bypasses cooldown)
4. **Extension cap**: `(prev_close − min5) / min5 ≥ 50%` → skip, where `min5 = MIN(close)` over the last ~5 trading days (`MAX_EXTENSION_PCT=50.0`, ep_detector.py:1858-1866). [Corrected 2026-07-18 — was "> 1.50× SMA-10", never in code; see #481.]
5. **Already scored today**: dedup within scan day
6. **Session RVOL@T** (post-9:30): same primitive as pre-market, but session-anchored. Threshold `MIN_SESSION_RVOL = 1.0`

**Post-grade** (`_post_grade_filters`, ep_detector.py ~1260 — run AFTER catalyst
classification so they can condition on `catalyst_quality`; moved here #405,
2026-07-03, "so we can use catalyst_quality in the carve-out condition"):
7. **M&A filter** (`ma_filter.is_likely_ma`): catalyst='mna' OR keyword scan OR Polygon news headlines — skip
8. **Routine + low gap**: `catalyst_quality == "routine" AND gap_pct < 12%` → skip
9. **Pre-market shares absolute floor** (with carve-out): `today_volume ≥ MIN_PREMARKET_SHARES` (25,000) UNLESS `pm_rvol ≥ 5×` OR (R6 carve-out) `gap_pct ≥ 10% AND catalyst_quality == "strong"` — relative anomaly / high-conviction trumps absolute count for low-float names

### Catalyst grading (Claude + Perplexity + SEC EDGAR)

LLM classifier returns one of: `game_changer`, `strong`, `routine`, `mna`, or None.

**Grounded grade (2026-06-04, #187/#190 — catalyst-axis Track A+B; deployed live).** The grade now reasons on a GROUNDED, UNTRUNCATED summary — the authoritative **SEC 8-K body** (`collector.get_sec_recent_filings`, near-real-time `data.sec.gov/submissions` endpoint, error-wrapped) + the Perplexity web synthesis — NOT raw 200-char yfinance headlines. Model upgraded **Haiku → `claude-sonnet-4-6`**. New prompt rule: broad sector-momentum / short-squeeze / non-company-specific technical moves grade `routine` (a gap-up alone is not a catalyst).
- **WHY**: RUM 2026-06-04 traded −1.07R as a false `strong` — the real catalyst (a $270M NVIDIA-Blackwell GPU-cloud **8-K filed 5:04am ET**) reached neither LLM (no EDGAR ingestion existed), so Haiku confabulated `strong` from headlines while the grade truncated the synthesis to 200 chars.
- **EVIDENCE**: 30-case bake-off — grounded summary flips the false-`strong` junk (RUM/PGY/CRSR/DY, short-squeeze/sector-rotation/ticker-mismatch) → `routine`, and Haiku≈Sonnet≈Opus on identical input (so the **input** is the lever, not the model); RUM grounded+8-K → `strong` with the correct $270M rationale; B0 confirmed EDGAR is near-real-time and the 8-K was retrievable ~4.5h pre-scan.
- **SHIP not shadow** (move-fast): fails CONSERVATIVE — the SEC fetch + grade are error-wrapped (→ `routine`), so the worst failure mode is a missed alert, not a bad trade. Watched on the next 7–10am ET scan.
- **REVERSION**: drop the `grounded_text` path + the `claude-sonnet-4-6` model in `_classify_catalyst_claude`, and the `get_sec_recent_filings` gather entry → restores the headline-Haiku grade. Plan: `~/.claude/plans/i-want-to-plan-groovy-horizon.md`.

**Materiality (#189, 2026-06-04 — built + offline-validated; deploys AFTER the grounded-grade scan confirms).** The grade prompt now includes the company **market cap** + a rule: a contract/deal/order is `strong`/`game_changer` ONLY if its value is SIGNIFICANT vs the company's size (a meaningful fraction of market cap / revenue) — "news existence ≠ EP-grade." EVIDENCE: the same RUM $270M 8-K grades `strong` at RUM's ~$2.5B cap but `routine` at a synthetic $600B mega-cap (validated on Sonnet). REVERSION: drop the `Market cap:` prompt line + rule 5 + the `mktcap_str` computation. Change-isolation: deployed one scan-cycle after the grounded-grade re-arch so the two grade changes are verified separately.

**Earnings-day pre-score boost**: when `is_earnings_day(ticker, today)` returns True (within {yesterday, today}) AND `is_revenue_stage(ticker)` returns True (yfinance Revenue Average > 0), upgrade catalyst from `routine` or None → `strong` BEFORE score computation. Audit event: `catalyst_earnings_boost`. This handles cases where the news scrape is hedged/hollow but yfinance confirms earnings (DDOG/AAON 5/07 class). **Pre-revenue companies** (clinical-stage biotech, SPAC, blank-check — Revenue Average == 0): boost is SKIPPED with `catalyst_earnings_boost_skipped` audit event. Their "earnings" event is pipeline / trial commentary, not a Q-rev catalyst — applying the boost causes the rubric to engage and produce misleading "Q-rev YoY un-extractable" downgrades. The Q-rev rubric gate ALSO skips for pre-revenue companies (belt-and-suspenders) so Claude's organic catalyst grade stands. Trigger: IMVT 2026-05-20.

**Hedge-phrase downgrade**: if Perplexity answer contains hedge phrases ("no specific information", "couldn't find", etc.) AND catalyst is `game_changer`/`strong`, downgrade one notch. Audit event: `catalyst_pplx_hedge_downgrade`.

### Score computation (`_score_ep`)

Multi-factor: gap_pct + pm_rvol + catalyst_quality component + regime + RS + prior_momentum (a 3-month extension PENALTY: −25 at ≥+50% / −15 at ≥+30%, Qullamaggie-sourced — not a positive factor; corrected 2026-07-18 from the imprecise "extension"). Catalyst is an ADDITIVE component (not a multiplier) of the `breakdown` (ep_detector.py ~1140-1146):
- `game_changer`: +25
- `strong`: +15
- `routine` (or anything else): +0

`_score_ep`'s full `breakdown` component list (current, 2026-07-18): `gap` (magnitude), `rel_volume` (RVOL / projected open-intensity), `catalyst` (quality tier), `float` (low-float bonus), `neglect` (52w-high distance), `vol_conviction` (pre-market volume percentile), `prior_momentum` (the extension PENALTY above), `theme_bonus` (R4 in-theme, 2026-05-17), `conviction_floor` (gap+quality floor overrides). **`analyst` (analyst-upgrades bonus) REMOVED 2026-07-18** — see change log below; it is no longer a scored factor.

Score thresholds:
- `< 50` → skip (below MODERATE)
- `50 ≤ score < ep_threshold` → MODERATE (briefing only)
- `≥ ep_threshold` (regime-dependent, `regime.py`: Bull=65, Choppy=70, Correcting=75, Crisis=80 — range 65-80) → HIGH (immediate Telegram + ORB submission window)

**Holistic Grade Judge overwrite**: when `holistic_judge_enabled` is ON (toggle,
ADR 0011/W2c — SHIPPED DORMANT, see 2026-06-08 change-log entry below), the
judge OVERWRITES the authoritative `score_tier` computed above — the field the
caller/ORB job actually reads. `baseline_floor_tier` is preserved as the
counterfactual and `grade_engine_authority` stamps which engine (`judge` vs
`fallback`) decided. Toggle OFF (current default) → floor score_tier stands,
byte-identical to the thresholds above.

### Earnings-day MODERATE → HIGH override (legacy override, kept)

If `tier == MODERATE` AND `gap_pct ≥ 10%` AND `is_earnings_day` → promote to HIGH. Audit event: `earnings_override_applied`. This complements the pre-score boost — boost handles `routine` not reaching 50; override handles `strong` reaching 50-65 in non-Bull regimes.

**Override-respects-downgrade rule (2026-05-27, #132).** If the same-ET-day `catalyst_earnings_revenue_weak_downgrade` event was logged for this ticker — the revenue-growth gate actively classified the earnings as low-quality (e.g. `q_rev_yoy_missing_no_prior_year_comparable`) — the override does NOT fire. Tier stays MODERATE. Audit event: `earnings_override_skipped_post_downgrade`. Origin: BBWI 2026-05-27 fired HIGH at 9:51 ET despite an explicit data-quality downgrade at 7:20 ET. The override is designed for the "news ingest lag" case where catalyst stayed `routine` because no headlines yet; an explicit data-quality downgrade is the opposite signal and must be respected. Fail-open on DB error (preserves news-ingest-lag tolerance).

### Submission window

HIGH alerts trigger ORB submission only when `now_et.hour == 9 AND now_et.minute < 45` — combined with the market-open gate (`now_et.hour > 9 OR (now_et.hour == 9 AND now_et.minute >= 31)`), the effective window is **9:31–9:44** ET (`scheduler.py` ~891-897), not the full 9:00 hour. HIGHs at 9:45–9:59 → `WINDOW_OUT_OF_ORB`. 10:00 ET cleanup cancels any unfilled `order_placed`.

## Known limitations / open questions

1. ~~`is_earnings_day` fail-soft direction inconsistent~~ — **resolved 2026-05-08 (session 2)**. All four call sites (parabolic, EP boost, EP cooldown bypass, EP MODERATE→HIGH override) now treat yfinance error as `True` (earnings day). Defensive at each site: rather over-boost / over-bypass / over-promote on data outage than miss a real earnings EP.

2. **Earnings-boosted `strong` lacks agreement multiplier**: a fresh classifier-found `strong` gets 1.2× confidence multiplier from Claude+Perplexity agreement. An earnings-boosted `strong` (upgraded from `routine`) has multiplier=1.0 because the agreement step ran with the original `routine`. Boosted strong is structurally weaker than classifier-strong. Probably fine but worth knowing.

3. **FMP earnings-window pre-check** (Track B Layer 3, task #18): when an earnings-day match is known ahead of time, bias the Perplexity prompt toward earnings as the catalyst. Currently the prompt is generic and may surface analyst-rating blurbs instead of the actual earnings beat. Filed pending FMP earnings-calendar coverage research (S&P-500 limit on current tier).

4. **Stop-limit gap-through on fast movers** (FLEX 5/06 class): 0.5% buffer can't span 4%-in-60-seconds moves. Telemetry filed (task #22) before considering wider buffer or stop-market.

## Change log (newest first)

### 2026-08-19 — `MIN_GAP_PCT`: 10.0% → 9.0% (OPERATOR-SIGNED, REVERSAL of 2026-05-17 R2)

**Trigger**: `tests/fixtures/must_not_miss_eps.py` (#577) found 15 of 25 evidence-sourced tradeable
≥10R winners (`docs/analysis/winner_r_available_2026-08-16.txt`, GEOMETRY 1) are excluded TODAY by
the 10.0% floor — a false EXCLUSION, the error P1 (`docs/roadmap/ep_profitability_program.md` §
THE PRINCIPLES) says must never happen silently. Operator: *"loosen to what though?"* Priced in
`docs/analysis/gap_floor_decision_table_2026-08-19.md` (749 tier-A gap days, $0, all pre-existing
captures or one-shot read-only prod pulls). Operator, on being shown the table: *"ok, let's take 9
for now."*

**Evidence** (N≥10 met — 749 gap-days, 15 winners in the excluded band): 9.0% recovers 8 of the 15
excluded ≥10R winners (MU 49R, MRVL 35R, SNOW 25R, BE 16R, ALGM 23R, AMKR 20R, UMC 18R, USAR 16R)
for +6-8 candidates/day (≈+25% of daily volume); pool ≥10R density improves 2.0% → 3.0%. 8.0% would
recover all 15 at +18-23/day (density 3.3%) — he chose the smaller option deliberately. 8.5% was
rejected: 56 extra gap-days over 9.0 buy exactly 1 more winner (the band's middle is hollow; winners
cluster at 8.0-8.4% and 9.5-9.9%, not evenly). ⚠ Honest margin: AMKR clears by 0.03pp (9.03% vs the
9.0% floor, on the fixture's session-open psv basis) — one of the 8 is basis-marginal, not a clean
clear like the other 7.

**Why the prior reasoning (2026-05-17 R2, ADR 0003 §3) was WRONG, not merely incomplete**: R2 lifted
8.0→10.0 on a **win-rate read of 8 trades** — the 8-10% gap bucket showed 0/8 (0%) win rate over a
60d cohort. That read predates P3 (`ep_profitability_program.md`, operator 2026-08-16: *"we need to
remember EPs are rare and winrate is low… if we hit a real EP we gain 10X, that's the distinction
here"* — "a median cannot see a 10x"). A 0%-win-rate read is structurally blind to the tail: on this
exact excluded 8-10% band, **337R of R-available sits below the 10% line, against 174R in today's
entire ≥10% pool** — two-thirds of the programme's own ≥10R tail was sitting under a line drawn on
eight losers, because win-rate arithmetic cannot see that a bucket can lose 8 small bets and still
carry the biggest winners. The bucket wasn't mis-measured in 2026-05-17; the measure itself (win
rate, pre-P3) was the wrong instrument for a rare/fat-tailed setup.

**Regime interaction — explicitly checked, NOT changed**: ADR 0003 §3's Phase-1 recommendation read
"lift floor to 10% (or 12% in elevated regimes)". That regime-dependent variant was **never built**
— grepped `ep_detector.py` + `regime.py`: `MIN_GAP_PCT` has always been one flat module-level
constant with no regime branch (confirmed 2026-08-19). The only elevated-regime-flavored number in
the file is `ep_threshold` (the HIGH-tier SCORE cutoff, `regime.py`: Bull=65 / Choppy=70 /
Correcting=75 / Crisis=80) — a completely separate gate, untouched by this change. Nothing to
preserve or migrate; there was no regime behavior on the gap floor to begin with.

**What did NOT change (THE LINE — operator ruled the value, nothing else)**: the R6 pm-shares
carve-out (`gap_pct ≥ 10% AND catalyst_quality == "strong"`, 2026-05-17 P2.1b) — a separately-signed
criterion that coincidentally shares the old 10% number; the "routine + low gap" post-grade filter
(`catalyst_quality == "routine" AND gap_pct < 12%`); the earnings-day MODERATE→HIGH override
(`gap_pct ≥ 10% AND is_earnings_day`); and the `_score_ep` gap-magnitude scoring tiers (8/10/15/20%
point bands). All four independently hardcode a number near the old floor but are distinct,
previously-signed gates — left untouched per the operator's exact instruction.

**Anticipated effect**: universe admission recovers 8 of the 15 named winners (gains a scan row/
trace — not a guaranteed alert; the top-20 gap cap and score<50 gate still stand downstream, per the
decision table §4). Live candidate volume: +6-8 names/day (≈+25%). The RT Pass-2 superset/floor
re-application (`_pass1_gap_floor`, `_apply_realtime_pass2`) and the entry-time re-check
(`entry_pipeline.check_rt_gap_floor`, wired via `live_tracker._MAGNA53_MIN_GAP_PCT`) both read the
same `MIN_GAP_PCT` constant, so they move to 9.0% automatically — no separate wiring change needed
or made.

**Reversion-flag**: REVERSAL of 2026-05-17 R2 (8.0→10.0). Env override for fast rollback:
`EP_MIN_GAP_PCT=10.0` (or any value) — no redeploy for an emergency revert to the constant; a true
revert of this decision also means re-adding the 8 tickers above to
`tests/fixtures/must_not_miss_eps.py::BASELINE_DEBT`.

**Status**: shipped 2026-08-19 (operator-signed), code + SSoT + fixture in the same commit. NOT
deployed — left in-tree per instruction (CLAUDE.md: agent commits, operator deploys). Verify-live at
deploy: first day's `mi_ep_scan_log` gap-candidate count should read ~6-8 higher; `/audit` or a
direct query for any of the 8 named tickers on a future analogous gap should show a scan row instead
of no trace.

### 2026-08-16 — Protective stop moves to entry − 2R at half size; the +2R target does NOT move (OPERATOR-SIGNED, THE LINE)

**Trigger**: the EP profitability program's stop-fork analysis
(`docs/roadmap/ep_profitability_program.md` §0c/§0c-pre, 2026-08-16). The live cohort's shape —
0 winners in 17, 10 of 12 losses at ≈ full −1R, median adverse excursion while held **−1.97R** —
says the ORB-low stop sits INSIDE the normal noise path of a working EP. The operator described the
bounded rule; §0c-pre simulated it as an actual arm (correcting the earlier error of quoting the
no-stop arm's number for it) and he signed it 2026-08-16.

**The change, exactly as signed:**
1. **Stop**: ORB low → **`entry − 2R`**, `R = entry − ORB_low` (so `new_stop = 2·ORB_low − ORB_high`).
   The ORB low still DEFINES R; it is no longer the exit.
2. **Size halves — via the existing formula, NOT a second multiplier.**
   `prepare_orb_order` already computes `shares = risk_dollars / (entry − stop)`; doubling the stop
   distance halves the share count by itself, leaving **dollar risk per trade unchanged**
   (`risk_dollars` still = equity × risk_pct = the dollar loss if the stop fills). An explicit
   halving on top would QUARTER the position — checked for and absent, pinned by
   `test_size_halves_via_the_formula_no_second_halving`.
3. 🔴 **The profit target does NOT move.** 1/3 still comes off at the ORIGINAL
   `entry + 2·(entry − ORB_low)` price. `scan_profit_triggers` previously framed the target off
   `entry − hard_stop` — with the new stop that silently becomes **+4R**, never tested, never
   approved. The frame is now `order_manager.profit_target_r_per_share`: ORB-based
   (`entry − orb_low`) for magna53, `entry − stop` for every other strategy (9M Day 2's
   prior-day-low stop IS its R — leaking the ORB frame there would rewrite ANOTHER strategy's
   target, the #490 latent-defect class). A magna53 row with no usable `orb_low` SKIPS the trigger
   loudly rather than fire at a fabricated level (ADR 0014). Pre-change open rows have
   `stop == orb_low`, so both frames agree — in-flight trades see a byte-identical target at flip.
4. **Breakeven-after-partial, the SMA trail, and `update_stop`'s raise-only broker floor are
   UNTOUCHED** (no diff in `exit_logic.py`, `live_tracker.py` daily pass, `update_stop`,
   `execute_partial_exit` breakeven = `max(stop, entry)` — which equals `entry` under either stop).

**Evidence** (r1 — N≥10; cited from §0c-pre, not re-derived): **matched 43 reconstructed HIGH
trades, identical rows, equal dollar risk** — live ORB-low stop **SUM −6.0R, median −1.00** vs
**2R stop at half size SUM +11.4R, median +0.33**. 3R at a third size: +12.2 sum but lower median
and max → **2R chosen**. The median going positive is the mechanism: a 2R-wide stop simply is not
hit as often, so most trades stop being full losers. **Limits, verbatim from the analysis:** one
regime (April–May 2026), reconstructed not lived, slippage and auction fills unmodelled, **no
out-of-sample until `mi_exit_path_shadow` accrues (review gated at 20 closed positions, ~early
October)** — that shadow frames R off `orb_low` FIRST (`stop_ref`), so its record stays in ORB-R
units across this change.

**Anticipated effect**: the median live trade stops printing an automatic −1.00R; stop-out
frequency falls; share counts halve; dollar risk per trade, alert volume, and admission are
unchanged. The +2R partial fires at the same prices as before.

**What was verified UNCHANGED** (each read in code, not assumed): entry trigger (stop-limit buy at
ORB high) + `stop_limit_buy_price` formula · `stop_too_wide` (`validate_orb_entry`, ORB range vs
1.5×ATR — judges ORB geometry, which did not move) · chase cap (`CHASE_RISK_INFLATION_CAP` —
formula untouched; its planned-risk denominator is now the 2R distance, so the DOLLAR risk it
admits at the cap, planned $risk × 1.5, is identical to before) · gap floor `check_rt_gap_floor` ·
ORB window/cleanup · OCO carve-out #566 + partial accounting #567 (consume `limit_price`/stop from
the row — upstream pin covers them) · all safeguards (max positions, daily loss, drawdown breaker,
circuit breaker, PDT) · 9M Day 2 builder (`prepare_prior_day_low_orb_order`) untouched.

**Downstream stop==ORB-low assumptions found and handled:** (a) `scan_profit_triggers` — THE
dangerous one, fixed above; (b) `/positions` pending-entry render (`agent.py`) displayed
`orb_low` as the stop — now prefers `stop_price` (orb_low kept as legacy-row fallback);
(c) telemetry R units: `mi_sell_discipline_records` / `pivot_stop_shadow` / `giveback_shadow`
define R = `entry − hard_stop` (actual placed risk) → their R for NEW trades is in 2R-stop units
(≈ half the old numeric R for the same move) — deliberate, their stated definition is "actual
initial stop"; `kill_scale_bands` (R = pnl/risk_dollars) and `mgmt_judge` (already
`entry − orb_low` by design) are unit-stable; `describe_stop_move`'s "x.xR beyond breakeven"
Telegram line now reads in placed-stop units (display only). (d) The 5-min shadow ORB variant
(`shadow_orb_tracker`) imports `prepare_orb_order` and inherits the change — correct, it is
defined as apples-to-apples with live. (e) The offline EOD sim (`backtester/tracker.py`,
`mi_paper_trades`) keeps its own old-rule stop — offline lane, out of the signed scope, flagged
here so its divergence is known.

**Reversion-flag**: **REVERSAL** of the founding ORB-low stop rule (operator's own
`EP_TRADING_RULES.md` §B, 2026-03-27; this SSoT's definition since birth 2026-05-07). Per
CHANGE_PROCESS r4, the prior reasoning was WRONG for this cohort, not merely incomplete: it treated
a touch of the ORB low as the setup's invalidation, but the measured excursion distribution says
otherwise — the median trade goes −1.97R against while held, and the 11 of 43 names that dipped
past −2R still summed +13.9R in outcomes. At −1R nothing is yet decided; the old stop was
exiting inside noise. Hard revert = restore `stop_loss_price = orb_low` in `prepare_orb_order`
(the `risk_per_share` line then restores full size by the same formula) + drop the
`profit_target_r_per_share` frame in `scan_profit_triggers` (back to `entry − stop`) + redeploy
market-agent + execution. No toggle — a stop level cannot ship dark; the reversion is a code
revert, which is why the SSoT + tests pin every half of it.

**Status**: **built 2026-08-16 (operator-signed), NOT deployed** — left in-tree per instruction;
deploy + verify-live are the operator's call. Verify-live when deployed: (1) first entry's
`orb_order_placed` audit + broker stop at `2·ORB_low − ORB_high`, shares ≈ half the old-formula
count, `risk_dollars` unchanged; (2) first +2R fire's `profit_trigger_fired` payload target =
`entry + 2·(entry − orb_low)` — NOT +4R; (3) breakeven/trail rows byte-identical in shape.
Tests: `tests/test_2r_stop_change.py` (14, behavioural), 7 mutations each reddening their named
test (recorded per docstring); full suite green.

### 2026-08-08 — #516: a keyword match may no longer overrule a contrary classification (OPERATOR-SIGNED)

**Ruling:** he judged 8 M&A suppressions across #514 and 2026-08-08. **7 were false positives**
(WEN, UMAC, LCID, FRMI, SOUN, LII, SCZM); **1 was correct** (CLRO). On the last four: *"none of
these are MA."*

**Change:** in `ma_filter.is_likely_ma`, when `catalyst_quality` is present AND is not `'mna'`,
the keyword-scan path is skipped. Our own graded view is no longer overridden by a bare word
match.

**Why this and not the obvious rule.** The obvious fix — *require the classifier to concur* —
would have released **CLRO, the one correct suppression**: CLRO was killed at the `9m_intraday`
detector before grading ran, so it has **no classification at all**. This guard only fires on a
CONTRARY verdict, so a name with no verdict is untouched. That distinction is the design.

**Measured over 73 fires / 60 days:** 28 (classifier agrees) stay suppressed · 27 (no
classification) unaffected · **18 released**. Of the released, the 4 he ruled are confirmed false
positives.

**The case that decided the binding-phrase question.** A prior test asserted that binding wording
should override a `routine` classification. **UMAC disproves it in production:** matched keyword
**"definitive agreement"** — the most binding phrase there is — while the real catalyst was
**Russell 2000 index inclusion plus a drone-sector tailwind**. The classifier said `routine` and
was right. That test is inverted, with the reason recorded in it.

**The safety net:** a veto FALLS THROUGH to the `polygon_news` check, which is deliberately NOT
gated. A genuine deal carrying a real headline still suppresses there. The keyword path simply
may no longer be the sole basis for overriding our own graded view.

⚠ **NOT FIXED, and PARKED by the operator (*"I don't know enough to make a call here yet"*):**
`polygon_news` fired on WEN ×5, LCID ×2 and FRMI — all with **no stored classification and no
stored news summary**. It is simultaneously the worst-performing path and the only one that keeps
no evidence of why it fired, which is why FRMI is unjudgeable after the fact. Separate decision.

**Telemetry:** `mna_keyword_vetoed_by_classifier` is written ONLY when the veto actually changed
the outcome, so the row count is a direct measure of the rule's effect. Isolated in its own
try/except — telemetry can never alter the verdict.

Tests: `tests/test_ma_keyword_veto_516.py` (7), mutation-checked against broadening the rule to
"require concurrence" (which correctly fails the CLRO test) and against removing it entirely.

### 2026-08-07 — #541: the entry trigger is now ASK-aware, not last-trade-aware (OPERATOR-SIGNED, LIVE)

**Trigger**: two live entries killed by the venue in single-digit milliseconds, two days running.

| date | ticker | ORB high (trigger) | last trade | ASK | venue verdict |
|---|---|---|---|---|---|
| 08-06 | INSM | 129.41 | 128.674 | **129.48** | `[6098] Stop Price Already Triggered` |
| 08-07 | QNST | 19.80 | 19.50 | **19.83** | `Unsolicited: Bad Stop 19.8` |

**Root cause**: a buy-stop placed at or below the current OFFER is immediately marketable, so it
is not a stop, and the venue refuses it. `#500`'s price-aware entry guard already owns exactly
this question — *"has price already run past the ORB high, so the trigger would be
in-the-money?"* — but it answered using `get_latest_trade`. On a thin first-minute gapper the last
trade and the offer diverge badly: both names read "not through" on trades and "already through"
on the ask.

⚠ **This is why three months of paper probes never reproduced it.** Paper fills against a synthetic
book with a tight spread; the live failure needs a WIDE ASK, which is what a thin gapper has in its
first minute and what paper does not model. The 08-06 probe deliberately tested the
trigger-already-printed shape on paper and saw it ACCEPTED — a false clear.

**Change**: `_pick_entry` now ALSO switches to the limit-buy fallback when `ask > orb_high`, at
`ask * 1.002`. New `alpaca_client.get_latest_quote` (SIP feed, same discipline as
`get_latest_trade`; a zero/absent ask returns None rather than 0.0, so a broken quote can never
read as a cheap offer).

**Not a new entry rule** — this is `#500`'s signed mechanism given the price reference the venue
actually uses. The trigger LEVEL is unchanged (the ORB high), the protective stop is unchanged (the
ORB low), and sizing is unchanged (planned risk).

**Bounded by the existing chase cap**, recomputed on the two real orders: QNST fallback $19.87 =
**1.12x** planned risk; INSM $129.74 = **1.10x**. `CHASE_RISK_INFLATION_CAP` is 1.5x, so both are
comfortably inside and an outsized chase is still refused.

**Evidence**: n=2, both first-minute gappers, both measured from the SIP NBBO at the exact
submission timestamp plus Alpaca's own event-stream reason. ⚠ **Honest limit — the RATE is not
measured**: how often the ask sits through the trigger on setups NOT worth taking is unknown, and
was offered to the operator as a pre-ship measurement. He ruled to ship without it, on the basis
that the alternative is a known-zero (the order is cancelled and we get nothing either way).

**Ship**: shipped behind `mi_safeguard_state('entry_ask_aware', <mode>)`, DEFAULT OFF, then flipped
ON for `live` by the operator on 2026-08-07 ("deploy and live now"). Fails CLOSED on an unreadable
flag or quote. 7 tests incl. a premise test that fails if the trade-vs-ask divergence ever stops
being the discriminator. Reversible with one row, no redeploy.

**Cost of NOT doing it, measured**: INSM ran +33% intraday; QNST posted record revenue +43% YoY and
net income +496%. Both entries were lost to a mechanism, not to judgement.


### 2026-08-02 — #490: real-time admission requires the level to SUSTAIN 3 bars (BUILT OFF, operator-signed)

**Trigger**: operator 2026-08-02 — *"target should be stable, in fact just a single 1min bar touching
>10% may be too lose especially for premarket, maybe we should see that move sustain with a few
bars."* Prompted by two cases he read himself: **MYGN 07-30** (*"I don't see >10% except for on
specific 1min bar and it crashed back down immediately… next day it dropped 46%"*) and **QURE 07-29**
(touched 12.3% inside the 09:30 bar, closed it at 9.7%, decayed all morning).

**The argument is a priori, NOT the backtest.** A level that holds three consecutive minutes is a
LEVEL; a level touched once and gone is a PRINT. This is the reasoning already embedded in the Q3
print-corroboration guard, applied one level up — Q3 asks *is this print real*, this asks *is this
LEVEL real*. ⚠ **The operator named the central risk himself — *"this is selecting criteria based on
hindsight of wins"*** — so the outcome table below is used ONLY as a safety check that nothing
valuable is destroyed, never to select the rule.

**Evidence** (r1: N≥10; we have 97) — `scripts/probes/_490_sustain_rule.py` over all 97
`ep_rt_universe_catch` events:

| rule | admits | med open→close | med open→high | med open→low | win ≥+5% |
|---|---|---|---|---|---|
| 1 bar (today) | 81 | +3.9% | +9.8% | −1.7% | 41% |
| 2 consecutive | 67 | +4.0% | +10.0% | −1.7% | 45% |
| **3 consecutive (SIGNED)** | **46** | **+5.0%** | **+10.4%** | **−1.2%** | **50%** |
| 3 of last 5 | 50 | +4.1% | +10.0% | −1.4% | 48% |
| 7 of last 10 | 10 | +0.2% | +5.9% | −2.8% | 20% |

Two signs it is not curve-fit: **it reverses** (7-of-10 is worse than doing nothing — a fitted curve
would be monotone), and **risk improves with return** (median open→low −1.7% → −1.2%), the opposite
of what fitting to wins usually buys. **M-of-N was tested as the operator asked and is NOT used** —
consecutive beats it at equal strictness.

⚠ **I recommended N=2; the operator signed N=3.** Recorded as his call. My argument was overfit
exposure — 3 is the argmax of the table and drops 10 good names incl. RACC (+31%) vs 3 for N=2.

**Anticipated effect**: roughly 57% of today's real-time catches survive. **This changes DETECTION
only** — operator ruling the same day, *"once open we are trading 1-min bars as per today"*: the
09:31 ORB entry mechanics are untouched.

**Implementation**: `_sustain_ok` (pure predicate) + a gate at the would-be-catch in
`_apply_rt_universe_overlay`, evaluated BEFORE the catch is logged (test-pinned — after would make
it cosmetic). Bars come from a new `collector.get_alpaca_minute_closes`, batched, memoised per tick,
on the tiny would-be-catch set (~0-3 symbols/tick). **BACKWARD-looking only** — a forward wait would
push detection past the 09:45 ORB cutoff and recreate the miss #490 exists to remove.

⚠ **FAILS OPEN on an undecidable verdict, and this is the load-bearing property.** No bars, too few
bars, a fetch error, or the toggle off ⇒ today's behaviour. Pre-market bars are genuinely sparse
(SCL had no 09:30 bar at all); converting "no data" into "reject" would silently become "reject
everything pre-market" — a far bigger change than the one signed. **Mutation-tested**: making sparse
bars reject fails 2 tests. Both rejects and undecidables are logged BY NAME
(`ep_rt_sustain_reject` / `ep_rt_sustain_undecidable`) so "the rule is on" cannot look identical to
"the rule never had data" — the exact instrumentation trap that made gate 1 unanswerable.

**Reversion-flag**: NEW. Reversion = `ep_rt_sustain_enabled` off (~60s, no deploy).

**Status**: **LIVE — operator signed the flip 2026-08-02 09:53 ET** (*"flip it now, it's more
conservative regardless"*). Shipped OFF, verified inert in both containers, then flipped; both
confirmed reading `True`.

⚠ **Its BLAST RADIUS today is telemetry, not trading, and that should not be misread as "it works".**
`ep_rt_universe_authoritative` and `ep_rt_gap_authoritative` are both still **False**, so a
universe catch is SHADOW — logged, never admitted. The sustain rule therefore changes *which shadow
catches get recorded*, and pre-filters the cohort so that when RT-3 is eventually flipped the
admission set is already correct. **It cannot affect a live trade while the authority toggles are
off.**

**The operator's reasoning is structurally correct**: the gate can only `continue` — it removes
would-be catches and can never admit one. There is no path by which it loosens detection.

15 tests. **Reversion**: `ep_rt_sustain_enabled` off, ~60s, no deploy.

**Watch for** (pre-committed): first 30 live catches vs the replay's prediction — materially worse
means the replay was fitted, revert; a rejected name running ≥+20% once is a review, twice a revert.


### 2026-08-01 — #490: MIN_GAP_PCT now enforced at SUBMISSION, not only at the scan tick (BUG FIX; built OFF)

**Trigger — operator ruling, 2026-08-01**: *"the blocking live path is in fact correct given the
price retreated from the 10% gap, so in a way the current path is a bug."*

**This is a bug fix, not a criteria change, and the distinction is the whole point.** `MIN_GAP_PCT =
10.0` is an existing signed criterion (2026-05-17 R2). `live_tracker.process_new_alerts_live` selects
`FROM mi_ep_alerts WHERE alert_date = $1 AND score_tier = 'HIGH'` — **the alert ROW, written on
whichever scan tick first scored it, often hours before the open** — and submits at 09:31 without
ever re-reading price. A name that retreated below the floor in between was entered **in violation of
the system's own criterion.** Nothing about the 10% threshold is being changed here; it is being
applied at the moment the money moves.

⚠ **I initially framed this as a new filter needing CHANGE_PROCESS r1's N≥10 before it could ship.
That was the wrong standard** — r1 governs *threshold changes*. There is no threshold change here.

**Evidence** (`docs/analysis/490_delay_missed_eps_2026-08-01.md`): FTNT 2026-07-30 — alert written
07:00 on a stale 10.79% gap; at **09:30:05, one minute before entry, the system logged its real-time
gap at 7.77%** — and entered anyway, for −$6.63. All three names that faded below the floor before
entry (WKC −$23.80, QBTS −$22.26, FTNT −$6.63) lost money. A gap that retreats before the open is the
setup failing its own premise, which is what the criterion exists to catch.

**Implementation**: `entry_pipeline.check_rt_gap_floor`, called as stage 4b — beside the fade guard
(same class of gate: setup quality read off live price) and BEFORE sizing and submission. Denominator
is `db.get_prev_close` reading `mi_daily_closes`, i.e. the **same Polygon prev_close the detector
uses as its sole denominator**, so the scan and this guard cannot disagree about one name on one day.
(`mi_ep_alerts` has no prev_close column — an earlier draft read `alert_context["prev_close"]`, which
does not exist, and would have silently failed open and done nothing.)

**FAIL OPEN, deliberately.** It blocks ONLY on a positive, trustworthy real-time read below the
floor. Toggle off, no prev bar, no/zero/negative last trade, or ANY exception → the entry proceeds
exactly as today. Same posture as `check_fade_guard`'s silent-on-data-failure rule: on a guard that
can only remove entries, a failure that blocks is far worse than one that lets a marginal trade
through. `tests/test_490_entry_gap_recheck.py` pins both invariants (21 tests incl. the floor
boundary — at exactly 10.00% it must PASS, not block). **Mutation-tested**: making it fail closed
fails 3 tests.

New skip reason `setup:gap_below_floor`, rendered via `humanize()` (test-pinned) so the machine
prefix never reaches Telegram.

**Reversion-flag**: NEW. Reversion = set `ep_rt_entry_gap_recheck` off — ~60s, no deploy.

**Status**: **LIVE — operator SIGNED OFF 2026-08-01 ("yes"), flipped 20:34 ET.**

Shipped OFF, verified inert in both containers, THEN flipped. Deployed `market-agent` → `execution`
(both green).

**Prod proof the guard is not a silent no-op** (run in-container after the flip, on real data):
```
apollo-execution:
  FTNT -> BLOCK: setup:gap_below_floor: rt 5.6% < 10% floor
          (alert said 10.8%, last $161.80 vs prev close $153.22)
```
FTNT's actual 7/30 entry was $166.65 against a $153.22 prev close = **8.8%, below the floor** — the
entry we should not have taken.

⚠ **The guard only ACTS on apollo-execution, and that is where entries run** (`EXECUTION_MODE=http`,
so `trigger_orb_entry` POSTs there — *"creds + broker live in execution"*). On apollo-market the same
call **fails open**, because that container's Alpaca credentials are deliberately blanked (creds
isolation). That is the designed direction, but it means **if `EXECUTION_MODE` were ever set back to
`inprocess`, this guard would silently stop working** rather than fail loudly. Worth knowing before
anyone touches that env var.

**Reversion**: set `ep_rt_entry_gap_recheck` to `'off'` — ~60s, no deploy.

⚠ **CORRECTED same evening (found by the `/simplify` pass, two reviewers independently): the guard
originally baked MAGNA53's floor into a SHARED pipeline stage.** `submit_trade_entry` is the single
funnel for MAGNA53 **and** 9M Day 2, and `check_rt_gap_floor` imported `ep_detector.MIN_GAP_PCT`
(10%) directly — so it would have applied MAGNA53's criterion to 9M Day 2, whose own signed bar is
**3% gap OR 4% intraday gain** (`ninem_detector._MIN_GAP_PCT`). That is rewriting another strategy's
entry discipline: THE LINE.

**Live exposure was ZERO and that was luck, not design** — 9M Day 2 is `phase=deprecated`, and the
phase gate (`entry_pipeline.py:481`) runs BEFORE stage 4b (line 544), so it never reached the guard.
Both reviewers predicted live 9M skips on Monday; verified against `mi_strategies` and the call
order, that prediction is wrong. The defect was LATENT — it would have fired the moment 9M Day 2 was
ever re-enabled.

**Fix**: the floor is now a per-strategy PARAMETER (`rt_gap_floor_pct`, default `None` = opt out),
exactly the idiom `check_fade_guard` already uses for `ratio`. MAGNA53 opts in at its own 10% from
`live_tracker.py`; 9M Day 2 does not. A test asserts the shared funnel no longer imports any one
strategy's constant, and another asserts the same price blocks at 10% and passes at 3%.

**Verify-live due Monday 2026-08-03**, and the reversion trigger is pre-committed:
1. Expect `setup:gap_below_floor` skips ONLY on names whose real-time gap is genuinely under 10% —
   spot-check each against `mi_daily_closes` prev close.
2. ⚠ **Revert trigger — needs an ABSOLUTE FLOOR before the ratio is allowed to mean anything:
   revert only if `HIGH alerts ≥ 4` AND `>1/3 of them blocked`.** The measured rate is ~1 in 6 live
   entries; a much higher rate means the real-time read or the denominator is wrong, not that the
   cohort collapsed. **Below N=4, do NOT act on the percentage** — with 2 alerts a single correct
   block reads as 50% and would revert a working guard, and with 0 alerts the ratio is undefined
   and passes vacuously. Under the floor, inspect each block by hand against `mi_daily_closes`
   prev close instead. (Same small-denominator trap as `_ROWCOUNT_MIN_MEDIAN` in #340 and the
   negative-control leg above — a percentage carries no signal until the denominator is real.)
3. Negative control: confirm entries still HAPPEN. Zero entries with zero `gap_below_floor` skips
   means the ORB job did not run, not that the guard is quiet.
4. ⚠ **Attribute every skip to WHICH guard fired — the two shadow each other.**
   `ep_rt_gap_down_authoritative` removes a stale name at the SCAN tick, so it never becomes an
   alert and never reaches the 09:31 check; `ep_rt_entry_gap_recheck` only ever sees what survived
   upstream. The measured split is real (WKC + QBTS were caught at the alert tick, FTNT at 09:30),
   but a raw count of `setup:gap_below_floor` will read artificially LOW and must not be read as
   "the entry check is inert" — it may simply be shadowed. Count `ep_rt_floor_flip_down` with
   `"acted": true` separately from `setup:gap_below_floor` skips.

### 2026-08-01 — #490: gap authority SPLIT — the REMOVE half gets its own toggle (built OFF, awaiting sign-off)

**Trigger**: operator, 2026-08-01, on being shown the volume cost of the RT cutover — *"with 30+
more EP that is potentially traded, that's adding a lot if true, may mean we need more filters if we
let this cohort in, not that is a reason to block them if legit"* → *"fix the vol"*.

`ep_rt_gap_authoritative` does two opposite things at once. Measured per-day over 7/21-7/31:

| half | effect | per day |
|---|---|---|
| flip-UP (`rt ≥ 10 > delayed`) | **admits** candidates the stale gap rejected | **+25.0** |
| flip-DOWN (`rt < 10 ≤ delayed`) | **removes** stale false-admits | **−13.9** |

Against a baseline of 1.86 HIGH alerts/day and 0.57 live entries/day, the admit half is a large
expansion — and grading runs only on ADMITTED candidates (`ep_detector.py:1888`), so it lands on the
LLM path whose end-to-end latency (median 27s, max 150s, measured at ~2 candidates/tick) is what
keeps detection inside the 09:45 ORB cutoff. **The remove half has no such cost: it shrinks the
cohort.** They were inseparable only because one assignment drove both.

**Evidence** (CHANGE_PROCESS r1 — N≥10 evaluated; full working
`docs/analysis/490_delay_missed_eps_2026-08-01.md`): 111 `ep_rt_floor_flip_down` ticker-days over
the 8 days the telemetry has existed. Of those, **11 became scored alerts — all 11 HIGH — and 4
reached a live trade row.**

⚠ **Only 2 of the 4 would actually have been prevented, and the timing is why.** `live_tracker.
process_new_alerts_live` selects `FROM mi_ep_alerts WHERE alert_date = $1 AND score_tier = 'HIGH'` —
**it reads the alert ROW, not the current tick's candidate list.** So dropping a candidate only
prevents an entry if the flip-down happens on the tick that would have WRITTEN the alert. A
flip-down after that is telemetry: the row already exists and the 09:31 entry proceeds.

| ticker | date | delayed | RT | flip-down @ | alert written @ | prevented? | P&L |
|---|---|---|---|---|---|---|---|
| WKC | 07-24 | 11.63% | 8.91% | 08:15:00 | 08:15:00 (same tick) | ✅ **yes** | **−$23.80** |
| QBTS | 07-27 | 11.29% | 9.50% | 07:20:01 | 07:20:00 (same tick) | ✅ **yes** | **−$22.26** |
| FTNT | 07-30 | 10.79% | 7.77% | 09:30:05 | 07:00:00 | ❌ no — 2.5h late | −$6.63 |
| ARM | 07-30 | 15.46% | 8.34% | 09:45:10 | 08:55:00 | ❌ no — after entry | $0 (cancelled) |

**Defensible saving: −$46.06 of a −$224.01 30-day total (20.6% of the loss) from 2 of 17 trades** —
neither of which ever qualified on real-time data, and both losers.

⚠ **Honest N**: the criterion is evaluated on 111 events / 11 alerts, but the P&L attribution rests
on **2 filled trades**. Telemetry only starts 2026-07-21, so a longer window does not exist yet.
Two trades is not a distribution — the case rests on the mechanism (these names did not meet the
10% floor on truthful data) rather than on the size of the measured saving.

▶ **FTNT exposes a separate and arguably larger gap, NOT fixed here.** Its alert was written at
07:00 on stale pre-market data; at **09:30:05 — one minute before the entry — the system recorded
that its real-time gap was 7.77%, below the 10% floor — and entered anyway**, because nothing
re-validates an alert against real-time data at submission time. That is an entry-path change, needs
its own sign-off, and is filed under #490 rather than smuggled into this one.

**What shipped**: `ep_rt_gap_down_authoritative` (runtime toggle + `EP_RT_GAP_DOWN_AUTHORITATIVE`
env), consulted ONLY when `ep_rt_gap_authoritative` is off, so full authority still subsumes it.

**Never-loosen, structurally**: the branch is guarded by `rt_gap < MIN_GAP_PCT <= dl` — the flip-DOWN
condition exactly — so it can only push a decided gap BELOW the floor. A superset-only admit
(`dl < MIN_GAP_PCT`) fails `MIN_GAP_PCT <= dl`, is never touched, and `_floor` drops it as today.
`tests/test_490_gap_down_authority.py` pins this with a 144-case sweep over (delayed, rt) pairs on
both the verified and unverified prev_close paths, asserting the admitted set is a SUBSET of today's.
**Mutation-tested**: removing the guard fails 3 tests including the sweep.

`ep_rt_floor_flip_down` now carries `acted` — without it the event read identically in both modes and
verify-live could not tell whether the cleanup was running.

**NOT changed**: `MIN_GAP_PCT=10.0`, the ORB window, scoring weights, safeguards, sizing, and the
flip-UP half — which stays gated behind `ep_rt_gap_authoritative` exactly as before.

**Reversion-flag**: NEW (splits an existing toggle; neither half changes meaning). Reversion = set
the toggle back off — no code change, no deploy.

**Status**: **LIVE — operator SIGNED OFF 2026-08-01 ("yes to both"), flipped 20:00 ET.**

Shipped OFF first and verified inert, then flipped — so the code path was proven live before it was
allowed to act. Deploy sequence (`ep_detector.py` is in `exec_loaded_modules.txt`, so BOTH services
run it): `deploy.sh market-agent` → `deploy.sh execution`, both green. Delta read before deploying —
the only code change in the range was this one. Toggle set in `mi_safeguard_state`
(`ep_rt_gap_down_authoritative` / `global` / `on`); **both containers confirmed reading
`down=True, full=False`** — i.e. the remove half is acting and the flip-UP half is still gated.

**Reversion**: set that row to `'off'` — takes effect within ~60s, no deploy, no code change.

**Verify-live due Monday 2026-08-03** (first market session), THREE legs — the third is the one that
makes the check non-vacuous:

1. `ep_rt_floor_flip_down` events carry `"acted": true` and the summary suffix `REMOVED`. Still
   reading `SHADOW` ⇒ the toggle is not being honoured.
2. The tickers named in those events do NOT appear in `mi_ep_alerts` for that date.
3. ⚠ **NEGATIVE CONTROL — confirm the scan ran at all** (any `ep_rt_*` event for 2026-08-03).
   Flip-downs averaged 13.9/day, but that is an average and a quiet Monday can legitimately produce
   zero. Without this leg, "no flip-down rows" passes legs 1-2 vacuously and is indistinguishable
   from the detector never running. (`shadow-zero-effect-check-instrumentation`: a dark mechanism
   reading zero effect is usually an artifact until the acting population is confirmed.)

### 2026-07-25 — #490 RT-1: full real-time detection built DARK (shadow note only — NO criteria change)

**Trigger**: operator ruling 2026-07-24 ("there isn't a rational reason to not use real-time
data when we are trading real-time") + the signed design
`docs/analysis/490_full_realtime_design_2026-07-25.md` (all 6 forks ruled). Detection reads a
~15-17-min-stale Polygon snapshot while execution is already Alpaca SIP; the class the #489
hybrid structurally cannot catch holds the biggest moves (NVVE +95.3% cross→high; TRAX +46.6%).

**Evidence**: design §9 — N=47 residual (hybrid_caught=false) cases, prod-measured on the
CROSS basis; 190/190 prev_close mismatch events proven to be Alpaca's pre-open T-2 off-by-one
(§1.2), not vendor noise.

**What shipped (ALL dark — `EP_RT_UNIVERSE_ENABLED` default false; runtime toggles
`ep_rt_universe_authoritative` / `ep_rt_volume_authoritative` default off; flags-off is
freeze-tested byte-identical)**: Pass-0 full-universe Alpaca SIP overlay (one fetch/tick,
reused by Pass-2 + the miss watchdog); tick-quality guards Q1-Q4 (NBBO band + quote freshness +
MANDATORY minute-bar corroboration for any RT-only admission + absolute insanity bound
replacing the 30pp clamp on the universe path) with a loud `ep_rt_tick_quality_reject` reason
enum; halt quarantine (heuristic, §4); corporate-action (split) hold (§2.2); G1 scan-log
columns populated (`gap_pct_rt/gap_pct_delayed/price_source/rt_price_age_s/prev_close_alpaca`);
`ep_rt_universe_catch` shadow events (audit-only, digest surfacing per the 7/21 noise ruling);
volume/RVOL shadow (§6.1, own flip); `current_price` coherence under authority (§6.4);
cross-basis residual columns + O-9 retired as a trigger (§9.4).

**Live-behavior deltas that ride the CURRENT hybrid (bug fix + observability, not criteria)**:
(1) the Pass-2 prev_close cross-check is now DATE-KEYED (§2.1) — pre-open, Alpaca's
`previous_daily_bar` deterministically holds T-2, so the old compare silently dropped the RT
read of every candidate whose prior day moved >0.5% (the pre-open shadow was censored:
flip-up 29 RTH vs 2 pre-open). Fail direction unchanged (real mismatches still degrade to
delayed); (2) the Pass-2 30pp clamp emits `ep_rt_gap_clamped` (C1 — clamps were invisible).

**NOT changed**: `MIN_GAP_PCT=10.0` (the 2026-05-17 R2 decision is preserved — and will be
enforced on truthful data post-flip), ORB window 9:31-9:44, scoring weights, safeguards,
sizing, the delayed Polygon path (retained as universe/reference/failure-ladder, §7). The
detection COHORT is untouched until the operator executes RT-3 (`ep_rt_universe_authoritative`
+ `ep_rt_gap_authoritative` on) after the RT-2 shadow packet — that flip gets its own
change-log entry (data source: "Polygon delayed reference + Alpaca SIP real-time universe
overlay").

**Reversion-flag**: NEW (first change to the detection data source; extends #489's shipped
shadow architecture). Rollback: R1-R5 (§8) — every rung instant + independent, landing on
byte-identical prior behavior.

**Status**: built 2026-07-25 (dark), NOT deployed. Next: operator deploys
(`deploy.sh market-agent`) → operator sets `EP_RT_UNIVERSE_ENABLED=true` for RT-2 shadow
(gates: ≥10 trading days AND ≥5 residual-catch days, 8 measurable gates, 3 operator-reviewed
named lists) → RT-3 operator flip.

### 2026-07-24 — FL-5 reconcile: doc synced to code

Six stale items corrected (no code change): (a) catalyst weights were
documented as multipliers (1.0×/0.7×/0.3×) — code is an ADDITIVE component
(`game_changer`→+25, `strong`→+15, `routine`→+0, ep_detector.py ~1140); (b)
`ep_threshold` range was "65-75" — `regime.py` runs Bull=65/Choppy=70/
Correcting=75/**Crisis=80**, so the true range is 65-80; (c) ORB submission
window text implied the full 9:00 hour — the market-open gate makes the
effective window **9:31-9:44** ET; (d) `MIN_GAP_PCT=10%` hard floor added to
the filter list (was undocumented); (e) the filter list now separates
**pre-grade** filters from the **post-grade** ones (M&A filter, routine+low-gap
skip, pm-shares floor carve-out — all in `_post_grade_filters`, moved
post-classification by #405 2026-07-03 specifically so they can read
`catalyst_quality`) instead of presenting all seven as one undifferentiated
pre-grade cascade; (f) added a note that the Holistic Grade Judge (toggle,
currently OFF) overwrites `score_tier` when enabled.

### 2026-07-23 — #500 Price-aware initial ORB entry: bounded limit-buy fallback when price is already above the ORB high (+ broker-cancel reason capture) [operator-SIGNED]

**Trigger**: ARWR 2026-07-22 (live) — +19.57% gap HIGH EP; the 9:31:00.8 stop-limit bracket
went pending_new → cancelled by Alpaca within ~1 min because price (~$89.06) was already above
the $87.92 ORB-high trigger (an in-the-money buy stop is invalid at the broker); operator saw
"entry cancelled, no reason." SMCI (sitting AT its ORB high) filled the same morning. The
re-entry path has handled exactly this since May (`attempt_day1_reentry` ~615); the initial
entry never did — so the entry mechanism failed preferentially on the most violent gappers.

**Evidence**: `docs/analysis/500_orb_entry_price_aware_proposal_2026-07-23.md` — full-history
cancelled-entry cohort N=11 (read-only prod SQL + SIP tape): in-the-money-stop class **N=2**
(ARWR live, CADL paper) — FLAGGED small-N (below the N≥10 bar; the branch is an order-type
correctness fix per the 2026-05-20 gate-inversion precedent, but the 1.5× chase cap IS a
threshold calibrated on N=2). ARWR fallback sim: +0.16R/−0.16R day-1-close bounds, MFE
+1.7R–2.1R, risk inflation ≤1.37× (admitted). CADL (+14.8% chase, 11.3× inflation, −3R/−11R
sims) is the cap's sole historical drop — **operator reviewed + confirmed the drop list per
rule 3 at sign-off 2026-07-23**. Adjacent classes NOT fixed (named to prevent attribution
drift): LULD rejects (#475 review), gap-through-limit (#22 / known-limitation 4).

**Anticipated effect**: entries where price ≤ ORB high at submit — byte-identical bracket
(zero behavior change; the overwhelming majority). When price > ORB high at submit (~2% of
the 89 historical submissions, concentrated in the strongest gappers): a bounded limit buy
(`latest×1.002`, risk-inflation cap `CHASE_RISK_INFLATION_CAP=1.5` env-tunable, worst case
1.5% equity vs the sized 1.0%) replaces a guaranteed broker cancel; beyond the cap →
`setup:chase_cap_exceeded` skip + Telegram (fail-safe: missed entry, never a bad fill). The
retry re-decides the branch. `mi_live_orders` records the ACTUAL order (type/limit; no fake
trigger row for the limit fallback). Broker cancels/rejects now persist a `broker:*`
skip_reason with a last-vs-trigger diagnosis (`order_manager.broker_terminal_reason`, WS +
polling paths) + Alpaca's terminal order snapshot merged into `mi_live_orders.raw_response`
— "no reason" cannot recur. Hardening ride-along: `place_limit_buy_with_stop` now passes
`OrderClass.OTO` + `StopLossRequest` + the naked-order guard (the alpaca-py
silently-dropped-stop_loss gotcha — a latent NAKED-limit-buy bug on the re-entry path, which
had never fired in prod: 0 limit buys in 89 historical entries). Est. ~1 engaged entry /
6 weeks at current alert volume.

**Reversion-flag**: NEW for `submit_entry` (extends the re-entry's price-aware branch — in
code since May, never fired in prod — to the initial entry, with a chase bound the re-entry
lacks). Hard revert = delete the `_pick_entry`/`_chase_cap_reason` branch in `submit_entry`
(restores the unconditional bracket) + revert the `broker:`/`setup:chase_cap_exceeded`
skip-reason additions. The `place_limit_buy_with_stop` OTO/naked-guard hardening should
survive any revert — it fixes a latent naked-order bug independently of #500.

**Status**: operator-SIGNED 2026-07-23 (decisions §7 of the analysis doc: branch + 1.5× cap +
CADL drop-list + reason capture approved; option B cancel-triggered retry DEFERRED,
data-gated on post-fix residual `broker:entry_cancelled` rows). Built 2026-07-23
(`tests/test_500_price_aware_entry.py`), NOT yet deployed. Pre-deploy: paper smoke of the OTO
limit-buy order shape (operator-run). Verify-live layers: (L1) deploy-day below-orbH entries
byte-identical brackets; (L2) first engaged fallback — log line + OTO stop leg + honest
mi_live_orders row; (L3) next broker cancel carries a `broker:*` reason, never a bare
"cancelled".

### 2026-07-19 — Large-cap rel_volume floor SHADOW observer added (audit-only, no criteria change)

Telemetry only, no detection-criterion change (operator shadow-approved 2026-07-19).
`_emit_large_cap_relvol_floor_shadow` (ep_detector.py) writes one
`filter:large_cap_relvol_floor_shadow` mi_audit_log row per HIGH alert with ADV$
(`adv_20 * prev_close` — the pre-gap price, matching `mi_stock_scores.close`, NOT
today's gapped `current_price`) >= $50M and rel_volume < 0.5, gated `LARGE_CAP_RELVOL_FLOOR_SHADOW_ENABLED`
(default ON). Does NOT skip the alert or change any grade/gate/entry decision — pure
observation of what a future LIVE floor would have done. See `data_gated_reviews.yaml` →
`large_cap_relvol_floor_shadow_evidence` for the forward-tracking review (N>=10 settled
shadow-flagged entries, ~2026-09-01) that gates any future LIVE flip
(`LARGE_CAP_RELVOL_FLOOR_ENABLED`) — operator-signed only, never auto-flipped.

### 2026-07-18 — Analyst-upgrades bonus REMOVED — dead feed since 2026-03-14 (#332, operator-signed)

**Trigger**: #332 C1 setup-class classifier build surfaced that `_score_ep`'s cached-grade tick
hardcoded `upgrades_30d = 0` (a latent inconsistency vs the uncached path). Gated fix on a
backtest before touching a live-scoring path per CHANGE_PROCESS.

**Evidence**: `docs/analysis/332_analyst_bonus_backtest_2026-07-18.md` (probe:
`scripts/probes/_332_analyst_bonus_backtest.py`, read-only, run over prod postgres + the REAL
production `get_fmp_analyst_ratings` function per memory `rigor-before-paid-eval-spend`):
1. The feed (`collector.get_fmp_analyst_ratings`, yfinance `Ticker.recommendations`) has been
   structurally dead since 2026-03-14 — it returns the AGGREGATE grade-count table (columns
   like `strongBuy`/`buy`/`hold`/`sell`), and the string-matcher compares grade NAMES against
   INTEGER COUNTS, which can never match. Verified by running the real function in the live
   `apollo-market` container for NVDA/AAPL/PLTR (the most analyst-covered names in the
   market) — all returned `upgrades_30d = 0` — plus 20 sampled live-alerted tickers, also 0.
2. **Realized impact of the cached-tick hardcode: 0 alerts, 0 tier flips** across all 251
   retained live alerts (2026-04-13 → 2026-07-17) — the uncached path ALSO always computed 0,
   so cached − uncached = 0 on every tick. The "fix" as originally scoped (thread the real
   cached value) would have threaded a constant 0.
3. Reconstructed counterfactual (a REPAIRED feed's value, had it worked): bonus-eligible
   alerts do NOT outperform (N=203 with fwd-10d outcomes; permutation p=0.29 overall, p=0.18
   within-HIGH; mean fwd-10d direction actually LOWER for eligible). What the live `>=3`
   threshold's grade-set actually selects is analyst-coverage BREADTH (TXN/QCOM/ROKU/DDOG/
   WDAY/ZM class) — a mature-large-cap proxy, the OPPOSITE of this rubric's own neglect thesis
   (`breakdown["neglect"]` already scores 52w-high distance directly). The honest "true
   upgrade" threshold (`>=3` distinct upgrade Actions) occurred once in 3 months of EP
   candidates — nothing to calibrate a bonus on even if repaired.

**Anticipated effect**: NONE on any historical or current alert/tier/score — removal is
**behavior-identical by construction** (the term contributed exactly 0 on every tick, ever,
since the feed always returned `analyst_upgrades=0` and `0 >= 3` is false). Forward-looking
effect: removes the risk of a future yfinance schema change silently re-animating the bonus at
an uncalibrated +5 raw points (worth 5.0–7.2 final points post-multiplier) with no edge behind
it.

**Reversion-flag**: REMOVAL (dead-feed retirement) — not a reversal of a specific prior dated
change; the bonus predates this SSoT's change-log history. Not a REFINEMENT (no repair
shipped) and not a REVERSAL of a deliberate calibration (the backtest's §4 shows no calibration
would have justified keeping/repairing it).

**Status**: shipped, behavior-identical by construction (evidenced against all 251 retained
live alerts, not merely asserted) — no field-validation period needed for a change with a
provably-zero realized delta.

**Scope of removal**: `breakdown["analyst"]` term + the `analyst_upgrades` parameter deleted
from `_score_ep` (`agents/market_intelligence/ep_detector.py`); the now-orphaned
`get_fmp_analyst_ratings` fetch + `upgrades_30d = sum(...)` aggregation removed from the
per-candidate scan loop and from `collector.py` (verified no other LIVE consumer via repo-wide
grep — a pre-existing, already-broken standalone script `backtest_ep.py` also referenced it
but was already non-functional before this change, unrelated missing symbol). The `#332`
classifier's OWN `upgrades_30d` (the `episodic_neglect` low-coverage cut) is UNAFFECTED by this
entry — it now sources independently from `collector.get_recent_upgrade_events` (yfinance
`Ticker.upgrades_downgrades`, dated events), a repair tracked in
`docs/decisions/0028-setup-class-conviction-profiles.md` §2, not this rubric.

### 2026-07-18 — Extension-rule wording corrected (transcription fix, NOT a criterion change) [#481]

The "Extension" rule (Universe eligibility line 19 + Filter 4 line 30 + score-factor list line 53)
was mis-transcribed at this doc's birth (2026-05-07, `59e4601`) as `prev_close ≤ 1.50× SMA-10` — a
rule that has **never existed in the code** (`git log --all -S "sma_10 * 1.5"` → no commit, ever).
The LIVE guard, since inception, is `MAX_EXTENSION_PCT=50.0`: skip if `prev_close` is ≥ 50% above the
MIN(close) of the last ~5 trading days (`ep_detector.py:99`, gate `:1858-1866`; MIN, not a single
5-days-ago point). Operator ruled 2026-07-18 (#481) that the live 50%/5-day rule is the intended
criterion → corrected the wording to match the code. **No detection behavior changed** — this is a
documentation/provenance fix. Also corrected line 53's score-factor list to name `prior_momentum`
(the 3-month extension PENALTY, −25/−15) rather than a non-existent "extension" component. The
constant is now cited in `gate_provenance_registry.py` against this corrected SSoT.

**Reversion-flag**: N/A (doc-only correction; the code has always been the 50%/5-day rule).

### 2026-07-04 — #347: LIVE enriched grade corpus + acting re-poll (operator-approved flip)

- **What changed:** premarket EP grades now use the ENRICHED corpus (SEC 400d filings
  + content-bearing primary-subject Benzinga + Perplexity, graded at the 12k window)
  instead of the legacy 6k grounded_text; the catalyst-cache re-poll now ACTS — a valid
  late-source upgrade (the BFLY class) rewrites the grade cache (quality+analysis, boost
  reset to 1.0, filters_cleared=False → the S6 machinery re-filters and proceeds as a
  fresh survivor). In-window (9:30+) first-seen names keep the legacy corpus (the shadow
  never validated in-window grading — latency + fidelity to evidence).
- **Evidence:** 10-day prod shadow — 183 grades; the 32 raw changes collapse to 5 distinct
  events, ALL correct-direction in the operator walkthrough (CMCSA spin-off un-mna'd;
  ZSQR deflated; LBRDK caught; RKLB un-suppressed; APOG = the fail-routine case, see
  guard); dilution suppression 10/10; re-poll fired exactly once, cleanly. Operator
  sign-off 2026-07-04 AM ("flip approved").
- **Guards:** APOG-class — the enriched classify's fail-routine sentinel triggers a
  LEGACY-corpus fallback + `live_enriched_grade_failed` audit (never a silent
  fail-to-routine). The enrichment shadow auto-resumes in reversion mode.
- **Reversion:** runtime toggle `live_enriched_corpus` (mi_safeguard_state row, ≤60s, no
  redeploy — the #400 pattern) with `LIVE_ENRICHED_CORPUS` env fallback; flipping it off
  restores the legacy corpus AND re-arms the validation shadow.
- **Reversion-flag:** none prior — this is the first corpus change since the shadow began.

### 2026-06-20 — Live AUTO-ENTRY for the real-money cutover (operator-signed)

MAGNA53 at `phase=live` + `live_real_enabled=True` now **auto-enters real money** through
the shared `entry_pipeline.submit_trade_entry` funnel (previously every live entry sent a
manual [Confirm] Telegram proposal — auto-entry was never wired for live). START-SMALL =
the **$5,000 account** itself (operator 2026-06-20): `position_size_multiplier=1.0` (full
1% risk/trade) + NO tight count cap (`max_concurrent_positions=NULL` → global 5) for broad
participation on a low-WR strategy (#197). Entry detection/criteria are UNCHANGED — this is
an entry-MECHANIC change only. Full design,
safety envelope, reversion path, and the `/pause` HARD-gate reaffirmation live in
`safeguards.md` change log 2026-06-20 (the portfolio-entry SSoT). Verify-live = first
auto-entry Monday.

### 2026-06-19 — #344 catalyst corpus-completeness — SHADOW (live flip GATED)

**Trigger**: BFLY 6/18 ran +56% with no alert. Graded `routine` because (1) at the
7:00 ET grade its corpus was EMPTY (the Midjourney PR hit Benzinga at 8:12 ET, after the
grade) and the per-day catalyst cache pinned that routine grade all day, and (2) the
6/18 news was an *update to an existing material partnership* — the $74M Midjourney
co-development/license ($15M one-time + $10M/yr + $9M milestones) was disclosed in a
PRIOR 8-K (2025-11-18, item 1.01), never in the grade corpus. Operator labeled BFLY a
real EP (HARD gate); `routine` was wrong. Evidence: `docs/analysis/missed_ep_bfly_2026-06-18.md`,
`docs/analysis/late_source_replay_344_2026-06-19.md`. Cache re-poll ALONE recovers
nothing (the 8:12 PR is headline-only → re-grading it stays routine; proven 0/12 in the
replay) — its value is conditional on the enrichment.

**Change (SHADOW only — live grade UNCHANGED)**:
- `collector.get_alpaca_news(include_content=True)` — stop discarding full Benzinga PR
  bodies (grade path only; default off elsewhere).
- `ep_detector.assemble_grade_corpus` (SSoT; the #344 replay imports it) — anchors the
  grade DATE and appends age-labeled PRIOR item-1.01 agreement + item-2.02 revenue
  context for MATERIALITY sizing, explicitly NOT as today's catalyst (prevents the
  date-confusion that mis-dates stale filings as fresh). **Window budgeting (6/19 fix):**
  the grader slices `grounded_text[:max_chars]`; the appended context would be truncated by
  a long today's-news 8-K, so today's-news is capped to `_GRADE_TODAY_MAX_CHARS=6000` (the
  lean live grader's effective today-window) and the enriched corpus is graded with
  `_GRADE_ENRICH_MAX_CHARS=12000`. The live non-enriched path is unchanged (`max_chars`
  defaults to 6000).
- **#238 dilution feed** (2026-06-19): `assemble_grade_corpus(dilution_filing=)` also appends
  a dated, age-labeled NEGATIVE-context block when a recent 424B5 (priced takedown) or 8-K
  item 3.02 (actual equity sale) is on file — point-in-time (filed ≤ grade), 21-day recency
  window (`recent_dilution_filing`). Framed "weigh AGAINST today's move … but do NOT
  auto-reject — a real EP can coincide with an opportunistic raise": the LLM stays JUDGE (a
  deterministic skip would violate `feedback-catalyst-sourcing-direct-over-llm`). Separate
  tight 424B5/8-K fetch so a prospectus can't crowd the 400d agreement-finder; `has_dilution`
  / `dilution_form` on the shadow rows. Offline canary 6/19 (`docs/analysis/dilution_canary_238_2026-06-19.md`),
  block confirmed IN the grade window (after the truncation fix below): SAFETY direction
  PASSED — 4 names / 6 alerts incl. the false-positive-risk WDC, **0 wrong suppressions**; the
  one change (ELVN game_changer→strong) is a conservative temper that STILL FIRES and matches
  the live grade; SHAZ game_changer + 3.02 unchanged, WDC strong×2 + stale 8-K/A 3.02 unchanged.
  Suppression value (a catalyst-less pump held routine) was unexercised offline → watched on
  the live `has_dilution` rows at the #347 flip.
- `ep_grade_enrich_shadow` (uncached, once/ticker/day): current vs enriched grade,
  web-inclusive. `ep_repoll_shadow` (cached path): re-grade ONCE when a new primary-subject
  source lands after a routine grade in the ORB window (`should_repoll_shadow`; never
  re-polls a firing grade). Flag `ENRICH_SHADOW_ENABLED`; error-wrapped.

**Hot-path safety (advisor 6/19)**: the shadow runs SYNCHRONOUSLY on `run_ep_scan` (the
order-submission path), so it is **PREMARKET-ONLY** (< 9:30 ET) — it never adds SEC GETs /
a Sonnet call inside the 9:30–10:00 ORB entry window, and never contends with the live
grade's EDGAR fetch during entries. The 400d SEC fetch is bounded (`max_filings=8`) and
fetched once/ticker/day (the re-poll reuses it). Latency is logged (`shadow_latency_s`);
Monday verify includes a scan-wall-time check, not just "rows wrote". Cost: grade-path LLM
+ SEC calls roughly double premarket (acceptable for telemetry; killable via the flag).

**Anticipated effect**: ZERO live grade-VALUE change (shadow writes audit rows only). Offline
two-case: BFLY routine→strong (cites today's news sized by the deal), BTQ ATM-dilution
canary stays routine. Offline 60-name cohort: BFLY-rise + AEHR-restore + CASY gc→strong
(conservative, still fires), 0 inflation — BUT the offline baseline is no-web and can't
measure web×enrichment double-counting, so it is NOT the flip gate.

**FLIP GATE (load-bearing — make enriched the live grade)**: requires Monday+ live shadow
data showing production net-correctness (enriched lifts true catalysts, inflates nothing —
read via `scripts/_344_shadow_verify.py`), re-poll fires once with tolerable latency, then
CHANGE_PROCESS + operator sign-off. Until then the live grade is byte-identical to before.
**⚠️ The flip MUST carry the grade window**: the validated shadow grades the enriched corpus
at `max_chars=_GRADE_ENRICH_MAX_CHARS` (12000); the live path defaults to 6000. The flip has
to pass `max_chars=_GRADE_ENRICH_MAX_CHARS` on the live `_classify_catalyst_claude` call, or
the appended dilution/agreement context truncates and the live grade won't reproduce the
measured shadow (the original truncation bug, re-introduced at flip).

**REVERSION**: set `ENRICH_SHADOW_ENABLED=false` (kills the shadow); the live grade path
is unchanged regardless.

### 2026-06-14 — M&A filter: acquirer-direction on the TITLE path (#284) — AWAITING SIGN-OFF

**Trigger**: 6/14 materiality dig (advisor-prompted, off the Sunday weekly review)
found the M&A pin filter suppresses **acquirer-side** names via TITLE match (Path A).
`_ticker_is_acquirer` only inspects per-ticker REASONING, so when reasoning is
absent/ambiguous an acquirer-side title leaks through. Material case: **ONDS 2026-05-28**
graded `strong` on a real Q1 earnings blowout ($50.1M rev), suppressed by the stale
(5/18) title *"Ondas Bets Big On AI Battlefield Software With Omnisys Buyout"* (Ondas is
the BUYER), then ran **+24%** (open-based, 5 sessions). Also **MYRG** (*"MYR Group …to
Acquire Valley Electric"*, +6.5%) and **CECO** (acquirer of THR — but CECO is a
multi-ticker title *bleed*, out of scope here → Path B). This is the residual the
2026-05-13 fix left: that fix only removed bare `"acquire"/"acquisition"` keywords;
`buyout`/`merger`/`definitive agreement`/`takeover` stayed **direction-blind on titles**.

**Fix**: `title_implies_acquirer(title, filing_company_name)` — anchored on the filing
company's POSITION in the headline (a title is not per-ticker, so "BigCo to Acquire
Acme" filed under target Acme must NOT read as acquirer). Target-guard FIRST. Two acquirer
signals, both requiring the filing co to appear BEFORE them: (1) verb form (acquirer verb
after the co — MYRG); (2) object form (acquirer-noun preceded by a capitalized non-filing
entity, after the co — ONDS "Omnisys Buyout"). Wired into Path A after `_ticker_is_acquirer`;
company name fetched lazily + memoized cross-call; emits `mna_acquirer_title_skipped`
(trading-day-deduped) on activation.

**Safety is NOT uniform (corrected 6/14 after /simplify — the original "never converts a
target" claim was WRONG):** the VERB form IS asymmetric-safe (target-guard first +
verb-must-follow-co). The OBJECT form is a BENIGN-FAILURE heuristic, NOT bulletproof — a
Title-Case headline verb/adjective before the noun ("Acme Mulls Buyout", "Acme Spurns
Sweetened Buyout") can be misread as a bought entity and mis-pass a noun-form target (the
`_GENERIC_ACQ_PRECEDERS` stoplist narrows but cannot close this — no NER/name-map).
Operator-signed KEEP 6/14: the failure is benign (a mis-passed target is price-capped ->
small/quick loss, paper-only) and every pass is surfaced for FP review by the recurring
`mna_filter_accuracy_review` (the monitored backstop). Verb-form-alone would be bulletproof
but would re-defer the material ONDS case.

**Evidence**: real title-fires are **N=3 in 120d** (KALV/MYRG/ONDS) — BELOW the N≥10 ship
bar, so flagged augmented-with-synthetic + shadow-validate (per sample-size discipline).
Labeled backtest **N=14 (6 acquirer / 8 target)** incl. the positional trap and CECO
out-of-scope: **14/14** (`scripts/probes/_284_mna_acquirer_backtest.py`). **16/16** unit tests
(`tests/test_ma_filter_direction.py`, incl. updated `test_title_acquirer_*` reflecting the
new behavior + ONDS/MYRG pass + Acme-target still fires + conservative-without-name).

**Anticipated effect**: acquirer-side title-match fires drop (ONDS/MYRG-class pass to
alert/entry); CECO-class title bleed UNCHANGED (still fires — needs Path B subject-relevance,
deferred under `mna_filter_direction_blindness_path_a`). Net ~1–2 fewer acquirer
suppressions/month (rare). Fail-direction is benign: a mis-passed target is price-capped
(small/quick loss, paper-only pre-6/22), vs the +24% winner the leak was costing.

**Reversion-flag**: REFINEMENT of the 2026-05-13 direction fix (adds title-direction
handling for the keywords that fix left direction-blind). Hard revert = drop the
`title_implies_acquirer` block in `polygon_news_has_mna_headline` Path A.

**Status**: OPERATOR-SIGNED 2026-06-14 (filter list reviewed; object-form KEEP after the
safety correction above). Committed `28c4e59` + `/simplify` cleanup (cross-call name memo,
trading-day audit dedup, precompiled object-form regex, honest docstring). Backtest 14/14,
16 unit tests. NOT yet deployed — deploy AFTER the Monday split go-live (intelligence-side
detection; no reason to add a variable to the 6/15 ORB-via-http window), then field-validate
the live wiring (first `mna_acquirer_title_skipped` rows) + the monthly accuracy review.

### 2026-06-12 — Rubric v3: catalyst FRESHNESS clause (judge + fallback grader)

**Trigger**: AKTS 2026-06-12 — the judge's first WRONG live load-bearing promote
(MODERATE→HIGH, `materiality=transformative`), caught same-day by the OPERATOR:
the "$1.1B Lilly partnership" was announced **2024-05-21** (two years pre-gap;
$60M upfront, $1.1B = milestones). The corpus was web-only
(`sources: {web_perplexity: 1}, has_direct_source: false` — no 8-K/wire existed
that day, which was itself the signal); Perplexity surfaced the old deal undated
as "the clearest catalyst"; the judge flagged the verifiability concerns in its
own rationale and promoted anyway. Neither rubric layer required the catalyst to
be NEW.

**Evidence**: single operator-labeled live case (flagged single-case-tune per
CHANGE_PROCESS rule 2) — but the change is a CORRECTNESS rule (freshness is
definitionally part of "a real catalyst" for an *episodic pivot*), not a
threshold tune; same class as the 2026-05-20 gate-inversion precedent. Catalyst
attribution correctness is the stated goal of the program
(`feedback_catalyst_correctness_is_the_goal`).

**Anticipated effect**: undated/stale catalysts can no longer justify HIGH from
either layer; web-only-sourced materiality promotions get explicit skepticism
(prefer floor tier). Expected effect size: rare (first occurrence in 3 days of
load-bearing operation) — but it is exactly the fail-open-to-floor direction:
worst case is a missed alert, never a bad entry.

**Reversion-flag**: REFINEMENT of the judge rubric (v2→v3) + grade prompt.
Prompt-era versioned: `RUBRIC_VERSION/RUBRIC_HASH` + `CATALYST_GRADE_PROMPT_VERSION`
both bumped to `v3-2026-06-12-catalyst-freshness` — every decision row stamps its
era; instant revert = restore the v2 text (hash flips back).

**Status**: shipped 2026-06-12 (operator-signed in-session). Field validation:
AKTS = named regression probe in the eval probe library; watch the next
`has_direct_source=false` promote candidate's `ep_grade_decision`.

### 2026-06-08 — Holistic Grade Judge supersedes the conviction floor (W2c, ADR 0011) — toggle-gated, SHIPPED DORMANT

**Trigger**: Operator directive (2026-06-08, memory `feedback_build_toward_vision_not_piecemeal` + signed ADR 0011): the conviction floor promotes to HIGH on **gap % + a catalyst enum alone** — materiality, theme, narrative, and structure are decorative. By the operator's framing the materiality-less grade is "definitionally incomplete" for the EP method. The North Star is ONE holistic LLM judge over the full rubric that moves the grade **bidirectionally** (promote an under-rated material-small-cap outlier / demote an immaterial big gap) and becomes the live **paper** grade.

**Evidence**: This is a **methodology-completeness** change, not a threshold tune, so it is NOT gated on backtested R-superiority (forward-from-gap is the saturated metric that killed the #189 materiality R-gate, ADR 0010). The operator SIGNED the 5-point rubric (ADR 0011 §Rubric). Field validation = the W1 shadow cohort (judge_tier vs floor delta) + operator review of the promotion/demotion delta lists + the **Unjustified Demotion Sweep** (`scripts/unjustified_demotion_sweep.py` — every judge `demote` whose ticker then ran ≥+18% MFE/5d) BEFORE the toggle is flipped ON. The agent never self-certifies the demotion list (HARD gate).

**Architecture**: the judge runs in the existing **post-loop** concurrent gather (own `_JUDGE_SEMAPHORE`, 15s `wait_for`). When `holistic_judge_enabled` is ON it OVERWRITES the authoritative `score_tier` (the single field the caller reads for alert+entry, and the downstream ORB job reads from the row) and stamps `grade_engine_authority ∈ {judge,fallback}`; `baseline_floor_tier` is preserved as the counterfactual. Judge `none` → suppression (no alert/entry); judge promote MODERATE→HIGH → flows into the ORB path as a floor-HIGH would. **FAIL-OPEN**: judge error/timeout → floor tier kept, authority `fallback` (counted). **FAIL-CLOSED toggle**: any toggle-read error → floor.

**Anticipated effect**: with the toggle OFF (current, SHIPPED DORMANT) — **zero behavior change**, byte-identical to W1 shadow; the judge writes only advisory columns + `ep_grade_decision` audit traces. With the toggle ON (operator-gated, paper-only) — the paper HIGH set is re-graded: gap-only HIGHs with no material catalyst demote out of entry; material-relative-to-size MODERATEs promote into entry. Net HIGH count change unknown until the live cohort accrues (first judge fire 2026-06-09).

**Known limitation**: the judge scope is the **score≥50 cohort** (MODERATE+HIGH results) — it can demote HIGHs and promote MODERATE→HIGH, but cannot rescue a name the floor scored <50 (those never reach the result dict). Sub-50 small-cap rescue is a future widening (cost/scope tradeoff). The cross-strategy allocator shadow-enqueue + scan_log record the floor tier (in-loop, pre-override) — acceptable (allocator is shadow-only #31).

**Reversion-flag**: NEW. Reversion = `docker exec apollo-market python scripts/set_holistic_judge.py off` (instant, no redeploy — the toggle is the kill switch). Hard reversion = drop the `_judge_authority` override block in `run_ep_scan`.

**Status**: SHIPPED DORMANT 2026-06-08 (toggle OFF, byte-identical). The flip to ON is operator-gated on the delta-list + Unjustified-Demotion-Sweep review (ADR 0011 go-live gate); PAPER-only; 6/22 real-money decision stays decoupled.

### 2026-05-27 — M&A filter Part B: sister-ticker possessive proximity check (#119)

**Trigger**: RGTI 2026-05-11 EP alert path still saw Polygon news-tagged M&A interpretation after Part A (#88) shipped. Part A required ticker in `insights` array AND M&A keyword in `sentiment_reasoning`. But the article's `reasoning` for RGTI was "Stock gained 8.29%...following IonQ's merger approval" — keyword present, but the deal belonged to IonQ (a sister-tagged ticker), not RGTI.

**Fix**: `reasoning_other_entity_owns_deal` — sentence-bounded look-back for `[CapitalizedWord]'s` possessive immediately preceding the M&A keyword. Block only when the possessor (case-insensitive) matches a sister ticker symbol from `insight_tickers` (with `.WS` warrant suffix stripped). Narrow by design — does NOT catch arbitrary company-name possessives (no name→ticker map available; e.g., "Hewlett-Packard's deal" on HPQ-tagged article passes through).

**11-case replay verification** (`scripts/_replay_88_mna_filter_fix.py`): 11/11 pass. D + EL TPs kept (zero regression), QBTS/RGTI/MNST/ONDS/INFQ/NBIS/NXT/IREN/FOUR FPs blocked (one via Part B specifically, others via existing Path B keyword-absent gate). PINS = ARTICLE_NOT_FOUND in Polygon (corpus issue, not logic).

**Position in Path B flow**: between the `matches_mna_keywords(reasoning)` check and the existing direction check — additive gate, doesn't restructure Part A. Per advisor 2026-05-27.

### 2026-05-27 — Override respects revenue-weak downgrade + Claude text fallback (#131/#132)

**Trigger**: BBWI 2026-05-27 fired HIGH EP at 9:51 ET despite the revenue-growth gate downgrading it at 7:20 ET (`q_rev_yoy_missing_no_prior_year_comparable`). Override path was unconditional on catalyst quality.

**Fix #132** (override-respects-downgrade): before applying `earnings_override_applied`, query mi_audit_log for a same-ET-day `catalyst_earnings_revenue_weak_downgrade` row for this ticker. If present, skip the override + emit `earnings_override_skipped_post_downgrade`. Tier stays MODERATE. Fail-open on DB error (preserves news-ingest-lag tolerance — the original override design goal).

**Fix #131** (Claude text fallback for extraction + boost): CRSR 2026-05-27 had no rubric block — extraction gated on `earnings_today_match` from yfinance, which missed CRSR's Q1 date. Added `_claude_text_signals_earnings(claude_analysis)` regex (conservative — only matches `Q[1-4] earnings`, `EPS of $X`, `revenue of $XM`, `beat/missed consensus`, `earnings release`). Applied to BOTH the boost gate (line 1229) AND the extraction gate (line 1280) so yfinance ingest-lag doesn't silently kill the rubric OR the catalyst quality lift.

**Override hierarchy after these fixes** (in evaluation order on a MODERATE+gap≥10 alert):
1. `is_earnings_day` via yfinance OR Claude text signal → check
2. If revenue-weak downgrade present today → skip override (tier stays MODERATE), audit `earnings_override_skipped_post_downgrade`
3. Else → fire `earnings_override_applied`, tier=HIGH

**Why these aren't band-aids**: BBWI's downgrade was an active quality decision (no prior-year revenue comparable = can't verify YoY growth = can't grade the earnings). Honoring it preserves the rubric's gating value. CRSR's missing rubric was pure ingest lag at yfinance — Claude's prose had the data the structured-metrics extractor needed.

### 2026-05-23 — M&A filter: Polygon news multi-ticker-tag-bleed fix (#88)

**Trigger**: 2026-05-22 L2 anomaly fired `mna_filter_fired` at 210 events vs 10 median (21× normal). Investigation surfaced 3 of 4 affected tickers (INFQ/QBTS/RGTI — all quantum names in our persistent Sugar Babies cohort) were false positives from a single 2026-05-11 Motley Fool sector roundup tagged with their symbols but only *about* IonQ/SkyWater. QBTS — the Pradeep Sugar Baby example shipped 2026-05-22 #80 — was being silently filtered out of 9M EP alerts. 90d audit walk surfaced ~77% FP rate on this polygon_news layer (3 TPs / 13 cases = 23% TP rate).

**Bug class**: Polygon's `/v2/reference/news` API returns articles tagged with multiple tickers. The previous filter ran `matches_mna_keywords(title) or matches_mna_keywords(description)` on each tagged article without verifying that *this* ticker was the article's M&A subject. Distinct from the closed `perplexity_hallucination_keyword_leak` review (Perplexity disclaimer text leak; that's catalyst_texts path, not polygon_news path) and from the 2026-05-13 NBIS direction-blindness fix (which removed keywords; this preserves keywords but adds an article-subject discriminator).

**Fix** (`ma_filter.polygon_news_has_mna_headline`, two-path acceptance):
- **Path A — title match**: M&A keyword in article TITLE → accept (high specificity, preserves existing behavior for explicit-target articles like EL "Walks Away From Merger Talks").
- **Path B — description-only match**: requires (i) ticker in article's `insights` array (Polygon's per-ticker AI tagging, a proxy for "article is about this ticker"), AND (ii) ticker's `sentiment_reasoning` itself contains an M&A keyword (proxy for "Polygon's AI thinks this ticker's move is M&A-driven").
- Missing `insights` field → SKIP article (conservative; emits `polygon_news_insights_missing` audit event for false-negative quantification).
- Loop semantics: continue past Path-B-rejected articles, don't terminate at first rejection.

Companion change in `collector.get_polygon_news`: expose `tickers` array + `insights` per-ticker structure that the API already returns (previously dropped).

**Evidence (backward-replay against 13 historical mi_audit_log cases via `scripts/_replay_88_mna_filter_fix.py`)**:
- 2/2 TPs preserved (D ×2 Dominion, EL via Path A)
- 8/10 FPs blocked (QBTS, MNST, ONDS, INFQ, NBIS, NXT, IREN, FOUR) — including the QBTS Pradeep-cohort case
- 2 still-FP: RGTI sympathy-merger reasoning bleed (Polygon's AI tagged "IonQ's merger" in RGTI's reasoning); PINS article not found in 21d window (data gap, not logic gap)

**Residual class** filed as #90 (M&A filter direction-blindness through Polygon news description matches) — covers RGTI sympathy-bleed + future cases where reasoning text mentions a competitor's M&A.

**Reversion flag**: REFINEMENT (narrowing FP class without changing detection criteria semantics). No backward action required if reverted — filter would just over-fire as before.

**Status**: shipped 2026-05-23.

### 2026-05-21 PM — REVENUE_STAGE_MIN_USD code default REVERTED to $5M (#68, advisor flagged)

**Trigger**: Today's earlier #63 ship (lower default to $0.01) was based on yesterday's #50 verdict that pre-revenue ($0 Revenue Avg) band had 67% 5d WR. Today's #59 hygiene fix (dedup mi_ep_alerts duplicates) revealed yesterday's cohort was polluted by KOD ×6 + KPTI ×4 + TH ×16 duplicate rows. Clean cohort puts $0 band at 14% WR / -8% avg — a LOSER band, not a winner.

**Decision**: The evidence supporting #63 ($0.01 default) has been retracted. At N=7 clean we don't have evidence supporting EITHER threshold, so the code default reverts to the conservative-block stance ($5M, what the original IMVT/ROIV ratchet aimed at). Prod env override stays at `REVENUE_STAGE_MIN_USD=0.01` as operator-pinned, explicitly provisional pending #55 at 2026-06-20.

**Status**: shipped 2026-05-21 PM (pending).

### 2026-05-21 AM — REVENUE_STAGE_MIN_USD code default lowered to $0.01 (#63, since reverted)

**Trigger**: Advisor review 2026-05-20 PM flagged that the code default ($5M) and prod env-var override ($0.01) had diverged. A fresh prod rebuild without the env-var set would silently regress to the over-blocking $5M value. Backward check (#50, 2026-05-20) showed the $0 Revenue Avg band had 67% 5d WR — $5M would have over-blocked profitable EPs.

**Fix**: changed code default from `5000000` to `0.01`. Documentation, function docstring, and SSoT updated. Operators wanting to TIGHTEN (experiment) override via env var; conservative default protects against rebuild regression.

**Status**: shipped 2026-05-21 commit (pending).

### 2026-05-20 — Pre-revenue gate: skip earnings boost + rubric for clinical-stage / SPAC

**Trigger**: IMVT 2026-05-20 morning. Catalyst classifier graded `routine` (no qualifying news), but `is_earnings_day=True` boosted it to `strong`. Q-rev YoY rubric then engaged, found no revenue data in news (because IMVT is a clinical-stage biotech with $0 expected revenue per yfinance Revenue Average), downgraded back to `routine` with reason `q_rev_yoy_unextractable_quality_low`. Net: same final state (routine) but operator-facing message blamed the wrong cause — implied rubric/extraction problem when the real issue was that the boost shouldn't have fired for a pre-revenue company.

**Bug class**: structural gate inversion (same as 2026-05-19 RVMD flag-universe fix). The earnings boost + Q-rev gate assume revenue-stage business. Pre-revenue companies (clinical-stage biotech, SPAC, blank-check) structurally can't satisfy the gate; applying it produces misleading downgrades. Sample-size discipline doesn't apply to gate inversions — fix is correctness, not threshold tuning.

**Architecture**:
- New helper `is_revenue_stage(ticker)` in `earnings_calendar.py` — reads `yfinance.Ticker.calendar.Revenue Average`. Returns True if ≥ threshold (default $0.01 as of 2026-05-21 — see change log below), False otherwise (pre-revenue / pipeline-driven). Threshold env-tunable via `REVENUE_STAGE_MIN_USD`. Fail-soft to True on any error.
- Earnings boost in `ep_detector.py` now gated on `earnings_today_match AND revenue_stage`. Pre-revenue companies on earnings day get `catalyst_earnings_boost_skipped` audit event (operator visibility — explains why no boost fired).
- Q-rev rubric gate ALSO gated on `revenue_stage` (belt-and-suspenders). Even if Claude graded strong on an organic clinical-stage catalyst (FDA, trial, M&A), the rubric won't engage and produce misleading downgrades. Claude's verdict stands.
- Per-ticker cache `_REV_STAGE_CACHE` (same lifecycle as `_CACHE` in earnings_calendar.py) — single yfinance call per ticker per day.

**Anticipated effect**: clinical-stage biotechs, SPACs, blank-check companies gapping on earnings-day news will no longer get spurious "Q-rev YoY un-extractable" downgrades. Catalyst grade stays at Claude's organic verdict. Final HIGH-alert behavior unchanged for the IMVT-class (catalyst remained routine pre-fix, will remain routine post-fix — just with cleaner audit message).

**Reversion-flag**: NEW (introduces revenue-stage check). To revert: set the gate booleans to `revenue_stage=True` unconditionally.

**Status**: shipped 2026-05-20.

### 2026-05-17 PM — P7.2: MAGNA53→flag carryforward (R3 alpha-slip hedge)

**Trigger**: R3 shipped this morning leaves a known alpha-slip window — 65% of failed-Day-1 alpha names made +5% within 21d, only 34% caught downstream. P7.1a sugar baby analysis confirmed loosening doesn't address the structural gap. Architectural hedge: feed R3-stopped MAGNA53 names into the continuation-flag detector's universe so the basing/tightness state machine catches the delayed-EP breakout.

**Evidence**: Block D audit (60d cohort) + P7.1a sugar baby recovery analysis (22.4% recovery at 0.50 cutoff, mostly fails 9M-volume gate not close_in_range).

**Anticipated effect**: ~1.3 R3-stopped names enter the flag scan's universe per day (bursty around earnings). Flag detector evaluates organically; most enter as `unqualified` initially, progress through stages over 1-3 weeks. Targets ~60-70% downstream capture lift from current 34%.

**Code**: see `docs/setups/flag_continuation.md` 2026-05-17 entry for implementation details. MAGNA53 detector itself unchanged — this is a downstream-detector universe expansion.

**Reversion-flag**: NEW (paired with R3 ship). Env `MAGNA53_FLAG_CARRYFORWARD_ENABLED=false` reverts.

**Status**: shipped 2026-05-17 commit `370aed1`. Verification at Day 7-14 (Stage 1 plumbing) and Day 21+ (Stage 2 alpha capture re-measurement).

### 2026-05-17 — EP Selectivity Phase 2 — five filter ships (R2/R6/R4/R1/R3) + bug fixes

Bundle commit per `~/.claude/plans/i-want-to-plan-groovy-horizon.md`. Phase 1 diagnostic in `docs/decisions/0003-ep-selectivity-overhaul.md`. Phase 2 ships these in risk-ordered sequence as separate commits with feature flags. Each entry below has its own block per CHANGE_PROCESS format.

---

#### P2.0a — Fundamentals fetcher temporal-mismatch fix (commit `68ae8d8`)

**Trigger**: 2026-05-17 user asked "what made VSNT a game_changer, I can't see it?" — VSNT scored composite=32.5 from fabricated 40,000%+ revenue growth via index-based `[i+4]` Y/Y lookup that compared 2026 Q1 ($1.687B) to 2012 Q3 ($3M). Polygon's `sort=filing_date` interleaves late-filed Q4 with current quarters.

**Evidence**: 25 of 97 cohort tickers had temporal-mismatch class: VSNT (14yr gap), ARX (11.5yr), TE (8.7yr), VG (3yr), TTMI (1.5yr), KALV/YSS (1yr), HUT/KYTX/NMAX/ORKA/PACS (out-of-order duplicates), 17 names with annual-only gaps. Affects rubric scoring on the cohort that contains the next NBIS-class winner.

**Anticipated effect**: catalyst rubric scores trustworthy across 100% of cohort. VSNT 32.5 → 17.3 (routine_correct). ARX 24.4 → 17.3. KLAR 0.0 → 17.3 (matches user expected). AEHR contracting -44% now correctly captured (was fabricated). Label distribution: 0/3/14/33 → 0/10/35/52 (gc/strong/RC/weak) — more honest spread.

**Reversion-flag**: REFINEMENT of `fetch_polygon_quarterlies` (no prior version).

**Status**: shipped 2026-05-17. Field validation: re-run rubric scorer on cohort N≥20 next month; verify no fabricated game_changer/strong from temporal mismatch.

---

#### P2.0b — Leveraged ETF universe gap, fail-safe (commit `68dc6da`)

**Trigger**: USAX + USGG admitted as MAGNA53 EP candidates on 2026-04-20 (operator labeled "N/A — leveraged ETF, should not be evaluated"). Root cause: `mi_security_types` weekly Monday refresh hadn't classified them yet; the existing `WHERE security_type NOT IN ('CS', 'ADRC')` filter only catches names ALREADY in the table.

**Evidence**: 2 confirmed cases in 30d label cohort. Polygon issues ETF classification within hours of listing; old weekly refresh leaves a 7-day gap.

**Anticipated effect**: unclassified tickers (not in either `_non_stock_tickers` nor `_known_stock_tickers`) skipped per scan tick. Aggregate counter logged at scan end so we know if the weekly refresh is overdue. Fail-safe direction: prefer to miss a new IPO Day-1 than admit an ETF.

**Reversion-flag**: NEW (no prior unclassified guard).

**Status**: shipped 2026-05-17. Followup filed in BACKLOG: if `_unclassified_skipped` consistently ≥10/scan, bump weekly→daily refresh cadence.

---

#### P2.1a (R2) — Lift gap floor 8% → 10% (commit `9787527`)

**Trigger**: ADR 0003 §3 cohort breakdowns: 8-10% gap bucket had **0/8 win rate** over 60d. 10-15% bucket 51.2% WR. Cleanest single-threshold cut.

**Evidence**: 60d cohort (165 alerts) breakdowns:
- 25%+ : 41.7% WR
- 15-25% : 51.2% WR
- 10-15% : 43.9% WR
- **8-10% : 0.0% WR (n=8)**

**Anticipated effect**: -8 alerts / 165 cohort = -5% direct volume reduction + downstream tightening of top-20-gap filtering.

**Reversion-flag**: NEW. Env override available: `EP_MIN_GAP_PCT=8.0`.

**Status**: shipped 2026-05-17. Field validation: 7-day post-ship HIGH-alert volume drop expected.

---

#### P2.1b (R6) — PM-shares carve-out for high-conviction names (commit `939c314`)

**Trigger**: CPA 5/14 (gap 13.12%, score 67.7, catalyst strong) was held 24 min by pre-catalyst pm-shares floor. Class B miss. Existing carve-out only bypasses on `pm_rvol ≥ 5x` — doesn't catch CPA-class where pm volume hasn't built relative ratio yet despite real catalyst.

**Evidence**: 3 documented cases (CPA + 2 others) in 60d where pm-shares floor blocked clean Class-A entries. Per pre-ship LLM-cost analysis: moving gate post-catalyst adds ~3-10 LLM calls/day (trivial).

**Anticipated effect**: new carve-out admits names with `gap ≥ 10% AND catalyst_quality='strong'`. Original `pm_rvol ≥ 5x` carve-out preserved. Architectural change: pm-shares gate moved from pre-catalyst (line 818) to post-catalyst (after routine-catalyst skip ~993).

**Reversion-flag**: REFINEMENT of 2026-05-08 (original pm_rvol carve-out). Env override: `R6_PMSHARES_CARVEOUT_ENABLED=false` disables NEW carve-out only.

**Status**: shipped 2026-05-17. Field validation: monitor for false-positives (low-pm-volume names admitted that fade).

---

#### P2.1c (R4) — In-theme +10 scoring bonus (telemetry-only) (commit `cf9167c`)

**Trigger**: Catalyst label cross-tab §4: in-theme alerts 67% WR vs uncovered 40% WR. 27pp lift. Theme heat is the single cleanest separator between real-strong and mislabeled-strong (30% in-theme rate for "strong" vs 7.1% for "routine_mislabeled").

**Evidence**: 60d cohort with operator labels.

**Pre-ship verification** (per `feedback_sample_size_discipline`): SQL check found **0 MODERATE-in-theme alerts would have crossed ep_threshold=70 with +10 bonus** in 60d cohort. R4 is decorative under current thresholds; shipped for telemetry/visibility only.

**Anticipated effect**: zero immediate selectivity change. Score breakdown captures theme context in `mi_ep_alerts.breakdown` JSON. Phase 5 meta-rubric will compose theme_context as separate input with calibrated weights. Paired-data signal for Phase 5 regression.

**Reversion-flag**: NEW. Env override: `R4_THEME_BONUS_ENABLED=false`.

**Status**: shipped 2026-05-17 as telemetry. Phase 5 calibration will determine production weighting.

---

#### P2.1d (R1) — Drop MODERATE auto-actions (investigated, NO CODE CHANGE)

**Trigger**: ADR 0003 R1 recommendation based on observed 28% WR for MODERATE vs 52% for HIGH.

**Investigation finding**: every entry pipeline already filters `score_tier = 'HIGH'`:
- `live_tracker.py:324`, `backtester/tracker.py:251`, `backtester/engine.py:534`
- `broker/shadow_orb_tracker.py:346`, `audit_invariants.py:387/404`
- `scheduler.py:1621`, `system_audit.py:188/196/354`

Data confirmation: **0 MODERATE alerts in mi_live_trades over 60d** (paper account, entry_price NOT NULL). Cross-strategy allocator enqueues MODERATE but is shadow-only.

The earnings-boost MODERATE→HIGH promotion path (line 1276) is preserved as methodologically correct per CLAUDE.md B12.

**Anticipated effect**: none — current architecture already enforces R1.

**Reversion-flag**: n/a (no change shipped). Defensive env-flagged guard filed in BACKLOG as low-priority follow-up.

**Status**: verified 2026-05-17 — no code change required.

---

#### P2.1e (R3) — Drop Day-1 same-day re-entry (commit `643a577`)

**Trigger**: ADR 0003 §3 — 0/6 re-entry win rate over 60d cohort. Methodology: failed first breakout invalidates the setup; same-day re-entry chases the failure.

**Evidence**: 6 re-entry attempts in 60d, all losers, avg ret -6.0%.

**Implementation**: env-flagged early gate in `attempt_day1_reentry()` (broker/order_manager.py:430). When R3 active (default): record stop_hit exit, close trade with `skip_reason='block:r3_reentry_disabled'`, emit `r3_day1_reentry_blocked` audit event.

**⚠ Known alpha-slip risk window** (per Block D audit):
- 112 MAGNA53 HIGH alerts failed Day 1 in 60d (97.4%)
- 76 of those (69%) made +5% within 21d
- Only 34% captured by downstream detectors (continuation flag 31.6%, sugar baby 0%, next MAGNA53 EP 0%)
- 66% of alpha slips through entirely
- Back-of-envelope: ~$625/day expected uncaptured alpha at typical position size

**⚠ PAIRED PHASE 7 WORK BUMPED TO NEXT-UP** (target completion 2026-05-24):
- P7.1 Sugar baby filter audit (0% capture is structurally broken)
- P7.2 MAGNA53 → continuation-flag carryforward (lift 31.6% → ~60-70%)
- P7.3 9M cohort delayed-EP audit

**If Phase 7 slips beyond 2026-05-24**: reconsider R3 reversion (set `R3_DAY1_REENTRY_ENABLED=true`) until paired work closes the gap.

**Reversion-flag**: NEW. Env override: `R3_DAY1_REENTRY_ENABLED=true` re-enables re-entry.

**Status**: shipped 2026-05-17 with paired-Phase-7 dependency. Field validation: monitor `r3_day1_reentry_blocked` audit events + Phase 7 Block D re-run after P7.2 ships.

---

### 2026-05-13 — M&A filter: drop direction-blind keywords (NBIS class)

**Trigger**: NBIS 5/13 was filtered as `M&A/buyout catalyst — no momentum trade` despite being the **acquirer** (bought Eigen AI for $643M). The keyword scanner in `ma_filter._MNA_KEYWORDS` matched bare `"acquire"` / `"acquisition"` regardless of which side of the deal the ticker was on — direction-blind substring scan. NBIS gapped +15.79%, pm_rvol 6.4× — clean EP setup lost.

**Evidence**: 90d audit-log backtest (`mna_filter_fired` events, 2026-02-12 → 2026-05-13). 16 distinct tickers caught by bare `"acquire"`/`"acquisition"`:
- **13 false positives** (acquirer or unrelated keyword mention): NBIS, WAT, MNST, FOUR, RKLB, IREN, VEEV, KGS, NXT, PINS, QBTS, QUBT, RAL.
- **3 nominal true positives**: EBAY (still caught via Claude `catalyst_quality='mna'`), WEN (recovered by adding `"take-private"`), GLIBK (the keyword matched accidentally in unrelated biotech chatter — Perplexity returned "no info"; structurally a FP that happened to land on a real target).

Other keywords spot-checked (90d): `buyout` (GBTG, WEN — both TP), `halper sadeh` (OGN — TP), `takeover` (WEN — TP), `merger` (KALV TP, RAL FP), `strategic transaction` (P FP, N=1). Retained — true-positive yield holds.

**Anticipated effect**: ~13 false positives / 90d eliminated (~1 per week). Zero genuine M&A targets lost — EBAY-class caught by Claude classifier branch; WEN-class caught by new `"take-private"` / `"private deal for"` phrasings. The 2 minor non-`acquire` FPs (RAL/P) are Perplexity-hallucination leaks (separate bug class).

**Reversion-flag**: REFINEMENT of `is_likely_ma` (no prior change to keyword direction-handling).

**Status**: shipped 2026-05-13. Field validation: monitor `mna_filter_fired` events for residual acquirer-side hits.

### 2026-05-08 (session 2) — Aligned `is_earnings_day` fail-soft direction across all 4 sites

**Trigger**: Advisor flag — three EP sites (boost, cooldown bypass, MODERATE→HIGH override) plus parabolic detector all handled yfinance errors with `False`, but the operational meaning of `False` differed per site (some permissive, some restrictive). Inconsistent and hard to reason about under outage.

**Evidence**: Logical.

**Anticipated effect**: on yfinance error → `earnings_today = True` everywhere. EP boost fires, cooldown bypasses, MODERATE→HIGH override promotes — all defensive (rather over-allow on data outage than miss a real earnings EP).

**Reversion-flag**: REFINEMENT.

**Status**: shipped.

### 2026-05-08 — Earnings-day pre-score catalyst boost

**Trigger**: DDOG 5/07 scored 30 every tick (gap 19-31%, pm_rvol 30-89×) — blocked by `score < 50 catalyst=routine`. AAON same. Both had earnings catalysts but the LLM classifier returned `routine` on hedged news scrape. Existing earnings-day MODERATE→HIGH override fires too late (requires score ≥ 50 first).

**Evidence**: Single-day case study (DDOG + AAON 5/07). 30d backtest in `mi_ep_scan_log` showed ~75-100 names blocked by `catalyst=routine` with score ≥ 30 + gap ≥ 10%; estimated 50-70% would be earnings-day matches under the boost. Live false-positive rate to be measured via `catalyst_earnings_boost` audit events on 5/8+ sessions.

**Anticipated effect**: ~40-70 boost firings per 30d. DDOG/AAON-class names promoted from score ~30 to ~70+ → cleared 50 threshold.

**Reversion-flag**: NEW.

**Status**: shipped (commit f5d1977). Field validation pending 5/8+ session.

### 2026-05-08 — EP cooldown bypass on fresh earnings catalyst

**Trigger**: HIMX 5/07 every tick blocked by `EP cooldown — alerted within last 60 days`. New earnings catalyst (gap +28%, pm_rvol 65×) doesn't reset cooldown. 60-day cooldown blocks legitimate quarterly re-firings.

**Evidence**: Single-day case study (HIMX 5/07).

**Anticipated effect**: cooldown bypassed when `gap_pct ≥ 15% AND is_earnings_day`. Routine post-news bumps still respect cooldown.

**Reversion-flag**: REFINEMENT of 60-day cooldown (no prior change to bypass logic).

**Status**: shipped (commit f5d1977). Audit event: `ep_cooldown_bypassed_earnings`.

### 2026-05-08 — Pre-market shares floor relative-anomaly carve-out

**Trigger**: AAON 5/07 early ticks blocked by `pre-mkt volume X < 25,000 shares` despite pm_rvol 32-60×. Absolute floor redundant with relative pm_rvol gate; low-float names always trip absolute regardless of relative anomaly.

**Evidence**: Single-day case study (AAON 5/07).

**Anticipated effect**: skip absolute floor when pm_rvol ≥ 5×. Keep absolute as fallback for names with no pm_rvol baseline.

**Reversion-flag**: NEW.

**Status**: shipped (commit f5d1977).

### 2026-05-08 — `is_earnings_day` window tightened ±1 day → {yesterday, today}

**Trigger**: advisor flag — earnings on `scan_date + 1` cannot have produced today's gap; matching them was over-permissive (sector-sympathy + earnings-later-in-week could false-positive).

**Evidence**: Logical (correctness fix, no quantified backtest needed).

**Reversion-flag**: REFINEMENT of CLAUDE.md 2026-05-05 ±1 day window.

**Status**: shipped (commit 035ad85). Affects EP boost + EP cooldown bypass + parabolic earnings exclusion.

### 2026-05-06 — Wave B #2: Unify EP volume gate to RVOL@T (one primitive, two anchors)

**Trigger**: HUT/BLMN/GLW HIGHs detected late at ~09:52 ET on 5/6, missing 9:45 ORB cutoff. Investigation surfaced three structurally distinct volume gates (pre-9:30 RVOL@T, 9:30-9:45 no gate, 9:45+ raw `today_5min_vol / 390min_ADV` ratio).

**Evidence**: Polygon minute aggs discriminator: HUT 9:31 → 7.29× RVOL@T, BLMN 9:31 → 11.84×, GLW 9:31 → 0.72× → 9:35 → 2.41× — all clear ≥1.0× before 9:45 cutoff.

**Anticipated effect**: collapsed three gates to one (RVOL@T with anchor selection — pm pre-9:30, session 9:30+). Threshold 1.0× for both anchors. Names like HUT/BLMN/GLW now qualify within first session minute.

**Reversion-flag**: REVERSAL of the prior three-phase architecture per user mandate ("having something the first 15 min makes no sense").

**Status**: shipped + validated against 5/7 morning session (no 09:52 pile-up; ep_filter_session_rvol firing correctly on SEZL/BLBD/ACVA/DGII at 09:46).

### 2026-05-03 — Catalyst hedge-phrase downgrade

**Trigger**: RDDT 5/01 catalyst pipeline returned "strong" with Evercore-initiation blurb instead of identifying the real driver (Q1 earnings beat). Perplexity returned hedged synthesis → Claude classified hollow news_summary as "strong".

**Evidence**: 1 case study + the structural argument that chained LLM calls hide their own data quality.

**Reversion-flag**: NEW.

**Status**: shipped + validated (CLAUDE.md 2026-05-05 confirmed firing).

### 2026-05-03 — pm_rvol gate universe: top-500 → $5M $-vol floor

**Trigger**: OMCL 4/28 HIGH alert (gap +22%) lost $1506. 30d audit showed 84.2% of HIGH alerts and 97.4% of MODERATE alerts silently bypassed the pm_rvol gate (rank 501+ outside top-500 universe). pm_rvol baseline was structurally non-functional for 85% of EP candidates.

**Evidence**: 30d audit: 32/38 HIGH, 37/38 MODERATE bypassed.

**Anticipated effect**: universe expanded ~5.3× (500 → 2647 tickers). Newly-included tickers warm up over ~10 trading days.

**Reversion-flag**: NEW.

**Status**: shipped (CLAUDE.md 2026-05-03).

---

Pre-2026-05-03 history is in CLAUDE.md "Recent Changes" / `CHANGELOG.md`. Backfill into this file as each section is touched.
