# Theme strength: what the one-sided trim does, and the 0%-breadth hole (#580, 2026-09-30)

## 1. The answer first

- **The trim inflates every theme with 3+ members.** `constants.trimmed_mean` drops the weakest member(s) and never the
  strongest, so a theme's RS reads about **+5 points** higher on `/themes` than a plain average (up to **+23** for a
  three-stock theme with one laggard). It feeds the engine's stored score too (+4 on average), and through it stage decisions.
- **Order mostly survives, the top 10 does not.** Against a plain mean, 3 of the top 10 change on a typical night;
  against a trim that cuts BOTH tails, about 1 changes. Overall rank agreement stays high (0.94–0.99).
- **A separate, money-path bug:** the breadth-decay rule treats a stored breadth of exactly **0%** as healthy
  (`(yesterday or 1.0) < 0.40`, `theme_engine.py:3926` — 0.0 is falsy), so a theme that collapses to 0% never fades.
  On 2026-09-29, **9 Mainstream themes** sat at exactly 0%; their members still collect the EP +10.
- **Breadth data is correct** (checked: stored 20-day averages match a recompute from daily closes — the bitcoin miners
  really were all below their 20-day average on 09-29; market-wide only 27% of stocks were).

## Ruling (2026-09-30)

- **The trim stays** (his ruling): the strongest members are the leaders that light a theme up; dropping them would hide
  the early signal the theme work exists to catch. Breadth now shows beside the score on both surfaces.
- **The 0% bug gets fixed** (his yes) — Saturday 10-03, after a replay of which themes fade and which EP alerts lose the +10.

## 2. Method and population

Read-only against prod, captured once in `scripts/probes/_580/` (`trimmed_mean_compare.py` + `_output.txt`; the
multi-MB raw dumps were not committed — the script regenerates them).

- **Population:** the last 20 distinct `mi_themes.theme_date` (2026-09-01 → 2026-09-29, no 09-07 row), non-Retired:
  **n = 2,285 theme-days** (103–122 per date). `/themes` population (non-Fading): **n = 1,411**. Member-count
  distribution on `/themes`: 2 members 113 · 3: 394 · 4: 259 · 5: 187 · 6–10: 310 · 11–20: 126 · 21+: 22.
- **Arms, fixed before running:** A = today's one-sided trim; B = plain mean; C = the same count dropped from both tails
  (a median for 3–4 members). Only the trimmed component is recomputed; everything else is held fixed.
- **Metric, fixed before running:** per date, Spearman rank agreement, top-10 overlap, and themes moving ≥3 places.
- **The 0% count:** `mi_themes` rows on 2026-09-29 by stage with `pct_above_20sma = 0` (Mainstream 9 of 49,
  Fading 20 of 43, Nascent 3 of 28, Accelerating 0 of 2).

## 3. Results

| Ranking (mean over 20 nights) | n | Agreement A–B | Agreement A–C | Top-10 kept A–B | Top-10 kept A–C |
|---|---|---|---|---|---|
| `/themes` (live RS, all members) | 1,411 | 0.94 | 0.98 | 6.9 of 10 | 9.1 of 10 |
| Engine stored score, trim-fed rows | 1,675 | 0.96 | 0.98 | 7.0 of 10 | 9.2 of 10 |
| Dashboard default stages (Accelerating + Mainstream) | 868 | 0.93 | 0.97 | 7.5 of 10 | 8.9 of 10 |

| Members | `/themes` themes | Mean inflation vs plain mean (RS pts) | Max |
|---|---|---|---|
| 3 | 394 | +6.0 | +22.9 |
| 4 | 259 | +5.2 | +16.8 |
| 5 | 187 | +4.3 | +12.4 |
| 6–10 | 310 | +6.0 | +18.6 |
| 11–20 | 126 | +4.4 | +9.9 |

Call sites of `trimmed_mean`: **8** (the task text said 7): `/themes` score and its 1M/3M/6M columns (briefing.py:681–684),
the engine's momentum → stored score → stages (theme_engine.py:3833), a new theme's birth score (:6879), and the ecosystem
board's raw score and depth gate (theme_ecosystems.py:302, :312).

## 4. What this does not answer

- **Whether the trim or the 0% bug changed any trade.** Stage replays under each fix (which themes would have faded, and
  which EP alerts lose the +10) are not run here; that is the evidence a CHANGE_PROCESS entry needs before either ships.
- **Which average is "right".** A plain mean shows a laggard's drag; a symmetric trim keeps outlier resistance without
  the upward bias; with breadth now shown on both surfaces, the laggard is visible either way. That is his ruling.
- **The stored score mixes scales** (shadow-promoted rows are a 0–100 plain mean with no news; live rows cap near 80) —
  it affects the dashboard's weekly Grid view, not the live ranking. Not addressed here.
