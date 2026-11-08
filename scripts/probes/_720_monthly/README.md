# #720 monthly trade review — runner

Plan (pre-registered 2026-11-08): `docs/analysis/720_monthly_review_plan_2026-11-08.md`.

Run day (first: Sun 2026-11-29):
1. `mkdir -p runs/<date>/data`; for each `capture/*.sql`:
   `docker exec -i apollo-postgres psql -q -X -v ON_ERROR_STOP=1 -U <user> -d <db> < capture/<name>.sql > runs/<date>/data/<name>.csv`
   (every file starts `SET default_transaction_read_only = on`). Run each ONCE.
2. `python run_review.py --manifest runs/<date>` — row counts + md5 + capture timestamp.
3. `python run_review.py --report runs/<date> --run-date <date> [--prev-capture <date>]` — reads the CSVs only; writes `review.md`.

No database connection is opened by `run_review.py`. Tests: `tests/test_720_monthly_review.py` (invented fixtures).
