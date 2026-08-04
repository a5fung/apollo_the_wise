# Theme birth RS-floor replay — fresh-cohort derivation (2026-08-03)

> **Evidence, not a change.** This doc answers the operator's ruling on the birth-gate floor
> ("start at RS ≥ 70, but DERIVE the final number from the replay before it ships") and his
> named risk ("a genuinely EARLY theme may be born WEAK and strengthen later… if weak-born
> themes mature, the floor needs a TRAJECTORY term rather than a LEVEL"). Any change to the
> gate cell still goes through CHANGE_PROCESS + operator sign-off — themes are no-money but
> feed the judge and allocation. Prior all-time derivation (254 births):
> `docs/analysis/theme_birth_gate_derivation_2026-07-27.md`. Rerunnable script:
> `scripts/probes/_theme_birth_rs_floor_replay.py` (`--fetch` re-pulls prod).

## Verdict in one paragraph

**A flat RS ≥ 70 floor is decisively rejected by the June–August cohort — it would have
truly lost 17 of this cohort's 59 maturing themes (29%), including north-star cases born in
the 20s–30s that later exceeded RS 85.** The operator's own suspicion is confirmed: weak-born
themes mature at a ~48% rate (21 of 44 born < 70), and blocking them needs a trajectory
term. **The shipped OR-cell (RS ≥ 70 OR pre-birth 5-session ΔRS ≥ 0) survives the fresh
replay**: real losses fall 17 → 7, and only 2 of those 7 ever became genuinely strong
(RS ≥ 85). The level number itself is nearly irrelevant once the rising arm exists — τ = 65,
70, 75 give **identical** results on this cohort — so **keep 70**: the data cannot
distinguish it from 65 or 75, but it can reject a flat floor at any τ and can reject τ = 80.
The remaining open parameter is the rising-arm threshold δ (0 vs mildly negative), which
this cohort cannot settle without overfitting one market episode; the observe-mode forward
review (`theme_birth_gate_observe_calibration`) is the right instrument for it.

## 0. Population, measurement, and instrument corrections

- **Population**: 178 births since 2026-06-01 (birth = `MIN(theme_date)` per `name`; matches
  the operator-verified counts: 126 born in July, 71 of them on the 2026-08-03 board).
  Empirical fact: **zero births June 1–21 — the birth wave starts 2026-06-22** (every
  early-June board theme predates June). Data end = 2026-08-03 (4,065 `mi_themes` rows,
  283 all-time names).
- **⚠ Stored `mi_themes.rs_avg` cannot be used raw at birth** (verified empirically, again):
  - **33 of 178 births carry a sentinel 0.0** (the `rs_scores else 0` fallback; their true
    member-level RS medians 52.2 — e.g. European Bank Stocks stored 0.0, member-level 78.1).
    No theme is ever < 5 two days running: rs < 5 is a sentinel, not a measurement.
  - **NULL rs_avg is a stage artifact**: Fading/Retired rows never carry it (226/226 Retired,
    664/788 Fading NULL); active-stage rows always do.
  - Units: `rs_avg` is 0–100 percentile; `pct_above_20sma` in the SAME row is a 0–1
    fraction. Checked before comparing anything.
- **Measurement used throughout: member-level cohort avg `rs_composite` at birth date**
  (one prod join vs `mi_stock_scores`) — this is exactly what the shipped gate reads
  (`db.get_cohort_rs_snapshot`), and it recovers the 33 sentinel births. Where stored
  rs_avg is valid it matches member-level almost exactly (n=145, median |diff| 0.0,
  p90 1.7), and valid day-1 stored values are stable into day 2 (median |Δ| 1.6, p90 8.4)
  — so "day one noise" is a sentinel/NULL problem, not a jitter problem, and **birth day
  itself is the measured day** once measured at member level.
- **Outcome frame**: a theme's first lifecycle only (rows before any > 7-calendar-day
  absence — `get_active_themes(stale_after_days=7)` makes absence the death signal; dying
  is silent, missing rows are the outcome, not missing data). One June+ name re-minted
  after a gap (Quantum Computing Hardware & Software, 10d) and is split accordingly.
  Snapshots are trading-day only, so weekend gaps never false-trigger.
- **Survivorship control**: every windowed outcome uses an equal **W = 15 calendar-day
  window from birth**; births after 2026-07-19 are **censored** (66 of 178).
  **Classifiable population: n = 112.**

## 1. Distribution of birth RS, and what each floor blocks

All 178 births (member-level birth RS): median 82.8, p25 49.2, p10 23.1.

