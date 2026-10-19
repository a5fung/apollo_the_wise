# #702 — does QULLAMAGGIE'S OWN SELECTION beat the average base? Pre-registration (2026-10-19, BEFORE any outcome)

**Why.** The holdout read (2026-10-19) failed the setup as tested — the trendline breakout bought at the 5-minute
opening-range high with the day's-low stop — on every testable cell. About 2 in 3 trades stop out within two sessions,
whatever the base. The operator approved ("ok", 2026-10-19) the next question: are the bases Qullamaggie himself picked
on his streams better than the average base our detector admits? If yes, the edge sits in a selection our filters do not
capture; if no, the base itself is not where the edge is.

## Method / population

- **His picks** = stock-bases from the 2016–2022 stream label set
  (`apollo_data/cb702/qm_streams/ext_2016_2022/labelled_candidates_ext.tsv`, `source = stream`, clean cut `hq = 1`) whose
  base was still IN PLACE on the talk day (`status_at_ref = in_base_at_ref`) — 330 distinct stock-bases — AND whose first
  breakout day E falls STRICTLY AFTER the talk date. A base he discussed after it broke out is excluded (hindsight).
  The 58–60 frame-verified bases (`vision/p4b_label_lines.tsv`) are reported beside as the stronger label.
- **Controls** — two, both from the SAME era, universe rules and detector (C0 on Alpaca-derived daily bars, 2017–2021):
  (a) every other C0 base (first breakout per base) whose E falls in the same calendar month as a pick's E;
  (b) the other C0 bases of the SAME tickers in the era (controls for "he talks about stocks that are already running").
- **Bars.** Alpaca SIP split-adjusted daily bars 2016-01..2022-06 (`qm_streams/alpaca_all_2016_2022/`), the runner's
  universe and C0 rules unchanged. Named differences from the 2022–26 runs: RS percentiles over Alpaca's symbol list
  (survivorship-biased — Alpaca omits many delisted names); security type unknown for many delisted names (admitted, as
  prod does; counted); no Apollo regime label before 2025 (months are matched instead).
- **Decisive metric (measures the base, not the entry that just failed):** the 20-session forward return from the breakout
  level, in ADR20 units: (close of E+20 − level) ÷ (level × ADR20 at E−1). Beside: max favourable excursion over 10 and 20
  sessions in ADR units; the share of bases reaching +5 ADR within 20 sessions; and, when minutes are fetched, the primary
  arm's R and ≥5R share.
- **The bar.** Difference = picks' mean − control (a)'s month-matched mean, with a month-block bootstrap 95% interval
  (2,000 resamples, seed 702). Lower end > 0 → **his selection adds edge**; upper end < 0 → **his picks did worse**;
  otherwise **can't tell**. Control (b) is reported beside with the same interval and decides nothing.
- **n.** Expected picks with a breakout after the talk: roughly 100–250 of the 330. A result on fewer than 30 picks is
  CAN'T TELL whatever the interval says.

## What this does not answer

- Whether the setup can make money: a better base can still lose under an entry that stops out 2 in 3 trades early.
- Whether WE can find his picks: the label is what he chose to talk about, not a rule; a positive result says the edge
  exists in selection, not how to compute it.
- 2020–21 dominate the picks (one strong bull market); the controls share the months, not necessarily the regime mix
  within a month.
- WOULD-FAIL-IF / the confound: a reader of his streams cannot tell a pick from a mention — stocks he talks about may simply
  be stocks already running. Control (b) is there to see it; a positive (a) with a null (b) reads as "his tickers", not
  "his bases".
