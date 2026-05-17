# Catalyst rubric — Phase 1 verification

_Applied to 50 tickers. Axes 1-3 + 6 scored (structured financials); Axes 4-5 still unscored (consensus + guidance data not fetched yet — future work)._

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
| game_changer | 0 | 0.0% |
| strong | 3 | 6.0% |
| routine_correct | 14 | 28.0% |
| weak | 33 | 66.0% |

## Top 15 by composite score

| Ticker | Label | Composite | A1 | A2 | A3 | A6 | n_quarters | source |
|---|---|---:|---:|---:|---:|---:|---:|---|
| RSI | strong | 29.25 | 5 | 3 | 4 | 1 | 8 | polygon |
| TEAM | strong | 24.38 | 4 | 5 | 1 | 1 | 8 | polygon |
| NBIS | strong | 22.75 | 4 | 3 | 1 | 2 | 5 | yfinance |
| VG | routine_correct | 22.58 | 5 | None | 0 | 1 | 8 | polygon |
| SITM | routine_correct | 21.12 | 4 | 0 | 5 | 0 | 8 | polygon |
| WYFI | routine_correct | 20.53 | 3 | None | 4 | 0 | 5 | yfinance |
| LC | routine_correct | 19.5 | 3 | 2 | 3 | 1 | 8 | polygon |
| MNDY | routine_correct | 19.5 | 2 | 4 | 4 | 0 | 5 | yfinance |
| ONDS | routine_correct | 19.5 | 5 | 0 | 1 | 1 | 8 | polygon |
| TRT | routine_correct | 19.5 | 5 | 0 | 1 | 1 | 8 | polygon |
| FLY | routine_correct | 17.88 | 3 | 2 | 1 | 2 | 5 | yfinance |
| TWLO | routine_correct | 17.88 | 3 | 0 | 4 | 1 | 8 | polygon |
| VISN | routine_correct | 16.42 | 2 | 4 | None | 0 | 5 | yfinance |
| CSCO | routine_correct | 16.25 | 2 | 2 | 4 | 0 | 8 | polygon |
| JMIA | routine_correct | 16.25 | 3 | 1 | 1 | 2 | 5 | yfinance |