| floor τ | blocks (all 178) | blocks (classifiable 112) |
|---|---|---|
| 60 | 58 (32%) | 38 (34%) |
| 65 | 61 (34%) | 41 (37%) |
| 70 | 66 (37%) | 44 (39%) |
| 75 | 72 (40%) | 47 (42%) |
| 80 | 81 (45%) | 54 (48%) |

Any flat floor in the candidate range blocks a third to a half of all births. Whether that
is good depends entirely on what the blocked themes would have done (§2–§4).

**Maturity by birth-RS band (classifiable, W=15d; "mat" = staged OR lived14, see §2):**

| band | n | matured | rate |
|---|---|---|---|
| 0–40 | 23 | 7 | 30% |
| 40–55 | 10 | 6 | 60% |
| 55–65 | 8 | 6 | 75% |
| 65–70 | 3 | 2 | 67% |
| 70–75 | 3 | 0 | 0% |
| 75–80 | 7 | 6 | 86% |
| 80–85 | 15 | 5 | 33% |
| 85–90 | 9 | 6 | 67% |
| 90–95 | 21 | 11 | 52% |
| 95–101 | 13 | 10 | 77% |

Matured median birth RS 83.7 vs not-matured 77.2. **No monotone trend — the 55–65 band
matures at 75% while 80–85 matures at 33%.** The level is a weak instrument (rank AUC
0.626), replicating the 7/27 all-time finding (medians 90.8 vs 88.5 there). The only band
where the level genuinely bites is **< 40, where 70% die** — and even there the exceptions
are the most north-star-shaped themes in the whole cohort (§2).

## 2. The weak-born: do they mature or die?

**Maturity definitions** (all measured inside the 15-day window; reported separately
because they disagree in degree):

- **staged** — reached Accelerating or Mainstream (51/112 overall);
- **lived14** — still being emitted ≥ 14 days after birth, i.e. survived the 7-day age-out
  twice over (58/112);
- **strong85** — any post-birth active-day rs_avg ≥ 85: "became genuinely strong", the most
  north-star-aligned bar (66/112);
- **mat** (headline) = staged OR lived14 (59/112). A "rose ≥ +10 from birth" definition was
  also computed but is not led with — it mechanically favours weak births (headroom bias).

**Of 44 classifiable births below 70: 21 matured (48%). Weak-born themes are 36% of ALL
themes that matured.** They are emphatically not junk-by-default. Named examples, all
verified in the row history:

- Domestic Steel Producers — born RS **27.8**, +64 RS in 3 active days, 19 snapshots.
- Bitcoin Mining & Crypto Infrastructure Operators — born **30.1** → staged + strong85.
- U.S. Domestic Steel Producers — born **34.6** → staged + strong85.
- Insurance Brokerage & Distribution Services — born **38.9** → staged, lived 26 snapshots,
  strong85. Truckload & LTL Freight (48.9), Franchise Auto Dealerships (53.3), Wealth
  Management Platforms (51.0), U.S. Petroleum Refining (65.2) — all strong85.

9 of the 44 weak-born reached RS ≥ 85 — born bottom-half, ended top-decile. **That is the
exact subtle-RS → early-theme → matures chain the north star hunts, and a flat floor at
any candidate τ kills every one of them at birth.**

The weak-born who died look different in trajectory, not in level:

| weak-born (<70) | n | pre-birth Δ5 median | rising share | post-birth Δ (3rd active day) |
|---|---|---|---|---|
| MATURED | 21 | **+0.8** | 12/21 | **+15.9 median** |
| died | 23 | **−5.3** | 10/23 | undefined — corpses go Fading by day 2–3 |

The post-birth column is the sharpest fact in the table: **a dying weak-born theme
almost never has a third active-RS day** (it flips to Fading, rs_avg goes NULL, then
retires ~day 7), while weak-born maturers are already +16 RS by their third active day.
Post-birth trajectory and survival are nearly the same variable.

## 3. Level vs trajectory — the decisive comparison

Rank AUC for predicting maturity (mat), classifiable cohort:

| predictor | n | AUC |
|---|---|---|
| birth RS level | 112 | 0.626 |
| birth RS level, weak-born only | 44 | 0.787 |
| pre-birth 5-session cohort ΔRS (gate-visible at decision night) | 112 | 0.537 |
| pre-birth Δ5, weak-born only | 44 | 0.578 |
| post-birth ΔRS at 3rd active snapshot (survival-conditioned; needs a 3-day deferral) | 62 | 0.567 |

