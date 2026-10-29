CHECK breakout v1 against his dated good setups — free, local, analysis only. Work in /Users/alvinfung/apollo_the_wise.

v1 (the operator-confirmed starting rules, 2026-10-28; read docs/setups/consolidation_breakout.md "### 2026-10-28" change-log entry and scripts/probes/_qm_0810_review/dating_calibration.md): on daily bars, a breakout day E for a stock qualifies when, with D = E - 1 (everything measured on bars <= D unless it is E's own volume / high):
- universe: raw close >= $5, 20-session median dollar volume >= $10M (this file's universe; use the split-adjusted close for the rest);
- prior move: the highest high in sessions [D-45, D-10] is >= 1.30x the lowest low of the 40 sessions before it (the existing `Prior move` row);
- base: the sessions after that high up to D, 10 to 45 sessions long; higher lows (the lowest low of the last 5 sessions > the base's lowest low);
- SURF: >= 5 consecutive sessions ending at D whose LOW sits within 1.0 ADR (ADR = the 20-session mean of (high - low) / close, in price: ADR% x close) of ONE of the 10-, 20- or 50-day SMA (the same average for the whole run) — report the any-average variant beside;
- TIGHTENING: the mean daily range of the last 5 sessions to D <= 1.1x that of the 5 sessions before them;
- the LEVEL = the base high (the highest high of the base); E's high clears it;
- VOLUME: E's volume >= 1.2x the 50-session average volume ending at D.
(RS >= 98 and the market are NOT part of this check — say so in the output; they need the universe-wide percentile.)

DO:
1. For each of his good setups (tier A+B) in scripts/probes/_qm_0810_review/dated_setups_2020-08-10.tsv (agreed, high/medium confidence; the calibration's 24, plus the 4 secondary rows separately), on /Users/alvinfung/apollo_data/cb702_pre_v2/daily_closes_all.csv.gz (headerless: ticker,date,open,high,low,close,volume; NOTHING after 2020-08-10): does v1 fire on his breakout day (HIT), one or two sessions later (LATE — say how many), earlier in the same base (EARLY), or not at all in 2020-02..2020-08-10 (MISS — say which gate failed on his day)? Also count how many OTHER days v1 fires in that stock's 2020-02..2020-08-10 window (the noise on his own names).
2. The volume of names: run v1 over EVERY stock in the file for every session 2020-02-03..2020-08-07 and report the fires per week (median, quartiles, max) — this is roughly the nightly list he would grade (before RS, which cuts further). Also report the count per week with an RS stand-in: the stock's 63-session return in the top 2% of the file's universe that day.
3. Write the code to scripts/probes/_qm_0810_review/v1_check.py and its full printout to scripts/probes/_qm_0810_review/v1_check.txt (run once; capture once). No network, no production server, no paid call; read nothing after 2024-12-31; spawn no subagents; no git; no edit outside those two files.
RETURN: the hit / late / early / miss table for the 24 (and the 4), the gate that failed on each miss, the noise per name, the fires-per-week numbers with and without the RS stand-in, and anything in the v1 wording that was ambiguous and how you read it.
