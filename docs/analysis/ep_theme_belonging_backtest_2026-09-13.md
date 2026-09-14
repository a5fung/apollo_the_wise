# Theme bonus by BELONGING — the backtest CHANGE_PROCESS requires (2026-09-13)

> Operator: *"EP gets boost if it belongs to a theme, regardless if it's already in a theme or
> not at the time of EP alert."* — and on the backtest's role: *"Is a bug, if we don't like the
> impact then is a question if themes should boost at all, or how much, or if themes are right,
> etc. Those are the legit questions, not if we should boost based on belonging to theme or it's
> actually in list, that is the bug."*

**Status: the machinery is built and tested; THE NUMBERS ARE PENDING THE PROD PULL.** The analysis
sandbox had no route to the database (its ssh path was blocked by the tool's own guard), so the
run is packaged as two commands and the results section below is filled from the second one:

```
bash scripts/probes/_ep_theme_belonging_pull.sh /tmp/etb        # read-only COPY ... TO STDOUT, five CSVs
python scripts/probes/_ep_theme_belonging_backtest.py /tmp/etb  # prints the tables; writes /tmp/etb/results.md
```

The fix shipped ON by the operator's ruling; this document is a REPORT on it, not a gate. If the
numbers below come back alarming they are reported the same day, plainly, and the revert lever
(`ep_theme_belonging` → `off`, no redeploy) is his.

## Method / population

- **Population**: every `mi_ep_alerts` row with a score, `alert_date >= CURRENT_DATE − 120`
  (**n = 346** at the time of the defect measurement, `theme_boost_arrives_late_2026-09-13.md`;
  the pull re-counts it). Each alert's scan-log row (`mi_ep_scan_log`, same ticker/date, nearest
  tick to `detected_at`) supplies the RAW score components (`score_breakdown`), the acting bar
  (`ep_bar`) and the acting rubric side (`score_side`) where they exist (recorded since #605,
  2026-08-29); older rows are re-scored through the real `_score_ep` from stored inputs and kept
  only when the recomputation REPRODUCES the stored score (±0.11) — rows that reproduce by
  neither route are counted as unreconstructible, never silently dropped.
- **Board as-of each alert**: `mi_themes` rows with `theme_date < alert_date AND theme_date >=
  alert_date − 7`, latest row per name, Retired dropped, then the stage filter — the mirror of
  `get_active_themes(stale_after_days=7)` at a morning scan (94% of theme rows are written
  17:00–17:59 ET the night before). The 22 alerts the live flag paid must REPRODUCE under this
  reconstruction before any new count is trusted; the script reports the agreement.
- **Belonging**: the SAME functions the live scan runs (`ep_theme_belonging.session_index`,
  `log_returns`, `excess_returns`, `build_baskets`, `score_belonging`) on `mi_daily_closes` over
  the 60 sessions strictly before the alert date, SPY-subtracted. Not a lookalike.
- **Score under the fix**: the stored raw components with `theme_bonus` set to +10 when the name
  belongs (it is never REMOVED — listed still belongs, so the fix is monotone), the conviction
  floor re-resolved through the real `resolve_conviction_floor`, the day's multiplier recovered
  from the stored score (and checked against 1.0 / 1.2 / 1.44 / …), the separation side's
  presentation through the real `apply_output_scale`. HIGH = score ≥ the row's own era bar.
- **Null controls**, two populations the same day, same test, same bars: (i) the scan log's
  scored-but-not-alerting names (the population the +10 is actually applied to); (ii) ten random
  board names per alert date with close ≥ $5 and ≥ $5M dollar volume, drawn by `md5(ticker||date)`
  so the draw is reproducible. Hit rate = share whose best paying-stage correlation clears the bar
  without being listed.

## Pre-registered, BEFORE the pull

| question | the number | what confirms the fix is sane | what says the bar is too low |
|---|---|---|---|
| alerts gaining the +10 that did not have it | count of 346, listed today = 22 | a minority, concentrated in names a theme later filed | a majority — the test is matching everything |
| HIGH crossings caused by the fix | named list with date / ticker / before / after / era bar | a handful; each one has a plausible theme | dozens |
| the same with Nascent paying | a separate count — HIS decision, not bundled | — | — |
| null control (i) scored non-alerts | co-move rate at 0.35 | materially BELOW the alerts' unlisted co-move rate | ≈ the alerts' rate — then 0.35 does not transfer to a max-over-baskets test |
| null control (ii) random board names | co-move rate at 0.30 / 0.35 / 0.40 / 0.50 / 0.60 | near the ≈0.05-correlation reference population's rate at 0.35 | high at 0.35 and only falls at 0.50+ — report the bar where it falls |
| era-bar recheck of "4 HIGHs depended on the +10" | recount at each alert's own bar | — | if the recount is not 4, the earlier read at a flat 70 was wrong and is corrected here |

**Decision rule declared now**: if control (i) fires at ≥ 70% of the alert population's unlisted
co-move rate, the bar does not separate and the doc says so; the recommendation then is the bar at
which control (ii) falls to the reference rate, for the operator to rule on — the fix itself stays
ON (his ruling), the bar is the criterion question.

## Results

*To be filled from `results.md` after the pull. Every table carries its n.*

## What this does not answer

- **Whether the +10 is the right size, or whether it should differ by stage.** Untested here —
  the operator named these as the legitimate questions that FOLLOW the bug fix.
- **Whether the boosted alerts made money.** Returns on themes are parked by his own sequencing
  (#655: right themes → early themes → only then trading).
- **Causality of the 4-day lag** (EP causing the membership vs the theme forming anyway) — not
  separable from this measurement.
- **The judge.** HIGH here means score ≥ bar; the Holistic Grade Judge overwrites `score_tier` on
  about half of alerts and is not replayed. A crossing counted here is a crossing at the scorer.
- **Intraday drift.** The replay scores each alert once; the live scan re-scores every tick and
  the basket context is fixed for the day.
- **Themes that never existed.** 69–79% of alerts sit in no theme at any stage on the day; a
  belonging test cannot reach a group the engine never formed — that is steps 1–2 of the theme
  programme, not this fix.
