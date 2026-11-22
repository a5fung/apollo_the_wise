# Market liquidity read — research + design (2026-11-22)

Status: **finding / proposal, not an owner.** Nothing here changes a rule, a gate, sizing or the regime score. Anything that would gate entries or change sizing is the operator's decision and goes through `docs/setups/CHANGE_PROCESS.md` (THE LINE). This doc proposes; it does not decide.

Seed: Matt Caruso (CFA, CMT), X post 11-22 — the AI-name selloff is "a money problem", monetary conditions changed in recent weeks, watch Kevin Warsh and the Fed (their pivot marks a bottom), junk bonds (JNK) trending down = liquidity draining. Video with @Crowded_Mkt_Rpt "Is the Stock Market Heading for a Liquidity Crisis?" (youtu.be/fdH9aFki8_U). Operator: "there's a thousand other things to look at ... this needs full research." Captured in `docs/methodology/operator_shared_notes.md` (commits `84877a2a`, `c529b1b6`).


## 0. His rulings 2026-11-22 (after the first draft) — these override the draft where they differ

- **The liquidity read is a DISPLAY for his own market read, beside breadth — not only an EP filter.** It ships as a view on its own merits; the EP / breakout test (§5) is a separate question about whether it should ever touch trading.
- **JNK: read vs its 20-day average as well as its trend** (Caruso). The display carries JNK vs 20d and vs 50d, and the 20d slope.
- **Gold / silver ratio: rising = tighter monetary conditions, falling = easier** (his note). Added to the display (GLD/SLV, or spot from a free source), with its 20d / 50d trend.


## Method and population

- **Method:** desk research (5 web lanes: practitioners, credit, Fed/money, market internals, academic evidence) + a repo inventory, synthesised and then critic-reviewed on 2026-11-22. No outcome was measured; every percentage in this doc is either a quoted market level or a pre-registered bar, not a finding.
- **Population for the proposed test (not yet run):** the §1 population of `docs/analysis/ep_winner_study_prereg_2026-11-21.md` — n = 4,665 gap-day EP events, 2016-01 .. 2024-09, of which 554 (11.9%) are §2 big winners; and the breakout replay trades 2017-03 .. 2021-12 and 2022-03 .. 2024-12 (n printed at Step 0, cut at 2024-12-31). The sealed 2025-26 rows are never read.

---

## 1. Summary for the operator

- **Nobody has proven that a liquidity measure tells you in advance when momentum stocks will work** — Caruso, Howell and the "net liquidity" charts are claims, and the academic evidence mostly shows credit stress arriving *at the same time* as the stock drop, not weeks before.
- **The one solid academic link is the one that matters to us: when the market as a whole turns illiquid, momentum strategies pay less and crash more** — so a liquidity read is worth testing on our own trades, as context beside breadth.
- **We can test it for $0 this week** on our 4,665 replayed EPs (2016-2024) and the breakout replay (critic: 2017-03 → 2021-12 and 2022-03 → 2024-12; the file runs to 2025-01-30 and must be cut), using junk-bond and Treasury fund prices we already hold; the test, the pass bar and the "don't show it" result are fixed below before any outcome is read.
- **Today's junk-bond spread (3.52% on 11-19, up from 3.34% on 11-09) is still low by history** — a slight widening, not yet the "draining" Caruso describes (headline read, not verified against JNK's price). critic: 3.52% on 2026-11-19 confirmed on the FRED series page 11-22; the 11-09 figure is not re-checked.
- critic: **a 2016-24 pass would be a first finding, not proof** — the EP study's per-year winner rates have already been looked at, and its own rules say a new idea can only be confirmed on the sealed 2025-26 years.
- **Action for you: none now.** The first build is display-only (a tile beside breadth); whether it ever touches entries or sizing is your call after the test.

---

## 2. Ranked shortlist (7 indicators)

Ranking rule: **can we test it on our own 2016-24 data now** first, evidence strength second. Tier A = backtestable now from local closes; Tier B = live display only until history is sourced.

