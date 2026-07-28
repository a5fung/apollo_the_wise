# Theme birth-gate floor — DERIVATION (2026-07-27)

> Evidence pack for the Phase-1 birth gate (design
> `docs/design/theme_system_consolidation_2026-07-27.md` §3/§8, all six decisions
> operator-ruled ADOPT 2026-07-27). The operator adopted **avg-RS ≥ 70 as a
> starting point and explicitly asked that the number be DERIVED, not enshrined**.
> This is that derivation. Population: all **254 historical theme births**
> (every distinct name ever in `mi_themes`). Data: prod SELECTs run 2026-07-27
> **after the 17:05 ET nightly** (19:1x ET — the population is post-rebuild;
> the mid-afternoon misread class is avoided). Scripts: scratchpad
> `derive_floor.py` / `derive_floor2.py` / `derive_cells.py`; inputs
> `mi_themes` (3,621 rows), `mi_theme_candidates_shadow` (143 rows),
> `mi_stock_scores` member-level RS history (67k rows).

## Headline: the operator's flat ≥70 is the WRONG INSTRUMENT — keep 70, add a trajectory arm

The level barely separates winners from corpses; the **trajectory** separates
cleanly and is gate-visible. **Derived cell: member-avg RS ≥ 70 OR pre-birth
5-session cohort ΔRS ≥ 0** ("level OR rising"). A flat ≥70 would silently kill
**19.4% of every theme that ever matured** (26 of 134) at 40% precision — more
future winners than junk. The OR-cell halves that loss (26 → 11 all-time; 4 in
the July replay, all rate-rotation sector slices) at equal junk-kill.

## 0. Instrument corrections (why naive reads mislead)

1. **Stored `mi_themes.rs_avg` is broken at birth for a whole class**: 30
   births carry stored rs_avg < 5 while their members' actual `mi_stock_scores`
   RS averaged > 40 on 22 of them (e.g. "Franchise Auto Dealership Groups"
   stored 0.0, member-level 53.2, later peaked 99.0 — `_score_new_theme`'s
   `rs_scores else 0` fallback). **All numbers below use member-level birth RS**
   (nearest score_date ≤ birth), which is also exactly what the shipped gate
   reads (`db.get_cohort_rs_snapshot`).
2. **Right-censoring**: a theme born last week that still exists is YOUNG, not
   "matured". Births after 2026-07-13 with no stage/longevity evidence are
   CENSORED (outcome unknown): 254 → **208 classifiable** (46 censored).
3. **Joins are dedup, not kills**: a birth suppressed because its cohort
   already lives on the board under another name loses nothing — the funnel
   below reports joins / delays / kills separately.

**Maturity (umbrella, reported per-component throughout)** = survived (on
today's board: last row ≤ 7d, non-Retired) OR staged (ever reached
Accelerating/Mainstream) OR long-lived (≥ 14 distinct days). Classifiable:
**134/208 matured (64%), 74 did not**.

## 1. RS-at-birth distribution vs outcome — the level does NOT separate

| birth RS (member-level) | n | matured | MAT% |
|---|---|---|---|
| 0–40 | 17 | 8 | 47% |
| 40–55 | 11 | 7 | 64% |
| 55–65 | 11 | 9 | 82% |
| 65–70 | 4 | 2 | 50% |
| 70–75 | 7 | 5 | 71% |
| 75–80 | 12 | 10 | 83% |
| 80–85 | 21 | 9 | **43%** |
| 85–90 | 19 | 14 | 74% |
| 90–95 | 39 | 22 | 56% |
| 95–101 | 67 | 48 | 72% |

Matured median birth RS **90.8** (p25 77.2, p10 53.2) vs unmatured median
**88.5** (p25 72.6, p10 24.0). No monotone trend — the 55–65 band outperforms
the 80–85 band. **This is the weak-separation finding the card asked to be
stated plainly: RS level at birth is a poor predictor of maturing.**

