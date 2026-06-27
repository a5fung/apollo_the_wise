# Anticipation coil-finder — operator validation (2026-06-27)

The #327 detector was rebuilt around the operator-locked model after the old peak-anchored "base =
peak..now" was shown to swallow the pullback (CRWD read 24% wide). This file captures the operator's
verbatim chart reads + the model, as the calibration record. See `scripts/_anticipation_coil_finder.py`.

## Locked model (operator-confirmed 2026-06-27)
1. **RUNUP** — a leg up ≥~15% (prior swing low → peak).
2. **HOLD** — the consolidation low stays above the **~50% retrace** of that runup leg. Give back more
   than half → the runup is negated → not basing, *regardless of tightness*. HARD gate. (50% is the
   operator's rough cap — "shallower the better, 50% is probably the limit, something to test" — so
   retrace is REPORTED + tuned, not silently hardcoded.)
3. **TIGHT** — within the holding zone, a tight, flat coil. RANKS what survives the hold gate.
4. **NOT gates** — pullback depth/duration/shape, or touching a specific MA (CRWD's 20MA kiss was
   incidental — "just how this stock worked out").

## Finder results (replay Apr15–Jun26, prod DB) — held + tight coils found for all 5 good names
GH 5/28 r17% band7.1% · HNGE 5/08 r21% coilD12 band7.9% (= the operator's May 6–28 base, found by the
detector) · CRWD 4/22 r32% band6.2% · FTNT 6/04 r25% band11.2% · DDOG 6/01 r41% band11.2%.
Hold gate REJECTED GPGI (retraced **199%** of its runup — fully negated).

## Operator reads on the "poor" four (VERBATIM, 2026-06-27) — none are garbage; quality nuances
- **OSCR** — "peak and base start at 6/10" (finder read 6/15 — peak detection ~5d late).
- **UAL** — "it's ok, but base is short, 6/22 is really the only tight day to enter, otherwise it's
  gappy." → ORDERLINESS gate (gappy/drunken-walk vs linear).
- **PTGX** — "has long base, from 3/25 really, and it's not really moving until 6/9, so such a long
  long base it's really too long to wait." → DURATION gate (base too long → no urgency).
- **TVTX** — "looks decent, 5/19 or 5/22 are both tight days to enter by a glance though this failed on
  6/22, it quickly reclaimed and setup again; the real setup for this one is the delayed EP (4/14) but
  challenging not to be stopped out." → valid; note the delayed-EP framing + the failed-then-reclaim.

## Refinements (next, all from the Pradeep blueprint — operator_shared_notes 6/22)
- **DURATION** — measure the FULL base length (range-bound days), not just the recent coil window;
  flag too-long (Pradeep 3–20d, sweet 4–10). PTGX is the case.
- **ORDERLINESS** — daily-range / gappiness measure (ADR over the coil); reject drunken-man-walk. UAL.
- **Peak accuracy** — OSCR's true peak is 6/10 not 6/15.

**Key conclusion:** structure (runup→hold→tight) is a clean SCREEN for valid coils; among valid coils
it does NOT pick the winner (the "poor" four are real coils, just lower-quality or context-failed). The
final selection rides on the catalyst layer + the duration/orderliness quality rankers — consistent
with the operator's own catalyst hierarchy.
