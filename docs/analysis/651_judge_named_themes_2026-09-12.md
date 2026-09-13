# How late is the theme engine? — NOT MEASURED YET: the runner is built, the paid pass could not run from the build card

**2026-09-12 · #651 · build complete, $0 spent · the historical pass needs one in-container command (below)**

## The answer, as of this write-up

- **No lead time is measured yet, and this is not the null either.** The extraction + the read are
  built and tested (26 tests, `tests/test_651_judge_named_themes.py`), but the build card had no
  route to production (SSH from the card was refused twice by the session's permission classifier),
  so the ~105 stored rationales were never sent to the model. Spend so far: **$0**.
- **What decides it:** run the historical pass once (captured to a file), then the report. The
  report's FIRST LINE is the answer in one of three forms — `MEASURED — N group(s) named by the
  judge BEFORE the engine had a matching theme … lead: Xd`, `CANDIDATES, NO LEAD TIME YET — …`
  (recurring groups the engine has never created), or `NULL — no judge-named group recurs across
  two or more tickers ahead of the engine`.

```
# inside apollo-market (after this commit is deployed there):
docker exec apollo-market python scripts/judge_named_themes_651.py --historical --capture /app/logs/651_capture.jsonl            # DRY RUN: pending count, $0
docker exec apollo-market python scripts/judge_named_themes_651.py --historical --capture /app/logs/651_capture.jsonl --commit   # the ONE paid pass (~$0.07), captured first
docker exec apollo-market python scripts/judge_named_themes_651.py --report --out /app/logs/651_report.txt                       # the answer; $0, re-runnable
```

Pre-deploy alternative (runs the committed code with the image + `.env`, touches no running
service): rsync the checkout to the host and `docker run --rm --network <compose net> --env-file
/home/apollo/apollo_the_wise/.env -e POSTGRES_HOST=postgres -v <checkout>:/app -w /app <market image>
python scripts/judge_named_themes_651.py --historical --capture /app/logs/651_capture.jsonl --commit`.
The table does not exist in prod until the deploy creates it (`init_db`), so a pre-deploy capture is
loaded afterwards with `--load-capture /app/logs/651_capture.jsonl` — **zero spend, never re-run**.

## Method / population — what will be measured, over what

- **Rows.** Every `mi_ep_alerts` row with a stored `judge_rationale` (>= 40 chars) and
  `alert_date >= 2026-07-01` — the grounded-judge era. Measured 2026-09-12 at $0 before this build:
  **150** such alerts, **105** of them mention a theme in prose. Forward, ~6 alerts a day.
- **Extraction.** One Haiku 4.5 call per alert (`JUDGE_NAMED_THEMES_MODEL`, tier-tracked; forced
  tool, no string parsing) returning, per alert, zero or more `{name, canonical_key, evidence,
  judge_says_untracked}`; `evidence` is the judge's own sentence. An alert naming nothing writes a
  `(none)` sentinel row so it is never re-billed. A failed call writes nothing and retries next night.
- **The filter is recurrence, not a score.** A group counts only when its normalised
  `canonical_key` appears on **>= 2 distinct tickers** (`recurring_groups`). Two mentions on one
  ticker is a story, not a theme. No tuned threshold exists anywhere in the read.
- **The engine's timeline.** `mi_themes` is a daily snapshot table: `MIN(theme_date)` per name is
  when the engine first had that theme, followed through `mi_theme_renames` lineage. The local
  copy used for the plumbing check spans **2026-03-27 → 2026-09-11, 546 distinct names**
  (`portfolio-app2/apollo_themes_snapshot.json`, no rename lineage).
- **Matching** (`match_theme`) is deterministic and printed beside every verdict: judge-key tokens
  vs theme-name tokens; a match is Jaccard >= 0.5 OR full containment of a >= 2-token side; one
  shared generic token (`ai`) is never a match. Up to five near-misses are listed under every group
  so a wrong `never_matched` is visible to the eye rather than buried.
- **Lead time** = `theme_first_date − first_named_date` in days, **positive = the judge was
  earlier**. Verdicts: `judge_earlier` / `already_existed` / `never_matched`, each with its n.

## What the plumbing check showed (synthetic capture, real theme names — NOT a result)

- Ran the report over the three judge phrases quoted in PLAN.md #651 (SEI, SNOW, AGX) plus two
  fabricated rows, against the real 546-name timeline. Numbers from it are meaningless and are not
  reported. One thing in it is real and changes how the result must be read:
- **The engine already has a theme literally named "AI data-center power buildout", first seen
  2026-09-04 — four days BEFORE the SEI 09-08 alert whose rationale used those exact words.** The
  judge is fed our active-theme context, so a rationale can ECHO our own theme name. "The judge
  named a theme" is therefore not "the judge discovered a theme"; only the dated comparison says
  which. That is why the deliverable is the lead-time verdict, not the name list, and why the
  `already_existed` verdict is expected to be common.

## What this does not answer

- **Whether the judge's groups are GOOD themes.** A recurring name the engine never created is a
  candidate for the operator's ruling, not a theme; nothing here creates, renames or promotes one.
- **Lateness in the OTHER direction.** Themes the engine created that the judge never named are not
  visible here — this is a one-sided read from the judge's side.
- **Fuzzy identity.** Two genuinely different phrasings that the model gives different
  `canonical_key`s stay separate groups; the deterministic normaliser collapses phrasings of one
  label, it does not judge meaning. The variants are printed so a split group can be seen.
- **Anything about outcomes.** No return, grade or entry is joined; the theme north-star question
  here is earliness only.

## Cost, priced up front and to be reported after the run

- Historical pass: ~105 alerts × (~300 in + ~60 out tokens) on Haiku 4.5 ($1/$5 per M) ≈
  **$0.07**; the script prints the actual figure from the response usage at the end.
- Forward: the nightly job `judge_named_themes_extract` (18:20 ET, bounded to 40 alerts a night)
  ≈ pennies a month. All spend lands in the standard cost meter under caller `judge_named_themes`.

## Where things live

- Module: `agents/market_intelligence/judge_named_themes.py` (extraction, sweep, the pure read).
- Table: `mi_judge_named_themes` (`db.py`; writer `insert_judge_named_theme_row`, registered in
  `scripts/preflight_db_updates.SHADOW_WRITER_STATEMENTS`).
- Runner: `scripts/judge_named_themes_651.py` (`--historical`, `--load-capture`, `--report`).
- Owner pointer: `docs/architecture/theme_engine.md` § "Judge-named theme capture (#651)".
- THE LINE: read by nothing that grades, admits, sizes, enters, exits, or creates a theme; the
  judge's own inputs never select from the table (pinned by the test file's group 5).
