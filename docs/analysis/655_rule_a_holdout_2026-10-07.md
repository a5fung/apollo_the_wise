# #655 rule A — hold-out check (2026-10-07)

Rule A = retire a theme after N consecutive nights failing the random-basket test (G3). His ruling 2026-10-04: WAIT — re-measure G3 after #491 (re-homing) has run three nights (Mon–Wed 10-05..10-07), then decide with a hold-out check. Re-measure (live `theme_correctness_check` rows): G3 86.2% Mon, 87.5% Tue, 85.5% Wed — still under the 90% bar. This file is the hold-out check. Read-only research; nothing here changes the engine (THE LINE — the rule is his ruling).

## Method and population

- **Rows:** every theme on the nightly board (non-Retired `mi_themes` rows) on each night, judged by the G3 random-basket co-movement test exactly as `theme_correctness_check` computes it.
- **Discovery window:** the 19 nights 2026-09-08 .. 10-02 from the #655 fix study's 10-04 capture (`scripts/probes/_655/fix_study/`), returns masked to sessions before each night; anchor = the study's own 26 retirements / 7 later-real (A3) and 23 / 4 (A5), reproduced exactly.
- **Hold-out window:** the 3 live nights 2026-10-05 .. 10-07, read from the stored `theme_correctness_check` rows (every theme's verdict kept in their detail) and cross-checked by a full rebuild from prod inputs (360 of 360 verdicts match).
- **Sizes:** n = 101–133 judgeable themes per discovery night (19 nights); n = 116–124 per hold-out night (3 nights); retirements n = 26 (3-night rule) and n = 23 (5-night rule) on discovery.
- **"Later proved real":** the study's definition — a retired theme that later passes the G3 test on the live board.

## 1. PRE-STATEMENT (written 2026-10-07 18:35 PDT, before any hold-out number was pulled or computed)

**Candidate rules (no parameter tuned on any result below):**
- **A3** — the studied rule: a theme in the G3 fail list on 3 consecutive nightly reads is retired that night. Streak logic exactly as `scripts/probes/_655/fix_study/verify_c.py`: a night on the board in the fail list adds 1, a night on the board NOT in the fail list resets to 0, a night off the board leaves the streak unchanged; once retired, a name stays retired.
- **A5** — the one alternative: the same rule with 5 consecutive nights. Chosen because the study already has discovery numbers for it (verify_c: 4 later-real themes killed, G3 passes 15/19 nights), so the hold-out comparison is like for like with no new discovery tuning. (The other candidate, "3 nights AND no RS average", was not chosen: it has no discovery baseline.)

**Windows:**
- **Discovery** = the 19 nights 2026-09-08..10-02 the study replayed (its 10-04 capture, excess returns masked to sessions before each night — verify_b/verify_c's method). Anchor before anything else: re-running verify_c's logic must give A3 = 26 retirements / 7 later-real, A5 = 23 / 4.
- **Hold-out** = the three nights the study never saw: Mon 10-05, Tue 10-06, Wed 10-07 (the latest night in prod). Per-theme G3 verdicts come from the live `theme_correctness_check` rows if the stored detail kept them; otherwise from a per-night rebuild with the same `compute_g3` (board = latest row per name within 7 days minus Retired, ordered by name as `get_active_themes` returns it; 60-session window strictly before the night; scores at the latest score date on or before the night), checked against the live row's headline count.
- **Two framings on the hold-out:** (a) **switched on Monday 10-05** — streaks start at zero on 10-05, so A3 can first act on 10-07 and A5 cannot act at all; (b) **running since 09-08** — streaks carried from the discovery simulation into 10-05..10-07 (the steady state).

**Measures (per window, per rule):**
- G3 pass rate by night after the rule, **drift-free** as verify_c: survivors keep that night's verdicts; rate = passing survivors / judgeable survivors; bar ≥ 90%.
- Themes the rule retires in the window (count + names).
- **"Later proved real" — the study's definition, unchanged:** retired by the rule during the window AND still on the board on the window's final night AND passing G3 that night (verify_c: `n in board(last) and n not in fails[last]`). Discovery final night = 10-02 (the study's), re-judged also at 10-07 as the forward check on the cost claim. Hold-out final night = 10-07.
- Cost in the study's terms = the count and names (with member count) of later-real themes killed.

**Caveats declared before the numbers:**
- **Horizon.** A theme retired on 10-07 has zero nights left to prove real, and one retired 10-05 has two. The hold-out's own later-real count is therefore structurally near zero and is NOT evidence the rule is safe. The out-of-sample test of the cost claim is the forward check: are the discovery window's later-real kills (Wealth Management and the other six) still on the board and still passing G3 on 10-05..10-07?
- **Regime.** Hold-out boards run with rule B (small weak-Fading retire, with the one-night wait) and #491 re-homing live; discovery boards had neither. Rule A's hold-out effect is therefore an effect on top of B — compare it to the study's A+B row, not A alone.
- **Retired names stay retired.** As in the study, a retired name is not allowed back; a re-mint under a new name is not modelled.

## 2. RESULTS

**Anchor (before anything else):** re-running the study's discovery replay on its own capture reproduces it exactly — A3 26 retirements / 7 later-real / G3 17 of 19 nights; A5 23 / 4 / 15 of 19 (`a_discovery_anchor.out`). The live G3 maths is unchanged (the 103/118 anchor test passes).

**Hold-out verdict source:** the live `theme_correctness_check` rows kept every per-theme verdict (detail 24–29k characters, not truncated), so the hold-out uses exactly what the nightly check said. Cross-check: rebuilding 10-05, 10-06 and 10-07 from pulled inputs reproduces every per-theme verdict (116/116, 120/120, 124/124), and the full recompute after each rule gives the same G3 as the drift-free figure on every hold-out night (the random stream shifts, no verdict flips) (`d_recompute_check.out`).

| Window | Rule | Nights G3 ≥ 90% | Themes retired | Later-real themes killed (study's definition) |
|---|---|---|---|---|
| No rule (live) | — | 0 of 3 hold-out nights (86.2 / 87.5 / 85.5%) | — | — |
| Discovery 09-08..10-02 | A3 | 17 of 19 (misses = first 2 nights, before any 3-night streak exists) | 26 | 7 at 10-02 → **8 at 10-07** |
| Discovery 09-08..10-02 | A5 | 15 of 19 (misses = first 4 nights) | 23 | 4 at 10-02 → 6 at 10-07 |
| Hold-out, running since 09-08 | A3 | **3 of 3** (94.1 / 94.3 / 91.6%) | 5 new | 0 — horizon 0–2 nights, not evidence of safety |
| Hold-out, running since 09-08 | A5 | 2 of 3 (91.5 / 91.0 / **88.5%**) | 2 new | 0 — same caveat |
| Hold-out, switched on Mon 10-05 | A3 | 1 of 3 (only 10-07 can act: 92.2%) | 9 (all on 10-07) | cannot be judged (0 nights left) |
| Hold-out, switched on Mon 10-05 | A5 | 0 of 3 | 0 | — |

**Regime comparison (promised in §1):** the hold-out boards already run rule B, so the like-for-like discovery figure is the study's A+B row — verify_c K=3 A+B passes G3 on 17 of 19 nights, the same as A alone (K=5 A+B: 15 of 19). B did not change what A does to G3 in discovery, and the hold-out A3 result (3 of 3 once running) matches that steady state.

**Forward check — the study's cost claim on nights it never saw (A3):**
- Still on the board AND passing on 10-07: **Wealth Management & Retail Brokerage Platforms (12–14 members, passes all 3 nights)**, Post-Acute & Home-Based Healthcare Services (6–8, all 3), Cloud Data Storage & Analytics Infrastructure (3, all 3), Cloud Supply Chain & Warehouse Management Software (3, all 3), Life Sciences & Healthcare Data/CRM Platforms (3, 2 of 3).
- No longer real: Digital Advertising & Ad-Tech Monetization Platforms (shrunk to 2 members, fails all 3 — A3 switched on Monday would retire it again on 10-07); Consumer PC & Gaming Hardware Refresh Cycle (off the board).
- Newly real by 10-07: Industrial Construction Execution & On-Site Supply Chain (10 members, passes 10-06 and 10-07), Liquid Biopsy & Molecular Cancer Diagnostics Testing (4, passes 10-06 and 10-07), Diabetes Management Devices (3, passes 10-07 only, 0.004 above the line — a coin flip).
- A5's later-real kills at 10-07: Cloud Data Storage, Cloud Supply Chain, Life Sciences, Industrial Construction, Liquid Biopsy, Diabetes (6).

**What A3 retires on the hold-out:**
- Running since 09-08 (5): Bitcoin Mining Stocks Rotation Reversal (3, Fading, no RS average) and Specialty Biopharma Clinical & Commercial Breakouts (3, Nascent, RS 96.8) on 10-05; Fintech Payments, Prepaid & Consumer Digital Banking Apps (3, Nascent, RS 90.5) on 10-06; Latin America Telecom & Pay-TV Services (2, Fading, no RS average) and Programmatic Advertising & Cloud Communications API Platforms (2, Nascent, RS 91.2) on 10-07.
- Switched on Monday (9, all 10-07): the five above plus Digital Advertising & Ad-Tech (2, Mainstream, RS 92.9), Digital Dollar & Crypto Payments Infrastructure (2, Mainstream, 92.7), Emerging Medical Device Innovators Breakout (3, Mainstream, 84.6), Enterprise Unstructured Data Storage Infrastructure (3, Mainstream, 95.9). **7 of the 9 are strong-RS Mainstream/Nascent themes; 3 are Nascent** — the early-theme class the north star protects.

**Where the G3 shortfall sits:** every G3 fail on 10-07 is a 2–3-member theme (18 of 18; 15 of 16 on 10-05, 14 of 15 on 10-06) — the same picture the study found.

## 3. CONCLUSION

- **Rule A3 still fixes G3 out of sample** — every hold-out night passes once it has been running (94.1 / 94.3 / 91.6%), but with 2–5 themes of margin; switched on Monday it acts first on Wednesday.
- **Its cost held out of sample:** 5 of the 7 themes the study said it would wrongly kill are still on the board and passing three nights later, Wealth Management (14 members) among them, and 3 more of its retirements have since passed — about 1 real theme killed for every 3 retired (8 of 26).
- **A5 is cheaper but does not hold the bar:** it fails 10-07 (88.5%) and does nothing for its first four nights.
- **Recommendation (his call — the rule is his ruling):** leave rule A off; it buys the G3 pass by retiring real and early strong-RS themes at the same rate on unseen nights, and the shortfall is entirely 2–3-member themes, so a fix belongs there.

## What this does not answer

- Whether the hold-out's newly retired themes would have proved real — three nights is too short; 0 killed there is not evidence of safety.
- What a fix aimed at the 2–3-member themes (where every 10-07 G3 fail sits) would do — not tested here.
- Anything about returns: themes are judged on correctness, not on trading results (his standing rule).

## 4. FILES

- `scripts/probes/_655/rule_a_holdout/a_discovery_anchor.py` / `.out` — discovery anchor (reproduces the study).
- `scripts/probes/_655/rule_a_holdout/b_holdout_pull.py` / `.out` — the one read-only prod pull (pickle kept in the scratchpad, not the repo).
- `scripts/probes/_655/rule_a_holdout/c_holdout.py` / `.out` — hold-out table, retirements, forward check.
- `scripts/probes/_655/rule_a_holdout/d_recompute_check.py` / `.out` — rebuild = live (every verdict), full recompute = drift-free.
