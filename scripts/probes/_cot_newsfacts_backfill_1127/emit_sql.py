"""Emit the one-off UPDATE (2026-11-27) that gives the nine 11-25 COT news alerts their figures.

Per (market, event) the patch = country / release / series from `cot_family.fill_news_item_from_fx` (which refuses unless
the saved raw rows reproduce the stored class and z). The SQL merges `patch || item`, so every stored key wins, and only
touches an item whose stored class AND z equal the ones the patch was built from; it raises (rolling back) unless
exactly 9 alerts / 16 items change. Input: the 11-25 alerts as the 11-26 snapshot exported them (their stored
news[] keys). Usage: python emit_sql.py <apollo_cot_snapshot.json> > backfill_1125.sql
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build import patch  # noqa: E402

snap = json.loads(Path(sys.argv[1]).read_text())
rows = [{"id": None, "market": a["market"], "direction": a["direction"], "alert_date": a["alert_date"],
         "detail": {"news": a["news"]}} for a in snap["alerts"] if str(a["alert_date"]).startswith("2026-11-25")
        and a.get("kind") == "news"]
assert len(rows) == 9, len(rows)
vals = []
for r, p in zip(rows, patch(rows)):
    for old, new in zip(r["detail"]["news"], p["news"]):
        add = {k: new[k] for k in ("country", "release", "series") if k in new and k not in old}
        vals.append("(%s, %s, %s, %r::float8, %s::jsonb)" % tuple(
            "'" + str(x).replace("'", "''") + "'" if not isinstance(x, float) else x
            for x in (r["market"], old["event"], old["class"], float(old["z"]), json.dumps(add))))
print(f"""-- 2026-11-27 one-off: the 11-25 COT news alerts get the figures they were scored on (display only; built by
-- scripts/probes/_cot_newsfacts_backfill_1127/emit_sql.py from the saved 11-25 FXEmpire rows). Stored keys win.
-- Run: docker exec -i apollo-postgres psql -U apollo -d apollo -v ON_ERROR_STOP=1 < backfill_1125.sql
-- (save the before-state first: SELECT id, detail FROM mi_cot_alerts WHERE alert_date = '2026-11-25' AND kind = 'news')
BEGIN;
CREATE TEMP TABLE p (market TEXT, event TEXT, cls TEXT, z FLOAT8, add JSONB) ON COMMIT DROP;
INSERT INTO p VALUES
  {(','+chr(10)+'  ').join(vals)};
DO $$
DECLARE n_alerts int; n_items int;
BEGIN
  UPDATE mi_cot_alerts a
     SET detail = jsonb_set(a.detail, '{{news}}', (
           SELECT jsonb_agg(COALESCE(p.add, '{{}}'::jsonb) || n.item ORDER BY n.ord)
             FROM jsonb_array_elements(a.detail -> 'news') WITH ORDINALITY AS n(item, ord)
             LEFT JOIN p ON p.market = a.market AND p.event = n.item ->> 'event' AND p.cls = n.item ->> 'class'
                        AND abs(p.z - (n.item ->> 'z')::float8) < 1e-9))
   WHERE a.alert_date = DATE '2026-11-25' AND a.kind = 'news' AND jsonb_typeof(a.detail) = 'object'
     AND jsonb_typeof(a.detail -> 'news') = 'array';
  GET DIAGNOSTICS n_alerts = ROW_COUNT;
  SELECT count(*) INTO n_items FROM mi_cot_alerts a CROSS JOIN LATERAL jsonb_array_elements(a.detail -> 'news') x
   WHERE a.alert_date = DATE '2026-11-25' AND a.kind = 'news' AND jsonb_typeof(a.detail) = 'object' AND x ? 'series';
  IF n_alerts <> 9 OR n_items <> {len(vals)} THEN       -- raising aborts the transaction: COMMIT then rolls back
    RAISE EXCEPTION 'expected 9 alerts / {len(vals)} items with figures, got % / %', n_alerts, n_items;
  END IF;
  RAISE NOTICE 'patched % alerts, % items now carry figures', n_alerts, n_items;
END $$;
COMMIT;""")
