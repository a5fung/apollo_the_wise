import json, collections
rows = [json.loads(l) for l in open("scripts/probes/_692_alpaca/input_replay_2026-10-02.jsonl")]
print(collections.Counter(r.get("kind") for r in rows))
td = [r for r in rows if r.get("kind") == "ticker_day"]
print(sorted(td[0].keys()))
print(collections.Counter(str(r.get("label"))[:30] for r in td).most_common(8))
print("<=06-17:", sum(1 for r in td if r["date"] <= "2026-06-17"),
      "06-18..10-02:", sum(1 for r in td if "2026-06-18" <= r["date"] <= "2026-10-02"))
print(collections.Counter(len(r.get("headline_asked") or []) for r in td))
