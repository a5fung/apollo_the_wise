# #299 (1A) — tape-feature judge eval: finding + rig + smoke (2026-06-17)

**What #299 is:** the tape features (opening-range÷ATR, premarket volume-curve vs the name's own
baseline, liquidity) are computed (SLICE B) and the judge prompt renders them (SLICE A), but the
scan does **not** pass them to the live judge yet. The judge is load-bearing on entry, so the tape
must EARN its way in via a with-vs-without eval the operator labels. This doc is the eval rig +
the zero-cost binding finding + the machinery smoke. **It does not decide ship** — the operator
does, off the full-run delta surface.

## Binding finding FIRST (zero LLM cost) — does the feature even exist at decision time?

The advisor's framing: the question isn't "does tape change verdicts," it's "is the feature
present *and* tradeable when the grade is made." OR÷ATR needs the 9:30–9:35 opening range; the ORB
submission window closes at 9:44; HIGHs at 9:45+ are `WINDOW_OUT_OF_ORB`.

**Timing histogram, n=569 HIGH alerts (2026-03-16 → 06-17), `detected_at` in ET:**

| bucket | share | tape availability at grade time |
|---|---|---|
| premarket (<9:30) | 14.1% | OR÷ATR = None; only pm_vol_curve / liquidity |
| **OR done + ORB-OPEN (9:35–9:44)** | **79.1%** | **OR÷ATR available AND ORB-tradeable** |
| OR done, OUT-OF-ORB (9:45–9:59) | 5.4% | OR÷ATR available but not ORB-tradeable |
| post-ORB (≥10:00) | 1.4% | — |

**Result — the feature is decision-relevant, not killed by timing** (the opposite of the initial
hypothesis). The 9:35–9:44 cluster is the 5-min scan cadence landing at :35/:40, by which point
the 9:30–9:34 opening range is complete and the ORB window is still open. The judge gates entry
synchronously (`ep_detector` ~L2489: the judge verdict mutates `score_tier` — the field the caller
reads for alert+ORB entry — *before* the entry fires), so a tape that shifts the judge verdict
shifts **tradeable** selection. → the expensive replay is warranted; build it (incl. OR÷ATR).

Two premises hardened (advisor 2026-06-17):
- `detected_at` is NOT mutated post-grade — `update_ep_alert_judge_result` writes only
  `score_tier`/`judge_*`/`grade_engine_authority`/`fire_axes`, so it IS the grade moment (the 79%
  thesis rests on this).
- The judge toggle `get_holistic_judge_enabled()` read **True** in prod 2026-06-17 — the judge is
  load-bearing on entry RIGHT NOW, so "tape shifts tradeable selection" is a live statement, not a
  conditional one. (Re-confirm the toggle if shipping later — a flip to shadow would make tape a
  display-only grade input.)

## The rig — `scripts/eval_tape_judge.py` (committed, READ-ONLY)

Re-grades each `mi_ep_alerts` row through `grade_holistic` twice: `tape=None` (today's behavior)
×K replicates, and `tape=<point-in-time dict>` ×1. Surfaces the rows whose verdict changed, for
operator labeling.

Disciplines (advisor 2026-06-17), all in code:
- **Point-in-time cut** — minute bars truncated to `t <= detected_at` before OR / premarket-cum-vol
  / liquidity-so-far. OR÷ATR is None pre-9:35 *by construction* (= the tradeability segmentation).
- **tz** — bar `t` is epoch-ms UTC; `detected_at` and the 9:30/9:35 cuts go through `ZoneInfo(ET)`.
  Covered by `tests/test_tape_eval.py` (8 pure tz / lookahead-cut tests).
- **Judge noise floor — BOTH arms** — `--replicates` runs the judge K× on *each* arm (no-tape AND
  with-tape; adaptive thinking, no temperature → non-deterministic on both). A delta counts ONLY
  when each arm's modal is stable across K AND the two modals differ. (Replicating only the no-tape
  arm — the original cut — would surface with-tape *sampling noise* as a "tape effect": no-tape
  stable HIGH ×K, with-tape rolls MODERATE once it'd be HIGH 2/3. advisor 2026-06-17.) Rows
  unstable on ≥1 arm are reported separately as noise-dominated, never counted.
- **Smoke ≠ efficacy** — small `--limit` validates machinery + presence rates only. The operator
  labels the full-run deltas; the agent never self-scores (ADR 0011).

**Operator caveat:** `get_minute_volume_baseline` is the *current* trailing baseline, not
as-of-alert-date → pm_vol_curve carries mild (slow-moving) baseline lookahead. OR÷ATR + liquidity
are reconstructed strictly point-in-time.

## Smoke (machinery, 2026-06-17): `--days 30 --limit 5 --replicates 2`

- **Machinery: PASS** — tape reconstructs from real Polygon minute bars + baselines and flows
  through both judge arms, no errors.
- **Presence (real data):** OR÷ATR 5/5, pm_vol_curve 4/5, liquidity 5/5 — all 5 in the 9:35–9:44
  tradeable bucket (matches the 79% finding; feature not starved by data gaps).
- **Noise floor:** 5/5 stable across 2 replicates.
- **Tape deltas: 0** on these 5 — expected for a tiny smoke of solid HIGHs; says nothing about
  efficacy (that's the full run).

## Next — operator-triggered full run

Scoped so the trigger isn't an unscoped bill (advisor 2026-06-17): `REPLAY_SQL` is HIGH+MODERATE,
so an unfiltered 95-day run is a few **thousand** rows. The tradeable cohort is HIGH, so run
**HIGH-only**. Cost = rows × 2 arms × K replicates Opus judge calls + 1 Polygon `get_minute_bars`
per row (rate-limited, sequential). HIGH-only over ~95 days ≈ ~570 rows → at K=3 ≈ **~3,400 Opus
calls** + ~570 Polygon fetches. The script prints the exact scope/estimate before it runs.

```
docker exec apollo-market python /app/scripts/eval_tape_judge.py \
    --days 95 --limit 0 --high-only --replicates 3
```

Then the operator labels each tape-delta right/wrong; ≥ a clear majority-correct on a non-trivial
delta count + a CHANGE_PROCESS entry + sign-off = wire the tape into the live judge (`ep_detector`
`_judge_shadow` passes the computed tape into `assemble_judge_inputs`). Re-run after shipping and
add to the monthly backward-check sweep.

**Pre-full-run hardening landed 2026-06-17** (advisor B/C): both arms now replicated (delta
integrity); the delta-render path is extracted + unit-tested (`tests/test_tape_eval.py`) so the
expensive run can't KeyError after the spend on its first real delta; `--high-only` + the cost
print added. 11 tape-eval unit tests green.
