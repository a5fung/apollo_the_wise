#!/usr/bin/env bash
# #657 — should the tape decide REMOVALS too? Stage 1 of 2: the READ-ONLY prod pull (2026-09-25).
#
# Pulls the eight CSVs `_657_comove_removals.py` reads, straight from prod Postgres via the
# operator-authorized `ssh ... docker exec apollo-postgres psql` read path (the
# _assign_comove_pull.sh idiom — read-only SELECTs only). Nothing is written to the database.
# Captured ONCE to scripts/probes/_657_out/ and read many times (cost rule 2026-08-03).
#
# Usage: bash scripts/probes/_657_pull.sh [output-dir]        (default scripts/probes/_657_out)
#        then: python scripts/probes/_657_comove_removals.py [output-dir]
set -euo pipefail
OUT="${1:-scripts/probes/_657_out}"
HOST="${APOLLO_HOST:-apollo@87.99.134.162}"
SINCE="${SINCE:-2026-06-01}"          # boards + audit trail from here (join-date tracing)
CLOSES_SINCE="${CLOSES_SINCE:-2026-04-01}"   # a full 60-session window before the older cutoff (~08-12) needs April
mkdir -p "$OUT"

run() {
  ssh -o ConnectTimeout=25 "$HOST" \
    "docker exec -i apollo-postgres psql -U apollo -d apollo -X -c \"COPY ($1) TO STDOUT WITH (FORMAT csv, HEADER true)\""
}

echo "themes: every mi_themes row since $SINCE (all stages incl. Retired tombstones) ..."
run "SELECT theme_date, name, stage, tickers::text AS tickers
     FROM mi_themes WHERE theme_date >= '$SINCE' ORDER BY theme_date, name" > "$OUT/themes.csv"

echo "events: the assignment / removal / validation / operator audit trail since $SINCE ..."
run "SELECT id, (created_at AT TIME ZONE 'America/New_York')::date AS run_date,
            to_char(created_at AT TIME ZONE 'America/New_York', 'HH24:MI') AS run_time_et,
            event_type, summary, detail
     FROM mi_audit_log
     WHERE created_at >= '$SINCE'
       AND event_type IN ('assignment_llm_proposed', 'assignment_skipped_sector_outlier',
                          'assignment_skipped_comove_below_bar', 'assignment_comove_admitted_over_sector',
                          'assignment_comove_summary', 'theme_comove_context_failed',
                          'theme_carryforward_filter_stripped', 'ticker_revalidated_out',
                          'validation_cooldown_triggered', 'validation_removal_shielded',
                          'validation_mass_removal_name_suspect', 'theme_pass1_protect_strip',
                          'theme_operator_promoted', 'shadow_themes_promoted', 'theme_retired',
                          'theme_auto_retired', 'theme_dissolved_flagged_pair', 'theme_cap_drop',
                          'theme_sector_cap_dropped', 'theme_member_pruned_while_rising',
                          'theme_birth_validated', 'theme_birth_gate', 'theme_discovered',
                          'theme_renamed_for_continuity', 'theme_renamed_on_mass_flag',
                          'theme_thesis_merged', 'theme_merge_parent_child', 'theme_split',
                          'global_ticker_ban_active')
     ORDER BY id" > "$OUT/events.csv"

echo "events_extra: the merge machinery (absorption / successor pointers / birth-gate joins) since $SINCE ..."
run "SELECT id, (created_at AT TIME ZONE 'America/New_York')::date AS run_date, event_type, summary, detail
     FROM mi_audit_log
     WHERE created_at >= '$SINCE'
       AND event_type IN ('theme_pass1_5_absorption', 'theme_ecosystem_assigned', 'theme_subtheme_route_merge',
                          'theme_canonicalize_blocked_mass_evicted', 'theme_dominant_split_eligible',
                          'theme_orphan_sub', 'theme_subtheme_routed')
     ORDER BY id" > "$OUT/events_extra.csv"

echo "renames: the theme rename lineage (mi_theme_renames, all rows) ..."
run "SELECT old_name, new_name, mechanism, theme_date FROM mi_theme_renames ORDER BY theme_date, id" > "$OUT/renames.csv"

echo "cooldowns: validation cooldowns since $SINCE plus every operator-bypassed (protected) pair ..."
run "SELECT ticker, theme_name, removed_at::date AS removed_on, cooldown_until::date AS cooldown_until,
            bypassed, bypassed_at::date AS bypassed_on, removal_reason
     FROM mi_validation_cooldowns WHERE removed_at >= '$SINCE' OR bypassed
     ORDER BY removed_at" > "$OUT/cooldowns.csv"

echo "exclusions: user-directed permanent bans (mi_theme_exclusions) ..."
run "SELECT * FROM mi_theme_exclusions" > "$OUT/exclusions.csv"

echo "sectors: the label per ticker (latest mi_stock_scores row, plus the overrides cache) ..."
run "SELECT ticker, sector, src FROM (
        SELECT DISTINCT ON (ticker) ticker, sector, 'scores' AS src
        FROM mi_stock_scores
        WHERE score_date >= CURRENT_DATE - 130 AND sector IS NOT NULL AND sector <> ''
        ORDER BY ticker, score_date DESC
     ) s
     UNION ALL
     SELECT ticker, sector, 'override' AS src FROM mi_ticker_overrides
     WHERE sector IS NOT NULL AND sector <> ''
     ORDER BY 1, 3" > "$OUT/sectors.csv"

echo "closes: every ticker that sat in any theme since $SINCE, plus SPY, from $CLOSES_SINCE ..."
run "WITH members AS (SELECT DISTINCT upper(unnest(tickers)) AS t FROM mi_themes WHERE theme_date >= '$SINCE'),
          uni AS (SELECT t FROM members UNION SELECT 'SPY')
     SELECT d.ticker, d.trade_date, d.close
     FROM mi_daily_closes d JOIN uni ON uni.t = d.ticker
     WHERE d.trade_date >= '$CLOSES_SINCE' AND d.close > 0
     ORDER BY d.ticker, d.trade_date" > "$OUT/closes.csv"

for f in themes events events_extra renames cooldowns exclusions sectors closes; do
  printf '  %-14s %8d rows\n' "$f.csv" "$(( $(wc -l < "$OUT/$f.csv") - 1 ))"
done
echo "done -> $OUT   (next: python scripts/probes/_657_comove_removals.py $OUT)"