Local data fact (checked 2026-11-22, rows ≤ 2024-12-31 only): `~/apollo_data/cb702*/daily_closes_all.csv.gz` closes are **raw, not dividend-adjusted** (HYG closes 80.10 on 2016-01-04, 80.99 on 2019-01-02 — the raw prints). critic: more exactly, **split-adjusted but not dividend-adjusted** in both files (AAPL 2020-08-28 is 124.81 in `daily_closes_all` vs 499.23 in `cb702_pre_v2/daily_raw_close.csv.gz`; NVDA is continuous across its 2024-06-10 10:1 split in `cb702`). Volume is split-adjusted too, so close × volume in A3 is consistent. Cross-check the rebuilt total return against any free adjusted-close source on 3 ex-dates per fund. HYG/JNK pay monthly, so raw price drifts down ~4-5%/yr against total return. Every Tier A rule below uses a **total-return series rebuilt by adding back distributions** (free from issuer distribution history); this is step 0 of the test plan.

### A1. High-yield credit trend — HYG (JNK from 2019-05) — Caruso's named gauge
- **Says:** junk-bond buyers are pulling back → funding for weak borrowers is tightening.
- **Compute:** HYG total-return close vs its 50-day average at the prior close; flag = below. Secondary: 50-day average slope negative; 52-week-low breach.
- **Data:** local file, HYG 2016-01-04 → 2024-12-31 continuous (stitch `cb702_pre_v2` + `cb702`, dedupe the 2021-09..2022-06 overlap); JNK only from 2019-05-06. Live: Alpaca bars, $0. ETF inception: HYG 2007-04, JNK 2007-12 (critic: recalled, not checked on issuer pages). critic: SJNK (short-duration HY, 2016 →), SPHY (2016 →), ANGL/FALN (fallen angels), BKLN (loans) are all in the local files too; SJNK is the low-duration answer to the 2022 failure below — a declared secondary only, not a substitute leg.
- **Updates:** daily, at the close.
- **Evidence: mixed.** Practitioner claims (TradingView, Investing.com commentary) that HYG/JNK diverge before S&P tops; an Investing.com review calls it "inconclusive". Credit and stocks bottomed together in Apr 2025 (Apr 7-8) and Mar 2020. Hotchkiss-Ronen (2002) find HY bond returns lead stocks; Kwan (1996) finds the reverse — direction contested (both recalled, not retrieved this session). Academic support is for spreads generally (Gilchrist-Zakrajsek, AER 2012), not ETF trends.
- **Fails when:** rates rise (price falls on duration, not credit — 2022); sector shocks (energy 2015-16, ~15% of HY, while non-energy yields were flat); false alarms 2011, 2015-16, 2018 Q4 (per evidence lane, recalled); the ETF trades at a discount to its holdings in a real seizure (Mar 2020 — size of discount recalled, unverified).

### A2. Credit vs Treasuries — HYG / IEI (variant HYG / IEF)
- **Says:** junk is underperforming safe bonds of similar duration → risk appetite falling, with the pure rate move stripped out.
- **Compute:** ratio of total-return HYG to total-return IEI; flag = ratio below its 50-day average at the prior close. IEI (3-7y) may match HYG's duration better than IEF (7-10y) — **a variant to verify** (compare durations on the issuer pages) before freezing; run IEF as the pre-declared alternate. HYG/LQD (junk vs investment grade) as a third view.
- **Data:** local, IEI/IEF/LQD 2016 → 2024 continuous. $0.
- **Updates:** daily.
- **Evidence: mixed-to-weak.** HY/IG ratio diverged ahead of the 2010 S&P fall (AOL/DailyFinance 2010, hindsight read); CMT Association (Nov 2022) warns ETF ratios mostly reflect duration differences and prefers the spread differential. No rigorous lead test found.
- **Fails when:** duration is mismatched (why IEI is the candidate); divergences persist for months.

### A3. Market-wide illiquidity — built from our own universe (Amihud)
- **Says:** trading the average stock moves price more per dollar → the market is thin; the academic state in which momentum pays less.
- **Compute:** for each stock-day in the local universe, |daily return| / dollar volume (close × volume); cross-sectional median per day; 20-day average; flag = 20-day value above its trailing 252-day 80th percentile at the prior close. Universe = names with price ≥ $5 and 20-day average dollar volume ≥ $5M (fixed now, before outcomes).
- **Data:** local OHLCV, $0. History as far back as the local file (2016).
- **Updates:** daily.
- **Evidence: strongest relevant, but not "liquidity" in Caruso's money sense.** Avramov et al.: illiquid market states → lower momentum payoffs, subsuming market-state and volatility effects; a QUB working paper: momentum unprofitable unconditionally over the last decade in US/Japan/Eurozone but substantial after liquid states; Butt-Virk (2022): momentum crashes tied to liquidity changes; Sadka (2003): ~half of momentum returns are liquidity-risk compensation; Asness-Moskowitz-Pedersen: funding liquidity a partial source. **Dissent:** a Critical Finance Review replication finds liquidity risk essentially unrelated to momentum. All on 12-1 month cross-sectional momentum, not breakouts or EPs; abstracts read, not full papers.
- **Fails when:** volume is seasonal (holidays, late December); universe composition shifts; it is contemporaneous with stress, not leading.

