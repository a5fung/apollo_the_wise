"""#655 rule B + ONE-NIGHT WAIT (operator ruling 2026-10-05) — G4 replay over the 19 rebuilt nights.

VARIANT, stated before any number was computed: a theme is retired by rule B only if tonight's row is
weak-Fading AND under 3 members (the shape verify_b.py replayed) AND its PREVIOUS persisted row (the
latest mi_themes row of that name with theme_date < tonight, any stage) was ALREADY under 3 members.
No previous row -> kept. Everything else is verify_b.py's harness: the board each night is rebuilt the
way db.get_active_themes builds it (latest row per name within 7 calendar days, then drop Retired).

G4 = share of board themes under 3 members, bar <= 10%.

Honest limits (same as verify_b.py, plus one):
  * the history capture has no rs_avg column, so "weak-Fading" is stage == 'Fading' alone (verify_b's
    own proxy). A scored Fading pair (numeric rs_avg, the #368 guard's case) would be counted here
    but is never retired by the live rule, so the replay can only OVER-state retirements.
  * a STATIC replay on baseline history: a theme the wait spares on its first small night is left on
    that night's board (that is the variant's G4 cost); nights after are as baseline history shows.
    A re-discovery under a new name (the 8.3% regrowth cost) is not simulated for either rule.

Run: python scripts/probes/_655/fix_study/rules_replay4.py
Reads the capture pickle the study wrote (655_capture.pkl); read-only, no prod access.
"""
import collections
import os
import pickle
from datetime import date, timedelta

SCRATCH = "/private/tmp/claude-501/-Users-alvinfung-apollo-the-wise/d30e3944-e07e-4b44-97de-010acba78d0b/scratchpad/"
d = pickle.load(open(SCRATCH + "655_capture.pkl", "rb"))
hist = d["history"]
MIN_MEMBERS = 3
BAR_PCT = 10.0

by_name = collections.defaultdict(list)
for r in hist:
    by_name[r["name"]].append(r)
for n in by_name:
    by_name[n].sort(key=lambda r: r["theme_date"])
dates = sorted({r["theme_date"] for r in hist})
nights = [D for D in dates if D >= date(2026, 9, 8)]


def board(D):
    """db.get_active_themes' shape: latest row per name within 7 days, then drop Retired / empty."""
    out = []
    for n, rows in by_name.items():
        rr = [r for r in rows if D - timedelta(days=7) <= r["theme_date"] <= D]
        if not rr:
            continue
        L = rr[-1]
        if L["stage"] == "Retired" or not L["tickers"]:
            continue
        out.append({"name": n, "stage": L["stage"], "tickers": list(L["tickers"]), "date": L["theme_date"]})
    return out


def prior_members(name, D):
    """Member count of the latest row of `name` with theme_date < D (any stage); None = no such row."""
    prev = [r for r in by_name[name] if r["theme_date"] < D]
    return None if not prev else len(prev[-1]["tickers"] or [])


lines: list[str] = []


def P(s=""):
    print(s)
    lines.append(s)


P(f"{'night':10s} {'board':>5s} {'small':>5s} {'fad-small':>9s} | same-night B: retired G4%  | WAIT: retired held(prior>=3/none) G4%")
pass_base = pass_b = pass_w = 0
tot_b = tot_w = 0
held_ge3 = held_none = 0
outcome = collections.Counter()   # what baseline history shows the spared themes did on their next persisted row
worst_w = 0.0
rows_out = []
for D in nights:
    b = board(D)
    n0 = len(b)
    small = [t for t in b if len(t["tickers"]) < MIN_MEMBERS]
    fad_small = [t for t in small if t["stage"] == "Fading"]
    s0 = len(small)
    # same-night rule B (verify_b.py's replay)
    nb = len(fad_small)
    g4_b = 100 * (s0 - nb) / (n0 - nb)
    # the one-night wait: retire only a Fading-small theme that was ALREADY small last persisted night
    retire_w, held = [], []
    for t in fad_small:
        pm = prior_members(t["name"], D)
        (retire_w if (pm is not None and pm < MIN_MEMBERS) else held).append((t["name"], pm))
    nw = len(retire_w)
    g4_w = 100 * (s0 - nw) / (n0 - nw)
    g4_0 = 100 * s0 / n0
    pass_base += g4_0 <= BAR_PCT
    pass_b += g4_b <= BAR_PCT
    pass_w += g4_w <= BAR_PCT
    tot_b += nb
    tot_w += nw
    for nm, _pm in held:
        nxt = [r for r in by_name[nm] if r["theme_date"] > D]
        if not nxt:
            outcome["no row after"] += 1
        elif nxt[0]["stage"] == "Retired" or not nxt[0]["tickers"]:
            outcome["gone next night (retired/empty)"] += 1
        elif len(nxt[0]["tickers"]) >= MIN_MEMBERS:
            outcome[">= 3 members next night"] += 1
        else:
            outcome["still < 3 next night"] += 1
    h_ge3 = sum(1 for _, pm in held if pm is not None)
    h_none = sum(1 for _, pm in held if pm is None)
    held_ge3 += h_ge3
    held_none += h_none
    worst_w = max(worst_w, g4_w)
    P(f"{D}  {n0:5d} {s0:5d} {nb:9d} | {nb:8d} {g4_b:11.1f}% | {nw:7d} {h_ge3:5d}/{h_none:<4d} {g4_w:11.1f}%")
    rows_out.append((D, nb, nw, h_ge3, h_none, g4_b, g4_w))

N = len(nights)
P()
P(f"G4 nights passing (<= {BAR_PCT:.0f}%): baseline {pass_base}/{N} | same-night rule B {pass_b}/{N} | one-night wait {pass_w}/{N}")
P(f"retirements per night (mean): same-night B {tot_b / N:.1f} | wait {tot_w / N:.1f}   (total {tot_b} vs {tot_w})")
P(f"themes the wait spared tonight: {held_ge3 + held_none} total = {held_ge3} had >= 3 members the night before + {held_none} with no previous row "
  f"({(held_ge3 + held_none) / N:.1f} a night)")
P(f"what the {held_ge3 + held_none} spared themes did on their next persisted row (baseline history): {dict(outcome)}")
P(f"worst night under the wait: G4 {worst_w:.1f}% (bar {BAR_PCT:.0f}%)")
failing = [(D, round(g, 1)) for D, _, _, _, _, _, g in rows_out if g > BAR_PCT]
P(f"nights failing G4 under the wait: {failing}")

open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "rules_replay4.txt"), "w").write("\n".join(lines) + "\n")
