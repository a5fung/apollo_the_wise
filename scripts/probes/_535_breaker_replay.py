"""#535 r1 backtest — would a loss-expiry window + partials-count have unblocked real days,
and does the breaker still fire on a genuine live-money bleed?  READ-ONLY, $0.

Closed live trades, newest first, as measured 2026-08-05 (14 trades, ZERO winners):
"""
from datetime import datetime, date

# (ticker, closed_at ET, pnl) — from mi_live_trades, account_mode='live', status='closed'
CLOSED = [
    ("BLZE", "2026-08-04 15:50", -36.79), ("BTDR", "2026-08-04 09:46", -28.12),
    ("FTNT", "2026-07-30 09:37",  -6.63), ("QBTS", "2026-07-28 09:36", -22.26),
    ("SMCI", "2026-07-27 10:37", -14.96), ("NVCR", "2026-07-24 15:36", -24.13),
    ("THC",  "2026-07-24 12:43", -16.28), ("WKC",  "2026-07-24 12:02", -23.80),
    ("HUT",  "2026-07-20 09:31", -19.53), ("MANE", "2026-07-16 09:30",  -2.40),
    ("TSEM", "2026-07-14 09:44", -23.01), ("WDFC", "2026-07-10 09:40", -19.03),
    ("CRCL", "2026-07-10 09:40", -19.18), ("WULF", "2026-07-06 09:57", -32.80),
]
THRESHOLD = 10           # CIRCUIT_BREAKER_CONSEC_LOSSES
REALIZED_PARTIALS = [("PLTR", "2026-08-05 09:45", 33.27)]   # the first live realized profit

def _dt(s): return datetime.strptime(s, "%Y-%m-%d %H:%M")

def counting_losses(as_of, window_days):
    """Losses that still count at `as_of` under an expiry window (None = today's behaviour)."""
    out = []
    for t, c, p in CLOSED:
        cd = _dt(c)
        if cd > as_of or p > 0:
            continue
        if window_days is not None and (as_of - cd).days >= window_days:
            continue
        out.append((t, c, p, round((as_of - cd).total_seconds() / 86400, 1)))
    return out

def open_state(as_of, window_days, partials_count):
    losses = counting_losses(as_of, window_days)
    if partials_count:
        # A realized profit AFTER the most recent counting loss breaks the streak.
        newest_loss = max((_dt(c) for _, c, _, _ in losses), default=None)
        for _, pt, pnl in REALIZED_PARTIALS:
            if pnl > 0 and _dt(pt) <= as_of and (newest_loss is None or _dt(pt) > newest_loss):
                return False, len(losses), "streak broken by a realized partial"
    return len(losses) >= THRESHOLD, len(losses), ""

AS_OF = _dt("2026-08-05 09:31")   # this morning's ORB, when 5 alerts were blocked
print("=" * 74)
print("A. WOULD TODAY'S 5 BLOCKED ALERTS HAVE ENTERED?  (as of 2026-08-05 09:31 ET)")
print("=" * 74)
for window in (None, 21, 14, 10, 7):
    for partials in (False, True):
        blocked, n, why = open_state(AS_OF, window, partials)
        label = f"expiry={'none' if window is None else f'{window}d':>5}  partials={'yes' if partials else 'no ':>3}"
        print(f"  {label}  counting losses={n:>2}  -> {'BLOCKED' if blocked else 'ENTERS'}"
              f"{'  (' + why + ')' if why else ''}")

print()
print("=" * 74)
print("B. THE SAFETY CHECK — does a REAL bleed still trip it under each window?")
print("   (how many of the 14 real losses fall inside the window at their own worst moment)")
print("=" * 74)
for window in (21, 14, 10, 7):
    worst = 0
    worst_at = None
    for _, c, _ in CLOSED:
        as_of = _dt(c)
        n = len(counting_losses(as_of, window))
        if n > worst:
            worst, worst_at = n, c
    verdict = "TRIPS on the real streak" if worst >= THRESHOLD else "would NEVER have tripped"
    print(f"  expiry={window:>3}d  peak counting losses={worst:>2} (at {worst_at})  -> {verdict}")

print()
print("  Read B like this: a window is only a safeguard if a genuine cluster of 10 losses")
print("  still reaches the threshold INSIDE it. A window so short that real bleeds expire")
print("  faster than they accumulate has disarmed the breaker, not modernised it.")
