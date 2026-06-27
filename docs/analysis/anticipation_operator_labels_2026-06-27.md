# Anticipation (#327) — operator labels (2026-06-27 pass)

**This file is the STABLE label of record. The worksheet generator
(`scripts/_anticipation_shortlist.py`) MUST NEVER write here** — a re-gen wiped in-progress labels
once. The generator writes the *unlabeled* board to
`docs/analysis/anticipation_shortlist_to_label_<date>.md`; copy your G/X labels from there into the
table below so a rebuild can't clobber them.

## How to label
Mark each candidate **G** (real Pradeep Anticipation setup — the quiet pocket inside a base, found
while still flat) or **X** (garbage — grind / decline / breakout-already-gone). These labels are the
calibration set the Track-2 structural model (the 5-metric feature matrix) is shaped against.

## Provenance of the board
- Universe + bars: rebuilt by `scripts/build_anticipation_universe.py --asof <basing date>` (#388 —
  CS-filtered via `mi_security_types`, complete; GH/HNGE asserted present).
- Anchor: base-start peak = earliest bar within 2% of the window peak (#389 — fixes the truncated-base
  bug; HNGE now reads its true ~12–15-day base, not `baseD 4`).
- All metrics measured as-of the **basing date** (pre-breakout), not 6/27 — hindsight discipline.

## Labels

| LABEL (G/X) | ticker | as-of (basing) | runup | baseD | notes |
|---|---|---|---|---|---|
| | | | | | |

## Known anchors (operator, going in)
- **Positive (good coils):** GH, HNGE, CRWD, FTNT, DDOG.
- **Poor (fired-but-bad):** OSCR, GPGI, UAL, PTGX, TVTX.
