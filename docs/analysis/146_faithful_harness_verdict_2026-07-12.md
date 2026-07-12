# #146 faithful harness (Block 4 T3) — the era discovery + the honest D2 verdict (2026-07-12)

**Probe:** `scripts/probes/_146_faithful_harness.py` (v2, replay-vs-replay). Read-only.

## Finding 1 — the era discovery (corrects Friday's framing)

Faithfulness-to-the-live-table is **structurally impossible**: **20 of 21** live TRIGGERED events
predate the **6/27–28 flag→HTF re-parameterization** (90% runup gate · Stage-2 200MA/52w-high ·
ADV≥500k/ADR≥4% floors · pole-volume confirmation). v1's per-event diffs show them failing
TODAY'S gates (`runup_56%_below_90%`, `adv_391k_below_500k`, `not_stage2`, …) — the detector that
produced them **no longer exists**, and the current detector has **N=1 live trigger**.

**Consequence:** Friday's "incumbent +0.78R / N=19" (in `146_triggered_gate_backtest_table`)
describes the RETIRED detector — still true as history, wrong as a description of today's gate.
The sitting's PARK ruling on 0026-D2 stands (indeed strengthens: there is no rule-grade live
evidence on the CURRENT detector in either direction). The 4/21 "unfaithfulness" was never a
harness bug — it was an era boundary.

## Finding 2 — the honest D2 table (current classifier, replay-vs-replay, apples-to-apples)

Two arms over the same 1,847 seed ticker-days, differing ONLY in the COILED conjunct; identical
settlement (entry=base_high, stop=breakout-day low, 10 trading days, break-day-exclusive).
*Coverage note: seed = old-detector TIGHTENING+ days; old WATCH-only days not replayed.*

| arm | n settled | median R | mean R | total R | win% | avg-winner |
|---|---|---|---|---|---|---|
| current rule WITH conjunct (replay-incumbent) | 4 | −1.00R | +0.60R | +2.4R | 25% | +5.42R |
| **D2 addressable (conjunct dropped, extra events)** | **11** | **−1.00R** | **−0.04R** | −0.5R | 36% | +1.63R |

**F1 ship rule (N≥10 · median ≥ −0.25R · win ≥ incumbent): NO-GO** (median −1.00R fails).

## Finding 3 — the D2 cohort's real problem is STOP GEOMETRY, not selection

The per-event tail is striking: the D2 names ACCESS enormous forward moves — VICR fwd-max
**+44.7R**, FLEX +11.2R, NBIS +5.1R, ARM +4.5R, VECO +3.5R — but 7/11 stop out at −1R on the
breakout-day-low stop before delivering. Selection is actually *better* than the incumbent's
(36% vs 25% win); what kills the cohort is the tight-stop × whipsaw interaction. **Routing:**
this is evidence FOR the already-designed **ADR 0031 structural-stop program** (would a
character-conditioned stop hold these names?), NOT for loosening the trigger. Recorded as a 0031
shadow-readout question — no new task (the 0031 shadow measures exactly this).

## Dispositions

- **0026-D2 stays PARKED** — now with the honest current-classifier table attached. Reopen only
  if 0031's shadow shows structural stops convert this cohort's tail (a named hypothesis).
- The current (HTF) detector's own trigger flow is ~4 events/3 months in replay + N=1 live —
  the #397 HTF GO/NO-GO (7/18) should note the LOW FLOW as its own datum.
- Friday's table doc gets an era-correction pointer to this doc.
