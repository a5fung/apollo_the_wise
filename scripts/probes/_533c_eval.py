"""#533 Change 6 — offline evaluation of the catalyst-tier SHADOW grader (2026-08-22).

Imports the REAL module (catalyst_tier_shadow.shadow_retier — never a lookalike) and
replays it over the 264 live alerts in _533c_capture.psv. Primary run uses the STORED
#568 expectedness axes (mi_alert_rank_shadow — the live derivation's own full-input
output); a consistency run re-derives them via the module's own compute path on the
captured (truncated) text. $0 — no LLM, no prod writes.
"""
import sys, re
from pathlib import Path
from collections import Counter, defaultdict

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))
from agents.market_intelligence.catalyst_tier_shadow import (
    shadow_retier, detect_demotion_marker, detect_concrete_event,
    sector_follow_through, compute_shadow_verdict)

P = REPO / "scripts/probes/_533c_capture.psv"
sections = {}; cur = None
for line in open(P, encoding="utf-8", errors="replace"):
    line = line.rstrip("\n")
    if line.startswith("==="): cur = line[3:]; sections[cur] = []; continue
    if cur is not None: sections[cur].append(line)

def parse(name):
    rows = sections[name]; hdr = rows[0].split("|"); out = []
    for r in rows[1:]:
        p = r.split("|")
        if len(p) != len(hdr): continue
        out.append(dict(zip(hdr, p)))
    return out

alerts = parse("ALERTS_TEXT"); expct = parse("EXPCT")
board = parse("BOARD"); regime = parse("REGIME")
ex = {int(e["alert_id"]): e for e in expct}
reg = {r["regime_date"]: r for r in regime}
bydate = defaultdict(dict)
for b in board: bydate[b["scan_date"]][b["ticker"]] = b["sector"] or None
live = [a for a in alerts if a["src"] == "live"]

CAT_PTS = {"game_changer": 25, "strong": 15, "routine": 0, "mna": 0}

def floor_for(gap, q):
    if gap >= 15 and q == "game_changer": return 80
    if gap >= 20 and q == "strong": return 80
    if gap >= 15 and q == "strong": return 70
    if gap >= 10 and q == "game_changer": return 60
    return 0

def shadow_for(a, use_stored=True):
    e = ex.get(int(a["id"]))
    sect = sector_follow_through(bydate.get(a["alert_date"], {}), a["ticker"])
    demo = detect_demotion_marker(a["analysis"], a["catalyst"])
    conc = detect_concrete_event(a["analysis"], a["gtext"])
    if use_stored and e:
        sched, combined, beat = e["sched"], e["combined"], e["expct_beat"] == "t"
    else:
        v = compute_shadow_verdict(
            ticker=a["ticker"], live_quality=a["quality"],
            claude_analysis=a["analysis"], grounded_text=a["gtext"],
            news_summary=a["catalyst"], sector_by_ticker=bydate.get(a["alert_date"], {}))
        return v["shadow_tier"], v["rule"]
    return shadow_retier(a["quality"], sched, combined, beat, demo, conc,
                         sect["sector_confirm"])

print("=" * 70)
print("A. FALSE-POSITIVE RATE ON ORDINARY ALERTS (live alerts, stored expct)")
print("=" * 70)
for label, sel in [("all live (n=%d)" % len(live), live),
                   ("last 60d", [a for a in live if a["alert_date"] >= "2026-06-23"]),
                   ("HIGH only", [a for a in live if a["score_tier"] == "HIGH"])]:
    lc, sc = Counter(), Counter()
    for a in sel:
        lc[a["quality"]] += 1
        sc[shadow_for(a)[0]] += 1
    n = len(sel)
    fmt = lambda c: {k: f"{v} ({v/n:.0%})" for k, v in sorted(c.items())}
    print(f"\n{label}  n={n}")
    print("  live:  ", fmt(lc))
    print("  shadow:", fmt(sc))

print("\nTransitions (all live):")
tr = Counter(); rules = Counter()
for a in live:
    t, r = shadow_for(a)
    rules[r] += 1
    if t != a["quality"]: tr[(a["quality"], t, a["ticker"], a["alert_date"])] += 1