### A4. Risk appetite inside equities — IWM / SPY (alternate SPHB / SPLV)
- **Says:** small, rate-sensitive, weaker-balance-sheet stocks lagging → financial conditions biting where our names live.
- **Compute:** IWM/SPY ratio below its 50-day average at the prior close. SPHB/SPLV as the pre-declared alternate.
- **Data:** local, 2016 → 2024. $0.
- **Updates:** daily.
- **Evidence: weak.** Practitioner commentary only (trade-ideas.com Oct 2026, TradingView); no lead-lag study found; no source at all for SPHB/SPLV.
- **Fails when:** sector mix or index composition drives it (many unprofitable Russell names); short squeezes; overlaps breadth.

### A5. Dollar — UUP
- **Says:** a rising dollar tightens offshore dollar funding.
- **Compute:** UUP total-return above its 50-day average **and** 20-day change ≥ +2% at the prior close.
- **Data:** local, 2016 → 2024; already in the Strength Map macro complex. FRED DTWEXBGS (free, from 2006) as a live cross-check.
- **Updates:** daily.
- **Evidence: weak.** Standard macro heuristic; no quantified lead to US equity momentum found.
- **Fails when:** the dollar rises on US growth (good) rather than stress (bad).

### B1. High-yield option-adjusted spread — FRED BAMLH0A0HYM2 (+ CCC minus BB: BAMLH0A3HYC − BAMLH0A1HYBB)
- **Says:** the extra yield junk borrowers pay over Treasuries, duration removed — the cleanest credit-stress gauge.
- **Compute:** daily level; 20-day change in basis points; distance above the trailing 12-month low. Use direction and speed, not level (spreads sat at lows for years in 2005-07 and 2021).
- **Data:** FRED, free, daily (T+1 morning). **Since Apr 2026 FRED serves only the trailing 3 years** (ICE licence; internal use only, no redistribution) → not testable on 2016-24 from FRED. Start storing our own daily snapshot now. Long free substitute: Moody's Baa minus 10-year (FRED BAA10Y).
- **Evidence: mixed — the best of the set.** 2007: spreads widened from a June 2007 trough ~4-6 months before the Oct 2007 peak (Livewire; Eco3min). Gilchrist-Zakrajsek: the forecasting power sits in the excess bond premium; Fed note (Pike & Vazquez-Grande 2019): 12-month recession AUROC out of sample 0.78 for the premium vs 0.70 for the 10y-3m curve, only 0.59 for recession *entry* (confirmed by search). But Eco3min's own Baa test flagged only 4 of 12 stock peaks — no better than chance (46.9% base rate). Coincident at the 2020 and Apr 2025 lows.
- **Fails when:** long quiet regimes; sector concentration (energy 2015; software / private credit 2026); recession forecasting is a 6-12 month horizon, not a swing-trade timer.

