# Real-time detection flip (#490) — evidence pack, 15 shadow trading days (7/21–8/10)

**EVIDENCE ONLY. Nothing flipped.** Entry detection is THE LINE.

## Headline
The false-admit half is ALREADY LIVE AND WORKING. The admit-expansion half is EV-negative
through the exits this book actually runs, except one thin pre-open pocket that a single trade
decides.

## Already on, and proven (no action needed)
- Scan-level stale-admit removal, acting since 2026-08-03.
- **Entry-time real-time gap gate, live by 08-06: 4 firings, 4 correct blocks.**
  - LFST 08-06 alert +18.8% vs real-time −2.0% · U 08-06 +18.4% vs +1.0%
  - ACMR 08-07 +15.1% vs +6.6% · **TH 08-10 +12.2% vs −5.0%** (skipped `setup:gap_below_floor`)

⚠ **Correction to the 08-10 framing:** real-time AGREED with TH's alert at 07:20 (12.2 = 12.2);
TH faded later. Flipping DETECTION to real-time would not have prevented the TH alert — only the
entry-time gate does, and it did.

## Still off
`ep_rt_gap_authoritative` and `ep_rt_universe_authoritative` — all 314 `ep_rt_admit` and 206
`universe_catch` events carry `authoritative: false`.

## True catches
- **29% of alerts arrive too late to enter**: 24 of 83 detected ≥09:45 ET over 15 days; 16 were
  HIGH-graded. **12 of those 16 had an earlier real-time catch** — ACHR (08:05, rt 14.3% vs
  delayed 0.2%), NESR, TSAT, MTW, DCTH, LRCX, ECG, NNE, TEVA, BLZE, LIND, HGTY.
- 4 of the 16 had NO shadow catch (HAS, AMRC, CAI, ONTO) — real-time would not have saved those.
- Raw would-have-caught flood: 543 ticker-days (~36/day); only 71 also passed the mechanical
  entry gates in-window — that is the honest ceiling on extra entries.

## False admits — the half that decides it
Modeled at catch price, live median stop (2.88%), live exit stack:
- **In-window crossers: mean −0.60R** (n=320/14d), 89% never see R>0, 80% stop day-0.
- Gate-passing subset: **−0.69R, 65 of 70 stopped day-0.**
- Pre-open catches: −0.22R (n=197).
- The shadow's own guards are outcome-validated: sustain_reject −0.77R, gap_clamped −1.00R,
  halt_suspect −1.00R, tick_quality_reject −0.26R.

## Value under the LIVE exit rule (not a better one)
- Enterable true-catch cohort: 10 trades / 9 days, **mean +0.36R to +0.57R — but 7 of 10 stop
  day-0 and the entire positive sum is ONE trade** (TSAT +6.45R). Without it: **−0.32R**.
- TSAT flips to −1R if entry is 1% higher. Daily bars cannot resolve it; minute bars would.
- Only positive pocket: pre-open + HIGH, **n=5, not signable**. Two of its three winners entered
  through the sustain rule's FAIL-OPEN door — the deployed filter would not have selected them.

## The 0-for-17 constraint, answered
17 closed live trades, 0 winners, mean −0.91R. **The shadow's edge does not survive these exits.**
Every admit-expansion class models negative. The in-window class alone would have added ~70
gate-passing entries at −0.69R over 14 days.

## Recommendation
- **Keep what is on.** No action.
- **Do NOT flip full real-time admission now.**
- **(a) Hold and accumulate to N≥20 pre-open HIGH catches, then re-cut** — after #548's exit
  work lands, because the same cohort under working exits may look materially different.
- NOT: flipping to chase the ACHR anecdote; tightening sustain fail-open (kills the winners);
  treating the 70% residual-capture rate as solved (unattributed since 08-02).

## Limits
Daily-bar model; flat 2.88% stop rather than each name's ORB range; partial-fill haircut from
n=1 (FIGS); LLM grade unsimulated for 501 never-alerted names; 15 days, one regime.
