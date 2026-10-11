"""#700 — the live closed-trade cohort numbers the render-time sections printed on 10-11 (bands /
early-window drift / replay-regression), from the one-time q3 capture. Read-only, local file."""
from datetime import date
from pathlib import Path
import statistics

HERE = Path(__file__).resolve().parent
sec, cur = {}, None
for raw in (HERE / "q3_render_inputs.out").read_text(encoding="utf-8").splitlines():
    if raw.startswith("=== "):
        cur = raw[4:].strip(); sec[cur] = []; continue
    if cur and raw and not raw.startswith("(") and "\t" in raw:
        sec[cur].append(raw.split("\t"))
rows = sec["LIVE_CLOSED"][1:]
rs, meta = [], []
for r in rows:
    _id, ticker, ad, sig, pnl, risk_actual, shares, entry, stop, exit_reason, closed = r
    risk = float(risk_actual) if risk_actual else float(shares) * (float(entry) - float(stop))
    rs.append(float(pnl) / risk)
    meta.append((date.fromisoformat(ad), ticker, exit_reason))
n = len(rs)
cur_since = date(2026, 9, 6)
current = [(r, m) for r, m in zip(rs, meta) if m[0] >= cur_since]
older = [(r, m) for r, m in zip(rs, meta) if m[0] < cur_since]
print(f"n={n} mean_r={sum(rs)/n:+.2f} cum={sum(rs):+.1f} t20={sum(rs[-20:])/20:+.2f} t40=n/a")
print(f"current (since {cur_since}): {len(current)} trades -> {[m[1] for _, m in current]}  older: {len(older)}")
print(f"current mean R {sum(r for r, _ in current)/len(current):+.2f}")
wins = sum(1 for r in rs if r > 0)
print(f"win {wins}/{n} = {100*wins/n:.0f}%  avgW {statistics.mean([r for r in rs if r>0]):+.2f}R avgL {statistics.mean([r for r in rs if r<=0]):+.2f}R")
# streak + maxDD
streak, worst, run = 0, 0, 0
peak = dd = cum = 0.0
for r in rs:
    run = run + 1 if r <= 0 else 0
    worst = max(worst, run)
    cum += r; peak = max(peak, cum); dd = max(dd, peak - cum)
print(f"cur loss streak {run} worst {worst} maxDD {dd:.1f}R")
last20 = list(zip(rs[-20:], meta[-20:]))
print("t20 window: current", sum(1 for _, m in last20 if m[0] >= cur_since), "older", sum(1 for _, m in last20 if m[0] < cur_since))
