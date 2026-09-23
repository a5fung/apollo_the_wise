# EP backtest under TODAY's rules, from raw bars — design spec

**Date:** 2026-08-29 (PT) · **Task:** filed on #482 (successor to the retracted geometry doc)
· **Status:** DESIGN ONLY — no code written, no behaviour changed, nothing deployed.
· **Standard:** this document follows `docs/methodology/analysis_standard.md` (§1 questions
answered in §0 below; §6 sections present; the failure catalogue was read first).

---

## §0 · The decision this serves

**Operator's words** (2026-08-29, on retracting the geometry analysis): *"stop using old data
when our system has evolved significantly week to week… The tactic we used is to just use raw
data to run our analysis given we have minute bars stored, that is the path we should go."*

1. **What decision does this serve?** Whether TODAY's EP system — today's rubric, today's
   admission stack, today's bracket — has positive expectancy, and if not, which stage loses the
   money. This is the #508/#533 selection question (*"making existing EP profitable is
   critical"*) asked honestly for the first time: every prior read averaged over populations
   admitted by rules that no longer exist.
2. **What would change the decision?** Expectancy in R of the re-derived cohort, live-bracket
   replayed. Positive median AND positive mean → the current system is sound and the work is
   elsewhere. Negative with today's admission → selection is still the lever, and the per-stage
   attribution (which gate admits the losers) is the evidence the operator acts on.
3. **What population answers it?** The population that TODAY's rules would have admitted over
   2026-04-13 → present, re-derived from raw price/volume data — NOT any stored trade or alert
   table. §2 derives it; §8 attacks it.
4. **What would make this wrong?** Written down FIRST, in §8, before any build. The retracted
   doc's failure mode (population admitted by mixed-era filters) has four descendants here; each
   is named with its mitigation and its residual.

**⚖ THE LINE:** this backtest produces evidence only. It changes no strategy, no entry/exit
discipline, no sizing, no target, no safeguard. Every flip that could follow from its results is
the operator's decision. Nothing here is a proposal to change the live system.

---

## §1 · "Today" is pinned, or it is not a target

The rules changed **twice on the design date itself** (extension cap 75→50 reverted 08-29;
rubric v4 + real-time volume/gap authority landed 08-27). "Today's rules" is only a valid
backtest target if it is **frozen as a manifest** the run embeds and every output cites.

**M1 — Rule manifest (built once, embedded in every output):**
- The git SHA of `apollo_the_wise` the constants are read from, recorded at build time.
- Every constant in the §4 gate table, read **from code at that SHA** — never from docs.
  (Proof this matters: `docs/setups/magna53_ep.md` §Universe still says `MAX_EXTENSION_PCT=75.0 ⚠now 50.0`;
  the code says `50.0` at `ep_detector.py:213`, operator-signed 2026-08-29. The doc is stale;
  the code is the truth. One of the retraction-day failures was exactly this.)
- The runtime-toggle snapshot. Captured 2026-08-29 (read-only, one query, file:
  `/Users/alvinfung/.claude/jobs/6b173ac9/tmp/capture_out.txt` §E):
  `ep_rt_gap_authoritative` ON (since 08-27) · `ep_rt_gap_down_authoritative` ON ·
  `ep_rt_universe_authoritative` ON (08-25) · `ep_rt_volume_authoritative` ON (08-27) ·
  `ep_rt_sustain_enabled` ON · `ep_rt_entry_gap_recheck` ON. `ep_score_separation`,
  `catalyst_tier_lattice`, `ep_shortlist_prescore` have **no DB row → default ON**
  (`db.get_runtime_toggle`, default=True; verified in code). `holistic_judge_enabled` ON (paper
  scope). The build must re-snapshot at build time and diff against this.
- Container env values (`EP_MIN_GAP_PCT`, `EP_RT_PASS2_ENABLED`, `EP_RT_UNIVERSE_ENABLED`,
  sustain-rule knobs) read from the running container at build time (read-only inspection).