tc = Counter((k[0], k[1]) for k in tr)
for k, v in sorted(tc.items()): print("  ", k, v)
print("Promotions strong->gc:", sorted([(k[2], k[3]) for k in tr if k[0] == "strong"]))
print("Corrective routine->strong:", sorted([(k[2], k[3]) for k in tr if k[0] == "routine"]))
print("\nRule counts:", dict(sorted(rules.items())))

print("\nConsistency run (module-derived expct on captured text) vs stored-expct run:")
diff = 0
for a in live:
    if shadow_for(a, True)[0] != shadow_for(a, False)[0]: diff += 1
print(f"  divergent shadow tiers: {diff}/{len(live)}")

print("\n" + "=" * 70)
print("B. ALERT-VOLUME CHANGE (within the already-alerted pool; counterfactual score)")
print("=" * 70)
vol = Counter(); moved = []
for a in live:
    t, _ = shadow_for(a)
    if t == a["quality"]: continue
    gap = float(a["gap_pct"]); score = float(a["ep_score"])
    rrow = reg.get(a["alert_date"])
    rmult = 1.2 if (rrow and rrow["regime"] == "Bull") else 1.0
    mult = rmult * float(a["conf_mult"] or 1)
    thr = int(rrow["ep_threshold"]) if rrow and rrow["ep_threshold"] else 70
    raw = score / mult
    raw_shadow = raw - CAT_PTS.get(a["quality"], 0) + CAT_PTS.get(t, 0)
    raw_shadow = max(raw_shadow, floor_for(gap, t))
    s_shadow = raw_shadow * mult
    old_tier = "HIGH" if score >= thr else ("MODERATE" if score >= 50 else "none")
    new_tier = "HIGH" if s_shadow >= thr else ("MODERATE" if s_shadow >= 50 else "none")
    if old_tier != new_tier:
        vol[(old_tier, new_tier)] += 1
        moved.append((a["ticker"], a["alert_date"], a["quality"], t,
                      round(score, 1), round(s_shadow, 1), old_tier, new_tier))
print("tier moves:", dict(vol))
for m in moved: print("  ", m)

print("\n" + "=" * 70)
print("C. THE GRADED REAL EPs")
print("=" * 70)
# MRNA at its real 07:05 tick: gap read 10.04, strong, score 21.6 (mult 1.2 era? compute)
mrna = [a for a in live if a["ticker"] == "MRNA" and a["alert_date"] == "2026-08-19"][0]
t, r = shadow_for(mrna)
print(f"MRNA alert row: live={mrna['quality']} -> shadow={t} ({r})")
rrow = reg.get("2026-08-19"); rmult = 1.2 if (rrow and rrow["regime"] == "Bull") else 1.0
thr = int(rrow["ep_threshold"]) if rrow and rrow["ep_threshold"] else 70
print(f"  regime {rrow['regime'] if rrow else '?'} mult={rmult} thr={thr}")
# 07:05 counterfactual: raw 21.6/mult; shadow GC -> +10 pts + floor 60 at gap 10.04
raw_0705 = 21.6 / rmult
raw_sh = max(raw_0705 - 15 + 25, floor_for(10.04, t))
print(f"  07:05 tick (gap read 10.04, score 21.6): shadow raw={raw_sh} -> score {raw_sh*rmult:.1f}"
      f"  -> {'HIGH' if raw_sh*rmult >= thr else 'MODERATE' if raw_sh*rmult >= 50 else 'dead'}"
      f"  (live died: 'score 22 < 50')")
# INTC 04-24 from the audit-log text (alert row purged)
intc_txt = ("Intel gapped up on blowout Q1 earnings released April 23, 2026, with the stock "
            "surging in after-hours trading driven by beats across three critical dimensions: "
            "revenue, margins, and forward guidance. The company reported $13.6 billion in Q1 "
            "revenue versus Wall Street expectations of $12.4 billion")
v = compute_shadow_verdict(ticker="INTC", live_quality="game_changer",
                           claude_analysis=intc_txt, grounded_text=intc_txt,
                           news_summary="Intel Q1 earnings blowout",
                           sector_by_ticker={"INTC": None})
print(f"INTC 04-24 (audit-text replay): sched={v['expct_sched']} combined={v['expct_combined']} "
      f"beat={v['expct_beat']} -> shadow={v['shadow_tier']} ({v['rule']})")
