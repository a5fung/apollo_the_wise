# #655 scope — the 2–3-member themes and the remaining churn (2026-10-10)

Scope only: nothing here is built, and nothing changes the engine. Both questions lead to a rule change that is his call (THE LINE does not apply — no money — but his 10-07 ruling says this goes to him, not built unasked). His sequence: (1) right themes, (2) early enough, (3) only then trading. North star: subtle RS → early theme → buy before mainstream, so **killing a small EARLY theme has a real cost** and every option below is scored on it.

## Method and population

- **One read-only prod pull** (`scripts/probes/_655_scope/capture.sh` → `capture.raw.gz`, $0): every `theme_correctness_check` row, every theme audit row since 09-14, `mi_themes` since 06-15, ecosystem map, industries, scores 09-25..10-09, closes 05-15..10-09.
- **Q-A population:** the last 10 nightly correctness rows (09-28 .. 10-09, 17:31 ET; the 09-28 00:12 manual run is left out) — **1,237 judged theme-nights, 489 of them 2–3-member themes**. Anchor: rebuilding each night's G3 from the capture gives **1,237 of 1,237 verdicts identical** to the stored rows (`a0_anchor.out`), so the replays below use the live maths.
- **Regime caveat:** rule B (small weak-Fading retire) went live 10-05, so the count of 2-member themes drops 15 → 4 on 10-05 and climbs back to 14–15 by 10-07 (the one-night wait).
- **Q-B population:** the last 14 engine nights (09-22 .. 10-09) — **154 times a theme left the board; 31 same-name returns (27 themes); 20 returns under a new name within 7 days** (Jaccard ≥ 0.5 to the removed members).
- **Option replays are per night on the real board, not cumulative** (a theme folded on night 1 is folded again each night it is still there) — a steady-state picture, not a day-by-day simulation.
- **"A co-moving group"** = passed the random-basket test (G3) on at least one of the 10 nights — the rule-A study's "later proved real" definition. **"Strong early"** = Nascent with RS ≥ 80 on the night the option takes it.
- Ecosystem map has no date column: today's mapping is applied backward (affects option iii only).

## Question A — the 2–3-member themes

**What the 10 nights show** (`a1_g3_by_size.out`, `a5_control_by_size.out`):
- **144 of the 152 G3 fails are 2–3-member themes** (50 at 2 members, 94 at 3); themes with 4+ members pass 98.6–100% every night (n = 70–77 a night).
- Only 345 of 489 small theme-nights pass (70.6%).
- **The failures are real, not a test artefact:** the random bar is already size-matched (median 0.41 for 2 members, 0.27 for 3, 0.12 for 6+), and failing small themes have a median cohesion of 0.15 against 0.50 for small themes overall. Their members do not move together.

**Do small themes grow?** (`a2_regrowth.out`, births 07-01..09-25, watched to 10-09):
- **246 themes were born with 2–3 members** (99 at 2, 147 at 3; 232 were born at 4+).
- **59 of the 246 later reached 4+ under the same name** (16 of 99 two-member births, 43 of 147 three-member births). Among them: U.S. Apparel & Fashion Recovery (2 → 16), Consumer Fintech (2 → 16), Private Equity & Alt Asset Mgmt (2 → 13), AI-Powered Enterprise Analytics (3 → 20), Genomics & DNA Sequencing (3 → 12), On-Site Power Generation for Data Centers (3 → 11), Bitcoin Mining Stocks Rotation Reversal (3 → 10).
- **139 of the 246** had at least half their founding members inside a 4+-member theme (any name) within 30 days.
- The 59 took a **median of 5 engine nights** to reach 4 members (middle half 1–9, longest 28); 28 took more than 5.

**Options** (`a3_options.out`, `a4_fold*.out`, `a6_costs.out`; baseline G3 passes 1 of 10 nights at 84.4–90.7%, G4 passes 2 of 10 at 3.4–12.3%):

