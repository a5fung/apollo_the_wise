"""Why did Alpaca miss Benzinga candidates Polygon gave on 05-27 .. 06-08? Truncation (limit 20 newest) or absent?"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
pull = [json.loads(l) for l in open(HERE / "news_pull.jsonl")]
for want in (("SUNE", "2026-06-08"), ("MYRG", "2026-05-27"), ("CGCT", "2026-05-29"), ("QURE", "2026-05-29"),
             ("D", "2026-05-18")):
    for c in pull:
        if c["kind"] == "cell" and (c["ticker"], c["day"]) == want:
            al = c["alpaca"]
            ts = sorted(a["created_at"] for a in al)
            print(want, "alpaca items:", len(al), "oldest:", ts[0][:19] if ts else None,
                  "newest:", ts[-1][:19] if ts else None)
            kw = [a["title"][:90] for a in al if any(k in (a["title"] or "").lower()
                  for k in ("merger", "definitive", "acquire", "business combination", "suniva", "valley electric"))]
            print("   alpaca titles with deal words:", kw[:5])
            pb = [(p["title"][:90], p["published_utc"], p["publisher"]) for p in c["polygon"]
                  if p.get("publisher") == "Benzinga"][:4]
            print("   polygon Benzinga items:", pb)
