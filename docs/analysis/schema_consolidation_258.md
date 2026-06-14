# #258 — initialize_schema() consolidation: audit evidence + plan

**Status: AUDIT DONE 2026-06-13 (evidence below). The consolidation EDIT is GATED —
see "Gate constraint". The db.py domain-package split is a SEPARATE later increment.**

## Why audit-first

`agents/market_intelligence/db.py::initialize_schema()` is one ~1,500-line function:
each `CREATE TABLE IF NOT EXISTS` is followed by `ALTER TABLE … ADD COLUMN IF NOT
EXISTS` patches accumulated over time. Consolidating safely requires knowing, per
ALTER, whether it's redundant — and that's a question about the LIVE schema, not the
source. So step 1 is a read-only audit diffing the live prod catalog against the
CREATE defs.

Reproduce:
```bash
# 1. dump live prod columns (read-only)
ssh apollo@<box> 'docker exec apollo-postgres psql -U apollo -d apollo -tAF "\t" \
  -c "SELECT table_name, column_name FROM information_schema.columns \
      WHERE table_schema='"'"'public'"'"' AND table_name LIKE '"'"'mi\_%'"'"' \
      ORDER BY table_name, ordinal_position;"' > scripts/_prod_columns_258.tsv
# 2. classify
python scripts/_schema_consolidation_audit_258.py
```

## Audit result (2026-06-13, against live prod)

58 live `mi_*` tables · 56 CREATE defs · **43 `ALTER ADD COLUMN IF NOT EXISTS` sites**:

| Bucket | N | Meaning | Action |
|---|---|---|---|
| REDUNDANT | 10 | column in a CREATE def AND in live prod | drop the ALTER (no-op) |
| FOLD | 33 | column live but MISSING from its CREATE def | add to CREATE, then drop the ALTER |
| KEEP | 0 | column in CREATE but absent from live (live migration) | — none |
| ANOMALY | 0 | neither | — none |

KEEP=0 + ANOMALY=0 means **prod is fully consistent with CREATE∪ALTER** — every
column the union defines exists in prod, so no ALTER is load-bearing as a live
migration. The consolidation is therefore mechanical:

1. **Fold** the 33 FOLD columns into their `CREATE TABLE` definitions (so a fresh DB
   gets a complete table). The exact list is the audit's FOLD bucket — e.g.
   `mi_stock_scores.sma_40`, all of `mi_ep_scan_log`'s 7, `mi_market_regime`'s
   breadth set, `mi_9m_day2_candidates`'s prev_* set, `mi_daily_closes` OHLC, etc.
2. **Drop** all 43 `ALTER ADD COLUMN` lines (the 10 REDUNDANT + the 33 now-folded).
   Result: clean CREATE-only schema init.

**Residual caveat (decide at edit time):** dropping the ALTERs is safe for prod and
any restore from a backup that postdates the columns (the nightly backups do — the
audit confirms prod has every column). The only thing that would miss a folded column
is a `CREATE TABLE IF NOT EXISTS` against an OLD pre-column table (it won't re-add to
an existing table). Realistic restores are recent, so this is safe; if extra caution
is wanted, keep a one-shot migration block for the handful of oldest columns. Validate
either way on STAGING (restores a real prod dump → exercises initialize_schema against
the actual catalog) + the `preflight_db_updates` gate before merging.

## Gate constraint (advisor 2026-06-13) — DO NOT land the EDIT in main before Monday

The #256 §C Monday rollback is `git pull origin main` → rebuild **combined**. Unlike
the W2 timeout fix (inert in combined/inprocess), `initialize_schema()` runs in EVERY
role including combined. So a schema-consolidation edit **committed to main** — even
staging-validated, even un-deployed — silently makes "collapse to combined = proven
byte-identical state" FALSE: a Monday emergency rollback would rebuild combined with an
unproven 1,500-line refactor baked in. Therefore the consolidation edit lands **after
Monday's #277 live-ORB gate is closed out** (or on a branch now, merged post-gate). The
audit + this doc are gate-safe (read-only / docs — they touch nothing executable).

## Sequencing

- ✅ Step 1 — audit (this doc). Evidence captured; edit is now mechanical.
- ⏸ Step 2 — the consolidation edit (fold 33 + drop 43), post-#277-gate, branch +
  staging-validated + `preflight_db_updates`. Faithful, behavior-identical.
- ⏸ Step 3 — db.py domain-package split (7,743 lines → domain modules). HIGH-churn
  import-surface change; its OWN session, after the schema consolidation settles.
