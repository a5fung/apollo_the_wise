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
| Consumer | portfolio-app2's Market Breadth page (#719's dashboard half — NOT built in this repo). Four panels: highs vs lows, advances vs declines, the stage 1-4 stacked bar, the theme tracker with a Today / 1W / 1M / YTD toggle. #722 adds the ecosystem group tiles that lead the theme tracker (the `ecosystems` array; the page half is portfolio-app2's) |
| Cost | Read-only. Measured on prod 2026-11-04: **15 s** on the first run, **11 s** after the review fixes, **174 KB**. The 300 s `statement_timeout` leaves ~20x headroom over the first run. #722's groups add three small CTEs over the theme members already read (no new table read) and ~5-7 KB of output; on the prod-sized local fixture the run stayed at ~4 s (`scale_output.txt`) |
| Verified | `scripts/probes/_719_export_breadth_1104/` — the SQL on a real Postgres against a synthetic fixture, every number recomputed independently in Python from the written rules (PASS), plus removal deltas for each hand-made case (`output.txt`), and the prod-sized timing run (`scale_output.txt`, `scale_plan.txt`). #722: the fixture carries ecosystem groups (a stock shared by two themes of one group, an unmapped theme, an explicit E-UNASSIGNED, a code outside the YAML, a group of memberless themes) and the Python recompute re-derives the names from the YAML; `check_722_existing_bytes.py` (`output_722_bytes.txt`) proves the text of every pre-#722 key is unchanged |
| Static tests | `tests/test_719_export_breadth_sql.py` — one read-only statement, every contract key, each pinned rule, the `eco_names` list == `theme_ecosystems.yaml`, and the shell's guard RUN against a fake `docker` and a real local git remote |

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

