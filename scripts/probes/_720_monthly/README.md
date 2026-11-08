# #720 monthly trade review — runner

Plan (pre-registered 2026-11-08; revised the same day against the challenge, before any read):
`docs/analysis/720_monthly_review_plan_2026-11-08.md`.

Run day (first: Sun 2026-11-29):
0. `python run_review.py --emit-predicates capture/predicates.sql` — regenerates the five folded reviews' predicate
   counts query from `data_gated_reviews.yaml` VERBATIM (a test pins the committed file to the YAML; run it again
   whenever a predicate moves).
1. `mkdir -p runs/<date>/data`; for each `capture/*.sql`:
   `docker exec -i apollo-postgres psql -q -X -v ON_ERROR_STOP=1 -U <user> -d <db> < capture/<name>.sql > runs/<date>/data/<name>.csv`
   (every file starts `SET default_transaction_read_only = on`; `predicates.sql` is a server-side multi-line COPY,
   the rest one-line `\copy`). Run each ONCE.
2. `python run_review.py --manifest runs/<date>` — row counts + md5 + capture timestamp.
3. `python run_review.py --report runs/<date> --run-date <date> [--prev-capture <date>]` — reads the CSVs only;
   writes `review.md` (the one page + the per-trade appendix) and `review.out` (every cell).

No database connection is opened by `run_review.py`. Tests: `tests/test_720_monthly_review.py` (invented fixtures
in the units prod writes; `RUN_REVIEW_720_PATH=<file>` runs them against another runner —
`challenge_1108/old_runner_red.txt` is that run against the pre-revision runner).