| Option | Rule or fix | G3 (≥ 90%): nights passing, range | G4 signed (≤ 10%): nights passing, range | Themes taken off (distinct, 10 nights) | of them a co-moving group | strong early taken | Cost / note |
|---|---|---|---|---|---|---|---|
| (i) birth minimum of 4 | rule change (3 lanes: discovery's 2, promote's 3, operator promote's 3; also contradicts the strong-pair design) | 10 of 10, 92.6–95.2% | 10 of 10, 1.1–7.4% | 75 | 53 | **18** (e.g. Liquid Biopsy, Vaccine Developers, International Telecom RS 98, Alternative Asset Managers RS 92) | the 59 growers are born ~5 nights later at best — and maybe never, since they grew by assignment INTO a theme that would not exist. Replay is optimistic. |
| (i-b) birth minimum 3 + co-movement test | rule change; **the membership test cannot judge a 3-member group** (its basket would be 2 names → "thin basket"), so the test would have to be G3's own random-basket check, run at birth | 10 of 10, 92.7–95.8% | 10 of 10, 1.9–9.1% | 36 | 14 | **12** (Liquid Biopsy, Alternative Asset Managers, CAD/PLM, Specialty Biopharma Breakouts RS 99 …) | every 2-member birth waits for a 3rd member or a 4th; needs new birth-path code |
| (ii) score G3 on 4+ members only, report small themes apart | **measurement change — it changes the signed bar's population; his call** | 10 of 10, 98.6–100% (n 70–77) | unchanged: 2 of 10 | 0 | — | 0 | hides a real fault: small themes pass only 60.0–79.2% a night (n 43–59), and their failures are real (cohesion 0.15) |
| **(iii) fail-only fold: a 2–3-member theme that fails G3 tonight is dissolved; members that pass the membership test (≥ 0.35) with the closest same-ecosystem 4+-member theme move there, the rest are released. Folds when at least half the members pass — for a 2-member theme that is ONE of the two (the pair dissolves, the other stock is released). Home picked by #505's closeness ranking AND its minimum (shares a member, or ≥ 50% industry overlap)** (`a4_fold_min505.out`) | rule change | **10 of 10, 91.9–95.9%** | 7 of 10, 1.9–11.8% | 21 (77 of 144 failing small theme-nights folded) | 7 | **2** (Alternative Asset Managers, Liquid Biopsy) | homes: Liquid Biopsy → Genomics & DNA Sequencing; Bitcoin Mining Rotation Reversal → Bitcoin Treasury proxies; Diabetes Devices → Medical Device rotation. 7 of 21 taken were co-moving groups on another night — **1 in 3, the same ratio rule A was turned off for (8 of 26)**; the difference is that the stocks are re-homed, not deleted, and far fewer strong early themes are taken. No home turned into a G3 fail on any night. |
| (iii) same, without #505's minimum (`a4_fold.out`) | rule change | 10 of 10, 92.1–96.4% | 7 of 10, 1.9–11.9% | 25 | 10 | 3 | adds poor homes, e.g. Life Sciences CRM → Cloud Contact Center |
| (iii) same, only after 2 failing nights | rule change | 8 of 10, 89.1–95.1% | 6 of 10 | 17 | 5 | 5 | the one-night wait buys little and loses the margin |
| (iii) same, strict (every member must pass) | rule change | 1 of 10 | 3 of 10 | 8 | 2 | 1 | failing small themes rarely have all members co-moving with one home — almost nothing folds |
| (iii) fold every small theme, failing or not | rule change | **0 of 10, 81.1–89.8%** | 9 of 10 | 69 | 63 | 8 | makes G3 worse: it folds the passing small themes and leaves the failing ones — reject |
| (iv) small-only probation: a 2–3-member theme failing G3 3 nights running is retired | rule change (rule A limited to small themes) | 8 of 10 (90.3–97.5% once running) | 6 of 10 | 19 | 5 | **7** | kills Liquid Biopsy (passed every night after reaching 4), Bitcoin Mining Rotation Reversal, Diabetes Devices, Digital Ad-Tech; members are released, not re-homed |

**Recommendation — (iii) fail-only fold, with #505's minimum.** This narrows the task's (iii) to failing nights, because folding every small theme drops G3 to 81–90%. It is the only option that passes G3 on all 10 nights while taking the fewest strong early themes (2, against 18 / 12 / 7). Its kill ratio is no better than rule A's (1 in 3 taken were co-moving groups); what makes it acceptable is that those stocks land in their closest co-moving theme instead of leaving the board. That fits "right themes first" without paying much in step 2. **It must ship with Q-B's re-mint cooldown**: today's Pass 1.5 already does a fold of this kind, and 8 of its 20 removals in the 14 nights were re-made within a week (same name or a new name).

## Question B — the remaining churn

**Cause of each same-name return** (`b1_churn.out`, `b2_returns.out`, `b5_flip_returns.out`; 31 same-name returns, 14 nights):
- **Pass-2 sector cap: 10** — 7 are ruling (a)'s case (≥ 3 members judged, none moves with the top theme), 2 are the 10-07 self-comparison bug (both fixed 10-09, built, ship in Saturday's deploy), 1 is a theme that reached the cap with only 2 members (Appalachian Natural Gas Producers, 10-01).
- **Pass 1.5 absorption: 6** (and 3 more re-made under a new name).
- **Merge-pass removal with no audit row of its own: 4** — 09-22 and 09-24, before the cap wrote rows; all four names hit the cap keywords "gas" / "space" / "satellite", so they are probably cap drops. Cannot be confirmed.
- **Rule B: 4; Arm-B thesis merge: 2; 5-night Fading retire: 2; renames: 2; empty shell: 1.**
- **26 of the 31 came back through the nightly shadow-promote lane.** That is the loop: a removal step takes a group off, and the promote lane puts it back the next night. The birth gate's verdicts on those return nights are mixed (birth, held, and several join verdicts on nights the name still came back, e.g. through a sibling cohort renamed to it), so which gate path lets each one through is not pinned here — see below.

