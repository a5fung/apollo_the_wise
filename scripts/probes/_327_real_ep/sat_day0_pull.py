"""#327 G12 (H7 day-0 afternoon re-entry) - READ-ONLY Polygon 1-min pull of the EP days whose minute bars in
minute.tsv.gz are not full (sat_day0_targets.tsv). Runs INSIDE apollo-market (key from env; sent as a Bearer header,
never printed, never in a URL). Writes /tmp/sat_day0_raw.tsv (RTH bars only, minute.tsv.gz columns) and
/tmp/sat_day0_status.tsv. No DB access, no writes to prod."""
import asyncio, os, sys, datetime as dt
from zoneinfo import ZoneInfo
import httpx

ET = ZoneInfo("America/New_York")
PAIRS = [('ABSI', '2026-06-24'), ('ACAD', '2026-06-26'), ('AEHR', '2026-07-15'), ('AGX', '2026-06-05'), ('ALAB', '2026-05-20'), ('ARWR', '2026-07-22'), ('AVAV', '2026-05-28'), ('AVAV', '2026-06-30'), ('CAMT', '2026-06-02'), ('CHRN', '2026-08-27'), ('CLSK', '2026-07-14'), ('CRSR', '2026-05-27'), ('DELL', '2026-05-29'), ('DFTX', '2026-06-22'), ('DOCN', '2026-07-07'), ('DY', '2026-05-27'), ('DYN', '2026-05-20'), ('ELVN', '2026-06-11'), ('EVTC', '2026-05-19'), ('FCEL', '2026-06-24'), ('FET', '2026-07-31'), ('FTK', '2026-08-03'), ('GH', '2026-05-20'), ('GRRR', '2026-06-02'), ('HGTY', '2026-08-05'), ('HPE', '2026-06-02'), ('IDR', '2026-06-15'), ('JBL', '2026-06-17'), ('MLTX', '2026-06-22'), ('MRVL', '2026-06-02'), ('MU', '2026-06-25'), ('NAVN', '2026-06-11'), ('NRIX', '2026-06-08'), ('NVTS', '2026-06-03'), ('PRG', '2026-07-15'), ('QURE', '2026-06-17'), ('RCAT', '2026-05-28'), ('ROCK', '2026-08-05'), ('RUM', '2026-06-04'), ('RXT', '2026-06-16'), ('SHAZ', '2026-06-12'), ('SNX', '2026-06-25'), ('STC', '2026-05-19'), ('SWBI', '2026-06-18'), ('SYRE', '2026-06-22'), ('TATT', '2026-05-20'), ('TATT', '2026-08-05'), ('TTAN', '2026-06-05'), ('UUUU', '2026-06-18'), ('WLDN', '2026-08-07')]

async def main():
    key = os.environ.get("POLYGON_API_KEY", "")
    if not key:
        print("NO_KEY"); sys.exit(2)
    hdr = {"Authorization": "Bearer " + key}
    out = open("/tmp/sat_day0_raw.tsv", "w"); st = open("/tmp/sat_day0_status.tsv", "w")
    out.write("ticker|d|t_ms|o|h|l|c|v\n")
    st.write("ticker|d|http|n_raw|n_rth|first_rth_et|last_rth_et|note\n")
    async with httpx.AsyncClient(timeout=30) as cl:
        for tk, d in PAIRS:
            url = f"https://api.polygon.io/v2/aggs/ticker/{tk}/range/1/minute/{d}/{d}"
            status = None; res = []; note = ""
            for attempt in range(4):
                try:
                    r = await cl.get(url, params={"adjusted": "true", "sort": "asc", "limit": 50000}, headers=hdr)
                except Exception as e:   # never str(e): httpx messages can carry the URL
                    note = "transport_" + type(e).__name__; status = "ERR"; await asyncio.sleep(2 * (attempt + 1)); continue
                status = r.status_code
                if status == 429:
                    await asyncio.sleep(15 * (attempt + 1)); continue
                if status == 200:
                    j = r.json(); res = j.get("results") or []
                    if j.get("next_url"): note = "HAS_NEXT_URL"
                break
            rth = []
            for b in res:
                e = dt.datetime.fromtimestamp(b["t"] / 1000, dt.timezone.utc).astimezone(ET)
                m = e.hour * 60 + e.minute
                if e.date().isoformat() == d and 570 <= m < 960:
                    rth.append((b, m))
            for b, m in rth:
                v = b.get("v", 0); v = int(v) if float(v).is_integer() else v
                out.write("|".join(map(str, (tk, d, b["t"], b["o"], b["h"], b["l"], b["c"], v))) + "\n")
            f = (rth[0][1] // 60, rth[0][1] % 60) if rth else None; l = (rth[-1][1] // 60, rth[-1][1] % 60) if rth else None
            st.write("|".join(map(str, (tk, d, status, len(res), len(rth),
                                          "%02d:%02d" % f if f else "", "%02d:%02d" % l if l else "", note))) + "\n")
            await asyncio.sleep(0.25)
    out.close(); st.close(); print("DONE", len(PAIRS))

asyncio.run(main())