**Ecosystem groups** (#722) — the `ecosystems` array: the active themes grouped by the ecosystem they are filed under, so the page can lead with the ~19 big groups instead of 140 small themes (93 of 144 themes hold 6 or fewer stocks).

- **Which group a theme is in** — its `e_code`. A theme with **no `mi_theme_ecosystems` row** (e_code null) is filed under `E-UNASSIGNED`, the catch-all `theme_ecosystems.py` / the `/themes` board already uses; `themes[].e_code` itself stays null. One entry per group that holds at least one exported theme, ordered by `code`.
- **Members count once** — a group's members are the DISTINCT tickers across all its themes (`n_members`; members with no price bars included, as in a theme's own count). A stock held by three themes of one group is one member, one vote in its return and one in `up_`. A stock held by themes of two *different* groups counts once in each — it is in both.
- **Returns** — exactly a theme's rule, applied to those unique members: equal-weighted mean in percent, 2 decimals, from the same bases (Today = 1 session back, 1W = 5, 1M = 21, YTD = the member's last close on or before `prior_year_end`). A member without both closes drops out of that window; `n_<window>` counts those that had them; a window none could fill is null. `up_<window>` = members with a positive return (as_of close above the base close), so `up_` ≤ `n_` ≤ `n_members`.
- **Group with no members** — a group whose themes hold no tickers is still listed, with `n_members` 0, null returns and zero counts.
- **Names** — the curated names live in `theme_ecosystems.yaml` (the SSoT for the E-* axis, deliberately not a DB table). The export is a bare psql file with no Python, so it carries a copy: the `eco_names` VALUES list, copied verbatim. **`tests/test_719_export_breadth_sql.py::test_eco_names_equal_theme_ecosystems_yaml` fails the build if the list and the YAML disagree — a renamed or added ecosystem needs `eco_names` updated in the same commit.** At output time `E-UNASSIGNED` prints as **`Other`** (not the YAML's "Unassigned"), and a code that is in no list (an auto-promoted ecosystem from `mi_theme_ecosystems_dynamic`) prints as its own code.
- Same guards as everything else: NaN closes never reach it (it reads `px`), the future-date ceiling and the 3,000-row session rule are upstream of it, and the whole thing stays inside the one read-only statement.

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
| `ecosystems` | array | #722 — one object per ecosystem group holding an exported theme, ordered by code (see below) |
| `stocks` | object | `{ "<TICKER>": [stage int \| null, rs_rank int \| null, [int, ...]] }` |
| `definitions` | object | the rules above in plain words, keyed `session`, `as_of`, `universe`, `new_highs_lows`, `advances_declines`, `stage`, `themes`, `ecosystems`, `theme_returns`, `theme_membership`, `stocks`, `not_claimed` — the page prints them |

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

Each `ecosystems[]` object (#722; the contract version stays `1` — the array is additive and no existing key changed):

| field | type | meaning |
|---|---|---|
| `code` | string | the ecosystem code (`E-CYBR`, ..., `E-UNASSIGNED`; an auto-promoted code too) |
| `name` | string | the plain name: the YAML's curated name; `E-UNASSIGNED` -> `Other`; a code in no list -> the code itself |
| `theme_idx` | array of int | positions in `themes` of the themes filed under this group — what the page expands to |
| `n_members` | int | UNIQUE member tickers across those themes |
| `ret_1d` / `ret_5d` / `ret_21d` / `ret_ytd` | number \| null | equal-weighted return of the unique members in percent (Today / 1W / 1M / YTD), the themes' own bases |
| `n_1d` / `n_5d` / `n_21d` / `n_ytd` | int | unique members that had both closes for that window |
| `up_1d` / `up_5d` / `up_21d` / `up_ytd` | int | of those, how many had a positive return — the page's "members up / total" is `up_<w>` / `n_<w>` |

Size: no per-day history; the stocks map dominates (~25-30 bytes a ticker). Target < 600 KB. #722's `ecosystems` adds ~5-7 KB.

## What it does NOT claim

- **No money, no signal.** Display only; nothing on the trading path reads it, and it is not a
  regime input (the regime's own breadth lives in `mi_market_regime`).
- **Not a full-market count.** The universe is what `mi_daily_closes` × `mi_security_types` holds
  (CS + ADRC, ≥ $1); a ticker without a security-type row is outside it.
- **Theme returns are not a backtest.** Today's membership over past windows is survivorship-biased
  (above); a 1M / YTD theme number is a description of today's basket, not of the theme as it stood.
- **A stage is a mechanical read of one moving average**, not a chart read.
- **A group is a description of today's baskets, not a signal.** Its members are today's theme lists (the survivorship caveat above applies to a group's 1M / YTD exactly as to a theme's), and a group filed under `E-UNASSIGNED` / `Other` is a holding lane for unmapped themes, not a coherent sector.

## Live breadth (#723) — the Today view during the session

His ask (2026-11-08): *"market breadth should be live"* · *"Only today needs to be live"*. Only the TODAY numbers
(new highs / lows, advances / declines, the groups' and themes' 1-day returns) are recounted during the session;
1W / 1M / YTD and the stages stay the nightly's. Design: `docs/design/723_live_breadth_design_2026-11-09.md`.
Display only, like everything else here.

### The three pieces

| | |
|---|---|
| **Reference** (nightly) | `scripts/export_breadth_reference.sql` — ONE read-only SELECT, run by `auto_export_snapshots.sh` as its **FIRST** step, in its own **guarded** block (`ON_ERROR_STOP`, 300 s `statement_timeout`, 200-byte floor): it runs before `cd $DEST`, the `git fetch` / `reset` and the all-or-nothing snapshot loop, so a GitHub outage at export time or a failed theme / trades / funnel export cannot leave the next session without a fresh reference (the live job would refuse all day and page at 10:15); its own failure leaves the previous reference where it was and the snapshots continue. **Not published** — it is the job's input, not a dashboard file (publishing it committed ~5,000 tickers to portfolio-app2 every night for a page that never read it). Written tmp + mv straight to **`/home/apollo/apollo_the_wise/logs/apollo_breadth_reference.json`** on the host (`BREADTH_REFERENCE_COPY` overrides) — the `logs/` dir docker-compose.prod.yml bind-mounts into apollo-market at `/app/logs`, which is where the job reads it |
| **Job** (intraday) | `agents/market_intelligence/breadth_live.py`, registered as `breadth_live_refresh` (intelligence-owned): cron hour 9-16 / every 15 min / Mon-Fri, with the window **09:45 ≤ t ≤ the session close ET** (`trading_calendar.session_close_time`: 16:00, **13:00 on an NYSE half day** such as Fri 2026-11-27 — 26 refreshes on a full day, 14 on a half day; the stamp stops moving when the market shuts) and the trading-day check enforced in code. Reads the reference, fetches Alpaca SIP snapshots for every ticker in it (`collector.get_alpaca_snapshots_batch`, 100 per call, ~50 calls, ~8 s measured) **on the job's OWN one-thread executor** (alpaca-py sets no HTTP timeout and `wait_for` abandons a hung call without stopping its thread — on apollo-market's shared default pool one hanging endpoint would have parked up to 100 blocking calls in front of every other `run_in_executor(None, …)` in the process, ep_scan first; a refresh **skips**, as a counted failure, while ANY earlier call is still unfinished — the executor keeps a set of submitted calls, each removed in a done-callback, because a hung call's queued successors get cancelled by their own `wait_for` timeouts and a last-call-only guard read idle while the thread was still stuck, and the fetch **stops after 3 lost chunks in a row**), computes the numbers below, **refuses a partial read** (any lost batch, or under **85 %** of the universe read — `COVERAGE_FLOOR`; the 11-09 probe read ~96 %) and otherwise writes **`/app/logs/breadth_live/apollo_breadth_live.json`** atomically (host: `/home/apollo/apollo_the_wise/logs/breadth_live/`). ONE audit row per run (`breadth_live_refresh`: counts + timing) |
| **Pusher** (host) | `scripts/push_breadth_live.sh`, a host cron **every minute** (the container has no git, no ssh and no deploy key — the `github-p2` alias lives on the host, where the nightly export pushes from). Idempotent: it hashes the live file and pushes only on a change, as ONE orphan single-file commit force-pushed to portfolio-app2's **`live-breadth`** branch (git plumbing — `hash-object` → `mktree` → `commit-tree` with no parent → `push --force <sha>:refs/heads/live-breadth`; the branch always holds exactly one commit, the default branch is never touched, so Streamlit Cloud never reloads). The branch name is **hard-coded** — no environment variable can point it at the default branch. It works in its **own bare repo** (`logs/breadth_live/.push.git`, created on first run, pruned after each push) and pushes to the remote **URL** (read from the nightly clone's config, or `BREADTH_LIVE_REMOTE`), so the nightly's clone gains no object and no tracking ref — a pusher retry can never collide with the nightly's `git fetch`. **One run at a time** (`flock -n`; a second run exits 0 at once) and the push runs under **`timeout 50`** (a hung ssh ends inside the cron period); both are util-linux / coreutils on the host. Records `push_status.json` beside the live file; the job reads it on its next refresh, writes `breadth_live_push_lagging` when the previous file was never pushed or the push failed, and **pages at the third straight refresh left unpublished** (~45 min; a host cron that was never installed is not silent). The retry is the next cron tick. Host line: `* * * * * /home/apollo/apollo_the_wise/scripts/push_breadth_live.sh >> /home/apollo/apollo_the_wise/logs/push_breadth_live.log 2>&1` |

The page (portfolio-app2, step 4 — not in this repo) reads the branch through the GitHub contents API with a
read-only token and shows "Live · as of HH:MM ET" while the file is ≤ 20 min old on a trading day, else the last
close, labelled. A failed refresh therefore never leaves an old number shown as live. **Three rules the page must
honour** (review 2026-11-10, item 7):
- **Age the file by the payload's `as_of`, never by the commit date** — a pusher that comes back after an hour down
  publishes an old file under a fresh commit.
- **Join themes by `name` and groups by `code`, never by `idx`** — the reference and the nightly snapshot are
  separately guarded steps, so one can refresh while the other keeps last night's ordering.
- **Yesterday's 16:00 file stays on the branch until 09:45** — the `as_of` DATE check (today, ET) is the only thing
  between it and a "Live" label.

### The reference file

One object: `version` 1, `generated_at`, `as_of` (the nightly session rule — the data, never the clock),
`universe {n}`, `themes[] {idx, name, e_code}` (the nightly's ordering, by name), `ecosystems[] {code, name,
theme_idx}` (the nightly's grouping and names: `E-UNASSIGNED` → `Other`), `stocks`, `definitions`.

`stocks` — one entry per universe stock and per active-theme member: **`[prev_close, hi252, lo252, hl_eligible, in_universe, theme indexes]`**.

- `prev_close` — the as_of close (what today's price is compared with for advances / declines and the returns).
- `hi252` / `lo252` — the highest high and lowest low over the **252 sessions ENDING at as_of** (idx 0..251,
  as_of included). ⚠ This window differs from the nightly's 1..252 on purpose: the live job tests TODAY's bar,
  which is not in the table yet, so as_of is inside its lookback. Only usable bars (high and low > 0, not NaN).
- `hl_eligible` — usable bars on ≥ 245 of those 252 sessions. The live job adds the nightly's other half: a
  usable bar today.
- `in_universe` — CS / ADRC closing ≥ $1.00 on as_of; counts run over these. A member outside it (an ETF, a
  sub-$1 name) is listed for the theme returns only, exactly as the nightly's `interest` set.
- The session, universe, NaN, active-theme, member and ecosystem CTEs are **copies** of the nightly's;
  `tests/test_723_breadth_live.py` fails if the bodies drift.

### The live file — `apollo_breadth_live.json`

| field | meaning |
|---|---|
| `version` | 1 |
| `as_of` | `YYYY-MM-DDTHH:MM:SS ET` — when this refresh ran (the page's stamp) |
| `reference_as_of` | the reference's `as_of` — the close every number is measured against |
| `universe_n` / `read_n` / `missing_n` | universe size; names with a daily bar DATED TODAY (ET) carrying a close; the rest |
| `highs_lows` | `{eligible_n, new_highs, new_lows}` — the nightly's names. Eligible = reference-eligible AND a usable bar today; new high = today's high ≥ `hi252`; new low = today's low ≤ `lo252` |
| `adv_dec` | `{advances, declines, unchanged, no_prior, missing}` — today's bar close vs the reference `prev_close` (never Alpaca's `previous_daily_bar`, which pre-open holds T-2 — #490). `no_prior` as the nightly; `missing` as above. The five sum to `universe_n` |
| `ecosystems_1d` | `[{code, name, n_members, ret_1d, n_1d, up_1d}]` — the groups' equal-weighted 1-day return over unique members with both closes, 2 decimals; `n_1d` had the data, `up_1d` were positive |
| `themes_1d` | `[{idx, name, n_members, ret_1d, n_1d}]` — the themes' 1-day return on the same rule |

Rules the counts follow: a name Alpaca did not return, or returned with a bar from an earlier day or without a
close, is **missing — counted, never guessed** (a stale bar would otherwise read as "unchanged"); a NaN or zero
high / low is an unusable bar and enters no test; a member counts once per group however many of its themes hold
it (the stocks map is one row per ticker). On an early-close day the last refresh is the 13:00 close — the stamp
never moves after the market has shut.

### Failure discipline

- **Stale reference** (`as_of` ≠ the previous NYSE trading day per `trading_calendar.previous_trading_day`, or
  missing / unreadable) → the job writes NOTHING and audits `breadth_live_reference_stale`. An old reference would
  count every name against the wrong close; the page falls back to the last close by the file's age.
- **A partial read is a failure, not a thin market** (`coverage_problem`): any lost Alpaca batch, or fewer than
  **85 %** of the universe names carrying today's bar (`COVERAGE_FLOOR`) → the job writes NOTHING. 49 lost batches
  of 50 would otherwise have published 100 advances / 4,900 missing under a fresh stamp, and a holiday the calendar
  failed to recognise (every bar dated the previous session, read_n 0) an all-zero market as live — the PLAN's
  "an intraday count that disagrees with the independent read".
- **A failed refresh** (fetch, coverage, compute, write; an empty Alpaca read is a failure, not a zero market; a
  refresh skipped because the previous Alpaca call is still hung on the job's thread) → audited
  (`breadth_live_refresh_failed`), counted; the **third straight failure in a session** re-raises once, so
  `audit_wrap` → `record_job_failure` pages — never the first, never every run. A success resets the streak.
- **A push that failed or never happened** → `breadth_live_push_lagging` at the next refresh (the live file is
  > 5 min old and `push_status.json` is absent, for an earlier file, or `ok: false`); the **third straight** such
  refresh re-raises once (after writing its own file) — the page for a host cron that is missing or failing — and
  a landed push resets it.
- Audit rows only; no `mi_job_runs` noise beyond the one row `audit_wrap` writes per run.

### Verified / not yet

- Unit (`tests/test_723_breadth_live.py`, invented data, no network): the arithmetic on a hand-worked fixture,
  the missing rules, the stale refusal and the page-after-three rule, the window and registration, the pusher's
  orphan single-file commit against a local bare remote, the shell's guarded second step against a fake docker.
- **Not verifiable off prod** (step 5, Fri 11-13 in session): one refresh's counts vs an independent read at the
  same minute; the Alpaca symbol coverage of the ~5,000-name universe (the probe read 958 of 1,000 — the 85 %
  floor must clear with room); the host cron (and, on Linux only, the pusher's `flock` test — skipped on macOS).
  ⚠ Two **known departures from the nightly's rules** the independent read must allow for (review 2026-11-10,
  item 8): (a) the universe is the **previous session's** ≥ $1 closes, where the nightly uses today's — names
  crossing $1 today and today's new listings differ; (b) Alpaca's daily-bar high / low **may include pre-market
  prints**, where the 252-day reference comes from `mi_daily_closes` regular sessions — compare the 09:45
  `new_highs` against a regular-hours read before trusting the count. Neither touches field names or
  unique-member counting. SIP creds reach apollo-market through the `ALPACA_API_KEY` fallback (the paper variables are blanked in
  compose) — proven from inside that container by the 11-09 probe (`scripts/probes/_723_design_1109/`).

## Change log

- **2026-11-10 (review fixes)** — the live job refuses a partial read (any lost batch, or under 85 % of the universe
  read — nothing written, counted toward the page); the fetch runs on the job's own one-thread executor, skips while
  a previous call is still hung, and stops after 3 lost chunks (`collector.get_alpaca_snapshots_batch` gained
  `executor=` and `max_consecutive_failures=`; both default to the EP callers' unchanged behaviour); the window ends
  at the day's session close (13:00 on a half day; `trading_calendar.session_close_time`); the pusher's branch is
  hard-coded, it runs under `flock` with a `timeout` on the push, in its own bare repo against the remote URL; the
  nightly writes the reference FIRST, in its own guarded block, and no longer publishes it; a file left unpublished
  for three straight refreshes pages. Page rules (age by `as_of`; join by name / code) and the two rule departures
  for the step-5 read recorded above.
- **2026-11-10** — #723 steps 2 + 3: the nightly reference export (second guarded step, host copy under
  `logs/`), the intraday `breadth_live_refresh` job (every 15 min 09:45-16:00 ET, Alpaca SIP snapshots vs the
  reference, `apollo_breadth_live.json`), the host pusher to the `live-breadth` branch. `collector.
  get_alpaca_snapshots_batch` gained the additive `daily_bar_high` / `daily_bar_low` keys. The nightly snapshot
  SQL and its output are untouched.
- **2026-11-04** — built (#719, Apollo half): the export, the guarded nightly step, the static and
  shell tests, the embedded-Postgres probe. The dashboard page is the portfolio-app2 half.
- **2026-11-08** — #722 (Apollo half): the `ecosystems` array — themes grouped by ecosystem, each group's unique members returned on the themes' own bases with the n that had data and how many were up. `eco_names` (copied from `theme_ecosystems.yaml`, test-guarded), `E-UNASSIGNED` printed as `Other`, an unmapped theme filed under it. Additive: every pre-existing key is byte-identical and `version` stays 1. Probe fixture extended (shared stock across a group's themes, unmapped / explicit-unassigned / unknown-code / memberless cases); the probe's stale stage recompute was brought to the 203-of-210 rule that shipped 2026-11-04 (it had failed since then).