**Options:**

| Option | Rule or fix | Same-name returns removed (of 31) | New-name re-mints removed (of 20) | Cost |
|---|---|---|---|---|
| Ruling (a) keep rule + 10-07 self-comparison fix | his ruling + bug fix — **built 10-09** | 9 | 3 | none new |
| **Re-mint cooldown at the birth gate: a cohort removed in the last 5 nights (merge, cap, retire) is joined to where its members went, unless it comes back with ≥ 1 new member** (`b7_cooldown.out`) | rule change (birth gate) | 12 (Pass 1.5: 4, un-rowed merge drops: 4, Arm-B: 2, rule B: 1, 2-member cap: 1) | 1 | blocks a comeback that did not grow; 6 of the 13 blocked came back as a co-moving group (6 have no G3 read) — mostly duplicates of a theme their members already sit in, but **Appalachian Natural Gas Producers (10-01) is a wrong block**. Of the 13 returns it allows, 11 came back bigger (e.g. AI data-center power 2 → 10, Coal Mining 2 → 4) and 2 after more than 5 nights. |
| Membership test at Pass 1.5 (ruling (a) carried over) (`b6_pass15_test.out`) | rule change | 0 — keeps 0 of the 20 Pass-1.5 removals; the absorbed members already sit in, or move with, the absorbing theme | 0 | reject: Pass 1.5 removes the right things; the return is the fault |
| Word-start keyword matching, parked items 1 + 2 (`b3_wordstart.out`) | rule change | 0 | 0 | changes the cap group of 3 of 242 live names: 2 "Aerospace" themes leave the satellite group (right), 1 "Biopharma" theme leaves biotech (wrong); the ecosystem fallback mapped 14 live names and word-start changes 0 — park |
| Collapse a re-minted newborn into its same-named incumbent before the merge, parked item 3 (`b4_shells.out`) | fix | 0–1 | 0 | 2 same-name empty shells in 14 nights; 1 removed the 19-member Global Oil & Gas theme on 10-07, and the 10-09 Pass-2 guards already cover that case — low value now |

**Recommendation — the re-mint cooldown, after ruling (a) ships.** With ruling (a) the cap churn is gone; what remains is mostly the promote lane re-making what Pass 1.5, Arm B or the cap removed the night before. A theme that blinks on and off is not a right theme (step 1). Each blink also restarts the theme's age, so the early-naming read (step 2) cannot trust it. The cooldown lets any group that has grown come back, so the north-star case (a small group gaining members) is not blocked. It is also what lets the Q-A fold stick.