### B2. Fed / money panel — net liquidity, financial conditions, 2-year minus funds rate
- **Says:** the policy side — is the Fed system adding or draining dollars; are conditions tight; is the market pricing cuts (Caruso's "pivot").
- **Compute:** net liquidity = WALCL − WTREGEN − RRPONTSYD, on a weekly Wednesday grid, 13-week change (never the level). **Units differ between series and the two research lanes disagreed on WTREGEN's — confirm units on each FRED series page before computing.** critic: checked on FRED 11-22 — WALCL millions (weekly, Wednesday; 6,741,452 on 11-18), WTREGEN **millions** (weekly, week ending Wednesday; 916,613 on 11-18), RRPONTSYD **billions** (daily; 0.401 on 11-20 — the reverse-repo facility is essentially empty). Convert RRP ×1,000 before subtracting. NFCI / ANFCI 4-week change. DGS2 − DFF 4-week change (pivot proxy).
- **Data:** FRED, free (needs a free FRED API key; no client exists in the repo). WALCL 2002, RRPONTSYD 2013 (near zero before 2021), NFCI 1971, DGS2 1976.
- **Updates:** WALCL weekly (Thursday), RRP daily, TGA weekly on FRED (WTREGEN; critic: a daily TGA needs the Treasury Daily Statement, not FRED), NFCI weekly (Wednesday, revised).
- **Evidence: weak.** Net liquidity: only promotional/in-sample (R² 0.57 vs S&P per Advisor Perspectives 2022; low before late 2020; "95%" claims with no method); levels-on-levels of two trending series; reverse causality (the Fed expands after drops); RRP is nearly empty so it now moves mostly on the Treasury cash account. NFCI: predicts the lower tail of GDP (Adrian-Boyarchenko-Giannone 2019, recalled) but contains equity and credit inputs — partly measures the outcome. Pivot-as-bottom: stocks kept falling for months after the first cuts in 2001 and 2007-08; worked in 1982, 1998, 2019, 2020 — depends on whether a recession follows (recalled history, untested).
- **Fails when:** QT and rate moves disagree (a Warsh-style mix of hikes plus balance-sheet shrinkage); slow; revised.

**Not shortlisted:** Howell / CrossBorder global liquidity (proprietary, monthly, fitted cycle whose calls have moved; cost unknown), MOVE index (paid licence; realised TLT volatility is the free proxy), M2 (slow, single-episode evidence), margin debt (monthly with 3-4 week lag; Deuskar-Kumar-Poland support is for margin *credit*, a different quantity), IPO activity (quarterly), bitcoin (likely follows liquidity rather than leads; local history too thin before 2024), VIX/VIX3M (contrarian — marks lows, not drains), RSP/SPY (duplicates breadth), BKLN (2026 private-credit story only; low price beta). Realised volatility (Daniel-Moskowitz; Barroso-Santa-Clara — the one out-of-sample-robust result) is carried as a **control** in the test, not a liquidity leg.

**critic: schools missing from the review (FRED series IDs and start dates below are recalled, not checked — WRMFNS may be discontinued) (none is added as a judged leg — the composite stays frozen; each is a declared secondary or a reasoned omission):**
- **Yields comparison — curve and real yields** (he named "yields comparison"): FRED T10Y2Y / T10Y3M (free, decades), DFII10 10-year real yield (2003 →); locally TIP/IEF (breakeven proxy) and TLT/SHY (curve proxy) 2016 → 2024 (checked in both local files). Rising real yields are the standard story for selling long-duration growth / AI names — arguably closer to the 11-22 selloff than credit. Should be at least a reported secondary in Step 1.
- **Funding plumbing / reserve scarcity** (the school most tied to a Warsh balance-sheet run-off): bank reserves (FRED WRESBAL / WRBWFRBL), SOFR minus interest on reserves (SOFR, IORB — IORB only from 2021-07; IOER before), standing repo facility use. The Sept 2019 repo spike is its in-sample episode. Live display candidate; history too short / regime-specific to test 2016-24 cleanly.
- **Treasury issuance and term premium**: bill-vs-coupon issuance mix (Treasury refunding), NY Fed ACM term premium (free, daily). Carried as context only.
- **Free long-history stress indices**: St. Louis Fed Financial Stress Index (STLFSI4, weekly, 1993 →) and OFR Financial Stress Index (daily, 2000 →) — a free daily-ish substitute for the licensed HY spread on 2016-24, and the obvious Tier A candidate for B1's missing history.
- **Bank lending**: Senior Loan Officer survey (quarterly, FRED DRTSCILM) — the classic credit-cycle read; too slow for entries. Regional banks (KRE) — 2023 stress episode.
- **Private credit / BDCs** (named in B1's 2026 failure mode): a BDC basket or BIZD — 2026-specific story, live display only.
- **Yen carry**: FXY is in the local files (2016 →); the 2024-08 episode in Step 0 is a carry unwind that none of the four legs is built to see.
- **Flows / positioning** (ETF flows into HY, money-market fund assets FRED WRMFNS): mostly paid or slow; not shortlisted.

**Unverified inputs carried as such:** Caruso's full framework (X returned 402; video yielded only its title — needs a transcript before anything is built *from him*); the 11-22 news context (Warsh-led Fed hike 9/16 to 3.75-4.00%, long-yield spike — search summaries only); the Mar 2020 HYG discount size; the 7.5%/yr Pastor-Stambaugh spread and ~0.5% Campbell-Thompson figures (recalled). Stockbee and Qullamaggie, in what was found, use breadth/price regime reads with no Fed or liquidity input; Qullamaggie's note that leaders start up before the market bottoms means a liquidity filter could conflict with his approach.

critic: **claims still resting on recall or abstracts, to treat as uncited until checked:** Hotchkiss-Ronen / Kwan direction; the 2011/2015-16/2018 false-alarm list; the QUB working paper and Butt-Virk (2022) (titles not given — find them before citing); the Critical Finance Review replication (likely Li-Novy-Marx-Velikov 2019 on Pastor-Stambaugh, which is about liquidity risk pricing in general, not momentum specifically — check before using it as momentum dissent); Sadka's paper is JFE 2006 (the 2003 date is the working paper); the Advisor Perspectives R² 0.57; Eco3min's 4-of-12 test; ETF inception dates. The FRED HY restriction, the 3.52% print and the FRED units are now checked (critic, 11-22).

---

## 3. Composite "liquidity state" (simple, rule-based)

Four Tier A legs, each evaluated **at the close before the event day** (an EP entry happens before that day's close exists):

| Leg | "Draining" flag |
|---|---|
| Credit trend | HYG total-return close < its 50-day average |
| Credit vs Treasuries | HYG/IEI total-return ratio < its 50-day average |
| Equity risk appetite | IWM/SPY ratio < its 50-day average |
| Dollar | UUP > its 50-day average **and** 20-day change ≥ +2% |

- **Draining** = 3 or 4 legs flagged.
- **Easing** = 0 legs flagged.
- **Neutral** = 1 or 2.

Frozen now: 50-day average, the 2% dollar move, the leg list, IEI as the Treasury leg (IEF the one pre-declared alternate). No tuning after outcomes are read.

critic: on the composite — it is **arbitrary but not overfit** (nothing has been fitted; the 50-day and 3-of-4 choices are conventional and frozen before outcomes). Three weaknesses to check in Step 0, without reading outcomes:
- **HYG is in two of the four legs** and IWM/SPY overlaps breadth and the SPY-trend placebo — "3 of 4" may mostly mean "HYG down and small caps lagging".
- **The dollar leg needs +2% in 20 days** — likely rare, so "Draining" may in practice be "3 of 3".
- **The share of days each 50-day leg flags is unknown** (an upward-drifting total-return series sits above its average more often than not) — measured in the Step 0 table; Draining frequency is set by how correlated the legs are, not by any liquidity level.
- **None of the four legs is a Fed, rate or yield input** — the composite is a market-price read of risk appetite, not Caruso's "money" read. Say so on any surface that shows it.

Step 0 therefore adds a **leg-rate and pairwise-overlap table** (share of days each leg flags; share of Draining days each leg is in; pairwise agreement). Consequence stated now: if the dollar leg is in < 10% of Draining days, report the state as "3 of 3 non-dollar legs" and keep the definition unchanged; if any two legs agree on > 85% of days, report that the composite is effectively three legs. Neither licenses changing a leg.

The market-illiquidity series (A3) is a **separate second state** (illiquid / normal), not a fifth leg, so the two questions — Caruso's money read vs the academic illiquidity read — get separate answers. Tier B series are shown beside the state on live surfaces, not folded into it, until they have history we can test.

---

## 4. How it sits beside breadth (display / context only)

- **Regime table:** add a `liquidity` JSONB key to `mi_market_regime` (state + the four legs + HY spread when available), computed in `agents/market_intelligence/regime.py` after `get_index_history`. **It does NOT feed the regime score or `ep_threshold`** — that would be a strategy change, operator-only, CHANGE_PROCESS. critic: `regime.py` is the module that sets `ep_threshold`, so writing there is on the money path even for a display field — prefer a separate job and table (e.g. its own `mi_liquidity_state` row) so a liquidity bug cannot touch the regime write. **Every item in this section is conditional on §5's result and needs the operator's go** before any prod schema, cron or Telegram line ships; the one exception worth asking him for now is the HY spread snapshot, because history is lost every day it waits.
- **Market Strength Map:** widen the "Macro backdrop" complex (`strength_map.py:116`, today only TLT + UUP) with HYG, HYG/IEI, IWM/SPY. Confirm HYG/JNK/IEI are in prod `mi_daily_closes` first (not confirmed in the inventory); add to the collector if absent.
- **Live breadth dashboard (#723):** one tile — state word + four leg dots + HY spread and its 20-day change — in the `breadth_live.py` JSON on the existing `live-breadth` branch. Daily cadence; the inputs only change at the close, so no intraday work.
- **Telegram / morning read:** one line beside the breadth line, e.g. "Liquidity: Neutral (credit trend down, dollar flat)". Monospace, no pipe tables.
- **Storage now:** a daily cron that snapshots FRED HY spread (+ CCC, BB, IG) into our DB from today, because FRED keeps only 3 years. critic: confirmed on the FRED page 11-22 ("Starting in April 2026, this series will only include 3 years of observations"; ICE: internal use only, no reproduction without permission) — internal storage is fine, showing it on the shared live-breadth dashboard is a third-party display question to check against the licence first.

---

## 5. Pre-registered test plan ($0, our data, 2016-2024 only)

Hard rules: **rows ≤ 2024-12-31 only, with an assert; the sealed 2025-26 is never read.** critic: the assert must cover **event/trade dates AND outcome windows**: the breakout trade file `cb702/out/trades_discovery_exitpb.tsv.gz` runs to D = 2025-01-30 and its late-2024 trades' `realized_r` may have been priced on 2025 bars; the `_702_race_1022/03_market_trend_split.py` harness cuts only SPY at 2024-12-31, not the trades (and its `astype(bool)` turns a missing SPY date into True). EP events with E in Oct-Dec 2024 have a 60-session winner window truncated at the cut. Drop trades with D > 2024-12-31, and report the Q4-2024 events separately or drop them — decide at freeze, stated in the commit. Nothing below is computed until this section is frozen in a commit. This doc is the registration.

### Step 0 — build checks (before any outcome is joined)
1. Rebuild total-return series for HYG, IEI, IEF, LQD, UUP, IWM, SPY from issuer distribution history; verify one known ex-date drop per fund is removed.
2. Stitch the two local files; assert no gaps > 5 trading days and no duplicate dates.
3. **Composition table first:** days and events per state, by year and by era (A 2016-22-04, B 2022-04 on). critic: **warm-up** — the 50-day legs need 50 sessions, so events before about 2016-03-15 have no state; A3 (20-day + 252-day percentile) has none before about 2017-02. Count and report dropped events by state-less reason. If any state has < 3 distinct episodes (episode = run of ≥ 5 consecutive trading days in that state) in an era, the verdict for that era is **"cannot tell"** — not a pass, not a fail. (Per #454: the EP population is ~94% Bull days; check before any cut.)
4. **Episode check** — expectations written now, to be checked before any outcome is read. A miss means the build is wrong (fix the build); it never licenses retuning thresholds.

| Episode | Expected state |
|---|---|
| 2018 Q4 (Oct-Dec selloff) | Draining for most of mid-Oct → Dec; credit and small caps both weak |
| 2020 (Feb-Mar crash, Fed backstop 3/23) | Draining late Feb → early Apr; Neutral/Easing by May-June |
| 2022 (rate-driven bear) | Credit trend and IWM/SPY flagged most of the year; **HYG/IEI may NOT flag much** (both fell on rates) — expected leg disagreement, not a defect |
| 2024-08 (yen carry unwind, ~Aug 1-7) | At most 1-2 legs, brief — likely Neutral; credit barely moved |

### Step 1 — EP test (4,665 events)
- **Data:** `scripts/probes/_ep_winner_study_1121/build/stage6_minutes/02b_events.tsv.gz` + `02b_rows.tsv.gz`; join on ticker + event date E to the state at the close before E. Baseline arm = the current live-exit arm in that replay (one arm only; named in the freeze commit). critic: `02b_rows` has arms 1 / 5 / 30 (opening-range minutes) × modes PRIMARY / ARMED / BYPASS; name the arm matching the live opening range and mode PRIMARY. Not needed for the primary statistic below, only for the R secondaries.
- **Primary statistic (winner tail, not median):** share of entered events that become big winners, **using the winner study's own big-winner definition** (copied verbatim into the freeze commit; if it is not a single R threshold, use realised R ≥ +5R). critic: it is known now — the `big_winner` column in `02b_events.tsv.gz` = highest close over sessions E..E+60 ≥ 1.5 × open(E) (`design/prereg_draft.md` line 102), 554 of 4,665 events (11.9%). It is price-based, so the "else +5R" fallback must be deleted at freeze — it is an unneeded fork. Decide at freeze whether the denominator is all events or `entered` events, and use one.
- critic: **the event list contains inverse, leveraged and volatility funds** (SQQQ, UVXY, VIXY, VXX, SPXU, FAZ, YANG, TECS, FNGD, SARK, SCO among others). They gap up and win precisely in selloffs, biasing the Draining winner share the wrong way. Exclude non-common-stock using `cb702_sic.psv` (last column `CS`), or report both — decided at freeze. The same filter applies to A3's universe, which today screens on price and dollar volume only.
- **Comparison:** Draining vs (Neutral + Easing).
- **Pass bar — all must hold:**
  1. Draining big-winner share is lower by **≥ one-third relative** (e.g. 9% vs 6%; critic: on the real 11.9% base rate, about 12% vs 8%).
   - critic: **power** — detecting 12% vs 8% at 95% / 80% power needs roughly 450-500 Draining events against the larger rest (≈ 900 only if the arms were equal), *before* the month clustering widens the interval. If Draining holds 10-20% of events (≈ 450-900), power is borderline and clustering decides; add, frozen now: Draining with fewer than 40 big winners → "cannot tell".
  2. 95% interval from a **calendar-month block bootstrap** (10,000 resamples) excludes zero — resampling months, not events, because events cluster.
  3. **Same sign in era A and era B.**
  4. **Adds to what we already have:** the gap survives within SPY above / below its 50-day average (critic: "survives" = same sign and at least half the pooled relative gap in **both** strata; define this way in the freeze commit) (our local breadth-like stratifier; the prod regime table is not available pre-2021 locally).
  5. **Beats the placebo:** a state built from SPY's own trend (SPY below 50-day and 50-day slope down) with the same day count. If the placebo splits outcomes as much, liquidity adds nothing.
  6. Survives the realised-volatility control (SPY 126-day realised volatility, top tercile vs rest).
- **Secondary (reported, not judged):** mean R, median R, fill rate, the Easing-only cut, the IEF variant, JNK (2019 on).

### Step 2 — Breakout test
- **Data:** `~/apollo_data/qm_breakouts_1102/` features (era A, era B) — read the schema with `~/apollo_data/venvs` (pyarrow). Reuse the harness of `scripts/probes/_702_race_1022/03_market_trend_split.py` and its outcome column; add the liquidity state as one more split column.
- critic: **the data line above is wrong.** That harness reads trades, not the `qm_breakouts_1102` parquet: `~/apollo_data/cb702_pre/out/trades_pre_exitpb.tsv.gz` (D 2017-03-01 → 2021-12-31) and `~/apollo_data/cb702/out/trades_discovery_exitpb.tsv.gz` (D 2022-03-31 → 2025-01-30; cut at 2024-12-31), filtered to arm `pp`, entry `orh5`, K `tl`, C0 = 1, mature = 1, outcome `realized_r`, bar **≥ 10R**. Its D is already the night before the trade, so join the state on D with no further shift. pyarrow is in the system `python3` (24.0.0), not in `~/apollo_data/venvs` (only `ocr`, `ytv`, neither has it). Era A starts 2017-03, and 2022-01 → 2022-03 is missing.
- Same primary statistic family (share of trades reaching the big-winner bar used in that harness), same six-part bar.

### Step 3 — second state (market illiquidity, A3)
- Same tests, illiquid vs normal. Judged separately; it is the academic question, not Caruso's.

### What each result means (stated now)
- critic: **any pass is discovery-grade** (EP-study outcomes by year already seen; confirmable only on 2025-26 when the seal lifts) — label it that way on the tile.
- **Pass on EP and breakout:** show the tile; bring a CHANGE_PROCESS proposal to the operator *only if he asks* — use for entries or sizing stays his call.
- **Pass on one only:** show as context, labelled for the setup where it held.
- **Fail (any of bars 1-6 — critic: the bar has six parts; "1-5" left the volatility control unjudged) or "cannot tell":** **do not show the state** — it would add a word with no meaning beside breadth. Keep storing the HY spread snapshot; re-run once the 2025-26 seal lifts.
- **Placebo matches:** liquidity is breadth by another name; drop it.

Cost: one Sonnet card (build + run), $0 data, no paid evals.

---

## 6. Data gaps and costs

| Gap | Fix | Cost |
|---|---|---|
| Local closes are raw (not dividend-adjusted) | rebuild total return from issuer distributions | $0 |
| No FRED client or key | thin client + free FRED API key | $0 |
| HY spread history on FRED = 3 years only; licensed, no redistribution | daily snapshot from now; BAA10Y as long free substitute | $0 |
| JNK only from 2019-05 locally | use HYG for 2016-24 | $0 |
| No pre-2021 VIX locally | use SPY realised volatility as the control | $0 |
| HYG/JNK/IEI in prod `mi_daily_closes` unconfirmed | check prod; add to collector if missing | $0 |
| critic: no rate/yield or funding leg tested | T10Y2Y, DFII10, STLFSI4 from FRED; TIP/IEF, TLT/SHY, FXY local — as secondaries | $0 |
| critic: Caruso video transcript | `~/apollo_data/venvs/ytv` exists (likely the YouTube transcript tool) — try it before any paid route | $0 |
| Caruso's actual framework unknown | video transcript + weekend report | $0 (transcript) / subscription unknown |
| Howell global liquidity | CrossBorder subscription | unknown (institutional) |
| MOVE index, Goldman FCI, real-time fed funds futures | paid licences; free proxies used instead | not needed |
| 2025-26 (the current episode) | sealed; watch live only | — |

---

## 7. What this does not answer

- **Whether the 11-22 selloff is a liquidity event** — 2025-26 is sealed; the live tile will show it going forward, but no backtest covers it.
- **Caruso's real rule** — his thresholds and actions are unread; this is not a replica of his read.
- **Timing a market bottom or a Fed pivot** — the evidence says pivots are not reliable bottoms; nothing here calls one.
- **Whether liquidity should gate entries or change sizing** — THE LINE; operator-only, CHANGE_PROCESS, backtest.
- **Rebound-crash risk after a selloff** (Daniel-Moskowitz) — a volatility question, carried as a control, not answered.
- **Exit rules** — this tests entry-day context only; exit questions go to the periodic trade review (#720).
- **The current bear regime (Nov 2026)** — a 2016-24 result is a baseline, not a verdict on today's market.

### Sources (by lane)
Practitioners: x.com/Trader_mcaruso (status 2122449884896985100, 2066628060380635460, 1893735010491916798); youtu.be/fdH9aFki8_U; capitalwars.substack.com (global liquidity cycle; 5-6 year re-fi cycle; think correctly about liquidity); rogermontgomery.com (Howell 2026 outlook); advisorperspectives.com/articles/2022/08/17; cryptoslate.com net-liquidity report; gist.github.com/dharmatech/c2dc1154167f3d1aed003aba7628a41e; retailtradersrepository.substack.com (Qullamaggie stream 91-95 review); sakatas.substack.com (situational awareness).
Credit: fred.stlouisfed.org/series/BAMLH0A0HYM2; eco3min.fr HY spread dataset; livewiremarkets.com credit warning; nber.org/papers/w17021 (Gilchrist-Zakrajsek); investing.com credit-spread analyses; thinkadvisor.com 2015-08-24; benzinga 2016 divergences; content.cmtassociation.org credit conditions part 2; invezz.com 2026-04-10 loan outflows; ssga.com private-credit dispersion.
Fed/money: fred WALCL, RRPONTSYD; chicagofed.org NFCI; federalreserve.gov FEDS 2013-39; Brookings BPEA FA22 (Ludvigson); Graduate Institute HEIDWP14-2024; nber w24687; fisherinvestments.com balance-sheet note.
Internals: Avramov et al. (en-coller.tau.ac.il); qub.ac.uk working paper; e-space.mmu.ac.uk momentum crashes (Butt-Virk); Sadka 2003 (nber); Asness-Moskowitz-Pedersen (stern.nyu.edu); Deuskar-Kumar-Poland margin credit (stern.nyu.edu); bauer.uh.edu Johnson 2011; mdpi.com/1911-8074/12/3/113; renaissancecapital.com reviews; Ritter IPO statistics.
Evidence: nber w20439 (Daniel-Moskowitz); federalreserve.gov FEDS Notes 2019-12-13 and 2016-04-08; academic.oup.com/rfs/article/21/4/1455 (Welch-Goyal); alphaarchitect.com avoiding momentum crashes.
