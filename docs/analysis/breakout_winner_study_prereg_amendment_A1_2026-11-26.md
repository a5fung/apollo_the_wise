# Breakout big-winner study — pre-registration amendment A1 (2026-11-26, operator: "amend")

Amends the frozen pre-registration `docs/analysis/breakout_winner_study_prereg_DRAFT_2026-11-24.md`
(sha256 `3eb2b9b0247bc0ba7bf0d8e6f1efd67da1078fc090373c83c1bc14599339042a`, frozen in `ed4de8ac`). That file is
not edited; this file is read alongside it and wins where they differ.

## Why
Stage 1c gate (c) STOPPED: control set B (the 11-01 Polygon tickers) agreed 314 of 324 = 96.9%, under the 99% line;
control set A agreed 300 of 300. The ten that disagree are symbols that changed hands: Alpaca's SIP history is filed
under TODAY's symbol, so in 2022 Alpaca "B" is Barrick (which took B in 2025, ~$20, 13M shares a day) and Alpaca
"GOLD" is a $73 stock trading 138k a day. The source is not what the pre-registration assumed — exactly what the gate
exists to catch. Evidence: `scripts/probes/_breakout_winner_study_1124/stage1c/gate.txt`, `diag_c.out`.

## The rule (A1)
1. The Alpaca raw-close pull (`apollo_data/cb702/raw_close_bwin_1124.csv.gz`, request sha256 `164da796…`) is
   DISCARDED in full. It stays on disk, unread by any later stage.
2. Every era-B ticker on the request list's main set (raw scale resting on the split list alone, `raw_src` 2 —
   757 names) is treated as NOT RETURNED and takes §1.3's derived-only handling; the "era-B price partly derived"
   tag fires. Control sets A and B play no further part.
3. Nothing else changes: populations, features, statistic, bars, verdict words, seeds, splits, order of work.

## Why this cannot lean toward a result
Written before any forward bar was read: only stages 1a, 1b and 1c (all outcome-free) had run. The affected names
carry 0.80% of era-B pool-candidate name-nights (stage 1c print), and the handling chosen is the pre-registration's
own existing fallback.

## Method and population
Population affected: the 757 main-set tickers of `stage1c/bws1124_raw_request.tsv` (era-B nights 2022-04-01 →
2024-10-03, split-list-only raw scale, at the $5M dollar-volume floor on ≥ 1 night). Derived from sealed local files
only (rows < 2025-01-01); no forward bar read.

## What this does not answer
- Whether Alpaca's history is wrong for names whose symbol never changed — control A says it is right for them; it is
  set aside wholesale because identity cannot be checked name by name without a third source.
- How much the derived-only handling shifts any era-B result; the "partly derived" tag reports it, nothing sizes it.
