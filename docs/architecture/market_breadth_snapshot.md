# Market breadth snapshot (#719) — the nightly export behind the dashboard's "Market Breadth" page

> SSoT for the breadth snapshot: every rule that produces a number, the JSON contract field by
> field, where it is produced and consumed, and what it does not claim. Registered in
> `docs/SSoT.md` 2026-11-04. Update THIS file in the same commit as any change to
> `scripts/export_breadth_snapshot.sql` (its `definitions` object is what the page prints, so the
> SQL, that object and this file must say the same thing) or to the breadth block of
> `scripts/auto_export_snapshots.sh`.
>
> ⚖ **Display only.** Nothing here feeds a trade, a grade, an alert, sizing or any safeguard. It is
> the operator's 11-04 idea (a daily breadth + theme view to complement the longer-term pages and
> the alerts), with another app's screenshot as the model:
> `docs/methodology/operator_shared_charts/2026-11-04_daily_breadth_dash_example/`.

## Where it is produced and consumed

| | |
|---|---|
| Query | `scripts/export_breadth_snapshot.sql` — ONE read-only SELECT emitting ONE JSON object (`psql -A -t -X`) |
| Run by | `scripts/auto_export_snapshots.sh` on the prod host, the same nightly host cron as the themes / trades / funnel snapshots (#194) |
| Guard | Unlike the other three (all-or-nothing: any one failing aborts the push), the breadth export runs **guarded**: `psql -v ON_ERROR_STOP=1` with a **300 s `statement_timeout`** (`PGOPTIONS`; a hung query ends as a non-zero exit instead of holding up the other three) into `apollo_breadth_snapshot.json.tmp`; if it exits non-zero or the output is under 200 bytes, the script logs to stderr, deletes the temp file, leaves the last published breadth file untouched, and commits the other three without it. The snapshot files live in one bash array (`SNAPSHOTS`; the breadth file is appended only on success); change detection stages them (`git add`) and tests `git diff --cached --quiet`, because the breadth file's first publish is a new, untracked file that a plain `git diff --quiet` does not see |
| Output | `apollo_breadth_snapshot.json` in the portfolio-app2 repo (pushed with the others) |
| Consumer | portfolio-app2's Market Breadth page (#719's dashboard half — NOT built in this repo). Four panels: highs vs lows, advances vs declines, the stage 1-4 stacked bar, the theme tracker with a Today / 1W / 1M / YTD toggle |
| Cost | Read-only. Measured on prod 2026-11-04: **15 s** on the first run, **11 s** after the review fixes, **174 KB**. The 300 s `statement_timeout` leaves ~20x headroom over the first run |
| Verified | `scripts/probes/_719_export_breadth_1104/` — the SQL on a real Postgres against a synthetic fixture, every number recomputed independently in Python from the written rules (PASS), plus removal deltas for each hand-made case (`output.txt`), and the prod-sized timing run (`scale_output.txt`, `scale_plan.txt`) |
| Static tests | `tests/test_719_export_breadth_sql.py` — one read-only statement, every contract key, each pinned rule, and the shell's guard RUN against a fake `docker` and a real local git remote |

## The rules (what each number means)

**Dates come from the data, never the clock.** The cron also runs on Saturday and Sunday, so the
calendar date is not a trading day.

- **Session** — a `trade_date` on which at least **3,000** `mi_daily_closes` rows join
  `mi_security_types` as `CS` or `ADRC`. This guards a partial ingest (an on-demand fetch stamped
  with the calendar date). The calendar is read over the last 500 calendar days before the newest
  `trade_date` in the table (~344 sessions; 273 are needed).
- **Future-date ceiling** — the newest `trade_date` that anchors that calendar is the newest one **at
  or before today's ET date**, so one stray future-dated row cannot move the calendar window.
- **Session index** — 0 = as_of, 1 = the session before it, and so on. Every window below is
  counted in session indexes, never by calendar arithmetic. The price window is the newest 273
  sessions (as_of + 272 prior).
- **as_of** — the newest session. `prev_session` = session 1. `prior_year_end` = the last session
  of the calendar year before as_of's year.
- **No session at all** (an empty or broken calendar) → the statement returns **zero rows**, so
  psql prints nothing and the nightly guard's 200-byte floor rejects it. Without that, the
  definitions text alone would carry an all-null object past the floor and publish it.
