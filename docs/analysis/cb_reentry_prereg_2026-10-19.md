# #702 — RE-ENTRY after a stopped first break: pre-registration (2026-10-19, BEFORE any re-entry outcome is read)

**Why.** The article's own example (TSLA 2020, re-shared by the operator 2026-10-19) shows the flaw: our rules bought the
first push above the May triangle's line (2020-05-18) and were stopped out the same day; the real breakout came on
2020-06-01, and the one-trade-per-base rule skipped it as a repeat break. Qullamaggie re-buys. The operator approved the
test ("Ok", 2026-10-19).

## Method / population
- **Level / entry / stop / exit:** the trendline level (`tl`), the 5-minute opening-range-high entry (ORH5), the low-of-day
  stop (no wider than one ADR20), and the ARTICLE exit `p33_s3_t10` — the only exit arm the runner computed on repeat
  breaks (his exit with the staller cut was computed on first breaks only; it read within noise of this arm on C0/C1).
- **Base** = the spec key (ticker, pole date). **Rule R1 (decides):** take the first break; when that trade has EXITED (any
  terminal exit) before a later break of the same base, take the NEXT break strictly after the exit day as ONE re-entry.
  Breaks while a trade is open are skipped. Beside: R2 = up to two re-entries; Rall = every break after each exit.
- **Exit day** = E + `sessions_held` sessions on the ticker's own trading days (0 = the breakout day).
- **Cells:** C0 (all bases) decides; C1 and C3 reported beside.
- **Periods:** 2022-03..2024-12 (discovery) DECIDES. 2025-01..2026-10 is reported beside as DESCRIPTIVE ONLY: it was read
  once for the registered primary; this is a new question on seen data, so a positive there is not a holdout pass.
- **Bar (discovery, C0):** the re-entry trades' own mean R, month-block bootstrap 95% interval (2,000 resamples by the
  month of E, seed 702): lower end > 0 → **re-entry adds edge**; upper end < 0 → **re-entry loses**; else **can't tell**.
  Also reported: per-base total R (first + re-entry) vs first-only, the ≥5R share, trades per base.
- **Consequence fixed now:** any positive goes to the forward SHADOW as a recorded rule, never straight to paper.

## What this does not answer
- His exit on re-entries (not computed for repeat breaks).
- Whether he would re-buy the SAME base after a stop (assumed from the TSLA example) or wait for the next base.
- The entry itself: a re-entry still buys an opening-range high with the day's-low stop, the mechanic that loses 2 in 3
  trades within two days.