Honest reading, sharper than "trajectory wins":

1. **No single variable predicts maturity well.** Level 0.626 overall is weak;
   pre-birth Δ5 alone is near-noise on this cohort (0.537) — weaker than the 7/27
   all-time separation suggested (+2.5 vs −5.3 medians there; +0.8 vs −5.3 here, rising
   share 57% vs 43%).
2. **But the OR-composition works anyway**, because the rising arm's job is not
   prediction — it is a *rescue valve for the exact class the level mis-handles*:

| cell (classifiable, maturity=mat) | blocked | FN (matured) | TP (corpse) | FN % of all matured | precision |
|---|---|---|---|---|---|
| RS ≥ 70 flat | 44 | 21 | 23 | **35.6%** | 52% |
| RS ≥ 60 OR Δ5 ≥ 0 | 21 | 8 | 13 | 13.6% | 62% |
| **RS ≥ 65 / 70 / 75 OR Δ5 ≥ 0** | **22** | **9** | **13** | **15.3%** | **59%** |
| RS ≥ 70 OR Δ5 ≥ +3 | 29 | 13 | 16 | 22.0% | 55% |
| RS ≥ 70 OR Δ5 ≥ −5 | 19 | 7 | 12 | 11.9% | 63% |
| RS ≥ 70 OR Δ5 ≥ −8 | 14 | 6 | 8 | 10.2% | 57% |

   Under the north-star bar (maturity = strong85) the contrast is starker: flat-70 FN =
   9/66 (13.6%) at 80% precision; the OR-cell FN = 3/66 (**4.5%**) at 86% precision.
   Definitions disagree on how bad flat is; **every definition agrees on the ordering:
   OR-cell dominates flat at every τ.**
3. **τ = 65, 70, 75 are literally identical on this cohort** (the rising arm rescues the
   65–75 sliver either way). The level number is not the load-bearing part of the cell.