## What this does not answer

- **Whether option (iii)'s folded themes were real *distinct* themes** — co-moving with a bigger theme does not prove they are not a sub-theme of it. #505's parent pass is the tool for that; not tested here.
- **What a birth minimum does over time:** the replay removes themes; it cannot show the themes that would never have grown without a home.
- **The 4 un-rowed exits of 09-22 / 09-24** are probably cap drops, but cannot be shown to be.
- **The 5-night cooldown length was not tuned** — 5 is rule B's and the Fading grace's horizon, chosen before the run.
- **Which birth-gate path lets each return through.** One candidate is in the code: when more than half of a cohort's members are already in live themes, the join check is skipped and left to the merge steps, which Pass 1.5 belongs to. The return-night gate rows do not confirm it for every case.
- **Settled G4** (his 10-08 ruling: themes in rule B's waiting night left out) was not computed for any option; only the signed G4 is shown.
- **Overlap with rule B:** option (iii) acts on the same small themes rule B retires, one or more nights earlier, so B's nightly retirements would fall. Not measured.
- **Returns:** nothing here is judged on trading results (his standing rule).
- **Ruling (a)'s live effect** is Monday 10-12's verify; the 9 returns credited to it here come from the replay, not from live nights.

## Files

`scripts/probes/_655_scope/`: `capture.sh` / `q1_capture.sql` (the one pull) · `load.py`, `board.py` (shared) · `a0_anchor` (rebuild = live) · `a1_g3_by_size` · `a2_regrowth` · `a3_options` (i, i-b, ii, iv) · `a4_fold` (+ `a4_fold_*.log` per-night folds; `--min505` = the recommended variant, `--fail2` = the two-night variant) · `a5_control_by_size` · `a6_costs` · `b1_churn` · `b2_returns` · `b3_wordstart` · `b4_shells` · `b5_flip_returns` · `b6_pass15_test` · `b7_cooldown` (each `.py` + `.out`).

## Verifier corrections (2026-10-10, independent re-derivation; `scripts/probes/_655_scope/verify/`)

The recommendations stand; these numbers in the tables above are superseded:

| Option | G3 nights passing | G4 nights passing | Themes taken | Strong early lost | Of those taken, later reached 4+ |
|---|---|---|---|---|---|
| (i) birth minimum 4 | 10/10 | 10/10 | 75 | 18 | 9 |
| (i-b) minimum 3 + co-movement | 10/10 | 10/10 | 36 | 12 | 5 |
| (ii) G3 on 4+ only (measurement) | 10/10 | 2/10 | 0 | 0 | — |
| (iii) fold failing small themes | 10/10 (91.9–95.9%) | 7/10 | 21 | 2 | 7 |
| (iv) retire after 3 failing nights | 9–10/10 (with earlier nights seeded) | 7–8/10 | 20 | 7 | 9 |
| fold EVERY small theme (half pass, #505 minimum) | 9/10 | 7/10 | 69 | 8 | 13 of the 59 growers |

- (iii) moves at least one stock on 63 of its 77 fold theme-nights; on 14 the passing members already sit in the home, so the theme is simply removed.
- (iii)'s lead over (iv) is on strong early themes taken (2 against 7) and on moving stocks into a home; on "later grew" it does not lose the fewest. Liquid Biopsy is taken by both (iii) and (iv).
- The 2-failing-nights variant of (iii) failing 09-28 is a start-up effect (no earlier night in the window).

Churn (Q-B), measured on the board: 151 removals, 29 returns (the 2 renames excluded). The 5-night re-make block removes **8 confirmed** returns, plus 4 of unknown cause (09-22/09-24, no audit row; probably cap drops that ruling (a) may already cover) — 8–12, not 12. Its cost is **at least 2 wrong blocks** of real groups that came back passing G3 (Appalachian Natural Gas Producers 10-01 — 7 members, the cap row judged 2 — and Small Modular Reactor, 4 members, no overlap with any board theme), and 2 more doubtful (AI Data Services, Semiconductor Process Instruments share only 1 of 3 members with a board theme).
