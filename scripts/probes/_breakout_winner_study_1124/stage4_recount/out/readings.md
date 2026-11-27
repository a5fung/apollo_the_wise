# Readings the frozen text leaves open (fixed before any stage output was opened)
1. A1: raw_close_bwin_1124.csv.gz never opened; era-B raw_src==2 names are derived-only (feature 2 NULL); notreturned_A1.txt used only as a cross-check at the end.
2. A2: f20 pooled discovery ratio read as observed / composition-expected (stage 2's number); applied only at the decision step after stage 2 may be opened.
3. Keep rule: blocked when a KEPT row of the identity lies in [ci-60, ci-1] (inclusive 60); first-break-after-10-quiet = previous break row >= 11 sessions earlier; coin = sha256("1124|ident|D")[:8] big-endian / 2^64.
   All three SETTLED by reproducing the text's own indicative numbers on the 11-13 capture (15,312 / 12,384 / 10,514 / 8,621; per-year 814/1,232/1,198/3,439/3,083/748; 3,054 tickers; 10,545 and 1,108).
4. Identity = connected component of the EP-style map recomputed from the 2021-09-27..2022-06-30 overlap closes (A2 identity_alt); string = alphabetically first era-A ticker else era-B.
5. Guard file era B = scripts/backtest_data_audit/runs_2026-10-23/universe/symbol_guard_B.tsv; adjustment flags = the two klasses of A_flags.tsv / B_flags.tsv (EP 4.0), dates >= 2025 dropped at read.
   Drop window = calendar sessions D-85..E (dates); drop reasons counted first-match in the order guard/flag, file-start, window-end. "split-list date not reflected in the bars" read as the adjustment flags; the raw split-list-in-window variant counted but NOT applied.
6. File-start artefact: ticker's first bar within 5 sessions of the era file start AND ((lower line unscored AND bars to D < 189) OR (ret126 blank AND bars to D < 120)).
7. Window end: ci(E)+60 > last session of the era calendar (era A file end 2022-06-30; era B sealed copy end 2024-12-31).
8. Windows for self-computed features: calendar sessions ci(D)-n+1..ci(D); NULL order history, coverage<90%, adjustment (flags), identity (guard), zero volume; 10/11/22/23 use history/coverage/identity only (text: "or a guard break lies inside").
   f8 = close(D)/min low(D-19..D) - 1 ; f13 window = the base (base_len sessions); f18 window D-19..D with D-20 as prior close; f21 window 200.
9. Outcomes: window ends at the session BEFORE a guard break dated E+1..E+60, or before a bar where raw/adj factor steps (>0.5% rel, variants 0.01% and 2% printed) AND the adjusted close moves >=+70% / <=-50%. Highest close includes E.
10. Stats: thirds by np.array_split sizes, tie block -> third of the lower-middle position of the block; strata (era, month) >= 6; MH for two-group (months with >=2 of each);
    tie-heavy fallback when pooled top or bottom third < 20% of scored; description-only: smaller group <100 or <15% (two-group), 24a/24b <300 scored.
    Permutation: u=default_rng(1124).random((10000,n)) events ordered (era,E,ticker); labels re-dealt in key order within (era,month) among events scored on the feature.
    Two-sided p = (1+#{|logr_perm|>=|logr_obs|})/10001. Bootstrap: default_rng(1124), 2000 draws of (era,month) blocks, 5th-95th percentile. Smoothing (w+.5)/(n+1) when either third has no winner.
    z = |log ratio| / SD(permuted log ratios), on the own set, on the group-common set, on the all-candidate common set (excluding 24a/24b).
11. Group and cap, two readings: R1 = winners chosen among candidates passing conditions 1-3; R2 = winners chosen among all candidates then required to pass 1-3. Reported both.
