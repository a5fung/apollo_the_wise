-- #687 read-only prod pull 4 (captured once): mi_security_types (schema + all rows), to apply the live
-- non-common-stock exclusion (security_type NOT IN ('CS','ADRC') skipped; unclassified skipped) to the rebuilt population.
\echo === SCHEMA ===
SELECT column_name, data_type FROM information_schema.columns WHERE table_name='mi_security_types' ORDER BY ordinal_position;
\echo === TYPES ===
SELECT * FROM mi_security_types;