4. **A post-birth trajectory term is real but operationally different**: it requires
   birthing provisionally and confirming ~3 days later. Since dying weak-borns rarely have
   a 3rd active day at all, a "provisional birth, confirm day 3" arm would separate well —
   but the existing machinery already approximates it for free: blocked cohorts that keep
   strengthening RE-PRESENT (Lane-1 re-emission / re-mint) and pass on a later sighting
   with Δ5 risen (§4's steel case, +13 days). No new mechanism is needed to get most of
   the post-birth arm's value.

## 4. The cost of each floor — what "blocked" actually does

Raw FN counts overstate the cost: the gate's join-or-new step sits BEFORE the floor, and a
blocked cohort can re-present later. Ticker-overlap dissection (intersection-over-smaller
≥ 0.5; LIVE join = target still on the board under the 7-day recency cap — suppression is
free; ledger-only joins are counted as losses):

**Flat RS ≥ 70** — blocked 44 → 21 matured. 4 of the 21 join a live theme (U.S. Domestic
Steel → Domestic Steel ov=1.0; Precious Metals Royalty → PM Gold & Silver ov=1.0; Global
Crude Tanker → Crude & Product Tanker ov=1.0; Bitcoin Mining → Crypto Asset Recovery
ov=0.5). **17 maturing themes truly lost — 29% of everything that matured — versus 23
corpses stopped (3 of which would have joined anyway). Roughly one real winner destroyed
per 1.2 corpses stopped: rejected.**

**RS ≥ 70 OR Δ5 ≥ 0 (the shipped cell)** — blocked 22 → 9 matured, of which:

| blocked maturer (birth RS / Δ5) | resolution |
|---|---|
| Bitcoin Mining & Crypto Infra (30.1 / −30.0) | JOINS live Crypto Asset Recovery — free |
| Domestic Steel Producers (27.8 / −27.8) | RESCUED: re-mint passes 13 days later, matures to strong85 — delay, not loss |
| CRE Brokerage & Advisory (37.4 / −12.1) | LOST |
| Insurance Brokerage & Distribution (38.9 / −2.0) | LOST (reached strong85) |
| Life Insurance & Annuity (56.7 / −18.2) | LOST |
| Truckload & LTL Freight (48.9 / −11.2) | LOST (reached strong85) |
| U.S. Regional & Mid-Cap Banks (62.5 / −5.4) | LOST |
| Industrial & Logistics REITs (37.8 / −1.3) | LOST |
| Open-Air & Strip-Mall REITs (41.1 / −16.1) | LOST |

**Net: 7 real losses (12% of maturers; only 2 ever became strong) versus 13 corpses
stopped.** All 7 losses are the same single market episode — the late-June rate-rotation
into financials/REITs/freight, born mid-turn while cohort RS was still falling. The 7/27
replay saw the same class and called it "top-RS-slice-of-one-industry categorisations";
this cohort's version genuinely matured, so it is booked here as real cost, not excused.

Context rates: 34/178 births join a live board theme at birth (the join lever carries the
funnel, consistent with 50/106 in the 7/27 July replay); the OR-cell floor itself blocks
~20% of classifiable births ≈ consistent with the ~5.9 → ~2.4 births/day funnel estimate.

## 5. Traps, named

- **Survivorship/recency**: "still alive today" runs 32% for week-26 births vs 80% for
  week-31 births — pure recency. All maturity numbers therefore use the equal 15-day
  window with 66 recent births censored, never "alive today". (Week 26 also shows the
  reverse: 15 matured but only 8 alive today — old cohorts mature then die; alive-today
  UNDERstates old cohorts and OVERstates young ones.)
- **Silent death**: absence ≥ 7 days from snapshots = aged out; treated as death
  everywhere; Retired rows (incl. synthetic engine-drop retirements) likewise. 8
  classifiable deaths were absorptions into a successor (dedup, not failure) — flagged in
  the TP counts, 2 sit inside the OR-cell's 13 "stopped corpses".
- **Day-one noise**: handled by measuring member-level (§0); the 33 sentinel-0.0 births
  would otherwise all have read "born at RS 0" and corrupted every floor number.
- **One cohort dominating**: leave-one-week-out sweep — flat-70 FN% ranges 31.8–40.0%,
  OR-cell 13.3–20.0% across all four exclusions; the ordering never flips. But the
  OR-cell's 7 real losses ARE one multi-week market episode (rate rotation, weeks 26–28);
  a different quarter may contain zero such episodes — or two.
- **Not fully out-of-sample vs the 7/27 derivation**: June/early-July births were inside
  its 254. The genuinely new evidence is births 7/14–7/19 (censored then, classifiable
  now): n=22, 9 matured; flat-70 blocks 11 with 2 FN (both live-joins), the OR-cell blocks
  6 with **0 FN**. Small but supportive.
- **Name-keyed births**: canonicalization renames can masquerade as births and split
  sighting chains; the overlap-join dissection recovers the material cases (steel,
  tankers, precious metals). Residual risk is small and biases AGAINST the gate (inflates
  apparent births/FN).
- **Small n**: 112 classifiable, 59 maturers — each FN is ±1.7% of "all matured". Cells
  within ~2 FN of each other (e.g. δ = 0 vs −5) are not distinguishable here.

## 6. Recommendation (evidence only — operator signs any change)

1. **Do not ship a flat floor at any τ.** This cohort makes the case more strongly than
   the 7/27 all-time replay did (FN 35.6% of maturers vs 19.4% there). The operator's
   at-ruling-time suspicion — weak-born themes DO mature, so the floor needs a trajectory
   term — is confirmed on fresh data. His anticipated amendment is already embodied in the
   shipped OR-cell; no further amendment of the ruling is required.
2. **Keep τ = 70 as the level arm of the OR-cell.** The replay cannot distinguish 65/70/75
   (identical outcomes once the rising arm exists) — so the operator's adopted 70 stands
   as *derived-equivalent*: nothing in the data argues for moving it, and τ = 80 and flat
   anything are both rejected. Honesty requires saying 70 is not uniquely optimal; it is
   inside the indifference band, and the band's edges are what the data actually pins.
3. **Keep δ = 0 for now.** δ ∈ [−5, 0] is an indifference band here (δ = −5 saves ~2 more
   maturers, admits ~1–2 more corpses — inside noise at n=44 weak-born, and re-fitting δ
   to rescue one market episode would be overfitting by construction). The 7/27 all-time
   result (δ = 0 beats +3/+5) still holds on this cohort (+3 is strictly worse).
4. **What would settle the residue** (τ within 65–75, δ within [−5, 0], and the
   rate-rotation FN class): the already-registered observe-mode forward review
   (`theme_birth_gate_observe_calibration`, fires at 20 observe rows) — specifically
   (a) actual maturation of `held_floor` verdicts, (b) how often held cohorts re-present
   and pass (the steel +13d pattern — if common, blocking's true cost is delay),
   (c) recurrence of rotation-style episodes. If forward data shows held_floor themes
   maturing above ~25–30%, widen δ toward −5 rather than lowering τ — the losses live in
   the falling-at-birth class, not the 65–75 level band.
