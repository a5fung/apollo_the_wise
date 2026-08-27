"""#490 root-cause probe (READ-ONLY, $0): third-party minute-volume truth for the
ep_rt_volume_shadow disagreement cases. Yahoo 1m bars WITH pre/post, captured once
to _490rt_vol_truth.tsv. No prod, no DB, no paid call."""
import sys
from datetime import date, timedelta
from zoneinfo import ZoneInfo
import yfinance as yf

_ET = ZoneInfo("America/New_York")
CASES = [("ATRO", "2026-08-12"), ("CAI", "2026-08-06"), ("PSIX", "2026-08-07"),
         ("WLDN", "2026-08-07"), ("FBRX", "2026-07-27"), ("TRAX", "2026-07-27"),
         ("VEEE", "2026-07-27"), ("OMER", "2026-07-27")]

out = open("scripts/probes/_490rt_vol_truth.tsv", "w")
out.write("ticker\tdate\tet_time\tvolume\tclose\n")
for tkr, d in CASES:
    d0 = date.fromisoformat(d)
    try:
        df = yf.Ticker(tkr).history(start=d0.isoformat(),
                                    end=(d0 + timedelta(days=1)).isoformat(),
                                    interval="1m", prepost=True, auto_adjust=False)
    except Exception as e:
        print(f"FAIL {tkr} {d}: {e}", file=sys.stderr); continue
    if df is None or df.empty:
        print(f"EMPTY {tkr} {d}", file=sys.stderr); continue
    n = 0
    for ts, row in df.iterrows():
        t = ts.tz_convert(_ET)
        if t.date().isoformat() != d:
            continue
        out.write(f"{tkr}\t{d}\t{t.strftime('%H:%M')}\t{int(row['Volume'])}\t{row['Close']:.4f}\n")
        n += 1
    print(f"{tkr} {d}: {n} bars", file=sys.stderr)
out.close()
