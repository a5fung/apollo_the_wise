# Breakout big-winner study — pre-registration amendment A2 (2026-11-26, operator: "amend")

Amends the frozen pre-registration `docs/analysis/breakout_winner_study_prereg_DRAFT_2026-11-24.md` (sha256
`3eb2b9b0…`) together with amendment A1 (`…_amendment_A1_2026-11-26.md`, sha256 `4a7beda1…`). Neither file is
edited; this one wins where they differ.

## Why
Stage 2 (calibration on SYNTHETIC labels only, no outcome read) stopped on its centring check (median ratio under no
effect inside 0.95–1.05):
1. **f20 (shape count), pooled discovery ratio** reads 0.940 (5% row) / 0.946 (8% row) under no effect. The miss is
   deterministic: ties put 57.8% of f20's bottom third in 2020 against 51.8% of its top third, and 2020's rate is
   higher, so the pooled ratio leans; the composition-expected value is 0.944.
2. **f24a, check era-B ratio, 3% sensitivity row only** reads 1.061 = 297/280 — equal winner counts in unequal
   thirds (discreteness); the main 5% row reads 0.994.
Evidence: `scripts/probes/_breakout_winner_study_1124/stage2/2_calib.txt`, `2_diag.txt`.

## The rule (A2)
1. f20's pooled discovery ratio (and any f20 ratio whose no-effect composition-expected value falls outside
   0.95–1.05) is read as **observed ÷ composition-expected**, the expected value computed under no effect by stage 2's
   own simulation and printed beside it; that quotient is what meets the floors and verdict words.
2. The 3% row is a sensitivity row: a centring miss there that is centred on the 5% row is LISTED, not blocking.
3. Nothing else changes.

## Method and population
Population: stage 1e's kept seed-1124 events — discovery 5,330 (2017–2020), check 6,266 (era A 2,910, era B 3,356);
stage 2 ran on synthetic labels only, 2,000 draws per feature per case per rate.

## Why this cannot lean toward a result
Written before any outcome was read (stage 3 has not run). The correction is the no-effect expectation from
synthetic labels, so it cannot see the real winners.

## What this does not answer
- Whether f20 carries any real signal; only that its ratio is now centred under no effect.
- Whether the tie structure also widens f20's spread; its power is reported, not corrected.
