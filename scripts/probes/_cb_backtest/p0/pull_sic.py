"""#702 P0: point-in-time SIC for the liquid universe. Input /tmp/cb702_liquid.txt (ticker|date);
output /tmp/cb702_sic.psv (ticker|date|status|sic_code|sic_description|type). Resumable; read-only."""
import os, time
import requests
pk = os.environ.get("POLYGON_API_KEY", "")
out = "/tmp/cb702_sic.psv"
done = set()
if os.path.exists(out):
    done = {l.split("|")[0] for l in open(out)}
todo = [l.rstrip("\n").split("|") for l in open("/tmp/cb702_liquid.txt") if l.strip()]
with open(out, "a") as fh:
    for t, d in todo:
        if t in done:
            continue
        for attempt in range(3):
            try:
                r = requests.get(f"https://api.polygon.io/v3/reference/tickers/{t}", params={"date": d, "apiKey": pk}, timeout=20)
                if r.status_code == 429:
                    time.sleep(5); continue
                j = (r.json().get("results") or {}) if r.status_code == 200 else {}
                fh.write("|".join([t, d, str(r.status_code), str(j.get("sic_code") or ""),
                                   (j.get("sic_description") or "").replace("|", "/"), str(j.get("type") or "")]) + "\n")
                fh.flush()
                break
            except Exception as ex:
                time.sleep(2)
        time.sleep(0.12)
print("done", sum(1 for _ in open(out)))
