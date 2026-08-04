# Why the live cohort loses — per-trade forensic, 13 closed trades (2026-08-04)

**Task #503.** Read-only. Nothing changed.

## The headline, and a correction to my own framing

Yesterday I told the operator *"we're giving back winners."* **That is true of 3 trades, not 13.**
The other 10 never got meaningfully green — there was nothing to give back. The corrected split:

| what happened | n | classification |
|---|---|---|
| reached **≥ +2R**, ended a loser | **3** | **(d) exit discipline** |
| reached +1R to +1.6R, ended a loser | 2 | (d) borderline — the +2R rule would NOT have caught these |
| never reached +1R | **8** | **(e) regime** — a momentum system finding nothing in a hostile tape |

## Every closed live trade, best move reached before its exit

| ticker | date | regime | peak reached (R) | realized (R) |
|---|---|---|---|---|
| MANE | 07-15 | Choppy | **+7.92** | −0.23 |
| QBTS | 07-27 | Correcting | **+3.74** | −1.00 |
| SMCI | 07-22 | Correcting | **+2.90** | −0.70 |
| CRCL | 07-10 | Choppy | +1.62 | −1.01 |
| NVCR | 07-23 | Correcting | +1.22 | −1.00 |
| WKC | 07-24 | Correcting | +0.90 | −1.03 |
| WULF | 07-06 | Choppy | +0.65 | −1.00 |
| THC | 07-24 | Correcting | +0.64 | −1.01 |
| HUT | 07-20 | Correcting | +0.51 | −1.07 |
| FTNT | 07-30 | Crisis | +0.40 | −1.03 |
| WDFC | 07-10 | Choppy | +0.29 | −1.04 |
| BTDR | 08-04 | Choppy | +0.22 | −1.03 |
| TSEM | 07-14 | Correcting | 0.00 | −1.00 |

## What each cause explains

**(d) Exit discipline — 3 trades.** MANE reached nearly eight times the risk taken and finished
down. QBTS and SMCI both cleared +2R. **These are exactly what the +2R profit trigger (live since
2026-08-01) exists to bank**, and it would have converted all three.

**(e) Regime — 8 trades.** They peaked between 0.00R and +0.90R. No exit rule banks a move that
never happens. **All 13 trades are in non-Bull regimes** — 8 Correcting, 4 Choppy, 1 Crisis, and
zero Bull. A breakout system in a corrective tape finding nothing is the system working, not
failing.

**(c) Entry mechanics — ruled out.** The 2026-08-03 stop-width replay tested widths up to 5.6×
current, including prior-day-low: **every loser still lost at every width**, and the simulated
cohort's apparent gains were carried by ≤5 outliers that vanish when removed.

**(b) Entry quality — ruled out.** Alerts market-adjusted return **+8.5% median over five days at a
90% win rate** (`catalyst_type_forward_signal`, 2026-08-03). Selection is healthy; the gap is
between the alert and the trade.

**(a) Variance — insufficient alone.** P(13 straight losses) at a 25-30% win rate is well under 1%.
Variance does not explain the streak by itself; regime plus three banked-then-lost winners does.

## Stops are working — say it plainly

Mean realized is ≈ **−1R**. Trades exit at plan, not worse. The earlier worry that stops sit at half
a normal day's range is real as a *description* but is **not the cause of the losses** — the replay
settled that.

## Recommendation

- **No new change.** The one lever the evidence supports is already live.
- **Re-measure after the next Bull stretch.** Eight of thirteen losses are a regime the system is
  not designed to profit in; judging it only on hostile tape is judging the wrong thing.
- **The honest open question is the 2 middle trades** (+1.2R and +1.6R) that the +2R rule misses.
  Whether to add a lower tier is a criteria change — CHANGE_PROCESS, N≥10, operator sign-off — and
  n=2 does not clear it.