**M2 — Cache the expensive artifacts rule-independently.** Minute bars and LLM grades are keyed
by `(ticker, date)` / `(ticker, date, corpus_hash)` — they do not depend on any threshold. When
the rules move again (they will), only the **$0 deterministic stages re-run**. This is the
design's answer to "is today's rules even a fixed target": the target moves, the re-aim is cheap.

**M3 — The run writes nothing to prod.** All prod access is SELECT-only. Backtest state lives in
local files (parquet/SQLite) on the machine that runs it.

---

## §2 · Population derivation — the stage the retraction was about

### Why `mi_ep_scan_log` alone cannot be the universe

The scan log only holds what the **era's Pass-1 floor admitted**. Measured (capture §A/§B,
40,736 rows, 3,927 ticker-days, 2026-04-13 → 2026-08-28):

| month | ticker-days logged | pool: max gap ≥9% & prev_close ≥$5 | of which 9–10% band |
|---|---|---|---|
| 2026-04 | 661 | 422 | 97 |
| 2026-05 | 888 | 764 | 87 |
| 2026-06 | 519 | 519 | **0** |
| 2026-07 | 430 | 430 | **0** |
| 2026-08 | 1,429 | 514 | 30 |
| total | 3,927 | 2,649 | 214 |

The June/July zeros are not market behaviour — they are the **10% floor era (2026-05-17 →
08-19) censoring the log**. Today's floor is 9%. Roughly a quarter of today's admissible band
(by April/May base rates, ~90/month) is simply absent from the scan log for ~3 months. Any
population built from the scan log inherits yesterday's filters — the retracted doc's defect 3,
one table upstream.

### D1 — Rebuild Pass-0 from raw data (the decision)

The candidate universe is re-derived per trading day from **facts, not filtered logs**:

1. **Daily seed** (`mi_daily_closes`: 2025-07-21 → present, 14,720 distinct tickers — the full
   captured Polygon universe, written contemporaneously, so delisted-since names are still in
   it): every ticker-day with `open ≥ prev_close × 1.07` **or** present in `mi_ep_scan_log` with
   any tick gap ≥ 9%. The 7% daily-open superset exists because today's authority is the
   **real-time premarket gap**, and a name can gap 9%+ premarket yet open below 9 (and vice
   versa); a 2pp margin catches the premarket-only crossers. Residual miss — a name that touched
   9% premarket but opened below 7% and never hit a scan tick — is stated in §9, not hidden.
2. **Universe floors applied from data, not from the log**: prev_close ≥ $5 (`MIN_PREV_CLOSE`),
   prior-day volume ≥ 50k (`MIN_PREV_DAY_VOLUME`), ticker length ≤ 5, not in `SKIP_TICKERS`.
   These floors are era-stable (unchanged in git history), so applying them retroactively is not
   era-mixing.
3. **Tick series reconstruction**: for every seed ticker-day, fetch 1-minute bars 04:00–16:00 ET
   from Alpaca (historical SIP; $0 under the existing subscription). Premarket bars give the
   gap-at-tick and cumulative volume-at-tick on the same 5-minute scan grid the live scheduler
   runs (7:00–9:59 ET) — i.e. the **real-time authority path, replayed from raw bars**, which is
   exactly the tactic the operator named. The sustain rule (`EP_RT_SUSTAIN_BARS=3` over a 15-min
   lookback) is computable from the same bars.

**Fetch burden, measured** (capture §C/§D): `mi_intraday_bars` holds 603,328 bars, 608 tickers,
1,757 ticker-days — but only **559 of 2,649 pool ticker-days (21%)** have the 09:30 bar (Apr
68/422, May 157/764, Jun 37/519, Jul 81/430, Aug 216/514). Coverage is best in August because
the recorder captures **alerted names** — the stored-bar set is itself survivorship-shaped (it
holds what the old rules alerted), which is why fetching is mandatory, not optional. Estimated
fetch: ~2,100 pool ticker-days + ~250 unlogged Jun/Jul 9–10% band days ≈ **2,400 ticker-days ≈
1.7M bars, $0, hours of wall-clock**. Fetch failures (Alpaca returns nothing — expect this to
correlate with delisting) are **counted and reported as their own cohort, never silently
dropped** (§8-T4).

