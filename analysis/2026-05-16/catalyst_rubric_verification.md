# Catalyst rubric — Phase 1 verification

_Applied to 97 tickers. Axes 1-3 + 6 scored (structured financials); Axes 4-5 still unscored (consensus + guidance data not fetched yet — future work)._

## Fixture verification

| Ticker | Expected | Got | Composite (scaled) | Match | Caps |
|---|---|---|---:|:---:|---|
| NBIS | game_changer | NOT_FETCHED | — | ✗ | — |
| CSCO | routine_correct | routine_correct | 14.62 / 39 | ✓ | no_milestone_low_growth |
| KLAR | routine_correct | routine_correct | 17.33 / 39 | ✓ | no_milestone_low_growth |
| TRT | strong | NOT_FETCHED | — | ✗ | — |
| ONDS | strong | NOT_FETCHED | — | ✗ | — |
| CPA | strong | weak | 6.5 / 39 | ✗ | no_milestone_low_growth |

## Label distribution across sample

| Label | N | Share |
|---|---:|---:|
| game_changer | 0 | 0.0% |
| strong | 10 | 10.3% |
| routine_correct | 35 | 36.1% |
| weak | 52 | 53.6% |

## Top 15 by composite score

| Ticker | Label | Composite | A1 | A2 | A3 | A6 | n_quarters | source |
|---|---|---:|---:|---:|---:|---:|---:|---|
| INOD | strong | 29.25 | 5 | 4 | 4 | 0 | 8 | polygon |
| STRL | routine_correct | 27.62 | 5 | 5 | 0 | 2 | 8 | polygon |
| STX | strong | 27.62 | 4 | 5 | 4 | 0 | 8 | polygon |
| TWLO | strong | 26.0 | 3 | 5 | 4 | 1 | 8 | polygon |
| BE | strong | 24.38 | 5 | 0 | 4 | 1 | 8 | polygon |
| LASR | strong | 24.38 | 5 | 0 | 4 | 1 | 8 | polygon |
| SITM | strong | 24.38 | 5 | 0 | 5 | 0 | 8 | polygon |
| GKOS | strong | 22.75 | 4 | 0 | 4 | 2 | 8 | polygon |
| HUT | strong | 22.75 | 4 | 3 | 1 | 2 | 8 | polygon |
| RSI | strong | 22.75 | 4 | 2 | 4 | 0 | 8 | polygon |
| TEAM | strong | 22.75 | 4 | 3 | 1 | 2 | 8 | polygon |
| AIP | routine_correct | 21.12 | 4 | 0 | 4 | 1 | 8 | polygon |
| AMD | routine_correct | 21.12 | 3 | 4 | 3 | 0 | 8 | polygon |
| FTAI | routine_correct | 21.12 | 5 | 3 | 0 | 0 | 8 | polygon |
| PCT | routine_correct | 21.12 | 4 | 0 | 4 | 1 | 5 | yfinance |