- **Bar** — a `mi_daily_closes` row on a session with `close > 0`. Rows on non-session dates are
  ignored.
- **NaN-close exclusion** — a row whose `close` is NaN is not a bar: it is dropped from the price
  window before any per-ticker number, so it reaches no close, return, high / low or stage average
  (Postgres orders NaN above every number, so `close > 0` alone would let it through).
- **Universe** — `security_type IN ('CS', 'ADRC')` with a close **≥ 1.00** on as_of. Its count is
  `universe.n`.

**New 52-week highs and lows** (over the universe):

- **Lookback** — the **252 sessions before as_of** (indexes 1-252; as_of excluded).
- **Usable bar** — `high_price > 0 AND low_price > 0`. A missing (NULL) or zero high or low is never
  usable, never enters a max/min, and can never make a new high or low.
- **Eligible** — a universe stock with a usable bar on as_of AND usable bars on **≥ 245** of the 252
  lookback sessions. Count: `highs_lows.eligible_n`.
- **New high** — an eligible stock whose as_of high is **at or above** the highest lookback high.
- **New low** — an eligible stock whose as_of low is **at or below** the lowest lookback low.
- A stock can, in principle, be both (an outside day engulfing the whole year).

**Advances / declines** (over the universe): as_of close vs the close on `prev_session` —
greater = advance, lower = decline, equal = unchanged. A stock with no bar on `prev_session` counts
in `no_prior` instead, so `advances + declines + unchanged + no_prior = universe.n`.

**Weinstein stage** (over the universe; the 30-week line = the 150-session SMA of close):

- **sma_now** — the mean close over sessions 0-149. **sma_20** — the same mean ending 20 sessions
  earlier (sessions 20-169). **sma_60** — ending 60 sessions earlier (sessions 60-209).
- **Needs a bar on at least 203 of the 210 sessions 0-209** (150 + the 60-session look-back; up
  to 7 missing, the same slack as the 245-of-252 high/low rule), else `unstaged`. Relaxed 2026-11-04
  from "all 210" after the first prod run: of 5,035 universe names, 169 had 1-7 missing bars (now
  staged), 209 have 8+ missing and 439 are listed under 210 sessions (both stay unstaged). Each SMA
  averages the real closes present in its window.
- **Slope** = `sma_now / sma_20 − 1`: **rising** if > +0.01, **falling** if < −0.01, else **flat**.
- **Rising**: close ≥ sma_now → **2**, else **3**. **Falling**: close ≤ sma_now → **4**, else **1**.
  **Flat**: sma_now > sma_60 (it came from an advance) → **3**, else → **1**.
- Stages 1 + 2 + 3 + 4 + unstaged **= universe.n** exactly (all five are counted over the same
  rows; a stock is unstaged when its stage is null).

**Themes:**

