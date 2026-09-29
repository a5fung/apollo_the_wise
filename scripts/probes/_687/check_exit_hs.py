"""#687 CHECK (4c) — the 17 day-0 partial-then-breakeven trades under BOTH _hs runner arms (floor = hard stop after the partial).
Appends to check_exit.txt."""
import io, contextlib
from datetime import date, timedelta
from pathlib import Path
import check_walk as CW
HERE = Path(__file__).resolve().parent
with contextlib.redirect_stdout(io.StringIO()):
    daily, m_entry, m_held, fills, theirs = CW.main()
def cont(rule, T, D, f, H, L, db, m0):
    E = f["px"]; hard = 2 * L - H; rps = E - L; tgt = E + 8 * rps; risk = E - hard
    idx = next(i for i, (t, _) in enumerate(m0) if t == f["t"])
    rem, pnl, seen = 1.0, 0.0, False
    for i, (t, (o, h, l, c)) in enumerate(m0[idx:]):
        if not seen:
            if h >= tgt and (i > 0 or not f["at_open"]):
                pnl += (tgt - E) / 3; rem = 2 / 3; seen = True
            continue
        if l <= hard:
            return (pnl + ((o if o < hard else hard) - E) * rem) / risk
    post, d = 0, D
    while d <= CW.HZ:
        d += timedelta(days=1)
        if d.weekday() >= 5 or d not in db or db[d][3] is None:
            continue
        o, h, l, c, v = db[d]; post += 1
        if l <= hard:
            return (pnl + ((o if o < hard else hard) - E) * rem) / risk
        if rule == "T20" and post >= 20:
            return (pnl + (c - E) * rem) / risk
        if rule == "S20":
            xs = [db[x][3] for x in sorted(db) if x <= d and db[x][3] is not None][-20:]
            if len(xs) == 20 and c < sum(xs) / 20:
                return (pnl + (c - E) * rem) / risk
    return None
out = {"T20": 0.0, "S20": 0.0}; n = 0; rows = []
for k, (e, H, L) in fills.items():
    T, D = k
    try:
        R, fin, xd, info = CW.walk("A0", T, D, e, H, L, daily[T], m_entry[k], m_held)
    except CW.Abstain:
        continue
    if fin == "stop_hit" and xd == D and info.get("partial_day") == D:
        n += 1
        t20 = cont("T20", T, D, e, H, L, daily[T], m_entry[k]); s20 = cont("S20", T, D, e, H, L, daily[T], m_entry[k])
        out["T20"] += t20 - R; out["S20"] += s20 - R
        rows.append((T, str(D), round(R, 3), round(t20, 3), round(s20, 3)))
msg = (f"   (4c) the {n} day-0 partial-then-breakeven trades under the _hs definition: T20_hs {out['T20']:+.2f}R, S20_hs {out['S20']:+.2f}R vs "
       f"their A0 value (the study books them as A0 in every runner arm). Per trade (A0, T20_hs, S20_hs): {rows}")
print(msg)
open(HERE / "check_exit.txt", "a").write(msg + "\n")
