\set QUIET on
\pset format unaligned
\pset fieldsep '|'
\pset footer off
SELECT table_name, column_name FROM information_schema.columns WHERE table_name IN ('mi_job_runs') ORDER BY ordinal_position;
