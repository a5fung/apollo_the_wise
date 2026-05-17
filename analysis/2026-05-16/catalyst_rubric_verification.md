# Catalyst rubric — Phase 1 verification

_Applied to 114 tickers. Axes 1-3 + 6 scored (structured financials); Axes 4-5 still unscored (consensus + guidance data not fetched yet — future work)._

## Fixture verification

| Ticker | Expected | Got | Composite (scaled) | Match | Caps |
|---|---|---|---:|:---:|---|
| NBIS | game_changer | strong | 22.75 / 39 | ✗ | — |
| CSCO | routine_correct | routine_correct | 16.25 / 39 | ✓ | no_milestone_low_growth |
| KLAR | routine_correct | weak | 0.0 / 39 | ✗ | no_milestone_low_growth |
| TRT | strong | routine_correct | 19.5 / 39 | ✗ | — |
| ONDS | strong | routine_correct | 19.5 / 39 | ✗ | — |
| CPA | strong | weak | 6.5 / 39 | ✗ | no_milestone_low_growth |

## Label distribution across sample

| Label | N | Share |
|---|---:|---:|
| game_changer | 1 | 0.9% |
| strong | 10 | 8.8% |
| routine_correct | 30 | 26.3% |
| weak | 73 | 64.0% |

## Top 15 by composite score

| Ticker | Label | Composite | A1 | A2 | A3 | A6 | n_quarters | source |
|---|---|---:|---:|---:|---:|---:|---:|---|
| VSNT | game_changer | 32.5 | 5 | 5 | 4 | 1 | 6 | polygon |
| RSI | strong | 29.25 | 5 | 3 | 4 | 1 | 8 | polygon |
| AEHR | strong | 27.62 | 4 | 3 | 4 | 2 | 8 | polygon |
| VIAV | strong | 27.62 | 5 | 3 | 1 | 3 | 8 | polygon |
| AIP | strong | 24.38 | 5 | 0 | 4 | 1 | 8 | polygon |
| ARX | strong | 24.38 | 5 | 0 | 4 | 1 | 8 | polygon |
| BE | strong | 24.38 | 5 | 0 | 4 | 1 | 8 | polygon |
| STX | strong | 24.38 | 3 | 5 | 4 | 0 | 8 | polygon |
| TEAM | strong | 24.38 | 4 | 5 | 1 | 1 | 8 | polygon |
| EOSE | strong | 22.75 | 5 | 0 | 4 | 0 | 8 | polygon |
| NBIS | strong | 22.75 | 4 | 3 | 1 | 2 | 5 | yfinance |
| VG | routine_correct | 22.58 | 5 | None | 0 | 1 | 8 | polygon |
| PACS | routine_correct | 21.12 | 2 | 5 | 4 | 0 | 7 | polygon |
| PCT | routine_correct | 21.12 | 4 | 0 | 4 | 1 | 5 | yfinance |
| SITM | routine_correct | 21.12 | 4 | 0 | 5 | 0 | 8 | polygon |
