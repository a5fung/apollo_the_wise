# #655 — the theme correctness test and the naming-latency target, for his sign-off

**Written Sun 2026-09-27 (PDT). $0: three independent probes on the live board of 2026-09-25, every
number computed locally from data captured once. Nothing here changes a threshold or a gate; every
bar and the target are his (THE LINE). Step 3 stays parked until he signs.**

Synthesised from three designs (grouping / identity / funnel) whose outputs sit in
`scripts/probes/_655/`. Where they measured the same thing they agree; where they disagree it is
said below.

## ⚠ CORRECTED 2026-09-27 — an adversarial critic re-ran the reads; the orchestrator checked its numbers against its output files. This section wins over everything below.

**Status: NOT ready to sign as written.** The draft's headline, "the board passes 0 of 6 reads", rests on bars
chosen after the data was seen, and two of its reads cannot tell a broken board from a good one. What survives is
a GROUPING test whose bars were written before its first run, today's baselines, and a named-case list for identity.

**✅ SIGNED BY HIM 2026-09-27 (*"Signed"*) — the four grouping bars below, as proposed.** The step-2 latency target is still his pick.

**What goes to him for signature (the grouping half, bars pre-registered in `scripts/probes/_655/grouping/grouping_test.py`
before any number printed; scored forward nightly, today's values are the BASELINE, not a verdict):**

| read | what it checks | proposed bar (pre-registered) | today (live board 09-25, 118 themes) |
|---|---|---|---|
| G1 member fit | each member moves with its own theme (market-adjusted, the engine's 0.35 scale) | ≥ 90% of judgeable members | **90.7%** (534 of 589) — passes |
| G2 misfiled | a member tied < 0.35 to its own theme and clearly closer to another | ≤ 5% | **3.4%** (20 of 589) — passes |
| G3 beats a random basket | the theme holds together better than a size-matched random group | ≥ 90% of themes | **87.3%** (103 of 118) — fails; 13 of the 15 misses are 2–3-member themes |
| G4 shape | themes under 3 members | ≤ 10% of themes | **8.5%** (10 of 118) — passes (the draft dropped this read without saying so) |
| judgeable share (new, per theme) | themes where the test can judge at least one member | bar is his | 74 of 118 (63%); 44 themes are too small or too new to judge |

- **Identity (is the theme named for its real driver) is NOT a pass/fail bar — it is a named-case list.** A
  board-wide bar fails 30% of nights even with the miners removed (31 of 102 nights since 05-04; 12 of 102 even
  when the same theme must flag 5 nights running), and one false flag ran 12 nights (a copper USER read as copper).
  **The miners case stands as a named case:** HUT, CIFR, IREN, CORZ, WULF and APLD move with AI infrastructure,
  not bitcoin, since about 05-08 (variant A only; the earlier "97–155 sessions" figure is not supportable, and from
  May to June the rival theme was a semiconductor one, not an AI one). The draft's fix fails its own read: after the
  six leave, the rest {ABTC, IOND, BTDR, CLSK, MARA, RIOT} still tie closer to "AI data-center power buildout" (0.72)
  than to bitcoin (0.47) — the "true miners" list is itself unsettled.
- **Duplicates: 6 exact-match pairs, not 5** (Mobile SoC ~ RF & Analog Wireless tie 1.00 with identical members),
  plus **9 pairs that move as one group (≥ 0.90) with under half their members shared** — e.g. the two P&C
  insurance themes (0.97), Crude & Product Tanker ~ Product Tanker (0.91, no shared members), the two airline
  themes (0.91). Reported as named lists; how to design that check is his call.
- **Step-2 latency: the draft's 27 sessions mostly measures RE-MADE themes, not late discovery.** Of 52 births in
  30 days, 43 had half their founders already sitting in one live theme during the lead window. **Groups never on
  the board: n = 9, median 37 sessions from first cluster to birth, 8 of 9 over 10** (11 of the 52 hit the
  40-session lookback, so the figure is censored). The miners were first named 07-08, two sessions after their
  cluster appeared; their six later births are re-mints (churn). **The target (5 vs 10 sessions) is his pick with
  no measured support either way** — the draft's "why 5" leaned on a price-outcome curve from 05-14..08-05.
  The live monitor should be each night's births and their lag; the proposed "unnamed clusters aged 5+" counter
  reads 0 on 11 of the last 15 nights while the lag is 27.
- **Dropped until rebuilt:** read #6 ("the name has settled") measures size and nesting, not naming indecision
  (62% of 10+-member themes flag vs 5% of 2–3-member themes). Read #2's "≥ 0.15 more" clause does nothing, and a
  random stock meets its "other ≥ 0.50" half the time; its suggested new homes (APLD and AGX into the bitcoin theme,
  ORCL into on-site power) are NOT moves.
- **Founders are cluster-screened** (20-day correlation ≥ 0.85), so they grade well by construction; the cleanest
  untested group is members that joined before 09-14 (84% pass G1).
- **THE LINE:** the draft's idea of adding a field to the EP catalyst grading call is a MONEY-PATH change (that grade
  is scored). Any membership move also changes which EPs get the +10 theme bonus. Nothing here writes to live theme
  state, and no read is wired to Telegram before he signs its bar (audit rows only).
- **Correction for PLAN #655:** "9 themes hold zero" was 9 Retired placeholder rows; on the engine's own board
  09-11 had 0 empty themes and 70% at ≤ 5 members — the same share as today. Only the 2-member count moved (21 → 10).

## 1. The answer first

- **The test:** six nightly reads on the live board. Five are price-only on the engine's own
  co-movement scale (market removed, 60 sessions; a real member ties to its theme at 0.5-0.8, a
  random stock at about 0.05, the signed admission bar is 0.35); the sixth counts the names the
  system itself gave a group. Four say whether the RIGHT STOCKS are together (members fit · misfiled
  members · theme beats a random basket · no duplicates); two say whether the NAME holds up (the
  named driver still explains the group · the name has settled). No labels, no returns.
- **Today's score: 0 of 6 pass at the recommended bars; the judgeability guard passes.** Two are
  near misses: members fit 89.6% (bar 90%, n=450, 2 names short) and misfiled 2.5% (bar 2%, n=589,
  15 names to move, 3 over). Four are real gaps: themes beating a random basket 87.3% (bar 90%,
  n=118; 13 of the 15 misses are 2-3 member themes), duplicates 5 (bar 0), named driver wrong on 1
  of the 10 themes it can reach (bar 0) — the miners, and name unsettled on 27% of themes (bar 10%,
  n=118).
- **#491, in his words — a theme change for the stocks, not a similar theme merge.** The miners
  theme passes every grouping read (the stocks do move together, 0.60 vs 0.17 for a random basket)
  and FAILS the named-driver read: it moves with bitcoin at 0.37 and with an AI theme at 0.68.
  Stock by stock, under three separate references, HUT, CIFR and IREN (in the theme), CORZ and WULF
  (in no theme) and APLD (filed under cloud storage) move with AI infrastructure, not bitcoin; ABTC
  and MARA still move with bitcoin, BTDR splits (bitcoin 0.47 vs AI 0.53) and stays. So six stocks
  should leave for an AI-compute theme and the bitcoin name stays right for the true miners.
- **What the test cannot do for #491:** CORZ and WULF cannot be moved by the engine today — their RS
  is 19, under the RS-70 assignment floor (#491 design §2 B2); lifting that is his call. And the
  check knows bitcoin is the wrong driver; it does not know which AI theme is the right home.
- **Step 2 target, proposed: name a group within 5 sessions of the tape showing it.** Today the
  median is 27 sessions (n=52 births in the last 30 days that had a stored cluster before birth).

## 2. The test

All six run on the engine's own maths (`agents/market_intelligence/market_adjusted_correlation.py`),
so they cost nothing and can run nightly. "Broken reads" = what a board of random baskets would score,
measured, so a pass cannot be produced by a dead engine.

| # | measure | what it checks | proposed bar | today's value (n) | broken engine reads | source |
|---|---|---|---|---|---|---|
| 1 | **Members fit their theme** | each member's tie to the rest of its own theme (one left out at a time) ≥ 0.35 | ≥ 90% of judgeable members | **89.6%** (403 of 450 members the 0.35 gate never tested); 90.7% on all 589 judgeable | random baskets of the same sizes: 3% (41 of 1,480 draws); same-sector random baskets: 35% (520 of 1,480) — so this read cannot tell a theme from a sector | grouping §G1, POST-HOC (4); funnel §C2 controls |
| 2 | **Misfiled members** | member fails its own theme (< 0.35) AND another live theme fits at ≥ 0.50, by ≥ 0.15 more | ≤ 2% of judgeable members | **2.5%** (15 of 589) — APLD, ACA, NTNX, TTEK, ORCL, KBR, AGX, HOOD, WES, DGX, ESTC, AMP … | not measured directly; a randomly placed member fails its own theme (~0.05) and a random stock's best tie to some theme is 0.54 at the median (n=1,705 unthemed), so roughly half of slots would flag | funnel §M1 (grouping §G2 agrees: 20 of 589 on a looser margin); grouping POST-HOC (1) |
| 3 | **Theme beats a random basket** | the theme's average pairwise tie beats the 95th percentile of 500 random baskets matched on size, strength and volatility — the only read that reaches 2-3 member themes | ≥ 90% of themes | **87.3%** (103 of 118); 2-3 members 31 of 44 (70%), 4+ members 72 of 74 (97%) | 5% by construction (the p95 line); median random-basket cohesion 0.04 vs themes 0.53 | grouping §G3 |
| 4 | **No duplicates** | two live themes share ≥ half their members AND their baskets tie ≥ 0.70 | 0 pairs | **5 pairs**: AI Memory ~ NAND/DRAM · Energy Infrastructure ~ Offshore Drilling · Farm Economy ~ Global Agriculture · Precious Metals Complex ~ Precious Metals Miners · Small Satellite ~ Space Economy | 0 by construction | grouping §G4, POST-HOC (3) |
| 5 | **Named driver still explains the group** | for a theme whose name claims a priced driver (bitcoin=IBIT, gold/silver=GLD/SLV, oil=USO, copper=COPX, uranium=URA): the group's tie to that price must not trail the best live theme of a DIFFERENT driver by 0.15 or more | 0 themes flagged; each flag is a named case for him | **1 of 10** in reach: Bitcoin Mining Stocks Rotation Reversal (bitcoin 0.37 vs an AI theme 0.68). Fired on 98 of 98 cohort theme-nights since 05-04 | false-flag 6% (38 of 586 other priced-driver theme-nights) | funnel §I1v2, §I1h |
| 6 | **Name has settled** | distinct names the system gave one group in 30 days (its live rows + its own shadow proposals) | ≤ 10% of themes at 4+ names | **27%** (32 of 118); median 2, miners 7 (4 of them naming AI/HPC) | a frozen wrong name reads 1 (this catches indecision, not wrongness) | funnel §I2 |
| G | **Guard: judgeability** | share of member slots the engine's own test can judge (needs 3 other members with history) — so splitting the board into tiny themes cannot inflate #1 and #3 | ≥ 80% of slots | **82.8%** (589 of 711); 44 of 118 themes have no judgeable member | falls as the board fragments | grouping §G1 |

Why #1 headlines the never-tested number: 139 of the 589 judged members were admitted BY the 0.35
test since 2026-09-14, and they pass at 94%. Scoring them is the gate grading its own admissions.

## 3. The step-2 latency target

- **Measure:** sessions from the first night a stored correlation cluster holds at least half of a
  theme's founders to the night the theme is born. Stored cluster → birth night; no trend
  definition, so it does not have the defect the 09-20 read had (days moved with the trend window).
- **Today:** median **27 sessions** (n=52 of 124 births 08-26..09-25 that had such a cluster; middle
  half 17-38). 46 of 52 (88%) waited more than 10 sessions. From the LAST sighting before birth: 9
  sessions, up from 2 in Jun-Jul and 6 in Aug — getting worse. It reproduces the 09-07 study
  (median 26, n=140 of 398; 84% of lineages match).
- **Proposed target:** median ≤ 5 sessions, and no more than 25% of births over 10.
- **Why 5:** the payoff curve (n=354 founder gaps) says every 5 sessions of EARLIER naming buys
  about 13 points of founder gaps still ahead — 29% today, 55% if named 5 sessions earlier, 68% at
  10, 81% at 15 (the curve stops at 15). Both 5 and 10 are more than 15 sessions earlier than today's
  27, so the curve does not separate them. 5 because the engine already names from the LAST sighting
  at a median 9 sessions (2 in Jun-Jul), so acting on the first or second sighting is within reach,
  and the 140 early-visible themes matured at 37%, the same as the rest — earlier naming cost no
  quality (`step3_theme_runway_2026-09-07.md`).
- **Nightly counter (the live form):** stored clusters no live theme covers, persisting ≥ 5
  sessions. Today **1** (insurance brokers AJG/BRO/MRSH/WTW/SONY, unnamed 8 sessions; the live
  broker theme holds only RYAN and WTW); 0-2 on each of the last 15 nights. Guard: stored clusters
  per night > 0 (7 on 09-25) — a dead cluster writer would read a perfect 0.
- **#491 on this measure:** 6 of the 7 miner-group births since 06-01 had a stored cluster 24-40
  sessions before naming.
- **Coverage caveat:** 42% of births had a stored pre-birth cluster; the other 58% are outside this
  read. The alternative shape he was offered 09-20 — "named before the group has gained X%", median
  +14% today (n=254) — is the fork in §5.

## 4. What it catches and what it misses

**Catches**
- Stocks that do not belong (#2): APLD ties -0.16 to its own cloud-storage theme and 0.87 to the
  miners; ACA, NTNX, TTEK, ORCL fit their own themes negatively.
- Themes that are not groups (#3): Industrial Construction (0.08 across 8 members), Cloud Data
  Storage (0.19 across 4) — indistinguishable from a random basket.
- The same group under two names (#4): 5 pairs.
- **#491 (#5 + #6):** the theme flag fires (bitcoin 0.37 vs 0.68) and has fired every night since
  05-04. Its member list, read against fixed references (his taxonomy stocks / IBIT vs NVDA-SMCI-VRT-CRWV
  / the board's own bitcoin-proxy vs AI-infra themes): HUT +0.34/+0.47/+0.23, CIFR +0.36/+0.45/+0.27,
  IREN +0.35/+0.54/+0.19, CORZ +0.48/+0.64/+0.35, WULF +0.46/+0.64/+0.38, APLD +0.40/+0.68/+0.32 move
  with AI infrastructure over bitcoin under all three (n=12 cohort names). ABTC, MARA, BTDR do not;
  CLSK under 2 of 3, RIOT under 1 of 3. The name churned 7 times in 30 days. The bitcoin link fell
  from ~0.5 (Mar-Apr) to ~0.1 (Jul-Aug) while the AI link held 0.45-0.60 — the switch has been
  sustained 97-155 sessions and the theme was mapped to bitcoin on 09-11, after both.
- Why his example beats a plain co-movement test: IREN co-moves with the miners basket at 0.80 and
  passes grouping; against bitcoin it reads 0.15, against AI infrastructure 0.69.

**Misses**
- **Identity for 108 of 118 themes (92%).** #5 reaches only names that claim a PRICED driver. A
  coherent group under a stable wrong name (AI, software, biotech) passes every read; #6 catches
  indecision, not wrongness.
- **#5 knows bitcoin is wrong, not what is right.** The competitor it names for the miners is a
  memory-chip theme (best of ~100 baskets). Destination is a separate question.
- **Two names disagree between reads.** The funnel's member arm flags BTDR and RIOT too (6 of 9)
  because it compares against a best-of-many competitor; the fixed-reference read does not. The
  fixed-reference list is the one to act on.
- **CORZ and WULF** are in no theme and no read moves them: homeless at RS 19 under the RS-70
  assignment floor; the pre-declared homeless rule missed them by 0.003 and 0.010.
- **Theme vs sector.** A random same-sector basket passes #3 35% of the time (520 of 1,480 draws);
  31 of 118 themes do not beat their own sector. A sector wearing a theme name passes.
- **Small themes are weakly judged.** 44 of 118 have no member the engine's own test can judge; a
  2-member theme must clear ~0.44 to pass #3.
- **Missing themes.** Only the nightly cluster counter (§3) sees them, and only where a cluster was
  stored.
- **Timing.** A right group named late passes all six; that is §3's job.
- **Self-grading on #1** is handled by the era split; on #2-#6 the 0.35 gate does not set the score.
- **A 60-session read lags a real switch by weeks**, and a short counter-move pulls it back (the
  miners' bitcoin link rose 0.06 → 0.27 during September's bitcoin rebound).

## 5. Decisions for him

Nothing below ships without his word; each is a detection criterion (CHANGE_PROCESS applies).

1. **#1 members fit, bar ≥ 90% on never-gate-tested members** — sign / raise / lower. Rec: sign at 90%; today 89.6% fails by 2 names, honest.
2. **#2 misfiled, bar 2% or 5%** — 2% FAILS today by 3 names (15 vs 12); 5% passes with room for a doubling. Rec: **2%** — the 15 flagged are all real defects (own fit -0.19 to +0.33) and are the repair list either way.
3. **#3 theme beats a random basket, bar ≥ 90%** — sign / lower to 85% (passes today). Rec: sign at 90%; the 13 failing small themes are the shape defect he named, and the bar should see it.
4. **#4 duplicates, bar 0** — sign / allow a count. Rec: 0; the 5 pairs are a named merge list for him (merging is his call — a join is dedup, never a merge).
5. **#5 named driver, margin 0.15, bar 0 flags** — sign / widen the margin to 0.20 (would cut some of the 6% false flags, not measured at 0.20; the miners still flag at a gap of 0.31). Rec: sign at 0.15; each flag is a named case, not an auto-action.
6. **#6 name settled, bar ≤ 10% at 4+ names in 30 days** — sign / loosen to 3+ or 5+ names. Rec: sign at 4+; today 27% and the miners' 7 names is the symptom he keeps seeing.
7. **Guard: judgeability ≥ 80% of slots** — sign / drop. Rec: sign; it is what stops #1 and #3 being gamed by splitting.
8. **Step-2 target: median ≤ 5 sessions (rec) / ≤ 10 / "named before +X% gained"** — Rec: **5 sessions, ≤ 25% over 10**. Both fail today (median 27; 46 of 52 over 10) and the payoff curve does not separate them; 5 because the engine already names from the last sighting at 9 sessions and earlier naming cost no quality; 10 only if he wants room for the birth gate's second-sighting wait. Gain-at-naming (+14% today) is measurable but depends on a trend window; days from the stored cluster do not.
9. **#491 destination** — the six converts need an AI-compute home and CORZ/WULF need the RS-70 floor question answered (#491 design B2). Not a bar; flagged because the test surfaces it every night and cannot resolve it.

**Action on him: rule on 1-8. Action on me once ruled: wire the six reads + counter into the nightly
theme-quality check (#531 already runs two guards there), report against the bars, and reopen step
3 only after both signatures.**

## 6. Method and population

- **Board:** the brief's query — `SELECT DISTINCT ON (name) * FROM mi_themes WHERE theme_date >=
  CURRENT_DATE - 7 ORDER BY name, theme_date DESC`, then `stage <> 'Retired'` — captured once per
  probe on 2026-09-26/27, latest `theme_date` 2026-09-25 (117 rows on 09-25, 1 carried from 09-24)
  → **118 rows = 117 distinct groups** (Mobile SoC 09-24 and RF & Analog 09-25 hold
  identical members — a rename the 7-day window keeps). Stages 44 Mainstream / 41 Fading / 29
  Nascent / 4 Accelerating. Source 110 `live` / 8 `shadow_promoted`. 711 member slots, 672 distinct
  tickers, all 672 with ≥ 30 of 60 sessions of history; 39 tickers in 2 themes. 10 themes at 2
  members, 34 at 3, 83 of 118 (70%) at ≤ 5, 0 empty. 44 themes have no member the engine's own test
  can judge.
- **Regime — read before trending against the 09-11 board:** the 0.35 co-movement admission gate
  is live since 09-14 (139 of 589 judged members came in through it); birth gate `dedup_only` since
  09-13; Shape A (removal sites see co-movement) since 09-25. The brief's "127 themes / 9 empty / 20
  at 2 / 65% ≤ 5" is the 09-11 board; today is two weeks into a different membership regime.
- **Co-movement:** the engine's own module, imported not re-derived: SPY-subtracted daily log
  returns, 60 sessions strictly before the read date (2026-07-02 → 2026-09-25), Pearson against the
  equal-weight basket mean, leave-one-out for members, ≥ 3 basket members and ≥ 30 overlapping
  sessions; bar 0.35 read from `theme_engine.py` (`ASSIGN_COMOVE_BAR`). Bitcoin = IBIT
  (`crypto_daily_closes` dates run one day off the equity session: 0.26 aligned by date, 0.96 shifted).
- **Prices:** `mi_daily_closes` close, 2026-02-01 → 2026-09-25, ~2,500 tickers (themed since 03-01 +
  the 09-25 score board + driver ETFs). **Strength/volatility for the matched control:**
  `mi_stock_scores` 2026-09-25 (2,397 scored, 2,369 usable). **Clusters:** `mi_correlation_clusters`
  since 2026-04-01 (stored = uncovered by the board that night, by construction). **Lineages:**
  every `mi_themes` row since 2026-05-01 + `mi_theme_renames` + 73 renames parsed from
  `mi_audit_log`. **Names the system proposed:** `mi_theme_candidates_shadow` since 06-01.
  **Catalyst text:** `mi_ep_alerts` last 90 days (cross-check only; 78 of 672 members have one).
  **Labels:** `mi_theme_relevance_cohort stratum='themed'` — read LAST, cross-check only, changed
  no rule.
- **Files** (all under `scripts/probes/_655/`): grouping — `grouping/grouping_test.py`,
  `grouping_test_out.txt`, `grouping_members.tsv`, `grouping_themes.tsv`, `grouping_homeless.tsv`,
  `live_themes.psv`, `scores_0925.psv`, `overrides.psv`, `theme_history.psv`, `hist_q.sql`,
  `closes.psv`, `closes_long_miners.psv`. Identity — `identity_test.py` (+`_out.txt`,
  `identity_per_theme.tsv`, `identity_491_members.tsv`, `identity_491_rolling.tsv`),
  `identity_twokey.py` (+`_out.txt`, `_per_theme.tsv`), `identity_twokey_boardrefs.py` (+`_out.txt`),
  `identity_beta_check.py` (+`_out.txt`), `live_themes_2026-09-27.psv`, `alerts.psv`. Funnel —
  `funnel_probe.py`, `funnel_probe_out.txt`, `funnel_live_board.psv`, `funnel_themes_hist.psv`,
  `funnel_clusters.psv`, `funnel_closes.psv` (+`_q.sql`), `funnel_btc.psv`, `funnel_scores_0925.psv`,
  `funnel_churn_events.psv`, `funnel_rename_events.psv`, `funnel_renames.psv`,
  `funnel_shadow_candidates.psv`, `funnel_birth_candidates.psv`, `funnel_labels.psv`,
  `funnel_audit_event_types.psv`.
- **Bars were written into each probe's header before its first run**; reads added afterwards are
  labelled POST-HOC in the output files and are used here only to explain, never to score.
- **Docs read:** `docs/architecture/theme_engine.md`, `themes_path_forward_2026-09-13.md`,
  `theme_lifecycle_diagnosis_2026-09-13.md`, `491_theme_migration_design_2026-08-05.md`,
  `cross_industry_themes_2026-09-13.md`, `step3_theme_runway_2026-09-07.md`,
  `655_theme_sequence_evidence_2026-09-20.md`; memory notes theme-north-star, his-theme-labels,
  themes-not-judged-on-returns-yet, check-the-population-before-the-analysis.

## 7. What this does not answer

- **Whether a theme with an unpriced driver is misnamed.** Two attempts were made and both failed
  their own gates; recorded so they are not re-derived: (a) a board-wide driver test using taxonomy
  stocks or the board's own themes as references flags 31-47 of 113 themes including plainly right
  ones (Canadian Big Banks, Domestic Airlines, Regulated Gas Utilities) and does not beat a random
  alternative (real 1-3 of 7-10 vs random p95 0.33-0.40); (b) keyword stems cannot classify catalyst
  text (whole-word matching disagreed with the theme on 17 of 46; RIOT's AI lease read as crypto).
  The evidence that would unlock it is a driver label on each EP alert's catalyst — one more field on
  the call that already writes `catalyst`, no new call — his to approve.
- **Which theme a convert should move TO.** #5 names the wrong driver, not the right home.
- **Whether a theme is only its sector.** 31 of 118 do not beat a same-sector basket; no bar is
  proposed because the sector control falls back to any sector when a cell is thin.
- **Missing groups beyond stored clusters.** The homeless co-mover read was tried and is noise: 8 of
  307 strong unthemed names flag against 11 of 300 random weak ones (3% vs 4%). A typical unthemed
  stock already ties 0.54 to its best theme, so "≥ 0.35 to some theme" means nothing.
- **Short-lived births.** 33 of 100 births in 08-26..09-18 were gone within 5 sessions (Jun-Jul: 21
  of 149, 14%); reported, not barred — a funnel-health number, not a "right themes" number.
- **The 58% of births with no stored pre-birth cluster.** Their latency is unmeasured by §3.
- **Returns and trading influence (step 3).** Excluded by his ruling; nothing here touches them.
