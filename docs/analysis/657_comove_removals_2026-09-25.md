# #657 — Should the tape decide REMOVALS too? Co-movement as an eviction rule (2026-09-25)

**Owner**: `docs/architecture/theme_engine.md` (membership test, change log 2026-09-13). This is a
finding, not an owner. It answers the task he filed when he ruled the cross-sector swap on
2026-09-13: *"swap job 1 and leave job 2, but file task to look into 2nd part and eval/analysis"*.

**Reproduce** ($0, read-only pull + offline replay through the LIVE functions):

```
bash scripts/probes/_657_pull.sh scripts/probes/_657_out        # eight CSVs, COPY … TO STDOUT (read-only)
python scripts/probes/_657_comove_removals.py scripts/probes/_657_out   # writes results.md + the psv files
```

**The decision it serves**: whether the co-movement test that now decides ADMISSION
(`ASSIGN_COMOVE_BAR = 0.35`, job 1, merged `b22e9ff3`) should also decide REMOVAL (job 2: the birth
strip `_strip_sector_outliers` and the nightly carry-forward strip
`_apply_carryforward_deterministic_filter`, both left on the sector label). His framing of the
hard case, HOOD: *"the theme of wealth management is only partially correct, Hood also moves with
crypto sometimes, and long with the market during high speculative times"* — a membership can be
partially correct, so the options are **evict**, **down-weight**, or **leave**, not only evict.

⚖ **THE LINE**: a removal rule is a detection criterion. Nothing here flips anything — no toggle,
no context passed, no table touched; the removal sites run exactly what they ran yesterday. Any
change goes through `docs/setups/CHANGE_PROCESS.md` and his sign-off.

---

## Method and population

Written before the numbers were run (the probe was executed after this section was committed to
disk); no window, bar, seed or cut-line below was changed after seeing a result.

**Data** (one read-only pull, 2026-09-25 06:41 PDT, parked and reused — nothing re-pulled):
`mi_themes` rows 2026-06-01 → 2026-09-24 (every stage incl. Retired tombstones);
`mi_daily_closes` 2026-04-01 → 2026-09-24 for every ticker that sat in any theme since 06-01 plus
SPY (the table is split-adjusted as of 2026-09-24); `mi_audit_log` since 06-01 for the
assignment / discovery / promotion / validation / strip / rename event types; `mi_validation_cooldowns`
(incl. every operator-bypassed pair); `mi_theme_exclusions`; `mi_theme_renames`; the sector label
per ticker (latest `mi_stock_scores` row within 130 days, `mi_ticker_overrides` filling gaps —
the scores row wins, as the engine's `stocks_by_ticker` does).

**A board as of a date D** = the 7-day mirror of `get_active_themes(stale_after_days=7)`: the
latest `mi_themes` row per name with `theme_date` in (D−7, D], Retired dropped. A membership is
one (ticker, theme) pair on that board.

**The judge** is the engine's own: `theme_engine._comove_verdict(ticker, members, ctx)` on a
`ComoveContext` built with the same `market_adjusted_correlation` primitives `_load_comove_context`
calls (`session_index` → `log_returns` → `excess_returns`), SPY-subtracted, over the 60 sessions
STRICTLY before the context date, leave-one-out against the equal-weight basket of the theme's
other members, ≥ 3 basket members with history, ≥ 30 overlapping sessions. Not re-implemented.
The bar is read from the code (`ASSIGN_COMOVE_BAR`). "Judgeable" = the verdict is not `None`;
an unjudgeable membership (thin basket / no history) is reported, never counted as an eviction —
the engine's own fail direction.

**Population 1 — today's board.** D = 2026-09-24 (the latest theme date and the latest close),
context date 2026-09-25 → the 60 sessions 2026-06-30 … 2026-09-24. Every membership judged in a
SINGLE pass against the FULL current basket (a nightly rule would iterate and cascade in small
themes; that cascade is not simulated, only the first pass is). n stated in the results.

**Two shapes of "job 2 on the tape"** — measured separately because they are different rules:
- **Shape A — as built.** Passing `comove_ctx` to the two strip sites re-judges only a
  SINGLETON-sector member (the only member the sector test touches): kept at ≥ 0.35, stripped
  below, stripped when unjudgeable. It can never evict a same-sector member, so it strips at
  most what today's label strips. Reported: singleton-sector members on today's board kept /
  stripped / unjudgeable under the context.
- **Shape B — the full tape.** Every judgeable membership below the bar is evicted, sector
  ignored. This is the DoD's eviction list. The 09-13 doc's "95 of 504" was ASSIGNMENT-night
  pairs judged against the PRIOR night's basket, not a board count; the bridge (which of those
  pairs are memberships today and what they read now) is reported so the two numbers are not
  left side by side.

**Per eviction** (Shape B): ticker, theme, stage, reading, overlap, basket size, sector label,
whether it is a singleton-sector member (the label would strip it tomorrow), Unknown-sector,
the join path, whether the membership LLM passed it, whether the operator placed or confirmed
it, whether the theme is a PAYING stage (Accelerating / Mainstream — a LISTED member gets the
EP +10 regardless of co-movement, `ep_theme_belonging` stage 1), and whether the pair is one of
the 09-13 backtest's 95.

