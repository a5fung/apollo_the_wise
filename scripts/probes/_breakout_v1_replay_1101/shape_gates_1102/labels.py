"""Label checks for the three shape gates (DEFINITIONS.md): MTW 10-30 (his 'not a breakout'), ZCSH (absent from the
stores), and the 12 of his 24 good setups v1 already catches. Read-only; writes labels.txt beside it.

Seal: the 12 read cb702_pre_v2 (2020 bars). MTW reads ONLY scripts/probes/_mtw_1102/mtw_bars.csv, sliced to <= 2026-10-30
(the watch night) before any computation — the declared exception in DEFINITIONS.md."""
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(HERE))
from agents.market_intelligence import breakout_v1 as bv            # noqa: E402
from agents.market_intelligence import consolidation_breakout as cb  # noqa: E402
from scripts.probes._cb_backtest import runner                       # noqa: E402
import gates_patch as G                                               # noqa: E402

NEW = ("riding", "rising_lows", "no_failed_attempt")
out_lines = []


def say(s=""):
    print(s, flush=True)
    out_lines.append(s)


def new_gates(bars, D):
    with np.errstate(invalid="ignore", divide="ignore"):
        rng = (bars.h - bars.l) / bars.c
    old = bv.v1_gates(bars, D, rs_best=99.0)
    P = old["pole_idx"]
    res = {"riding": G.riding_gate(bars, rng, D), "rising_lows": G.rising_lows_gate(bars, D),
           "no_failed_attempt": G.no_failed_attempt_gate(bars, D, P)}
    return old, res


def fmt(res):
    r = res["riding"]["value"]
    f = res["no_failed_attempt"]["value"]
    return (f"G1 riding {'PASS' if res['riding']['pass'] else 'FAIL'} "
            f"[10d: closes under {r['sma10']['closes_under']}, lows too deep {r['sma10']['lows_too_deep']}, worst {r['sma10']['worst_low_adr_under']} ADR | "
            f"20d: closes under {r['sma20']['closes_under']}, lows too deep {r['sma20']['lows_too_deep']}, worst {r['sma20']['worst_low_adr_under']} ADR] ; "
            f"G2 rising lows {'PASS' if res['rising_lows']['pass'] else 'FAIL'} {[round(x, 3) for x in res['rising_lows']['value']['block_lows']]} ; "
            f"G3 no failed attempt {'PASS' if res['no_failed_attempt']['pass'] else 'FAIL'} "
            f"[ceiling {f.get('ceiling')}, last-5 high {f.get('recent_high')}, close {f.get('close')}]")


# ── MTW ──
df = pd.read_csv(REPO / "scripts/probes/_mtw_1102/mtw_bars.csv")
df = df[df.trade_date <= "2026-10-30"].reset_index(drop=True)
mtw = cb.daily_bars_from_arrays([date.fromisoformat(d) for d in df.trade_date], df.open_price, df.high_price,
                                df.low_price, df.close, df.volume)
D = len(mtw) - 1
old, res = new_gates(mtw, D)
say("=== MTW, watch night 2026-10-30 (his read: NOT a breakout) ===")
say(f"parity with the live list row (pole 2026-10-06, base low 21.05, level 23.875, surf run10 10): "
    f"pole {old['pole_date']}, base low {old['base_low']}, level {old['level']}, surf {old['gates']['surf']['value']}, "
    f"old shape gates failed: {[k for k in old['failed'] if k not in ('rs',)]}")
say("  " + fmt(res))
mtw_fail = [k for k in NEW if not res[k]["pass"]]
say(f"  new gates MTW fails: {mtw_fail}  -> bar (a) {'PASS' if mtw_fail else 'FAIL'}")
say()

# ── ZCSH ──
say("=== ZCSH (his positive example, 2026-10-29) ===")
say("  NOT in the stores: 0 rows in cb702_pre_v2/daily_closes_all.csv.gz and 0 in the sealed (< 2025) cb702 copy — a 2026 fund.")
say("  Not checked; bar (b) rests on the 12 alone.")
say()

# ── the 12 ──
TWELVE = [("CELH-1", "CELH", "2020-06-23"), ("CELH-3", "CELH", "2020-08-05"), ("CODX-1", "CODX", "2020-04-16"),
          ("LVGO-4", "LVGO", "2020-07-06"), ("OPK-2", "OPK", "2020-07-17"), ("OSTK-2", "NXH", "2020-06-23"),
          ("SRNE-2", "SRNE", "2020-07-31"), ("PRTS", "PRTS", "2020-07-08"), ("ARCT", "ARCT", "2020-07-13"),
          ("HL", "HL", "2020-08-04"), ("IBIO-1", "IBIO", "2020-07-15"), ("PENN-2", "PENN", "2020-06-23")]
Dd = runner.load_daily(Path("/Users/alvinfung/apollo_data/cb702_pre_v2/daily_closes_all.csv.gz"))
say("=== THE 12 of his 24 v1 already catches (each at its catching fire: E = the date shown, D = the session before) ===")
counts = {k: 0 for k in NEW}
all3 = 0
for name, t, e in TWELVE:
    bars, cidx = runner.bars_for(Dd, Dd.tid[t])
    ei = bars.dates.index(date.fromisoformat(e))
    Di = ei - 1
    cut = cb.daily_bars_from_arrays(bars.dates[:Di + 1], bars.o[:Di + 1], bars.h[:Di + 1], bars.l[:Di + 1],
                                    bars.c[:Di + 1], bars.v[:Di + 1])   # bars <= D only
    old, res = new_gates(cut, Di)
    for k in NEW:
        counts[k] += bool(res[k]["pass"])
    ok3 = all(res[k]["pass"] for k in NEW)
    all3 += ok3
    oldfail = [k for k in old["failed"] if k not in ("rs", "universe")]
    say(f"  {name:7s} D {bars.dates[Di]} | all three {'PASS' if ok3 else 'FAIL'} | old shape gates failed {oldfail} | "
        f"ADR20 {old['adr20']:.2%}")
    say("          " + fmt(res))
say()
say(f"kept of 12: G1 riding {counts['riding']}, G2 rising lows {counts['rising_lows']}, G3 no failed attempt "
    f"{counts['no_failed_attempt']}, all three {all3}   (bar (b): >= 10)")
(HERE / "labels.txt").write_text("\n".join(out_lines) + "\n")