Flat-floor sweep (all-time classifiable):

| τ (flat) | blocked | blocked-MATURED (FN) | blocked-unmatured | FN % of all matured | precision |
|---|---|---|---|---|---|
| 55 | 28 | 15 | 13 | 11.2% | 46% |
| 60 | 33 | 19 | 14 | 14.2% | 42% |
| 65 | 39 | 24 | 15 | 17.9% | 38% |
| **70** | **43** | **26** | **17** | **19.4%** | **40%** |
| 75 | 50 | 31 | 19 | 23.1% | 38% |
| 80 | 62 | 41 | 21 | 30.6% | 34% |

## 2. THE operator-named risk, measured: weak-born themes DO mature — and they are RISING

**Of 43 classifiable themes born < 70, 26 matured (60%). 19% of ALL themes
that ever matured were born < 70.** Named examples: Domestic Steel Producers
(born 27.8 → staged + on board), Bitcoin Mining & Crypto Infrastructure (30.1 →
peak 97.9), Industrial & Logistics REITs (37.8 → 16 days), the whole late-June
rate-rotation cohort (insurers/banks/REITs born 37–65, most still on the
board). A flat level is therefore the wrong instrument — exactly the
subtle-RS → early-theme → matures chain the north star hunts.

**The trajectory separates where the level cannot:**

| cohort (member-level ΔRS) | post-birth Δ5td (median) | rising share | Δ10td |
|---|---|---|---|
| weak-born (<70) MATURED | **+7.9** | 20/24 | **+11.7** |
| weak-born (<70) unmatured | +1.4 | 9/17 | **−1.4** |

And **pre-birth** (what a gate can actually see on decision night — cohort RS
at first sighting minus 5 sessions earlier): weak-born matured **+2.5 median,
15/26 rising** vs weak-born unmatured **−5.3 median, 7/17 rising**.

**Answer to level-vs-trajectory: TRAJECTORY.** The gate needs a rising-RS arm;
the level alone mis-classifies the class the system exists to find.

## 3. Cell sweep — level OR rising

Pass = RS ≥ τ OR pre-birth Δ5-session ≥ δ (unknowns never satisfy an arm):

| cell | blocked | FN (matured) | TP (unmatured) | FN % of matured | precision |
|---|---|---|---|---|---|
| RS≥70 flat | 43 | 26 | 17 | 19.4% | 40% |
| RS≥65 OR Δ5≥0 | 20 | 11 | 9 | 8.2% | 45% |
| **RS≥70 OR Δ5≥0** | **21** | **11** | **10** | **8.2%** | **48%** |
| RS≥70 OR Δ5≥+3 | 24 | 13 | 11 | 9.7% | 46% |

τ=65 vs τ=70 are near-identical once the rising arm exists (the arm rescues
the 65–70 sliver anyway) — **so the operator's 70 stands, as the level arm of
an OR-cell, not as a flat floor.** δ=0 beats +3/+5 (the +3 boundary loses
Senior-Care REITs +0.9 and Midstream +1.6, both matured).

Residual 11 all-time FN under the chosen cell: Domestic Steel 27.8/Δ−27.8,
Bitcoin Mining Infra 30.1/Δ−33.3 (rescued in practice — it JOINS Crypto Asset
Recovery via the 14d ledger), and 9 late-June rate-rotation sector slices
(REITs/insurers/banks/freight, born weak AND falling). That residual class is
overwhelmingly **"top-RS slice of one industry" categorisations** — the §4
driver-test failure, not the early-theme class; a driver bar (Phase 1 does not
ship one — underived) is the right instrument for them, not a higher floor.

## 4. Each lever's INDIVIDUAL effect on July's 106 births (61 live + 45 promoted)

