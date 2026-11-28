import json, sys
sys.path.insert(0, "/Users/alvinfung/portfolio-app2")
import theme_data
g = theme_data.get_canonical_weekly_grid(weeks=200)
out = {}
for w in ("2026-11-23", "2026-11-30"):
    x = g[g["week_start"].astype(str).str[:10] == w]
    out[w] = sorted(x[x["week_rank"] <= 30]["canonical_id"]) if len(x) else None
json.dump(out, open("/Users/alvinfung/apollo_the_wise/scripts/probes/_644_correction_1128/board.json", "w"))
print({k: (None if v is None else len(v)) for k, v in out.items()})