**Where it runs:** the market-agent container lacks Alpaca data credentials; the fetcher runs on
**apollo-execution** (precedent: `scripts/backfill_forward_minute_bars_562.py`, the #577
replay) or locally with paper keys. Fetch once → store under the backtest's local cache →
never re-fetch (cost rule: capture once, read many).

---

## §3 · Stage 1 — re-score under today's rubric: what is honestly reconstructible

Today's score (`ep_rubric.SCORE_WEIGHTS`, separation table, flag ON, presented scale; bar =
`SEPARATION_BAR = 65`; regime multiplier ×1.2 Bull else ×1.0 at `ep_detector.py:2861`):

| component | max pts (raw) | input needed | reconstructible? | policy |
|---|---|---|---|---|
| gap (flat) | 10 | gap ≥ 8% | ✅ from rebuilt tick series | exact |
| liquidity | 15 | 20d ADV$ ex-ante | ✅ `mi_daily_closes` as-of (same source live uses) | exact |
| catalyst | 25 | LLM grade of the day's news | ⚠ **the hard one — see below** | bracket + optional paid re-grade |
| float bonus | 5 | float < 50M shares | ❌ only TODAY's float is fetchable (FMP) — historical float not stored | use current float, flag as approximation, sensitivity ±5 raw pts |
| vol_conviction | 5 | premarket vol percentile vs own history | ❌ baseline distributions not stored for non-logged names | stored `vol_percentile` where present (`mi_ep_alerts` only); else 0 with sensitivity ±5 raw pts |
| theme bonus | 10 | in Accelerating/Mainstream theme as-of date | ✅ `mi_themes` is a daily snapshot table (115 snapshot dates, 2026-03-19→08-28; as-of read pattern exists at `db.py:3813`) | as-of read, `theme_date ≤ scan_date`, 7-day staleness horizon |
| conviction floor (branch 4) | floor 60 | gap ≥10 + catalyst = game_changer | depends on catalyst | follows catalyst policy |
| regime ×1.2 | — | regime as-of | ✅ `mi_market_regime` daily, 2025-03-03→present (n=390) | as-of read |
| confidence_multiplier | — | Perplexity agreement boost | **retired 2026-08-27 (#233)** | fixed 1.0; engineer verifies at build SHA |

Two honest caveats on the ✅ rows: `mi_themes` and `mi_market_regime` are **as-was outputs of
the era's theme/regime engines**, not what today's engines would have said. They are as-of reads
(no lookahead), but they carry era, worth ~10 raw pts and the ×1.2 multiplier. Stated in §9.

### The catalyst grade — the input that decides whether Stage 1 is buildable

The catalyst is worth up to 25 raw pts **plus** the floor-60 rescue **plus** three admission
gates (§4: routine+low-gap skip, pm-shares carve-out, cooldown earnings interaction). It cannot
be waved at. Three facts:

1. **Stored grades are era-stamped but less than useless only pre-June.** The classifier prompt
   has been v3 since 2026-06-12 and is still v3 today (`CATALYST_GRADE_PROMPT_VERSION`,
   `ep_detector.py`). Rubric v4 (08-27) changed the **judge**, not the classifier. So stored
   `catalyst_quality` from 06-12 onward is today's classifier, modulo model-version drift.
   Coverage of the pool by any stored grade: 714 of 2,649 ticker-days (Apr 65 / May 225 / Jun
   110 / Jul 119 / Aug 195) — the old gap-ordered shortlist graded different names than today's
   prescore ordering would surface, so the holes fall exactly on the names the new ranking
   promotes.
2. **A fresh retro-grade is possible but has a leak channel.** The corpus must be rebuilt from
   **dated sources only** (FMP/Polygon historical news, published-timestamp ≤ the alert tick;
   `grounded_text` is stored for alerted names — 100% of alerts since July, 128/202 in May).
   **Perplexity is excluded from the retro path** — it searches today's web and cannot be
   time-boxed; it would grade April's news with knowledge of April's outcome. This is a
   deliberate infidelity to the live path (which uses Perplexity search) and is stated as such.
   LLM parametric hindsight is bounded: Apr–Aug 2026 events post-date the graders' training
   cutoffs, so the model cannot "remember" outcomes; the leak lives in corpus selection, hence
   the timestamp gate, and republished/updated articles are filtered on original publish date.
3. **It costs real money** — priced in §7, one number.

**D2 — the decision: bracket first ($0), grade only if the bracket is inconclusive.**
- **Run L (catalyst-blind lower bound):** catalyst = 0 for everyone, no floor rescue. Only names
  clearing the bar on deterministic components alone are admitted (needs ~40 raw of a
  deterministic max of 45 — near-max everything; severely under-admits).
- **Run U (catalyst-generous upper bound):** catalyst = `strong` (15) for every candidate that
  has any same-day news row; `game_changer` where the stored grade or earnings-day flag says so.
  Over-admits by construction.
- Every downstream number is reported as the **[L, U] interval**. If the conclusion (sign of
  expectancy, rank of loss source) is the same at both ends, the question is answered for $0 and
  the paid path is never run. If the ends disagree, **Stage 1b** (paid re-grade of the
  re-derived shortlist, today's v3 prompt, dated corpus, no Perplexity) resolves it — §7 prices
  it. Stored v3-era grades (lattice-corrected, deterministic — `catalyst_tier_lattice` transform
  re-applied in code) are reused wherever they exist, shrinking the paid set.

### The judge is part of today's admission and cannot be fully replayed

`holistic_judge_enabled` ON → the Opus judge **overwrites the authoritative `score_tier`**
(`magna53_ep.md:242`; measured: authority `judge` on 145 of 147 alerts in the 60d to 08-27, tier
changed on **43 of 147 ≈ 29%**). Its live context includes tape features, the
Perplexity-disagreement block, narrative cohort — partially unreconstructible. **D3:** the
backtest's primary run is **judge-OFF** (deterministic tier), with the 29% overwrite rate
applied as an explicit uncertainty band on the alert count; the optional paid variant runs the
judge on modeled HIGHs with the reconstructible context subset and reports agreement, never
silently substituting. A backtest that quietly modeled the judge as faithful would be
manufacturing precision.

---

## §4 · Stage 2 — today's admission stack, in order, from code

Order matters (first failure skips). Every constant below was read from code on 2026-08-29;
the build re-reads at the manifest SHA.

| # | gate | constant (source) | reconstruction |
|---|---|---|---|
| 1 | universe floors | `MIN_PREV_CLOSE=5.0`, `MIN_PREV_DAY_VOLUME=50_000`, `MAX_TICKER_LEN=5`, `SKIP_TICKERS` (`ep_detector.py:163-166`) | ✅ from `mi_daily_closes` |
| 2 | gap floor, real-time authoritative | `MIN_GAP_PCT=9.0` (`ep_detector.py:112`); Pass-1 superset 5.0 then rt re-floor (all rt toggles ON per manifest) | ✅ gap-at-tick from fetched premarket bars = the rt path replayed |
| 3 | sustain rule | 3 consecutive minutes ≥ floor, 15-min lookback (`EP_RT_SUSTAIN_BARS/LOOKBACK`) | ✅ same bars |
| 4 | pm / session RVOL | `MIN_PM_RVOL=1.0`, `MIN_SESSION_RVOL=1.0`, baseline n≥10 (`minute_volume.py:75-77`) | ⚠ baseline = each ticker's own 14d minute-volume profile; not stored for unlogged names. **D4:** probe the bind rate on stored rows first ($0 — how often does pm_rvol<1 kill a gap≥9 candidate?); if it rarely binds, missing→pass (P1: a false exclusion is invisible) + count; if it binds often, extend the bar fetch 14 days back for candidates only |
| 5 | cooldown | `EP_COOLDOWN_DAYS=60`; bypass if gap ≥15% AND earnings day | ⚠ **self-consistency**: computed against the RE-DERIVED alert history, not `mi_ep_alerts` — else old-rule admissions leak in through the back door. Pre-window seed (before 04-13) comes from `mi_ep_alerts` as-was; affected names counted, sensitivity run both ways. Earnings dates from the earnings calendar ($0) |
| 6 | extension cap | `MAX_EXTENSION_PCT=50.0` — **reverted 08-29, code not the stale doc** (`ep_detector.py:213`); vs MIN(close) of last ~5 days | ✅ `mi_daily_closes` |
| 7 | quality filters | ADV$ median-20d ≥ $1M · ATR14% ≤ 15 · mcap ≥ $500M (`backtester/filters.py:21-23`) | ADV/ATR ✅ from `mi_daily_closes` (OHLC backfilled 2026-04-25 — ATR unknown for ~2 weeks of April; missing→pass, counted). Mcap ❌ live path reads **current** mcap — the file's own `skip_mcap` flag documents this as unfit for historical scans. **D5:** approximate as current shares-outstanding × historical prev_close, flag drift, sensitivity at ±30% |
| 8 | shortlist | prescore ordering (`SHORTLIST_WEIGHTS`, liquidity-dominant, tie-break ADV$ then ticker — fully deterministic, `ep_rubric.py`), cap `SHORTLIST_SIZE=20` per tick with grade-cache semantics | ✅ replay per 5-min tick; the cap is why the paid-grade ceiling in §7 is 20/day, not the whole pool |
| 9 | score bar | presented ≥ `SEPARATION_BAR=65` (raw 40 through the ×1.25+15 map); no MODERATE band exists (separation ON → `resolve_moderate_cutline=None`, so the earnings MODERATE→HIGH override is dormant) | ✅ given §3's score |
| 10 | post-grade filters | M&A skip · routine+gap<12 skip · pm-shares ≥25k with 5×RVOL / gap≥10+strong carve-outs (acting = lattice-corrected grade) | depends on catalyst policy (bracketed in L/U) |
| 11 | judge overwrite | see D3 | judge-OFF + uncertainty band |
| 12 | ORB window | alert must exist by 09:44 ET (`scheduler.py:989`: hour==9 & minute<45); pre-9:30 HIGHs → order at 09:31; ≥09:45 → `WINDOW_OUT_OF_ORB`, no entry; 10:00 cancels unfilled | ✅ alert tick from the replayed grid decides |

**Not simulated, by decision (D6):** max-5 concurrent positions, the 2% daily loss limit, both
breakers. They are path-dependent on live account equity and breaker state that cannot be
honestly reconstructed (a breaker whose 7/31 firing cancelled most of a day's entries is real
history, not a rule property). Primary output is **per-signal** expectancy; a portfolio overlay
(max-5, first-come) runs as a labelled second pass so the operator sees both. Stated in §9.

---

## §5 · Stage 3 — entries and exits from bars

**Entry (live bracket, from code + `magna53_ep.md` lines 14-22):**
- ORB bar = the **09:30 ET 1-minute bar** (`fetch_orb_bar_with_retry` — cache/REST both resolve
  to the true 09:30 minute).
- Stop-limit buy at ORB high, submitted in 09:31–09:44 for eligible alerts. Fill model: first
  subsequent minute bar (09:31→09:59) whose high ≥ ORB high fills at `max(bar_open, orb_high)`;
  a bar **opening** above the limit price = no fill that bar (stop-limit semantics — the
  gap-through case the live telemetry tracks); unfilled at 10:00 → cancelled, no trade. Fade
  guard: MAGNA53 HIGH passes `None` → skipped (CLAUDE.md, `check_fade_guard`) — not simulated.
- **Stop (2026-08-16, operator-signed):** protective stop at `entry − 2R` where
  `R = entry − ORB_low` (equivalently `2·ORB_low − ORB_high`). Sizing
  `shares = risk_dollars / stop_distance` → half size, **same dollar risk**. The +2R partial
  target does NOT move: **1/3 off at the ORIGINAL `entry + 2·(entry − ORB_low)`**
  (`order_manager.profit_target_r_per_share` pins the frame). Verified live 08-18/08-19
  (AMLX/MRNA/MRVL stops match `2·ORB_low − ORB_high` exactly — SSoT change log).
- After the partial: stop rises to breakeven (`max(stop, entry)`; `breakeven_at_broker` ON,
  confirmed live on AMLX/MRNA).

**Exit engine — reuse, don't re-implement (D7).** `broker/exit_logic.py` is the pure,
side-effect-free single source of truth for the hard-stop / breakeven / SMA10-20 trail /
partial ladder, and its docstring says backtest semantics are its default. The backtest drives
**the same function** the live tracker uses — the strongest possible defence against the
"control was not live" failure (§8-T2). Day-of events (stop, +2R partial) are decided on the
minute walk, **first touch wins**; a single minute bar spanning both stop and target resolves
**stop-first** (conservative; the sensitivity run flips it target-first and reports both).
Subsequent held days step `exit_logic` on daily OHLC from `mi_daily_closes` (its native
convention: stop fires when `bar_low ≤ hard_stop`) — minute-resolution refinement only for the
subset with full bar coverage, reported as a calibration delta. Horizon cap: 40 sessions,
force-marked at close, counted.

**Coverage gaps:** any candidate whose day-of minute bars cannot be fetched (delisted, symbol
change) is excluded from the replay and **reported as its own line with n and its daily-bar
outcome where available** — never dropped silently, never fabricated as −1R (§8-T4).

**Units:** all outcomes in **R = planned dollar risk** (`entry − hard_stop` per share × shares
— invariant across the 08-16 change by construction). Percent never substitutes for R where a
stop exists.

---

## §6 · Stage 4 — scoring

- **Expectancy in R: mean AND median, n on every figure**, win rate as a secondary column only.
- Splits, each with its own n: by month · by gap band (9–10 / 10–15 / 15–20 / 20+) · by
  catalyst tier (within L/U bracket) · deterministic-score band · filled-vs-unfilled ·
  entry-day-stopped vs held.
- **Live and paper never pool — and this cohort is NEITHER.** The simulated cohort is labelled
  `modeled`. Calibration compares it against actuals separately: paper trades (Apr–Jun, n≈213)
  and live trades (Jun–Aug, n≈110) each get their own replay-vs-actual reconciliation on the
  overlap set (same ticker-day admitted by both old-live and modeled-today rules).
- **Single-big-mover check** (standard §5): the result re-stated without the largest positive
  and largest negative name.
- **n discipline:** any cell under n=10 reports "too few to judge" and draws no conclusion.
  If the FULL modeled cohort lands under ~30 fills, the honest headline is the interval and
  "insufficient n", not a verdict.
- **Acceptance checks before any number is reported** (verify-before-reporting):
  1. **Current-era reproduction:** run the whole pipeline on 08-27/08-28 raw data; the modeled
     alert set must match the actual alert set (rules coincide except the extension band, whose
     diffs must be exactly the 50–75% names). A mechanism check, not a statistic (n=2 days).
  2. **Stop-math pin:** modeled stops on post-08-16 actual trades must equal placed stops
     (AMLX/MRNA/MRVL class) to the cent.
  3. **Bracket sanity:** Run L cohort ⊆ Run U cohort, always.

---

## §7 · Cost — the whole path, priced up front

| item | basis (measured, capture §G, 14d actuals) | cost |
|---|---|---|
| Alpaca minute-bar fetch (~2,400 ticker-days ≈ 1.7M bars, + optional 14d RVOL lookback per D4) | historical data on existing subscription | **$0** |
| All DB reads, daily data, theme/regime as-of, prescore, deterministic score, both bracket runs, full entry/exit replay, scoring | SELECT + local compute | **$0** |
| **Stage 1b (only if the L/U bracket is inconclusive):** re-grade ≤ 20/day × ~96 trading days = 1,920 ceiling, minus ~25% reusable stored v3 grades → ~1,450 LLM grades @ $0.0135 (ep_catalyst_grade $0.0112 avg n=71 + type classifier $0.0023 n=17) | `api_usage` actuals | ~$20 |
| optional judge variant on modeled HIGHs (~2.5/day × 96 ≈ 240 @ $0.0335, n=17 actuals) | same | ~$8 |
| retries / corpus-fetch overhead headroom ×1.4 | — | ~$12 |
| **TOTAL if the paid stage runs** | | **≈ $40, ceiling $60** |

The $0 path runs **first and completely**. The paid stage needs operator sign-off on the one
number above before the first dollar, and runs **once** — grades captured to the rule-independent
cache (M2), post-processed locally forever after.

---

## §8 · Adversarial — what would make THIS backtest wrong the way the last one was

Written before the build, as the standard requires. Each threat: mitigation, then the residual
that survives mitigation — because pretending a mitigation is total is how the last one died.

- **T1 · Survivorship in the scan log.** The retracted analysis trusted `mi_live_trades`; the
  naive fix trusts `mi_ep_scan_log`, which §2 proves is floor-censored (June/July 9–10% band:
  0 rows logged). *Mitigation:* Pass-0 rebuilt from `mi_daily_closes` + raw Alpaca bars.
  *Residual:* the 7% daily-open superset can still miss a premarket-only 9% toucher that opened
  <7% and fell outside every logged tick — a small, one-sided (candidate-losing) hole, bounded
  by the Aug base rate of premarket-vs-open divergence, and reported.
- **T2 · The "today's rules" target is stale by ship time.** It changed twice on the design
  date. *Mitigation:* the M1 manifest pins SHA+toggles+env; every output names its manifest;
  M2 makes re-runs cheap when rules move. *Residual:* the report is honest about WHICH today it
  measured; there is no fix for the operator changing the rules after reading it — nor should
  there be.
- **T3 · The re-scored population is an artifact of unreconstructible inputs.** Catalyst (25
  pts + floor + 3 gates), judge (29% tier overwrite), float, vol_conviction, mcap, RVOL
  baselines are imperfect. *Mitigation:* nothing imputed silently — the L/U bracket carries the
  catalyst uncertainty through EVERY downstream number; judge-OFF with an explicit band; named
  sensitivities on the small components. *Residual:* if L and U disagree on the sign, the $0
  answer is honestly "indeterminate without $40 of grading" — that is a finding, not a failure.
  If even Stage 1b's dated-corpus grades disagree with live grades on the overlap set at a high
  rate, Stage 1 is declared unsound for the pre-June window and the scored window narrows to
  06-12+ (where v3 stored grades exist). The narrower honest answer beats the wider fake one.
- **T4 · Coverage bias correlated with outcome.** Bar availability correlates with liquidity
  and listing survival; delisted names (likely the worst outcomes) fail today's fetch.
  *Mitigation:* stored bars are NOT preferred over fetched ones (store-first would inherit the
  alert-shaped recorder bias §2 measured); fetch-failures become a named cohort with daily-bar
  outcomes where recoverable. *Residual:* if that cohort exceeds ~5% of admitted names, the
  headline number carries a stated one-sided bias flag.
- **T5 · Lookahead through as-of reads.** Theme/regime/earnings reads must be `date ≤
  scan_date`; the catalyst corpus must be publish-timestamp-gated; float/mcap are the two
  knowingly-current inputs (named, sensitivity-bounded). *Mitigation:* every as-of accessor in
  the build takes the scan timestamp as an argument — no accessor may read "latest". One
  structural leak remains by design: `mi_themes`/`mi_market_regime` rows are the era engines'
  outputs (as-was, not as-would-be-today) — stated in §9, worth ≤10 raw pts + the ×1.2.
- **T6 · Simulator artifact reported as observation** (the "+2R winners" failure). *Mitigation:*
  the three acceptance checks in §6 gate reporting; the current-era reproduction check is the
  strongest — if the pipeline cannot reproduce two days it has full data for, no historical
  number leaves the building.

---

## §9 · What this does not answer

- **Whether a DIFFERENT rule set would be better.** This measures today's manifest only. It is
  not a sweep, not an optimizer, and its per-gate attribution is descriptive, not a proposal.
- **Anything the judge decides.** Judge-OFF is an admitted infidelity worth ~29% of tier
  decisions; the paid variant bounds it but cannot replay the judge's full live context.
- **Portfolio-level truth.** Breakers, loss limits and max-positions are not simulated (D6);
  per-signal expectancy ≠ account equity path.
- **Pre-June catalyst fidelity.** Stored grades before 2026-06-12 are prompt-era v1/v2; if
  Stage 1b's overlap check fails, the window honestly narrows.
- **Theme/regime as-would-be-today.** As-was engine outputs are used as-of; ≤10 raw pts +
  the regime multiplier ride on them.
- **Premarket-only crossers below the 7% open superset**, fetch-failed (mostly delisted)
  names, and fill-model error on stop-limit gap-throughs — each is counted and reported, not
  resolved.
- **Execution reality of half-size orders** (slippage, partial fills, ask-aware entry): the
  fill model is mechanical.

## §10 · ⚖ THE LINE

This design produces evidence about the current system. It proposes no change to any strategy,
entry or exit discipline, sizing, target or safeguard; nothing here flips anything. If its
results ever argue for a change, that change goes through CHANGE_PROCESS with operator sign-off
— the decision is his alone.

---

## §11 · Build order (each step independently useful; stop-points marked)

1. **Manifest builder** — SHA + constants + toggle/env snapshot → `rules_manifest.json`. ($0)
2. **Pass-0 seeder** from `mi_daily_closes` + scan-log union; universe floors. ($0)
3. **RVOL bind-rate probe** (D4) on stored rows → decides fetch depth. ($0, STOP-POINT: fixes
   the fetch plan)
4. **Bar fetcher** on apollo-execution → local cache keyed (ticker, date). ($0, hours)
5. **Deterministic admission + score, Runs L and U**; per-gate kill counts. ($0)
6. **Entry/exit replay** driving `exit_logic.py`; acceptance checks §6. ($0)
7. **Report** — [L,U] intervals, splits, calibration, coverage cohorts. ($0, STOP-POINT: if the
   bracket is conclusive, DONE)
8. **Stage 1b re-grade** — only on operator sign-off of the ≈$40 (ceiling $60) number; grades
   cached; report re-issued with the interval collapsed.

**Method/population statement (Gate 6):** populations in this document are: `mi_ep_scan_log`
40,736 rows / 3,927 ticker-days, 2026-04-13→08-28; `mi_intraday_bars` 603,328 bars / 1,757
ticker-days, same window; `mi_daily_closes` 2025-07-21→08-28 (14,720 tickers); `api_usage`
14 days to 2026-08-29; toggle snapshot 2026-08-29. All captured once to
`/Users/alvinfung/.claude/jobs/6b173ac9/tmp/capture_out.txt` and read from file.