- **Join path** = the first audit event since 06-01 naming the pair, following the theme's rename
  lineage (`mi_theme_renames` + `theme_renamed_*` events): `assignment_llm_proposed` (the
  assignment LLM, then the immediate post-assignment validation), `theme_discovered` (the
  discovery LLM, then birth validation #266), `shadow_themes_promoted` (a Lane-2 cohort),
  `theme_operator_promoted` (his hand). "Unknown" when no event names the pair.
  ⚠ Amended after the first run, and stated as such: that run left 19 of 52 joins untraceable, so
  the merge-machinery event types (`theme_pass1_5_absorption`, `theme_auto_retired` successor
  pointers, `theme_birth_gate` joins, `theme_thesis_merged` / `theme_merge_parent_child`) were
  pulled the same day (read-only, `events_extra.csv`) and a "merge:*" path added — an edge
  source → target on the join date whose target is this theme and whose source held the ticker
  on its prior row, or ("merge:unlogged") the ticker sat in a theme the session before that was
  Retired at the join. This changed provenance LABELS only; no population, window, bar, seed or
  verdict moved.
- **Passed the membership LLM** = the pair sat on the board across ≥ 1 Mon/Wed/Fri run date after
  its join date without a `ticker_revalidated_out` row (the rescore validator runs every
  Mon/Wed/Fri on every theme with ≥ 2 members). ⚠ Survival is not always an LLM yes: the
  mass-eviction skip (#214, ≥ 3 flagged AND ≥ 50 %) and the min-survivor guard
  (`PRUNE_MIN_TICKERS`) both keep a flagged member; that is stated as a caveat, not corrected for.
- **Operator placed / confirmed** = the ticker is in a `theme_operator_promoted` event's ticker
  list for that theme, or the pair is an operator-bypassed cooldown (`get_operator_protected_set`).

**What happened afterwards — out of sample, NOT returns.** Two windows, both derived, not picked:
- **W1 (the 09-13 backtest's board).** Board as of 2026-09-11; in-sample verdict on the 60
  sessions to 09-11 (context date 09-12); out-of-sample co-movement over the sessions AFTER
  09-11 through 09-24 — 9 returns (09-14 … 09-24). Basket frozen at the 09-11 members.
- **W2 (engine-grade).** T = the first close of `session_index(SPY, 2026-09-25, 30)` =
  **2026-08-12**, so exactly 30 returns follow it through 09-24 — the engine's own minimum
  overlap. Board as of 08-12; in-sample verdict on the 60 sessions to 08-12 (context date
  08-13); out-of-sample = the 30 returns after 08-12. Basket frozen at the 08-12 members.
- The out-of-sample reading uses the same maths (`mac.build_baskets` + `mac.correlate`,
  leave-one-out) with `min_overlap` set to the window length (9 / 30) and `min_members` = 3 —
  a declared override of the 30-session default, because W1 is shorter than it. A member
  missing a close inside the window is "unjudgeable OOS" and counted.
- **What is read**: the GROUP contrast. Mean out-of-sample co-movement and the share below 0.35
  for the would-be-evicted memberships vs the kept ones (n each), plus the Spearman rank
  correlation between in-sample and out-of-sample readings over every judgeable membership.
  The kept group is the noise baseline — on 9 sessions the standard error of a Pearson r near
  0.3 is ≈ 0.34, so W1 gives no per-name verdict; only W2 (30 sessions, SE ≈ 0.17) is read
  per name, and only as "stayed below / rose above the bar", both directions, with n.
- A price path (median market-adjusted return of the evicted names vs their theme baskets over
  the window) is shown ONCE, as context; it is not a verdict (operator: themes are not judged on
  returns yet).

**Tightness before / after with the matched random control.** No engine-level tightness metric
exists (`grep` of `agents/` finds none); the metric is the one the 09-13 doc used —
**tightness = mean leave-one-out co-movement of each member with the rest**, via
`_comove_verdict`, over members the tape can judge, defined when ≥ 3 such members remain.
- For each theme with ≥ 1 eviction: before = the members as they stand; after = minus the
  evictions; control = remove the SAME NUMBER of members chosen at random from the theme's
  judgeable members, 300 draws, `numpy.random.default_rng(20260925)`. Reported: before, after,
  control mean, and the share of draws whose tightness ≥ the tape's.
- ⚠ In-sample this is biased by construction — removing the lowest-scoring members raises the
  mean of what is left — so the in-sample table is a floor, not evidence. **The reading that
  counts is out of sample**: evictions selected on the in-sample window (W1 / W2), tightness
  change measured on that window's OOS sessions, against the random-removal control measured
  on the same OOS sessions.

**What the system already does** (before any of this is called a gap): the count of evictions
that are singleton-sector members (the carry-forward filter strips those anyway), Unknown-sector
(the label never touches them), and the churn the split ruling itself creates — pairs the tape
admitted OVER the label since 09-13 (`assignment_comove_admitted_over_sector`) that the label
then stripped as `sector_outlier` within 7 days.

**Consequences counted**: themes Shape B pushes under 3 members (the P2 starvation direction, in
reverse); evictions inside paying-stage themes (the +10 exposure); HOOD's reading against its
wealth-management theme and against every crypto-named basket on the board (descriptive — the
code comment is explicit that 0.35 is a per-pair bar, not a best-of-many one).

**Fixed before running**: bar = `ASSIGN_COMOVE_BAR` (0.35, read from code); lookback = 60
sessions; W1 / W2 as derived above; control draws = 300; seed = 20260925; single-pass
judgement; 7-day board mirror. None was revisited.

---

## Results

**Headline (every number below is repeated with its n in the tables):**
- **Today's board**: 704 memberships, 608 judgeable; the full tape rule (Shape B) evicts **52 of 608 (9%)** across 22 of 109 themes. 50 of 52 had passed the membership LLM at least once; **0 of 52** were placed or confirmed by the operator; **18 of 52 sit in a paying theme** and carry the EP +10 through the LISTED shortcut today.
- **How they got in**: 27 of 52 were judged by an LLM at join (assignment); **16 of 52 arrived through the merge machinery** (thesis merges, absorptions, successor pointers) — no LLM judged the pair at join, e.g. SR and ATO, two gas utilities, moved into *Crude & Product Tanker Shipping* (Mainstream) on 09-24 and read 0.10 / 0.27.
- **Out of sample, 30 sessions (W2, n = 25)**: **11 of 25** names the tape would have evicted kept failing to move with their theme (the tape was right); **14 of 25** started moving with it (the tape was early or wrong). The kept names read below the bar 24 of 307 times (8%) — the evicted group is 5.5× more likely not to co-move, but a single reading is wrong more often than right per name.
- **Tightness, out of sample, vs the matched random control**: evicting the tape's names tightened the changed themes by about +0.04 more than removing the same number of random members (W1: 0.59 → 0.63 vs 0.58 random, 15 themes; W2: 0.60 → 0.63 vs 0.59, 6 themes); it beat 95% of random draws in 3 of 15 (W1) and 0 of 6 (W2) themes. Small, positive, not decisive.
- **What the system already does**: only **1 of 52** evictions is a singleton-sector member (the label strips it anyway) — 51 of 52 are reachable ONLY by the full tape rule. **Shape A (as built)** would strip nothing the label does not already strip (1 of 8 singletons today) and would KEEP 7 of 8. Meanwhile the split ruling has created a loop: **16 of 21** cross-sector pairs the tape admitted since 09-13 were stripped by the label within days, **9 of 21** re-admitted two or more times.
- **HOOD**: 0.31 with *Wealth Management & Retail Brokerage Platforms* (its theme; below the bar) and **0.65–0.74 with three bitcoin baskets** it is not in — his "partially correct" in numbers.

**Verification that the offline judge is the live one**: the 09-24 nightly run's own audit rows were replayed through the same context — PUBM 0.583 (basket 4), VSXY 0.345 (9), BAND 0.1384 (4), VSAT 0.448 (3) reproduce to four decimals; the remaining rows differ only by that night's basket composition (a strip or an earlier admit) or name a ticker outside the members-only closes pull. Same maths, same closes.

### 1. Population — today's board

| population | n |
|---|---|
| themes on the 2026-09-24 board (7-day mirror of get_active_themes, Retired dropped) | 109 |
| memberships (ticker, theme) | 704 |
| … judgeable by the tape (≥3 basket members with history, ≥30 overlapping sessions) | 608 (86% of 704) |
| … NOT judgeable → the sector test keeps deciding (fail-safe) | 96 {'unjudgeable:thin_basket': 96} |
| themes the rule cannot touch at all (every member unjudgeable — a 3-member theme leaves a 2-name basket after leave-one-out) | 36 of 109 (every theme with an unjudgeable member: 36) |
| **Shape B evictions: judgeable memberships below 0.35** | **52 of 608 (9%)** |
| themes with ≥1 eviction | 22 of 109 |
| themes an eviction pass would leave under 3 members | 2 of 22 changed themes |
| themes it would leave under PRUNE_MIN_TICKERS=2 (retired next pass) | 1 of 22 |
| evictions inside a PAYING theme (Accelerating/Mainstream — a LISTED member gets the EP +10 regardless of co-movement) | 18 of 52 (18 distinct stocks) |

### Provenance of the evictions (each n is of the eviction list)

| join path (first audit event naming the pair, rename lineage followed) | n |
|---|---|
| assignment_llm | 27 of 52 |
| merge:unlogged | 15 of 52 |
| shadow_promoted | 5 of 52 |
| unknown | 4 of 52 |
| merge:merge_pass_successor | 1 of 52 |

| how the pair got onto the board | n |
|---|---|
| an LLM judged THIS pair at join (assignment proposal + immediate validation, discovery/split + birth validation) | 27 of 52 |
| the MERGE MACHINERY moved it in (thesis merge / Pass 1.5 absorption / sub-theme merge / merge-pass successor / birth-gate join) — no LLM judged the pair at join | 16 of 52 |
| a Lane-2 shadow cohort was promoted whole | 5 of 52 |
| untraceable | 4 of 52 |

| membership-LLM / operator flags | n |
|---|---|
| passed the membership LLM at least once (validated at join, or survived ≥1 Mon/Wed/Fri rescore) | 50 of 52 (96%) |
| … validated at join (assignment / discovery / split path) | 27 of 52 |
| … survived ≥1 Mon/Wed/Fri rescore after joining | 50 of 52 |
| … survived ≥3 rescores | 48 of 52 |
| operator placed or confirmed (operator-promoted theme ticker, or bypassed cooldown) | 0 of 52 |
| one of the 09-13 backtest's 95 assignment-night pairs | 16 of 52 |
| median days on the board (join → 2026-09-24) | 16 |

### What the strips the engine ALREADY runs would do with the same names

| overlap check | n |
|---|---|
| evictions that are SINGLETON-sector members (the carry-forward label strip removes these tomorrow anyway) | 1 of 52 |
| evictions with an Unknown sector (the label never touches them) | 0 of 52 |
| evictions the label leaves alone (same-sector, known) — reachable ONLY by Shape B | 51 of 52 |

### Shape A — as built (`comove_ctx` passed to the two strip sites): singleton-sector members only

| singleton-sector members on today's board | n |
|---|---|
| singleton-sector members (what the label strips tonight without the context) | 8 of 704 memberships |
| … the tape would KEEP (≥ 0.35) | 7 of 8 |
| … the tape would STRIP (< 0.35) — the label strips these too | 1 of 8 |
| … unjudgeable → stripped by the label as before | 0 of 8 |

| stock | theme | stage | sector | reading | tape says |
|---|---|---|---|---|---|
| OKLO | Small Modular Reactor & Advanced Nuclear Fission Techno | Nascent | Utilities | 0.90 | admit |
| LEU | Small Modular Reactor & Advanced Nuclear Fission Techno | Nascent | Energy | 0.84 | admit |
| MAS | Home Improvement Retail & Building Products | Nascent | Industrials | 0.68 | admit |
| PUBM | Digital Advertising & Ad-Tech Monetization Platforms | Mainstream | Technology | 0.66 | admit |
| TNET | Enterprise HR & Workforce Management SaaS | Mainstream | Industrials | 0.61 | admit |
| VSAT | Space Economy: Satellite Communications & Launch Servic | Mainstream | Technology | 0.49 | admit |
| WLTH | Wealth Management & Retail Brokerage Platforms | Mainstream | Technology | 0.40 | admit |
| AGRO | Global Agriculture Value Chain Recovery | Mainstream | Consumer Defensive | 0.09 | reject |

### The churn the split ruling creates (job 1 admits on the tape, job 2 strips on the label)

| since 2026-09-13 | n |
|---|---|
| pairs the tape admitted OVER the sector label (`assignment_comove_admitted_over_sector`) | 21 distinct pairs (33 events) |
| … stripped again by the label as `sector_outlier` within 7 days | 16 of 21 |
| … re-admitted over the label ≥2 times (the loop) | 9 of 21 |

| night | stock | theme | admitted at | stripped by label after (days) | times admitted |
|---|---|---|---|---|---|
| 2026-09-15 | BAH | Defense Intelligence & Cybersecurity IT Contractor | 0.73 | 1 | 3 |
| 2026-09-17 | BAH | Defense Intelligence & Cybersecurity IT Contractor | 0.69 | 1 | 3 |
| 2026-09-21 | BAH | Defense Intelligence & Cybersecurity IT Contractor | 0.74 | — | 3 |
| 2026-09-23 | BLSH | Bitcoin Holding & Trading Proxy Equities | 0.67 | 1 | 1 |
| 2026-09-18 | BTDR | Bitcoin Mining Stocks Rotation Reversal | 0.78 | 3 | 2 |
| 2026-09-22 | BTDR | Bitcoin Mining Stocks Rotation Reversal | 0.81 | — | 2 |
| 2026-09-16 | BTU | Metallurgical & Thermal Coal Mining Rebound | 0.72 | 1 | 1 |
| 2026-09-21 | BXC | Homebuilders & Residential Construction Supply Cha | 0.37 | 1 | 1 |
| 2026-09-22 | CCS | Homebuilders & Residential Construction Supply Cha | 0.76 | 1 | 1 |
| 2026-09-16 | ECO | Crude & Product Tanker Shipping | 0.80 | — | 1 |
| 2026-09-23 | ENSG | Skilled Nursing & Senior Housing Healthcare REITs | 0.60 | 1 | 1 |
| 2026-09-18 | GOLD | Gold & Precious Metals Miners Rotation | 0.53 | — | 1 |
| 2026-09-22 | GOLD | Precious Metals Complex Rebound | 0.54 | — | 1 |
| 2026-09-15 | GPN | B2B Digital Financial Infrastructure & Payment Rai | 0.75 | 1 | 1 |
| 2026-09-16 | IRDM | Space Economy: Satellite Communications & Launch S | 0.43 | 1 | 3 |
| 2026-09-18 | IRDM | Space Economy: Satellite Communications & Launch S | 0.40 | 3 | 3 |
| 2026-09-22 | IRDM | Space Economy: Satellite Communications & Launch S | 0.41 | 1 | 3 |
| 2026-09-21 | MLAB | Life Science Tools & Analytical Instruments | 0.66 | 1 | 2 |
| 2026-09-23 | MLAB | Life Science Tools & Analytical Instruments | 0.64 | 1 | 2 |
| 2026-09-15 | MSTR | Bitcoin Treasury & Crypto Proxy Equities Correlati | 0.78 | 1 | 2 |
| 2026-09-23 | MSTR | Corporate Digital Asset Treasury Vehicles | 0.87 | 1 | 2 |
| 2026-09-23 | NBIS | Emerging AI Compute & Cloud Infrastructure Platfor | 0.73 | 1 | 1 |
| 2026-09-24 | PUBM | Digital Advertising & Ad-Tech Monetization Platfor | 0.58 | — | 1 |
| 2026-09-22 | TNET | Enterprise HR & Workforce Management SaaS | 0.64 | 1 | 2 |
| 2026-09-24 | TNET | Enterprise HR & Workforce Management SaaS | 0.62 | — | 2 |
| 2026-09-18 | UMAC | Space Economy: Satellite Communications & Launch S | 0.64 | — | 1 |
| 2026-09-21 | VICR | On-Site Power Generation & Distribution Equipment  | 0.64 | 1 | 2 |
| 2026-09-23 | VICR | On-Site Power Generation & Distribution Equipment  | 0.62 | 1 | 2 |
| 2026-09-17 | VSAT | Space Economy: Satellite Communications & Launch S | 0.52 | 1 | 3 |
| 2026-09-21 | VSAT | Space Economy: Satellite Communications & Launch S | 0.47 | 1 | 3 |
| 2026-09-24 | VSAT | Space Economy: Satellite Communications & Launch S | 0.45 | — | 3 |
| 2026-09-18 | WLTH | Wealth Management & Retail Brokerage Platforms | 0.36 | 3 | 2 |
| 2026-09-24 | WLTH | Wealth Management & Retail Brokerage Platforms | 0.41 | — | 2 |

### 2. The eviction list (Shape B, today's board)

Every judgeable membership below 0.35. LLM = passed the membership LLM at least once; op = operator placed/confirmed; single = singleton-sector (the label strips it anyway); pay = paying-stage theme; bt95 = in the 09-13 backtest's 95.

| stock | theme | stage | reading | basket | sector | joined | path | rescores | LLM | op | single | pay | bt95 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| HTFL | AI-Driven Diagnostics & Imaging Re-Rating | Mains | 0.12 | 8 | Healthcare | 2026-08-21 | merge:unlogged | 13 | y | — | — | y | — |
| CDNA | AI-Driven Diagnostics & Imaging Re-Rating | Mains | 0.15 | 8 | Healthcare | 2026-08-25 | assignment_llm | 12 | y | — | — | y | y |
| DGX | AI-Driven Diagnostics & Imaging Re-Rating | Mains | 0.28 | 8 | Healthcare | 2026-09-03 | assignment_llm | 8 | y | — | — | y | y |
| LH | AI-Driven Diagnostics & Imaging Re-Rating | Mains | 0.29 | 8 | Healthcare | 2026-09-03 | assignment_llm | 8 | y | — | — | y | y |
| ORCL | AI-Powered Enterprise Analytics & Intelligent Wo | Fadin | -0.14 | 17 | Technology | 2026-09-08 | assignment_llm | 7 | y | — | — | — | y |
| MSFT | AI-Powered Enterprise Analytics & Intelligent Wo | Fadin | 0.19 | 17 | Technology | 2026-09-01 | assignment_llm | 9 | y | — | — | — | y |
| DB | Bank Stocks: Rising-Rate NIM Expansion | Fadin | 0.22 | 44 | Financial Serv | 2026-09-14 | merge:unlogged | 4 | y | — | — | — | — |
| BCS | Bank Stocks: Rising-Rate NIM Expansion | Fadin | 0.24 | 44 | Financial Serv | 2026-09-14 | merge:unlogged | 4 | y | — | — | — | — |
| MFG | Bank Stocks: Rising-Rate NIM Expansion | Fadin | 0.24 | 44 | Financial Serv | 2026-09-17 | assignment_llm | 3 | y | — | — | — | — |
| BBVA | Bank Stocks: Rising-Rate NIM Expansion | Fadin | 0.25 | 44 | Financial Serv | 2026-09-14 | merge:unlogged | 4 | y | — | — | — | — |
| SAN | Bank Stocks: Rising-Rate NIM Expansion | Fadin | 0.28 | 44 | Financial Serv | 2026-09-14 | merge:unlogged | 4 | y | — | — | — | — |
| C | Bank Stocks: Rising-Rate NIM Expansion | Fadin | 0.31 | 44 | Financial Serv | 2026-09-16 | assignment_llm | 3 | y | — | — | — | — |
| LYG | Bank Stocks: Rising-Rate NIM Expansion | Fadin | 0.34 | 44 | Financial Serv | 2026-09-14 | merge:unlogged | 4 | y | — | — | — | — |
| IOND | Bitcoin Mining Stocks Rotation Reversal | Mains | 0.18 | 9 | Financial Serv | 2026-09-11 | shadow_promoted | 5 | y | — | — | y | — |
| APLD | Cloud Data Storage & Analytics Infrastructure | Mains | -0.18 | 3 | Technology | 2026-09-17 | merge:unlogged | 3 | y | — | — | y | — |
| ESTC | Cloud Data Storage & Analytics Infrastructure | Mains | 0.26 | 3 | Technology | 2026-08-13 | assignment_llm | 17 | y | — | — | y | — |
| ARHS | Commercial, Office & Home Furniture Retailers an | Fadin | 0.33 | 4 | Consumer Cycli | 2026-08-18 | assignment_llm | 15 | y | — | — | — | — |
| SR | Crude & Product Tanker Shipping | Mains | 0.10 | 12 | Utilities | 2026-09-24 | merge:unlogged | 0 | n | — | — | y | — |
| ATO | Crude & Product Tanker Shipping | Mains | 0.27 | 12 | Utilities | 2026-09-24 | merge:unlogged | 0 | n | — | — | y | — |
| EMBJ | Defense Electronics & Aerospace Subsystem Suppli | Mains | 0.09 | 8 | Industrials | 2026-08-11 | unknown | 18 | y | — | — | y | — |
| RTX | Defense Electronics & Aerospace Subsystem Suppli | Mains | 0.16 | 8 | Industrials | 2026-08-11 | unknown | 18 | y | — | — | y | — |
| EFOR | Defense Intelligence & Cybersecurity IT Contract | Mains | 0.19 | 6 | Technology | 2026-08-19 | shadow_promoted | 14 | y | — | — | y | — |
| VVX | Defense Intelligence & Cybersecurity IT Contract | Mains | 0.34 | 6 | Industrials | 2026-09-21 | assignment_llm | 1 | y | — | — | y | — |
| TBBB | Defensive Consumer Staples Rotation | Fadin | 0.19 | 16 | Consumer Defen | 2026-08-28 | assignment_llm | 10 | y | — | — | — | y |
| GO | Defensive Consumer Staples Rotation | Fadin | 0.32 | 16 | Consumer Defen | 2026-08-25 | assignment_llm | 12 | y | — | — | — | — |
| MGNI | Digital Advertising & Ad-Tech Monetization Platf | Mains | 0.26 | 3 | Communication  | 2026-09-14 | assignment_llm | 4 | y | — | — | y | — |
| HNRG | Diversified Power Generation Capacity Expansion  | Fadin | 0.17 | 4 | Utilities | 2026-09-08 | shadow_promoted | 7 | y | — | — | — | — |
| AES | Diversified Power Generation Capacity Expansion  | Fadin | 0.20 | 4 | Utilities | 2026-09-16 | assignment_llm | 3 | y | — | — | — | — |
| EVRG | Diversified Power Generation Capacity Expansion  | Fadin | 0.28 | 4 | Utilities | 2026-09-15 | unknown | 4 | y | — | — | — | — |
| OGE | Diversified Power Generation Capacity Expansion  | Fadin | 0.33 | 4 | Utilities | 2026-09-08 | shadow_promoted | 7 | y | — | — | — | — |
| FTK | Energy Infrastructure & Services Complex | Fadin | 0.01 | 15 | Energy | 2026-09-15 | merge:merge_pass_successor | 4 | y | — | — | — | — |
| WKC | Energy Infrastructure & Services Complex | Fadin | 0.12 | 15 | Energy | 2026-09-16 | assignment_llm | 3 | y | — | — | — | — |
| NTNX | Enterprise Server, Storage & Data Infrastructure | Nasce | -0.19 | 7 | Technology | 2026-08-17 | assignment_llm | 15 | y | — | — | — | y |
| ITUB | Fintech & Digital Finance Sector Re-rating on Fe | Fadin | 0.17 | 21 | Financial Serv | 2026-09-16 | merge:unlogged | 3 | y | — | — | — | — |
| XP | Fintech & Digital Finance Sector Re-rating on Fe | Fadin | 0.20 | 21 | Financial Serv | 2026-09-16 | merge:unlogged | 3 | y | — | — | — | — |
| CHYM | Fintech & Digital Finance Sector Re-rating on Fe | Fadin | 0.28 | 21 | Technology | 2026-09-16 | merge:unlogged | 3 | y | — | — | — | — |
| PGY | Fintech & Digital Finance Sector Re-rating on Fe | Fadin | 0.34 | 21 | Technology | 2026-09-16 | merge:unlogged | 3 | y | — | — | — | — |
| KSPI | Fintech & Digital Finance Sector Re-rating on Fe | Fadin | 0.34 | 21 | Technology | 2026-09-16 | merge:unlogged | 3 | y | — | — | — | — |
| QURE | Genetic Medicine: Gene Editing & Gene Therapy In | Fadin | 0.29 | 3 | Healthcare | 2026-09-02 | assignment_llm | 8 | y | — | — | — | y |
| AGRO | Global Agriculture Value Chain Recovery | Mains | 0.09 | 3 | Consumer Defen | 2026-09-02 | unknown | 8 | y | — | y | y | — |
| ACA | Industrial Construction Execution & On-Site Supp | Fadin | -0.16 | 7 | Industrials | 2026-09-09 | assignment_llm | 6 | y | — | — | — | y |
| TTEK | Industrial Construction Execution & On-Site Supp | Fadin | -0.12 | 7 | Industrials | 2026-08-21 | assignment_llm | 13 | y | — | — | — | y |
| J | Industrial Construction Execution & On-Site Supp | Fadin | -0.08 | 7 | Industrials | 2026-08-11 | assignment_llm | 18 | y | — | — | — | — |
| KBR | Industrial Construction Execution & On-Site Supp | Fadin | 0.12 | 7 | Industrials | 2026-08-20 | assignment_llm | 14 | y | — | — | — | y |
| AGX | Industrial Construction Execution & On-Site Supp | Fadin | 0.20 | 7 | Industrials | 2026-09-14 | assignment_llm | 4 | y | — | — | — | y |
| TRAX | Inflammatory Disease & Immunology Biologics | Fadin | 0.22 | 8 | Healthcare | 2026-09-08 | assignment_llm | 7 | y | — | — | — | y |
| AUPH | Inflammatory Disease & Immunology Biologics | Fadin | 0.30 | 8 | Healthcare | 2026-08-20 | assignment_llm | 14 | y | — | — | — | — |
| INSP | Medical Device Mean-Reversion & Rotation Recover | Fadin | 0.21 | 13 | Healthcare | 2026-07-20 | shadow_promoted | 27 | y | — | — | — | — |
| GKOS | Medical Device Mean-Reversion & Rotation Recover | Fadin | 0.31 | 13 | Healthcare | 2026-08-17 | assignment_llm | 15 | y | — | — | — | y |
| BLZE | Network Security & Zero-Trust Edge | Mains | 0.30 | 17 | Technology | 2026-09-22 | merge:unlogged | 1 | y | — | — | y | — |
| XP | Wealth Management & Retail Brokerage Platforms | Mains | 0.07 | 12 | Financial Serv | 2026-09-01 | assignment_llm | 9 | y | — | — | y | y |
| HOOD | Wealth Management & Retail Brokerage Platforms | Mains | 0.31 | 12 | Financial Serv | 2026-08-21 | assignment_llm | 13 | y | — | — | y | y |

### Bridge to the 09-13 backtest's "95 of 504"

- Those 95 were ASSIGNMENT-NIGHT pairs judged against the PRIOR night's basket. Parsed from the committed doc: 95 rows = 90 distinct pairs; **23 of 90 distinct pairs are memberships on today's board** (25 rows; the rest left the board or the theme retired); of those 23 pairs, 16 still read below 0.35 today, 3 now read above it, 4 unjudgeable today (the table lists rows, so HOOD and TRAX appear twice).

| stock | theme (09-13 doc) | 09-13 reading | today |
|---|---|---|---|
| CHKP | Network Security & Zero-Trust Edge | 0.27 | 0.46 admit |
| CVLT | Network Security & Zero-Trust Edge | 0.31 | 0.50 admit |
| IVZ | Wealth Management & Retail Brokerage Platforms | 0.25 | 0.63 admit |
| ACA | Industrial Construction Execution & On-Site Supply | 0.18 | -0.16 reject |
| AGX | Industrial Construction Execution & On-Site Supply | 0.09 | 0.20 reject |
| CDNA | AI-Driven Diagnostics & Imaging Re-Rating | 0.14 | 0.15 reject |
| DGX | AI-Driven Diagnostics & Imaging Re-Rating | 0.27 | 0.28 reject |
| GKOS | Medical Device Mean-Reversion & Rotation Recovery | 0.29 | 0.31 reject |
| HOOD | Wealth Management & Retail Brokerage Platforms | -0.01 | 0.31 reject |
| HOOD | Wealth Management & Retail Brokerage Platforms | 0.01 | 0.31 reject |
| KBR | Industrial Construction Execution & On-Site Supply | 0.10 | 0.12 reject |
| LH | AI-Driven Diagnostics & Imaging Re-Rating | 0.22 | 0.29 reject |
| MSFT | AI-Powered Enterprise Analytics & Intelligent Work | 0.30 | 0.19 reject |
| NTNX | Enterprise Server, Storage & Data Infrastructure H | 0.06 | -0.19 reject |
| ORCL | AI-Powered Enterprise Analytics & Intelligent Work | 0.04 | -0.14 reject |
| QURE | Genetic Medicine: Gene Editing & Gene Therapy Inno | 0.23 | 0.29 reject |
| TBBB | Defensive Consumer Staples Rotation | 0.33 | 0.19 reject |
| TRAX | Inflammatory Disease & Immunology Biologics | 0.21 | 0.22 reject |
| TRAX | Inflammatory Disease & Immunology Biologics | 0.15 | 0.22 reject |
| TTEK | Industrial Construction Execution & On-Site Supply | 0.19 | -0.12 reject |
| XP | Wealth Management & Retail Brokerage Platforms | 0.26 | 0.07 reject |
| BOX | Enterprise Unstructured Data Storage Infrastructur | -0.17 | n/a unjudgeable:thin_basket |
| CORT | Peptide & Hormone Therapies for Metabolic & Endocr | 0.25 | n/a unjudgeable:thin_basket |
| MMED | Diabetes Management Devices (CGM, Insulin Pumps &  | 0.32 | n/a unjudgeable:thin_basket |
| PRCH | Digital Insurance Distribution & InsurTech Platfor | 0.05 | n/a unjudgeable:thin_basket |

### HOOD — the "partially correct" case, today's readings (descriptive; 0.35 is a per-pair bar, not best-of-many)

| theme | stage | HOOD is a member | reading | tape |
|---|---|---|---|---|
| Bitcoin Balance Sheet Proxies | Nascent | no | 0.74 | comoves |
| Bitcoin Holding & Trading Proxy Equities | Mainstream | no | 0.65 | comoves |
| Bitcoin Treasury & Crypto Proxy Equities Correlation Basket | Mainstream | no | 0.65 | comoves |
| Wealth Management & Retail Brokerage Platforms | Mainstream | yes | 0.31 | below_bar |
| Bitcoin Mining Stocks Rotation Reversal | Mainstream | no | 0.27 | below_bar |

### 3. What happened afterwards — OUT OF SAMPLE co-movement (not returns)

### W1 — the 09-13 backtest's board: board 2026-09-11 (119 themes, 718 memberships, 592 judgeable), in-sample = 60 sessions to 2026-09-11, out-of-sample = 9 returns 2026-09-14 … 2026-09-24

| group (in-sample verdict) | n | OOS judgeable | mean OOS co-movement | median | share < 0.35 OOS | share ≥ 0.35 OOS |
|---|---|---|---|---|---|---|
| would be EVICTED (in-sample < 0.35) | 60 | 58 | 0.30 | 0.36 | 29 of 58 (50%) | 29 of 58 (50%) |
| KEPT (in-sample ≥ 0.35) | 532 | 527 | 0.73 | 0.80 | 42 of 527 (8%) | 485 of 527 (92%) |

- Spearman rank correlation between the in-sample and out-of-sample readings over all 585 judgeable memberships: **0.67**.
- Noise floor: with 9 returns the standard error of a Pearson r near 0.3 is ≈ 0.34 — no per-name verdict is readable in this window; only the group contrast is.
- Price path, CONTEXT ONLY (not a verdict): median market-adjusted return over the window, evicted names -4.1% (n=58) vs their theme baskets -5.1% (n=58).

### W2 — engine-grade window: board 2026-08-12 (88 themes, 436 memberships, 338 judgeable), in-sample = 60 sessions to 2026-08-12, out-of-sample = 30 returns 2026-08-13 … 2026-09-24

| group (in-sample verdict) | n | OOS judgeable | mean OOS co-movement | median | share < 0.35 OOS | share ≥ 0.35 OOS |
|---|---|---|---|---|---|---|
| would be EVICTED (in-sample < 0.35) | 25 | 25 | 0.38 | 0.42 | 11 of 25 (44%) | 14 of 25 (56%) |
| KEPT (in-sample ≥ 0.35) | 313 | 307 | 0.73 | 0.78 | 24 of 307 (8%) | 283 of 307 (92%) |

- Spearman rank correlation between the in-sample and out-of-sample readings over all 332 judgeable memberships: **0.78**.
- Noise floor: with 30 returns the standard error of a Pearson r near 0.3 is ≈ 0.17 — a per-name direction is readable, with n.
- Price path, CONTEXT ONLY (not a verdict): median market-adjusted return over the window, evicted names -11.8% (n=25) vs their theme baskets -16.0% (n=25).

**Per name (readable at 30 returns): 11 of 25 would-be-evicted names kept failing to move with their theme (the tape was right); 14 of 25 started moving with it (the tape was early or wrong).**

| stock | theme | stage | in-sample | OOS (30 returns) | direction |
|---|---|---|---|---|---|
| CVLT | Network Security & Zero-Trust Edge | Mains | 0.33 | 0.83 | rose above the bar |
| FLS | Industrial Equipment & Flow Control – Capex Cycle  | Mains | 0.32 | 0.73 | rose above the bar |
| DPC | Defense Electronics & Aerospace Subsystem Supplier | Mains | 0.14 | 0.63 | rose above the bar |
| FSK | Private Equity & Alternative Asset Management Plat | Mains | 0.21 | 0.62 | rose above the bar |
| BFH | Consumer Fintech & Digital Credit Platforms | Fadin | 0.23 | 0.58 | rose above the bar |
| ROAD | Industrial Construction Execution & On-Site Supply | Accel | 0.28 | 0.57 | rose above the bar |
| EQPT | Industrial Equipment Rental & Material Handling | Accel | 0.32 | 0.54 | rose above the bar |
| TPC | Industrial Construction Execution & On-Site Supply | Accel | 0.22 | 0.52 | rose above the bar |
| INSM | Specialty Pharmaceutical Commercialization & Rare  | Mains | 0.30 | 0.51 | rose above the bar |
| MPWR | AI data center infrastructure buildout | Nasce | 0.29 | 0.51 | rose above the bar |
| CORT | Peptide & Hormone Therapies for Metabolic & Endocr | Mains | 0.21 | 0.50 | rose above the bar |
| AADX | Defense Electronics & Aerospace Subsystem Supplier | Mains | 0.12 | 0.47 | rose above the bar |
| ARXS | Defense Electronics & Aerospace Subsystem Supplier | Mains | 0.07 | 0.42 | rose above the bar |
| CMCO | Industrial Equipment Rental & Material Handling | Accel | 0.16 | 0.40 | rose above the bar |
| BLZE | AI data center infrastructure buildout | Nasce | 0.22 | 0.34 | still below |
| MRCY | Defense Electronics & Aerospace Subsystem Supplier | Mains | 0.28 | 0.34 | still below |
| CNMD | Medical Device Mean-Reversion & Rotation Recovery | Mains | 0.27 | 0.31 | still below |
| ATI | Defense Electronics & Aerospace Subsystem Supplier | Mains | 0.03 | 0.25 | still below |
| BMRN | Specialty Pharmaceutical Commercialization & Rare  | Mains | 0.24 | 0.23 | still below |
| RTX | Defense Electronics & Aerospace Subsystem Supplier | Mains | 0.12 | 0.21 | still below |
| DFNS | Defense Electronics & Aerospace Subsystem Supplier | Mains | 0.06 | 0.15 | still below |
| EMBJ | Defense Electronics & Aerospace Subsystem Supplier | Mains | 0.16 | 0.07 | still below |
| J | Industrial Construction Execution & On-Site Supply | Accel | -0.00 | 0.05 | still below |
| VLTO | Industrial Equipment & Flow Control – Capex Cycle  | Mains | 0.32 | -0.02 | still below |
| OMER | Specialty Pharmaceutical Commercialization & Rare  | Mains | 0.12 | -0.23 | still below |

- Mirror, the kept side: 24 of 307 (8%) in-sample-kept memberships read below 0.35 out of sample.

### 4. Tightness before / after, with the matched random-removal control

Tightness = mean leave-one-out co-movement of each member with the rest (no engine metric exists; the 09-13 doc's). Control = remove the SAME NUMBER of members at random from the theme's judgeable members, 300 draws, seed 20260925. 'control ≥ real' = draws whose after-tightness is at least the tape's.

### 4a. In-sample on today's board — a FLOOR by construction (removing the lowest-scoring members raises the mean of what is left)

| theme | stage | evicted | members | before | after | control mean | control ≥ real (of draws) |
|---|---|---|---|---|---|---|---|
| AI-Driven Diagnostics & Imaging Re-Rating | Mains | DGX, CDNA, HTFL, LH | 9 | 0.39 | 0.57 | 0.34 | 6/300 |
| AI-Powered Enterprise Analytics & Intelligent Wo | Fadin | MSFT, ORCL | 18 | 0.68 | 0.77 | 0.68 | 1/300 |
| Bank Stocks: Rising-Rate NIM Expansion | Fadin | BBVA, BCS, LYG, SAN, C, MFG, DB | 45 | 0.61 | 0.69 | 0.61 | 0/300 |
| Bitcoin Mining Stocks Rotation Reversal | Mains | IOND | 10 | 0.76 | 0.83 | 0.76 | 32/300 |
| Cloud Data Storage & Analytics Infrastructure | Mains | ESTC, APLD | 4 | 0.24 | n/a | n/a | n/a/0 |
| Commercial, Office & Home Furniture Retailers an | Fadin | ARHS | 5 | 0.49 | 0.54 | 0.47 | 64/300 |
| Crude & Product Tanker Shipping | Mains | SR, ATO | 13 | 0.76 | 0.87 | 0.76 | 5/300 |
| Defense Electronics & Aerospace Subsystem Suppli | Mains | EMBJ, RTX | 9 | 0.42 | 0.52 | 0.40 | 11/300 |
| Defense Intelligence & Cybersecurity IT Contract | Mains | EFOR, VVX | 7 | 0.52 | 0.65 | 0.49 | 17/300 |
| Defensive Consumer Staples Rotation | Fadin | TBBB, GO | 17 | 0.56 | 0.61 | 0.56 | 1/300 |
| Digital Advertising & Ad-Tech Monetization Platf | Mains | MGNI | 4 | 0.50 | n/a | n/a | n/a/0 |
| Diversified Power Generation Capacity Expansion  | Fadin | HNRG, AES, OGE, EVRG | 5 | 0.28 | n/a | n/a | n/a/0 |
| Energy Infrastructure & Services Complex | Fadin | FTK, WKC | 16 | 0.49 | 0.58 | 0.48 | 1/300 |
| Enterprise Server, Storage & Data Infrastructure | Nasce | NTNX | 8 | 0.50 | 0.60 | 0.50 | 49/300 |
| Fintech & Digital Finance Sector Re-rating on Fe | Fadin | XP, ITUB, PGY, KSPI, CHYM | 22 | 0.45 | 0.51 | 0.44 | 0/300 |
| Genetic Medicine: Gene Editing & Gene Therapy In | Fadin | QURE | 4 | 0.44 | n/a | n/a | n/a/0 |
| Global Agriculture Value Chain Recovery | Mains | AGRO | 4 | 0.56 | n/a | n/a | n/a/0 |
| Industrial Construction Execution & On-Site Supp | Fadin | TTEK, J, AGX, ACA, KBR | 8 | 0.17 | n/a | n/a | n/a/0 |
| Inflammatory Disease & Immunology Biologics | Fadin | AUPH, TRAX | 9 | 0.49 | 0.58 | 0.47 | 4/300 |
| Medical Device Mean-Reversion & Rotation Recover | Fadin | GKOS, INSP | 14 | 0.55 | 0.60 | 0.54 | 2/300 |
| Network Security & Zero-Trust Edge | Mains | BLZE | 18 | 0.71 | 0.74 | 0.71 | 22/300 |
| Wealth Management & Retail Brokerage Platforms | Mains | XP, HOOD | 13 | 0.42 | 0.49 | 0.41 | 6/300 |

- Across the 16 measurable changed themes: mean tightness **0.55 → 0.63**; random removal of the same count lands at **0.54** (n=16).

### 4b. OUT OF SAMPLE — evictions chosen on the in-sample window, tightness change read on the 9 OOS returns (W1, board 2026-09-11) — this is the reading that counts

| theme | stage | evicted | members | in-sample before → after | OOS before | OOS after | OOS control mean | control ≥ real (of draws) |
|---|---|---|---|---|---|---|---|---|
| AI-Driven Diagnostics & Imaging Re-Rating | Fadin | DGX, CDNA, HTFL, LH | 8 | 0.36 → 0.53 | 0.58 | 0.73 | 0.52 | 15/300 |
| AI-Powered Enterprise Analytics & Intelligen | Fadin | MSFT, ORCL | 16 | 0.69 → 0.77 | 0.80 | 0.88 | 0.80 | 22/300 |
| Commercial, Office & Home Furniture Retailer | Accel | ETD | 6 | 0.56 → 0.61 | 0.42 | 0.37 | 0.40 | 193/300 |
| Consumer Fintech & Digital Credit Platforms | Fadin | KSPI, PYPL | 14 | 0.45 → 0.48 | 0.54 | 0.56 | 0.53 | 71/300 |
| Defense Electronics & Aerospace Subsystem Su | Fadin | RTX, ARXS, EMBJ | 5 | 0.26 → n/a | 0.47 | n/a | n/a | n/a/0 |
| Defensive Consumer Staples Rotation | Fadin | UTZ, TBBB | 16 | 0.55 → 0.66 | 0.50 | 0.53 | 0.50 | 41/300 |
| Digital Insurance Distribution & InsurTech P | Fadin | GSHD, LIFE, PRCH, NP | 4 | 0.21 → n/a | 0.02 | n/a | n/a | n/a/0 |
| Diversified Power Generation Capacity Expans | Nasce | OGE, HNRG, KEP | 4 | 0.22 → n/a | 0.52 | n/a | n/a | n/a/0 |
| Energy Supply Disruption: Middle East Geopol | Mains | BTU, XPRO, FTK, NESR, WTTR | 59 | 0.71 → 0.77 | 0.73 | 0.78 | 0.73 | 1/300 |
| Enterprise Server, Storage & Data Infrastruc | Fadin | NTNX | 8 | 0.47 → 0.58 | 0.50 | 0.62 | 0.49 | 41/300 |
| Farm Economy Value Chain Re-Rating | Accel | FMC | 7 | 0.52 → 0.56 | 0.68 | 0.80 | 0.67 | 41/300 |
| Global Agriculture Value Chain Recovery | Mains | DOLE | 9 | 0.47 → 0.48 | 0.56 | 0.57 | 0.55 | 106/300 |
| Hospital & Behavioral Health Facility Proced | Fadin | ACHC | 5 | 0.45 → 0.63 | 0.59 | 0.62 | 0.57 | 128/300 |
| Industrial Construction Execution & On-Site  | Fadin | TPC, TTEK, J, ACA, KBR, FLR | 7 | 0.21 → n/a | 0.37 | n/a | n/a | n/a/0 |
| Industrial Equipment & Flow Control – Capex  | Fadin | FLS, VLTO | 4 | 0.36 → n/a | 0.31 | n/a | n/a | n/a/0 |
| Inflammatory Disease & Immunology Biologics | Fadin | TRAX | 13 | 0.49 → 0.54 | 0.67 | 0.65 | 0.67 | 235/300 |
| Legacy Telecom & Pay-TV/Broadcasting Distrib | Nasce | CHTR, TDS, ECHO | 4 | 0.23 → n/a | -0.12 | n/a | n/a | n/a/0 |
| Medical Device Mean-Reversion & Rotation Rec | Fadin | INSP | 14 | 0.58 → 0.61 | 0.64 | 0.68 | 0.64 | 40/300 |
| Molecular & Genomic Diagnostic Testing | Fadin | VCYT, CDNA, BLLN | 4 | 0.27 → n/a | 0.62 | n/a | n/a | n/a/0 |
| Neurology & Rare Disease CNS Biopharmaceutic | Nasce | BIIB, EWTX, ARWR | 5 | 0.36 → n/a | 0.41 | n/a | n/a | n/a/0 |
| Oil Refining & Marketing | Nasce | OGS, AESI, SWX, SR | 27 | 0.58 → 0.62 | 0.58 | 0.63 | 0.57 | 6/300 |
| Oncology Therapeutics RS Turnaround | Fadin | SMMT, INCY, ZLAB | 16 | 0.49 → 0.53 | 0.50 | 0.49 | 0.49 | 148/300 |
| Peptide & Hormone Therapies for Metabolic &  | Fadin | CRNX, CORT | 4 | 0.37 → n/a | n/a | n/a | n/a | n/a/0 |
| Wealth Management & Retail Brokerage Platfor | Fadin | XP, APAM | 20 | 0.48 → 0.51 | 0.50 | 0.55 | 0.50 | 16/300 |

- W1: across the 15 measurable changed themes, OOS tightness 0.59 → 0.63 (tighter in 12 of 15); random removal of the same count lands at 0.58; the tape's eviction beats the random control's mean in 12 of 15 themes, and beats ≥95% of draws in 3 of 15.

### 4b. OUT OF SAMPLE — evictions chosen on the in-sample window, tightness change read on the 30 OOS returns (W2, board 2026-08-12) — this is the reading that counts

| theme | stage | evicted | members | in-sample before → after | OOS before | OOS after | OOS control mean | control ≥ real (of draws) |
|---|---|---|---|---|---|---|---|---|
| AI data center infrastructure buildout | Nasce | BLZE, MPWR | 8 | 0.56 → 0.67 | 0.58 | 0.62 | 0.55 | 31/300 |
| Consumer Fintech & Digital Credit Platforms | Fadin | BFH | 7 | 0.51 → 0.55 | 0.58 | 0.56 | 0.57 | 137/300 |
| Defense Electronics & Aerospace Subsystem Su | Mains | DFNS, MRCY, DPC, EMBJ, AADX, ARXS, ATI,  | 9 | 0.15 → n/a | 0.31 | n/a | n/a | n/a/0 |
| Industrial Construction Execution & On-Site  | Accel | J, ROAD, TPC | 4 | 0.23 → n/a | 0.34 | n/a | n/a | n/a/0 |
| Industrial Equipment & Flow Control – Capex  | Mains | FLS, VLTO | 10 | 0.59 → 0.65 | 0.61 | 0.67 | 0.60 | 44/300 |
| Industrial Equipment Rental & Material Handl | Accel | CMCO, EQPT | 4 | 0.35 → n/a | 0.47 | n/a | n/a | n/a/0 |
| Medical Device Mean-Reversion & Rotation Rec | Mains | CNMD | 4 | 0.40 → n/a | 0.23 | n/a | n/a | n/a/0 |
| Network Security & Zero-Trust Edge | Mains | CVLT | 13 | 0.63 → 0.66 | 0.81 | 0.81 | 0.81 | 81/300 |
| Peptide & Hormone Therapies for Metabolic &  | Mains | CORT | 5 | 0.42 → 0.46 | 0.29 | n/a | n/a | n/a/0 |
| Private Equity & Alternative Asset Managemen | Mains | FSK | 11 | 0.68 → 0.73 | 0.75 | 0.76 | 0.75 | 50/300 |
| Specialty Pharmaceutical Commercialization & | Mains | OMER, INSM, BMRN | 10 | 0.42 → 0.52 | 0.30 | 0.35 | 0.27 | 66/300 |

- W2: across the 6 measurable changed themes, OOS tightness 0.60 → 0.63 (tighter in 4 of 6); random removal of the same count lands at 0.59; the tape's eviction beats the random control's mean in 4 of 6 themes, and beats ≥95% of draws in 0 of 6.

---

## What this does not answer

- **Whether a down-weight changes any EP outcome.** No down-weight mechanism exists to replay, so leave vs down-weight is NOT separated by this evidence; only evict-on-one-reading is. The $0 next step: read `mi_ep_theme_belonging_shadow` for the 18 paying-theme evictees (the fit judge's verdicts are already recorded there for names it scored) before spending any call.
- **A per-name verdict in W1.** 9 sessions carry a standard error of ≈ 0.34 on a reading near 0.3; only the group contrast (n = 58 vs 527) is read there.
- **n = 25 in W2.** One board date with 30 sessions after it. A rolling version (every board date since 06-17 with 30 sessions after it, each name counted once) would give the n; it was not pre-registered here and is not run.
- **The cascade.** A nightly rule iterates: after the first pass a smaller basket re-judges the survivors. Only the first pass is simulated. The Defense Electronics theme on 08-12 (8 of 9 members below the bar, in-sample tightness 0.15) shows what the cascade would do — dissolve the theme — and that theme then partly cohered (0.31 OOS).
- **Hysteresis or persistence cut-lines** (a lower removal bar than the admission bar; N consecutive readings). Not pre-registered, not measured — a follow-up must state them before looking.
- **The third of the board the rule cannot reach.** 36 of 109 themes have exactly three members with history; leave-one-out leaves a two-name basket and every member is unjudgeable. A removal rule at these settings never touches them.
- **Whether "survived a rescore" is an LLM yes.** The mass-eviction skip (#214) and the min-survivor guard keep flagged members; survival is an upper bound on LLM approval. 50 of 52 is that upper bound.
- **The 15 "merge:unlogged" and 4 untraceable joins.** The merge machinery writes no per-ticker row; the class (merged in, not judged at join) is derived from the prior board and the retirement of the source theme, and the mechanism label is not. EMBJ / RTX (08-11), EVRG (09-15) and AGRO (09-02) could not be tied to any event.
- **Trade returns.** Nothing here touches EP outcomes; the money-path read stops at "18 of 52 carry the +10 today".
- **The SSoT sentence.** `docs/architecture/theme_engine.md` (membership-test bullet) said the birth and nightly strips use the tape; the code withholds the context at both sites since his ruling. Corrected in this commit to match the code; the drift existed from 09-13 to 09-25.


---

## Recommendation

⚖ THE LINE: nothing is flipped by this document. Every option below is his to sign, behind `docs/setups/CHANGE_PROCESS.md`.

**Recommendation: DOWN-WEIGHT, not evict — and treat Shape A as a separate, smaller decision.** Stated against the north star (subtle RS → early theme → matures → buy before mainstream) and the HOOD example.

- **Evict (Shape B, one 60-session reading below 0.35) — not supported as a standalone rule.** Out of sample at 30 sessions the tape was right on 11 of 25 names and early-or-wrong on 14 of 25 (n = 25). The names it gets wrong are, by construction, the ones whose co-movement forms AFTER they join — the early names the north star wants kept. It would also dissolve themes (2 of 22 changed themes drop under 3 members; Defense Electronics on 08-12 would have lost 8 of 9), and 16 of 52 of today's evictees entered through merges no LLM judged, which is a merge-machinery finding rather than a tape finding.
- **Leave — has a measured cost, and it is on the money path.** 18 of 52 evictees are LISTED members of paying themes and receive the EP +10 today regardless of co-movement (XP 0.07 and HOOD 0.31 in a Mainstream wealth theme; SR 0.10 and ATO 0.27, gas utilities, in a Mainstream tanker theme, never judged by an LLM). The group is 5.5× more likely than kept names not to co-move over the next 30 sessions (11 of 25 vs 24 of 307).
- **Down-weight — the option that matches a partially-correct membership**, which is exactly HOOD (0.31 with its theme, 0.65–0.74 with three bitcoin baskets). The evidence separates evict from the other two; it CANNOT separate down-weight from leave, because no down-weight exists to replay. Candidate shapes, none pre-decided, all his call: (a) a below-bar LISTED member does not get the automatic +10 and is judged by the same fit call an unlisted name gets (`ep_theme_belonging` stage 3) — a money-path change; (b) a persistence rule — a member is only removed after N readings below the bar, measurable offline before any flip; (c) a removal bar lower than the admission bar — must be pre-registered before it is measured.
- **Shape A (as built — pass the context to the two strip sites)** is NOT an eviction rule: on today's board it strips 1 of 8 singleton-sector members (AGRO 0.09, which the label strips too) and keeps the other 7 (OKLO 0.90, LEU 0.84, MAS 0.68, PUBM 0.66, TNET 0.61, VSAT 0.49, WLTH 0.40) that the label removes tomorrow. His 09-13 ruling ("leave job 2") predates the loop this created: 16 of 21 cross-sector pairs the tape admitted were stripped by the label within days and 9 of 21 bounced two or more times, each bounce re-spending a proposal and a validation. **Surfaced for his decision**, not pre-decided: closing the loop is a smaller change than the eviction question, and it removes fewer names, never more.

**Stopping rule for a follow-up, if he wants one**: pre-register the rolling W2 (every board date with 30 sessions after it) and the persistence rule (N = 5 / 10 readings) BEFORE running; sign-off only on numbers from that document.
