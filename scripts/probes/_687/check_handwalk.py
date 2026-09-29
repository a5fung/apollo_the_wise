"""#687 INDEPENDENT CHECK (4b) — hand-walk logs (my walker, step by step) for 10 trades x A0/A1/D10 and 5 trades x T20_hs,
plus two decision days recomputed from the raw daily closes by hand (SMA10/SMA20, ADR, the depth stop). Writes check_walks.txt."""
import csv, io, contextlib
from datetime import date, time, timedelta
from pathlib import Path
import check_walk as CW
HERE = Path(__file__).resolve().parent
with contextlib.redirect_stdout(io.StringIO()):
    daily, m_entry, m_held, fills, theirs = CW.main()
O = open(HERE / "check_walks.txt", "w")
def P(*a):
    s = " ".join(str(x) for x in a); print(s); O.write(s + "\n")
MAIN = [("BE", "2025-07-24"), ("HL", "2025-08-07"), ("FCEL", "2026-04-29"), ("EPSM", "2025-04-24"), ("SEZL", "2025-05-08"),
        ("AXGN", "2024-01-05"), ("ALEX", "2025-12-09"), ("VYGR", "2024-01-02"), ("KROS", "2024-01-04"), ("MHK", "2024-07-26")]
RUN = [("DELL", "2026-02-27"), ("BE", "2025-07-24"), ("MHK", "2024-07-26"), ("AXGN", "2024-01-05"), ("HL", "2025-08-07")]
def one(arm, k):
    T, D = k[0], date.fromisoformat(k[1]); e, H, L = fills[(T, D)]
    log = []
    try:
        R, fin, xd, info = CW.walk(arm, T, D, e, H, L, daily[T], m_entry[(T, D)], m_held, log=log)
    except CW.Abstain as ex:
        R, fin, xd = None, f"abstain {ex}", None
    r = theirs[(T, D)]
    tR = r[f"{arm}_R"]
    P(f"## {T} {D} {arm}: MINE {R:+.4f} {fin} {xd} | STUDY {float(tR):+.4f} {r[f'{arm}_final']} {r[f'{arm}_exit_day']} -> {'MATCH' if abs(R - float(tR)) < 0.005 else 'DIFFER'}")
    for s in log[-14:] if len(log) > 14 else log:
        P("   " + s)
for k in MAIN:
    for a in ("A0", "A1", "D10"):
        one(a, k)
P("")
for k in RUN:
    one("T20_hs", k)
# ── by hand from raw daily closes: two decision days ──
P("")
P("## BY HAND from pull_daily_out.txt (no walker): the resting stops on two decision days")
def by_hand(T, D, day, note):
    D = date.fromisoformat(D); day = date.fromisoformat(day); db = daily[T]
    prior = [db[x][3] for x in sorted(db) if x < D]
    held = [db[x][3] for x in sorted(db) if D < x < day]            # closes through the day BEFORE `day` (the 16:45 line that rests on `day`)
    xs = prior + held
    s10, s20 = sum(xs[-10:]) / 10, sum(xs[-20:]) / 20
    pre = [db[x] for x in sorted(db) if x < D][-20:]
    adr = sum((b[1] - b[2]) / b[3] for b in pre) / len(pre)
    line = max(s10, s20)
    o, h, l, c, v = db[day]
    P(f"   {T} entry {D}, {note}: line resting on {day} = max(SMA10 {s10:.4f}, SMA20 {s20:.4f}) = {line:.4f} (entry-day close omitted; "
      f"the ratchet can only hold it higher); ADR20 {adr:.4f} -> depth stop line x (1 - ADR) = {line * (1 - adr):.4f}; day bar o {o} l {l} c {c}; "
      f"low <= line: {l <= round(line, 2)}; low <= depth stop: {l <= round(line * (1 - adr), 2)}; close >= line (reclaim): {c >= round(line, 2)}")
by_hand("EPSM", "2025-04-24", "2025-05-13", "A0 sold here (touch), D10 sold here, A1 held")
by_hand("BE", "2025-07-24", "2025-08-08", "A0 sold here on the touch; A1/D10 held")
O.close()