- **Join-or-new (≥50% intersection-over-smaller vs board + 14d ledger,
  including quiet/dead entries): 50/106 (47%)** were re-mints of something
  alive or recently seen — Clinical-Stage Oncology ×3 names, the defense-primes
  chain ×4, steel ×3, tankers ×3, Rare-&-Orphan etc. Far above the design's
  member-overlap estimate (3/106) because the live instrument couldn't see
  ledger/dead-theme re-mints. **Dedup, not loss** — the bet stays on the board.
- **Two-sighting bar: kills 5** (1-day-never-re-sighted; 1 classifiable-dead +
  4 young-unknown), **delays every other birth by ~1 trading day** (costless —
  member EP alerts are not gated on theme birth). Weekend-safe: Fri + Mon = 2
  distinct days. This is a LOWER bound on its effect: post-birth presence has
  carry-forward inertia a pre-birth candidate wouldn't.
- **Floor (RS≥70 OR rising), after joins + two-sighting: kills 7 more** — 4
  classifiable-matured (ALL of them late-June-style rate-rotation slices:
  Franchise Auto Dealerships 53.2/Δ−0.5, Industrial & Logistics REITs
  37.8/Δ−2.9, Open-Air Strip-Mall REITs 41.1/Δ−21.7, U.S. Regional Banks
  62.5/Δ−5.3), 2–3 censored-young. The RS-38.7 Hospital and RS-49.1 Utilities
  graduates of 07-27 never birth (Hospital additionally joins; Utilities holds
  at the floor).

**Combined July funnel (gate order: join → two-sighting → floor):
106 → 50 join / 5 killed at the bar / 7 killed at the floor → 44 births/month
≈ 2.4/day** — inside the design's ~40–55/month estimate, now derived rather
than estimated.

## 5. Honest caveats

- "Matured" leans on board-survival; persistent **sector slices** count as
  matured even where the §4 driver test would call them categorisations — this
  makes the FN counts CONSERVATIVE (the real cost of blocking them is lower
  than stated).
- The two-sighting simulation uses within-`mi_themes` recurrence as the proxy
  for pre-birth candidate recurrence (no pre-birth ledger existed for Lane-1
  history); directionally a lower bound on the bar's kill rate.
- 46 July-era births are censored (too young to classify); the July funnel
  labels them explicitly rather than counting them either way.
- The promoted lane's candidate ledger (143 rows) only covers shadow-lane
  sightings; canonicalization renames break some name-keyed sighting chains
  (member-overlap matching recovers most).

## 6. The shipped cell (operator signs THIS, per CHANGE_PROCESS)

```
BIRTH_GATE_RS_FLOOR        = 70.0   # level arm (operator's adopted start — survives)
BIRTH_GATE_TRAJ_MIN        = 0.0    # rising arm: pre-birth 5-session cohort ΔRS >= 0
BIRTH_GATE_TRAJ_SESSIONS   = 5
BIRTH_GATE_MIN_SIGHTINGS   = 2      # distinct days, weekend-safe
BIRTH_GATE_JOIN_OVERLAP    = 0.5    # intersection-over-smaller vs board
BIRTH_GATE_LEDGER_DAYS     = 14     # join-or-new memory incl. quiet candidates
```

P3 market-adjusted co-movement (coverage_probe's kept primitive) is recorded
on every ledger row as **evidence annotation only** — a blocking co-movement
threshold was NOT derived here and would violate the derive-don't-pick
discipline; the accrued column is the input for deriving one later.

**Forward validation before the cell acts (coordinator+operator-agreed
2026-07-27)**: the toggle is 3-state (`off`/`observe`/`on`). The deploy state
is `observe` — verdict + deciding lever + inputs recorded per would-be birth
while every theme is born exactly as today — so this replay's numbers get a
FORWARD check (held-verdict themes' actual maturation, join-pair quality,
two-sighting resolution, rising-arm rescues) before any birth is suppressed.
The comparison fires via the run-count-gated review
`theme_birth_gate_observe_calibration` (20 observe-mode gate rows ≈ 2 trading
weeks; never date-gated). The operator signs the cell against BOTH this replay
and the forward evidence.