- **Active themes** — `db.get_active_themes`' rule, anchored on as_of instead of the clock: the
  LATEST `mi_themes` row per name with `theme_date >= as_of − 7 days` FIRST, then drop names whose
  latest row is `Retired` (filtering Retired inside the DISTINCT ON would resurrect a freshly
  retired theme from an older row — the 2026-06-09 #214 bug). No upper bound on `theme_date`: a
  weekend run may read a theme row dated after as_of. Ties on the same date break on the newest `id`.
- **e_code** — `mi_theme_ecosystems.e_code` by `theme_name`, the theme export's join; null when
  unmapped.
- **Members** — the distinct non-empty tickers of the latest row (a repeated ticker counts once).
- **Returns** — `strength_map._basket` semantics: equal-weighted mean of member returns in
  percent, rounded to 2 decimals. **Today / 1W / 1M** = as_of close vs the close 1 / 5 / 21
  sessions earlier; **YTD** = as_of close vs the member's last close on or before `prior_year_end`
  (looking back no further than the 273-session window). A member without both closes drops out of
  that window; `n_<window>` counts the members that had them; a window no member could fill is null.
  Differs from `strength_map._ret` in one way: that indexes by the ticker's OWN bars, this indexes
  by market sessions, so a member's stale close is never passed off as the window's start.
- ⚠ **Survivorship** — membership is TODAY's list (`theme_membership: "today"`), applied to every
  window. Over 1M and YTD that flatters a theme: names often joined it because they had already
  run. The page should say so next to the 1M / YTD toggle.

**Stocks map** — one entry per universe stock AND per active-theme member (members outside the
universe — an ETF, a sub-$1 name, a name with no bars — are included so the theme drill-down
resolves): `[stage, rs_rank, theme_indexes]`.

- `stage` — 1-4, or null when unstaged. Computed for any listed ticker with a bar on at least 203 of the 210 sessions; only universe stocks are counted in `stages`.
- `rs_rank` — from `mi_stock_scores` on the newest **usable** score date: the theme export's
  `usable_score_date` rule verbatim (the newest date holding at least half the median row count of
  the last 10 scored dates — never `max(score_date)`, which a one-row on-demand lookup can capture).
  ⚠ The rank's denominator is the ~2,400 names the RS run keeps, not the universe; most of the
  universe has a null rank.
- `theme_indexes` — positions in the `themes` array. ONE ordering (theme name) feeds both, so an
  index always points at the right theme.

## The JSON contract

One object. Types are JSON types; "date" = a `YYYY-MM-DD` string.

| field | type | meaning |
|---|---|---|
| `version` | int | contract version, `1` |
| `generated_at` | string | `YYYY-MM-DDTHH:MM:SS ET` — when the export ran |
| `as_of` | date | the newest session; every number is as of its close |
| `prev_session` | date | session 1 (the advances / declines comparison) |
| `prior_year_end` | date \| null | the YTD base session; null if the data holds no prior-year session |
| `score_date` | date \| null | the RS run `rs_rank` comes from |
| `theme_membership` | string | always `"today"` — the survivorship label |
| `universe` | object | `{ "n": int }` |
| `highs_lows` | object | `{ "eligible_n": int, "new_highs": int, "new_lows": int }` |
| `adv_dec` | object | `{ "advances": int, "declines": int, "unchanged": int, "no_prior": int }` |
| `stages` | object | `{ "1": int, "2": int, "3": int, "4": int, "unstaged": int }` — sums to `universe.n` |
| `themes` | array | one object per active theme, ordered by name (see below) |
| `stocks` | object | `{ "<TICKER>": [stage int \| null, rs_rank int \| null, [int, ...]] }` |
| `definitions` | object | the rules above in plain words, keyed `session`, `as_of`, `universe`, `new_highs_lows`, `advances_declines`, `stage`, `themes`, `theme_returns`, `theme_membership`, `stocks`, `not_claimed` — the page prints them |

Each `themes[]` object:

| field | type | meaning |
|---|---|---|
| `idx` | int | its position in the array (0-based) — what `stocks[...][2]` refers to |
| `name` | string | theme name |
| `stage` | string | the theme's lifecycle stage (Nascent / Accelerating / Mainstream / Fading) |
| `e_code` | string \| null | its ecosystem code |
| `theme_date` | date | the snapshot date its membership comes from (may post-date `as_of` on a weekend run) |
| `n_members` | int | distinct members |
| `members` | array of string | the members, sorted |
| `ret_1d` / `ret_5d` / `ret_21d` / `ret_ytd` | number \| null | equal-weighted member return in percent (Today / 1W / 1M / YTD) |
| `n_1d` / `n_5d` / `n_21d` / `n_ytd` | int | members that had the data for that window |

Size: no per-day history; the stocks map dominates (~25-30 bytes a ticker). Target < 600 KB.

## What it does NOT claim

- **No money, no signal.** Display only; nothing on the trading path reads it, and it is not a
  regime input (the regime's own breadth lives in `mi_market_regime`).
- **Not a full-market count.** The universe is what `mi_daily_closes` × `mi_security_types` holds
  (CS + ADRC, ≥ $1); a ticker without a security-type row is outside it.
- **Theme returns are not a backtest.** Today's membership over past windows is survivorship-biased
  (above); a 1M / YTD theme number is a description of today's basket, not of the theme as it stood.
- **A stage is a mechanical read of one moving average**, not a chart read.

## Change log

- **2026-11-04** — built (#719, Apollo half): the export, the guarded nightly step, the static and
  shell tests, the embedded-Postgres probe. The dashboard page is the portfolio-app2 half.
