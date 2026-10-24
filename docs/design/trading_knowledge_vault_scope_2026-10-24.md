# Trading knowledge vault — scope (#707, 2026-10-24)

**Status: SCOPE for his ruling.** Nothing is migrated yet. The forks he decides are in §8; everything else is a proposal he can
strike.

## 1. The goal, in his words

- *"Idea is to create a trading knowledge vault, think a proprietary trading system, and that is the brain of this operation and
  portable and implementation anywhere. Apollo is just a manifestation of it. Like Obsidian for Karpathy wiki."* (10-21)
- *"goal is to build trading knowledge brain and successfully trade those setups and strategies profitably. His database is just
  the starting point, proven to work, we want to rebuild it, extract knowledge, build on top of it, improve it and trade it
  profitably"* (10-23)
- So the vault's loop is: **rebuild** Qullamaggie's setup database → **extract** the rules → **build on top** with our own tests
  and results → **improve** → **trade** it (Apollo).

## 2. What the vault is, and is not

| The vault holds | Apollo keeps |
|---|---|
| setup and family DEFINITIONS (what a breakout / EP / parabolic short is, buy point, stop) | how Apollo implements them (code, thresholds as built, job wiring) |
| his rulings, dated and verbatim | PLAN.md, task state, deploy notes |
| raw sources as captured (his notes, stream captions, tweets, book notes) | architecture docs, runbooks |
| every test as question → pre-registration → verdict → what it changed | the probe code and outputs (linked by commit, not copied) |
| the setup database (one row per setup instance) | the live tables (mi_*) |
| lessons (how to work, how to test) — today machine-local | CLAUDE.md working rules for the agent |

**Rule against drift:** a fact lives in ONE place. Apollo's `docs/setups/*.md` keep their implementation half and link to the
vault page for the definition; a lint (§6) fails when the two disagree.

## 3. Structure (plain Markdown, Obsidian-readable, wiki links)

```
vault/
  index.md                 entry point: setups, families, principles, open questions
  changelog.md             dated, one line per change
  setups/                  breakout.md, ep.md, parabolic_short.md  (definition, buy point, stop, exits, his words, tests, examples)
  families/                consolidation.md, ...                   (contexts that host setups — never a setup itself)
  principles/              tail_not_median.md, selection_vs_execution.md, market_exposure.md, ...
  rulings/                 YYYY-MM-DD_<topic>.md                   (verbatim, who, what it overrides)
  tests/                   <id>_<question>.md                      (question, prereg link, verdict, consequence, commit)
  methods/                 backtest_data_standard.md, how_to_replay_his_calls.md, chart_reading.md
  lessons/                 one file per lesson                     (the 74 memory files, made machine-independent)
  sources/                 raw captures: operator_notes/, streams/ (captions + frame index), tweets/, books/ (notes + short quotes)
  database/                setup_instances.parquet + schema.md    (§4); large assets by path + hash, never in git
```

## 4. The setup database — the core table

One row per setup instance, whatever produced it (his stream call, our detector, a book chart, a tweet):

| column | meaning |
|---|---|
| instance_id | stable key |
| stock, company key | ticker as of the date + a point-in-time company id (FIGI / CIK) |
| date, setup, family | the event day; breakout / EP / parabolic short; consolidation etc. |
| source, source_ref | his stream (video + timestamp), our detector, tweet, book page |
| his_grade | bought / best / not yet / none |
| chart | path + hash of the frame or a rendered chart |
| features | the bar-derived features as of the decision time (versioned) |
| outcome_his_rules | the replay result under his rules (versioned; empty until a frozen read writes it) |
| data_version | which price file and which rule version produced the row |

Today's starting rows: 854 stream moments where his grade, the chart on screen and our prices agree (2,184 frames); the 236
on-or-before breakout calls with their replay outcomes; 26 EP calls; the operator-labelled EPs (`docs/methodology/operator_labelled_eps.md`).

## 5. Migration list

| Moves into the vault | From | How |
|---|---|---|
| his shared methods (2,574 lines) | `docs/methodology/operator_shared_notes.md` | kept verbatim under `sources/`; compiled into setup / principle pages that cite the lines |
| rulings | PLAN lines, notes, CLAUDE.md definitions (SETUP vs FAMILY) | one dated file each, verbatim |
| lessons | 74 machine-local memory files | copied, made machine-independent; memory keeps only agent-session state |
| the data standard | `docs/methodology/backtest_data_standard.md` | first `methods/` page (his 10-23 ask) |
| test verdicts | `docs/analysis/*.md` (354 docs) | one summary page per question, linking the doc and commit — the docs stay in Apollo |
| labelled examples | `operator_labelled_eps.md`, `tests/fixtures/htf_labelled.py`, the stream label set | rows in the setup database |
| **stays in Apollo** | code docs, architecture, PLAN, runbooks, probe code, CLAUDE.md working rules | linked, never copied |

## 6. Ingest and lint (the Karpathy LLM-wiki pattern)

- **Ingest:** a new source (his note, a tweet, a stream, a test verdict) is captured raw into `sources/` the same turn; an LLM pass
  then updates the pages it touches and the index, and writes one changelog line. A test verdict updates its setup page and the
  database rows it produced.
- **Lint (scheduled, and before every commit to the vault):** broken links; orphan pages; a claim with no source or test cited; two
  pages that contradict each other; a setup page whose definition disagrees with Apollo's SSoT; a verdict newer than the page that
  quotes an older one.

## 7. How Apollo uses it

- The vault is its own private repo, checked out beside Apollo; Apollo pins a commit of it.
- Apollo reads definitions and rulings from it (prompts, the SSoT links, the tests that pin definitions); Apollo's results flow back
  as test pages and database rows.
- Portable by construction: no Apollo code is needed to read it.

## 8. Decisions for him

| Fork | Options | Recommendation |
|---|---|---|
| Where it lives | a separate private repo / a folder inside Apollo | separate private repo (his "portable … Apollo is just a manifestation") |
| External sources | verbatim / notes + short quotes | notes + short quotes for books and paid material; his own notes verbatim |
| Large assets (frames 1.6 GB, charts) | git LFS / object storage / local data folder | local data folder + hashes now, object storage later |
| Start order | all at once / setups first | setups first: breakout, EP, parabolic short pages + the database, then the rest |

## 9. Dated plan (weekends are the build slot)

| When | What | Done when |
|---|---|---|
| Sat 10-24 | this scope; his ruling on §8 | §8 ruled |
| Sat–Sun 10-31 / 11-01 | repo skeleton; migrate his notes (verbatim), rulings, lessons, the data standard; index + changelog | the vault opens in Obsidian and every moved page cites its source |
| Sat–Sun 11-07 / 11-08 | the setup database v1 (the 854 stream rows + replay outcomes + labelled EPs); the three setup pages | one query answers "every breakout he graded, with its chart and outcome" |
| Sat–Sun 11-14 / 11-15 | ingest + lint routine, scheduled | the lint runs clean and a new note flows in without a hand step |
| after | Apollo reads definitions from the pinned vault | the SSoT-vs-vault lint passes in Apollo's CI |

What this does not answer: how big the database must be before rules extracted from it are trusted (that is the replay program's
question, #705), and whether Apollo's live trading changes (his sign-off, THE LINE).
