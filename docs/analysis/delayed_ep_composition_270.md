# #270 — delayed-EP re-entry composition: step 1 (logic validated vs MNTS)

**Status: STEP 1 DONE 2026-06-14 — the composition state machine reproduces the known
MNTS lifecycle (gate-free replay). Calibration (cohort) + the deployable shadow
detector are next; the detector is GATED (see "Gate").**

## What #270 is

Per the MNTS case study (`docs/analysis/mnts_delayed_ep_case_study_2026-06-11.md`) +
`memory:user-delayed-ep-reentry-template`: the fragments already fire (EP gap, flag
WATCH, 9M pings) but nothing ASSEMBLES them. #270 is the missing **composition state
machine** for a tiny-cap delayed-EP re-entry, from daily bars:

```
WATCHED   gap day: close >= (1+GAP)*prev_close, close > SMA200, vol >= VOLX*ADV20.
          Records gap_day_low (the U&R reference) + gap_day_vol.
ARMED     within ARM_WINDOW days: low < gap_day_low (UNDERCUT of the gap-day low —
          the exact event the flag detector wrongly INVALIDATES on), vol < burst.
TRIGGERED after armed: close > gap_day_low AND close > SMA20 (reclaim BOTH refs) AND
          vol > EXPANSION * avg(pullback vol) (the explosive R-leg volume signature).
```

The undercut-is-the-arming-event (not invalidation) is the irony at the heart of #270:
the flag-rule universe and the delayed-EP universe need separate state tracks.

## Step 1 — replay validated vs MNTS (gate-free)

`scripts/_270_delayed_ep_replay.py` runs the state machine over a pulled daily-bar
snapshot. Against MNTS (2025-05..2026-06):

```
2026-05-26  WATCHED   gap +110% close 15.48 > SMA200 12.51; vol 79.8M = 12.7x ADV20; gap_day_low=11.86
2026-06-08  ARMED     UNDERCUT gap_day_low 11.86: low 11.80; vol 6.5M < burst 80M (contraction)
2026-06-11  TRIGGERED RECLAIM close 16.30 > gap_day_low 11.86 & > SMA20 12.12 & > EMA21; vol 21.4M = 2.1x pullback-avg
RESULT: PASS — reproduces WATCHED 5/26 / ARMED 6/08 / TRIGGERED 6/11 (the +43% day).
```

This proves the composition LOGIC reproduces the known case. It is N=1 validation of
the logic — NOT a calibration verdict (single-case; the methodology anti-overfit rule
applies). Reproduce:
```bash
ssh apollo@<box> 'docker exec apollo-postgres psql -U apollo -d apollo -tAF "\t" \
  -c "SELECT trade_date,open_price,high_price,low_price,close,volume FROM mi_daily_closes \
      WHERE ticker='"'"'MNTS'"'"' ORDER BY trade_date;"' > scripts/_270_bars_mnts.tsv
python scripts/_270_delayed_ep_replay.py
```

## Thresholds (TEMPLATE-grounded defaults — OPERATOR to calibrate, not self-certified)

| Param | Default | MNTS actual | Note |
|---|---|---|---|
| GAP | +40% | +110% | gap-day close vs prior close |
| VOLX | 3x ADV20 | 12.7x | mirrors the 9M 3x-ADV gate |
| ARM_WINDOW | 15d | undercut 9d after gap | undercut must land within window |
| EXPANSION | 1.5x pullback-avg vol | 2.1x | the R-leg volume signature |

Reclaim requires close > BOTH gap_day_low AND SMA20 (the two-fold U&R); EMA21 is
reported as confirmation. Universe deliberately INCLUDES sub-$500M (the live scanner's
`mcap_too_small` floor is kept for auto-trading, dropped for this watch/observe lane).

## Sequencing

- ✅ Step 1 — composition replay, validated vs MNTS (this doc). Gate-free.
- ⏸ Step 2 — COHORT calibration: run the replay over recent sub-$500M huge-gap names
  (seed from mi_ep_alerts / mi_9m_* ), measure fire-rate + threshold sensitivity →
  operator calibrates GAP/VOLX/ARM_WINDOW/EXPANSION before anything ships. Gate-free.
- ⏸ Step 3 — the deployable SHADOW detector (lifecycle state table + scheduler job +
  `/`-surface). GATED post-#277: a new scheduler job + CREATE TABLE run in COMBINED =
  Monday's §C rollback target, so it must not enter main's rollback path until the
  gate closes. Build on a branch + staging-validate, merge post-gate.

## Gate

The replay (read-only script + this doc) is gate-safe — it touches nothing executable
in any role. The deployable detector (Step 3) is sequenced post-#277, same discipline
as #258 step 2.
