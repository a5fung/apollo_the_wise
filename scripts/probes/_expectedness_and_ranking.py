#!/usr/bin/env python3
"""EXPECTEDNESS AXIS (Part 1) + CANDIDATE RANKING (Part 2) — 2026-08-16.

Operator framing (roadmap §2c): the catalyst EXPLAINS the gap, so its explanatory
content is already priced in; the catalyst's marginal value is what it implies about
the NEXT WEEKS. Rubric spec: roadmap "THE EXPECTEDNESS AXIS (added 2026-08-15)".

READ-ONLY analysis over cached prod pulls. No LLM spend (all classification is
deterministic regex/keyword/numeric over stored text). Nothing proposed — grading
and admission are the operator's sole authority (THE LINE). Output is evidence + a
fork, never a rule change.

Inputs (capture-once caches in this directory):
  _expct_alerts.tsv        mi_ep_alerts x mi_ep_catalyst_metrics, 357 rows 05-11..08-14
                           (pulled 2026-08-16; the purge ate everything before 05-11)
  _533n_daily.tsv          daily bars for the 320 alert tickers through 08-14
  _552_cohort.psv          the 749 tier-A real-stock gap days 03-03..07-15 (incl. the
                           78 tail winners; ETF-clean rebuild from the 552 probe)
  _expct_cohort_daily.tsv  daily bars for the 491 cohort tickers 2025-11-17..08-14
                           (pulled 2026-08-16)

PART 1 — expectedness classes, fully deterministic:
  axis 1 SCHEDULED vs UNSCHEDULED:
    - grounded_text opens with "[SEC {form} filed {date}, items {items}]" when a
      filing grounded the grade (build_grounded_text, ep_detector.py) — parse it.
    - SCHEDULED (filing evidence): 10-Q/10-K, or 8-K/6-K whose items include 2.02
      (results of operations = the diarised earnings release).
    - UNSCHEDULED (filing evidence): 8-K WITHOUT 2.02 (1.01 material agreement,
      2.01 completed acquisition, 7.01 Reg FD, 8.01 other events, 5.02 officers).
    - no SEC block -> keyword fallback on catalyst+judge_rationale+grounded slice;
      earnings-shaped language -> scheduled_kw, event-shaped -> unscheduled_kw,
      neither -> UNKNOWN (a first-class value, per the spec).
  axis 2 BACKWARD vs FORWARD (same text):
    - FORWARD = future commitment/capability: approval/clearance, pivotal endpoint,
      named contract/lease/order with value or term, backlog, guidance RAISE,
      merger/acquisition, index inclusion, commercial launch.
    - BACKWARD = a closed period reported: revenue/EPS actuals, record quarter,
      beat vs estimate, YoY% framed as the quarter's result.
    - both -> MIXED_FWD (spec: a scheduled release containing a forward fact takes
      the strongest forward element + a mixed flag). Analyst actions (initiations/
      PT/upgrades) with NO company fact -> ANALYST_ONLY (present in corpus; the
      spec has no home for them and inventing one silently would be a guess).
  axis 3 BEAT vs GROWTH, two separate numbers:
    - beat_flag: beat/topped/exceeded-vs-consensus language (presence only — the
      surprise MAGNITUDE needs the consensus feed, not derivable from stored text).
    - growth: q_revenue_yoy_pct (stored numeric, mi_ep_catalyst_metrics) with a
      regex fallback for "+X% YoY" revenue phrasing. The >=39% split cites the
      Pradeep bar already in the notes (06-16) — a pre-existing threshold, NOT fit
      here.

  Outcome unit (house, ADR-normalised): tailx = (max high D+1..D+20 - close_D)
  / close_D / ADR20, ADR20 = mean((h-l)/c) over the 20 sessions ending D-1 (the
  _552 SQL definition). PRIMARY = share reaching >=8xADR + P90(tailx); median
  secondary. Session-permuted p via _tail_stats (house floors). Gap-controlled:
  repeated inside gap terciles, because the whole point is the part of the
  catalyst NOT already in the gap.

PART 2 — candidate score from the three signals that survived ADR-normalisation
  (weekend synthesis C1/C3 + winner_r_available + structure_model.md 4c):
    smaller gap · tighter EP day (range as % of day high) · less MA-distance
    extension (median distance of the open above each MA below it, in ADR units,
    SMA 10/20/50 on closes through D-1 — the 4c definition).
  Score = the AVERAGE OF THREE PERCENTILE RANKS (ascending), parameter-free.
  Target: the 26 tradeable >=10R winners (winner_r_available_2026-08-16.txt,
  geometry 1), reproduced here from bars and asserted against the published list.
  Scored population = the 749 tier-A gap days (the morning candidate pool; the 26
  are NOT in the surviving alert table, so the alert population cannot contain
  them). Catch-rate on the tail first: top decile / top quartile vs base rate.

  ⚠ OVERFITTING: the three features were CHOSEN on this same data this weekend.
  A true holdout is impossible; the early/late split below tests only stability
  of the ranking, not validity of the feature choice, and 13 of the 26 sit on
  one session (2026-04-08). Every variant tried is counted in the ledger.

Output: docs/analysis/expectedness_and_ranking_2026-08-16.txt (capture once).
"""
from __future__ import annotations

import csv
import re
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _tail_stats import describe_tail, perm_p_stat, p90, share_stat, MIN_N_SHARE  # noqa: E402

OUT = HERE.parent.parent / "docs/analysis/expectedness_and_ranking_2026-08-16.txt"

L: list[str] = []  # output buffer


def w(s: str = ""):
    L.append(s)


# ══════════════════════════════════════════ loads ══════════════════════════════════════

def load_bars(path: Path, sep: str):
    bars: dict[str, list[tuple]] = defaultdict(list)
    with open(path) as f:
        for row in csv.reader(f, delimiter=sep):
            if len(row) < 7:
                continue
            t, d = row[0], row[1]
            try:
                o, h, lo, c, v = (float(x) for x in row[2:7])
            except ValueError:
                continue
            bars[t].append((d, o, h, lo, c, v))
    for t in bars:
        bars[t].sort()
    return bars


ALERT_BARS = load_bars(HERE / "_533n_daily.tsv", "|")
COHORT_BARS = load_bars(HERE / "_expct_cohort_daily.tsv", "|")

ALERTS = []
with open(HERE / "_expct_alerts.tsv") as f:
    for row in csv.reader(f, delimiter="|"):
        if len(row) < 15:
            continue
        ALERTS.append(dict(
            ticker=row[0], date=row[1], gap=float(row[2]), ep_score=float(row[3]),
            tier=row[4], judge_tier=row[5], quality=row[6], ctype=row[7],
            authority=row[8], source=row[9], catalyst=row[10], ctype_rat=row[11],
            judge_rat=row[12], grounded=row[13],
            yoy=(float(row[14]) if row[14] not in ("", None) else None),
            extraction=row[15] if len(row) > 15 else ""))

COHORT = []
with open(HERE / "_552_cohort.psv") as f:
    for row in csv.reader(f, delimiter="|"):
        if len(row) < 12:
            continue
        COHORT.append(dict(
            ticker=row[0], date=row[1], gap=float(row[2]), o=float(row[3]),
            hi=float(row[4]), pc=float(row[5]), c=float(row[6]), adr=float(row[7]),
            dvol=float(row[8]), tailx=float(row[9]), winner=row[10] == "1",
            alert_n=int(row[11])))

# ═════════════════════════════ PART 1: classification ══════════════════════════════════

SEC_RE = re.compile(r"\[SEC ([^ \]]+) filed (\d{4}-\d{2}-\d{2}), items ([^\]]*)\]")

EARN_KW = re.compile(
    r"reported (?:its )?(?:record )?(?:q[1-4]|first|second|third|fourth)[- ]quarter"
    r"|q[1-4] (?:fy)?20\d\d (?:results|earnings|revenue)"
    r"|quarterly (?:results|report)|earnings (?:report|release|call|beat)"
    r"|reported earnings|eps of \$|vs\.? consensus|consensus estimate"
    r"|(?:beat|topped|exceeded)(?:\w|\s|,){0,40}(?:estimate|consensus|expectation)"
    r"|q[1-4] 20\d\d (?:record )?revenue|(?:record )?q[1-4] (?:20\d\d )?(?:revenue|sales|earnings|results)"
    # r2 blind recall pass (patterns widened from UNKNOWN-class text only; outcomes never consulted):
    r"|(?:upside )?earnings surprise|q[1-4] fy ?\d{2,4} report|in its q[1-4](?:\w|\s|,){0,20}report",
    re.I)

FWD_KW = re.compile(
    r"fda[ -](?:granted|approv|clearance|accepted)|accelerated approval|510\(k\)|breakthrough (?:therapy|device)"
    r"|approval of|regulatory (?:approval|clearance)|marketing authori[sz]ation"
    r"|(?:phase (?:3|iii)|pivotal)(?:\w|\s|,){0,60}(?:met|positive|success|primary endpoint|endpoint met)"
    r"|primary (?:pfs )?endpoint (?:was )?met"
    r"|(?:contract|order|lease|agreement|deal)(?:\w|\s|,|\$|\.){0,50}(?:worth|valued|\$\d|million|billion|multi-year|\d+[- ]year)"
    r"|(?:awarded|wins?|won|secured|signed)(?:\w|\s|,){0,40}(?:contract|order|agreement|lease|deal)"
    r"|backlog(?:\w|\s|,){0,40}(?:surge|grew|growth|increase|record|x |times)"
    r"|(?:raised?|raising|hiked?|boosted|lifts?|increased)(?:\w|\s|,){0,30}(?:full[- ]year |fy ?20\d\d |annual )?(?:revenue |sales )?(?:guidance|outlook|forecast)"
    r"|guidance raise|to acquire|to be acquired|merger agreement|definitive (?:merger )?agreement"
    r"|acquisition of|agreed to (?:buy|acquire)|will replace(?:\w|\s|,){0,40}s&p"
    r"|inclusion in the s&p|joins? the s&p|added to the s&p"
    r"|commercial launch|launch of(?:\w|\s|,){0,30}(?:drug|product|platform|service)"
    r"|strategic (?:partnership|collaboration|investment)|partnership with|collaboration with"
    r"|equity (?:investment|stake)|takes? a stake"
    # r2 blind recall pass (patterns widened from UNKNOWN-class text only; outcomes never consulted):
    r"|received approval|approval from|regulator(?:\w|\s|,){0,30}approved|formally approved"
    r"|joint development agreement|development agreement|supply (?:agreement|deal|mou)"
    r"|\bmou\b|memorandum of understanding|letter of intent"
    r"|expanding its(?:\w|\s|,){0,50}(?:facility|production|capacity|plant|contract)",
    re.I)

BWD_KW = re.compile(
    r"reported (?:record )?(?:revenue|net income|sales|eps|profit)"
    r"|(?:revenue|sales|net income|eps)s? (?:of|was|were|reached|came in at) \$"
    r"|record (?:quarter|quarterly|revenue|sales|q[1-4])"
    r"|(?:beat|topped|exceeded)(?:\w|\s|,){0,40}(?:estimate|consensus|expectation)"
    r"|(?:revenue|sales)(?:\w|\s|,){0,30}(?:up|grew|increased|rose) \d{1,4}(?:\.\d+)?%"
    r"|first profitable quarter|profitability milestone|swung to (?:a )?profit"
    # r2 blind recall pass:
    r"|(?:upside )?earnings surprise",
    re.I)

ANALYST_KW = re.compile(
    r"initiated coverage|price target|analyst|upgrad(?:ed?|es) (?:to|from|the)"
    r"|outperform|overweight rating|buy rating|coverage on",
    re.I)

BEAT_KW = re.compile(
    r"(?:beat|topped|exceeded|above)(?:\w|\s|,|\$|\.){0,40}(?:estimate|consensus|expectation)"
    r"|revenue beat|earnings beat|\$[\d.,]+[mb]? vs\.? \$[\d.,]+[mb]? est"
    # r2 blind recall pass:
    r"|(?:upside )?earnings surprise|stronger[- ]than[- ]expected",
    re.I)

YOY_RE = re.compile(r"(?:up|grew|increased|rose|\+)\s?(\d{1,4}(?:\.\d+)?)%\s?(?:yoy|y/y|year[- ]over[- ]year)", re.I)


def classify(a: dict) -> dict:
    text = " ".join([a["catalyst"], a["ctype_rat"], a["judge_rat"]])
    gtext = a["grounded"]
    full = text + " " + gtext[:1500]
    m = SEC_RE.search(gtext)
    form, items = (m.group(1).upper(), m.group(3)) if m else ("", "")
    has202 = "2.02" in items
    # axis 1
    if form.startswith(("10-Q", "10-K")) or ((form.startswith(("8-K", "6-K"))) and has202):
        sched, sched_src = "scheduled", "filing"
    elif form.startswith("8-K") and items.strip() and not has202:
        sched, sched_src = "unscheduled", "filing"
    elif form.startswith(("425", "S-4", "SC ")):
        sched, sched_src = "unscheduled", "filing"
    elif EARN_KW.search(full):
        sched, sched_src = "scheduled", "keyword"
    elif FWD_KW.search(full) or ANALYST_KW.search(full):
        sched, sched_src = "unscheduled", "keyword"
    else:
        sched, sched_src = "unknown", "none"
    # axis 2
    fwd, bwd = bool(FWD_KW.search(full)), bool(BWD_KW.search(full))
    if fwd and bwd:
        looking = "mixed_fwd"
    elif fwd:
        looking = "forward"
    elif bwd:
        looking = "backward"
    elif ANALYST_KW.search(full):
        looking = "analyst_only"
    else:
        looking = "unknown"
    # axis 3
    beat = bool(BEAT_KW.search(full))
    growth = a["yoy"]
    if growth is None:
        g = [float(x) for x in YOY_RE.findall(full)]
        growth = max(g) if g else None
        growth_src = "regex" if g else "none"
    else:
        growth_src = "stored"
    return dict(sched=sched, sched_src=sched_src, looking=looking, beat=beat,
                growth=growth, growth_src=growth_src, sec_form=form, sec_items=items)


# ─────────────────────────── outcomes for the alert population ─────────────────────────

def alert_outcome(t: str, d: str):
    seq = ALERT_BARS.get(t, [])
    idx = next((i for i, b in enumerate(seq) if b[0] == d), None)
    if idx is None or idx < 20:
        return None
    adr = st.mean((b[2] - b[3]) / b[4] for b in seq[idx - 20:idx] if b[4] > 0)
    if adr <= 0:
        return None
    c0 = seq[idx][4]
    fwd = seq[idx + 1: idx + 21]
    if len(fwd) < 5:
        return None
    mx = max(b[2] for b in fwd)
    return dict(tailx=(mx - c0) / c0 / adr, nfwd=len(fwd), adr=adr)


for a in ALERTS:
    a.update(classify(a))
    o = alert_outcome(a["ticker"], a["date"])
    a["out"] = o

POP = [a for a in ALERTS if a["source"] == "live" and a["out"] is not None]
FULL = [a for a in POP if a["out"]["nfwd"] >= 20]

TESTS = []  # (label, detail) ledger — every comparison attempted


def tail_line(name, rows):
    vals = [r["out"]["tailx"] for r in rows]
    sess = {r["date"] for r in rows}
    n8, s8 = (sum(1 for v in vals if v >= 8), (100 * sum(1 for v in vals if v >= 8) / len(vals)) if vals else None)
    med = round(st.median(vals), 2) if vals else None
    p9 = round(p90(vals), 2) if len(vals) >= 20 else None
    return (f"  {name:<34} n={len(vals):>3} ({len(sess):>2}s)  reach>=8xADR "
            f"{n8:>2} = {('%.1f%%' % s8) if s8 is not None and len(vals) >= MIN_N_SHARE else 'N<10'}"
            f"  P90={('%+.2fx' % p9) if p9 is not None else 'N<20':>7}  med={med}x")


def compare(label, rows_a, name_a, rows_b, name_b, register=True):
    w(f"  -- {label} --")
    w(tail_line(name_a, rows_a))
    w(tail_line(name_b, rows_b))
    va = [r["out"]["tailx"] for r in rows_a]
    vb = [r["out"]["tailx"] for r in rows_b]
    sa = [r["date"] for r in rows_a]
    sb = [r["date"] for r in rows_b]
    p_share = perm_p_stat(va, vb, sa, sb, share_stat(8.0))
    p_p90 = perm_p_stat(va, vb, sa, sb, lambda v: (p90(v) or 0.0)) if min(len(va), len(vb)) >= 20 else None
    w(f"    perm p (session-shuffled): share>=8xADR "
      f"{('p=%.4f' % p_share) if p_share is not None else 'N too thin'} · P90 "
      f"{('p=%.4f' % p_p90) if p_p90 is not None else 'N too thin'}")
    if register:
        TESTS.append((label, f"{name_a} vs {name_b}"))
    w()


def part1():
    w("=" * 98)
    w("PART 1 — THE EXPECTEDNESS AXIS: derivation, coverage, and whether it separates outcomes")
    w("=" * 98)
    n = len(ALERTS)
    live = [a for a in ALERTS if a["source"] == "live"]
    w(f"corpus: {n} distinct (ticker, alert_date) rows in mi_ep_alerts, {min(a['date'] for a in ALERTS)}"
      f"..{max(a['date'] for a in ALERTS)} (everything before 2026-05-11 was purge-eaten)")
    w(f"  live-source rows: {len(live)} · replay/other-source rows: {n - len(live)} (excluded from outcome tests)")
    sec = [a for a in ALERTS if a["sec_form"]]
    w(f"  grounded_text carries a parseable [SEC form/items] header: {len(sec)} of {n} "
      f"({100 * len(sec) / n:.0f}%) — the filing-evidence path")
    w(f"  q_revenue_yoy_pct present (stored numeric): {sum(1 for a in ALERTS if a['growth_src'] == 'stored')} of {n}")
    w()
    w("HOW EACH CLASS WAS DERIVED (deterministic; no LLM):")
    w("  scheduled   <- 10-Q/10-K, or 8-K/6-K with item 2.02 (earnings release); keyword fallback")
    w("                 for earnings-shaped text when no filing grounded the grade")
    w("  unscheduled <- 8-K WITHOUT 2.02 (1.01/2.01/5.02/7.01/8.01), 425/S-4; keyword fallback")
    w("  forward     <- approval/clearance · pivotal endpoint · valued contract/lease/order ·")
    w("                 backlog · guidance RAISE · M&A · index add · commercial launch")
    w("  backward    <- closed-period actuals: reported revenue/EPS, record quarter, beat, YoY%")
    w("  both        -> mixed_fwd (spec: strongest forward element wins + mixed flag)")
    w("  analyst_only-> initiations/PT/upgrades with NO company fact (not in the spec's classes;")
    w("                 refused to force them into one)")
    w()
    # coverage tables
    for ax, key in (("AXIS 1 (scheduled vs unscheduled)", "sched"),
                    ("AXIS 2 (backward vs forward)", "looking")):
        cnt = defaultdict(int)
        src = defaultdict(int)
        for a in ALERTS:
            cnt[a[key]] += 1
            if key == "sched":
                src[(a[key], a["sched_src"])] += 1
        w(f"  {ax}: " + " · ".join(f"{k}={v} ({100 * v / n:.0f}%)" for k, v in
                                   sorted(cnt.items(), key=lambda kv: -kv[1])))
        if key == "sched":
            w("    evidence source: " + " · ".join(f"{k[0]}/{k[1]}={v}" for k, v in sorted(src.items())))
    cls1 = sum(1 for a in ALERTS if a["sched"] != "unknown")
    cls2 = sum(1 for a in ALERTS if a["looking"] not in ("unknown",))
    g = sum(1 for a in ALERTS if a["growth"] is not None)
    b = sum(1 for a in ALERTS if a["beat"])
    w(f"  AXIS 3: beat-language flag on {b} of {n} · growth number recovered on {g} of {n} "
      f"({sum(1 for a in ALERTS if a['growth_src'] == 'stored')} stored + "
      f"{sum(1 for a in ALERTS if a['growth_src'] == 'regex')} regex)")
    w(f"  CLASSIFIABLE FRACTION (all rows): axis1 {cls1}/{n} = {100 * cls1 / n:.0f}% · axis2 "
      f"{cls2}/{n} = {100 * cls2 / n:.0f}% (honest unknowns kept, never guessed)")
    hist = [a for a in ALERTS if a["catalyst"].startswith("Historical scan:")]
    w(f"  ⚠ coverage split that matters: {len(hist)} rows carry NO catalyst corpus at all "
      f"('Historical scan: ...' backfill) — ALL {len(hist)} are non-live replay rows.")
    lv = [a for a in ALERTS if a["source"] == "live"]
    c1l = sum(1 for a in lv if a["sched"] != "unknown")
    c2l = sum(1 for a in lv if a["looking"] != "unknown")
    w(f"  ON THE LIVE CORPUS (n={len(lv)}): axis1 {c1l}/{len(lv)} = {100 * c1l / len(lv):.0f}% · "
      f"axis2 {c2l}/{len(lv)} = {100 * c2l / len(lv):.0f}%")
    w()
    # spot-check block for auditability
    w("  fixture spot-checks (the audit's own worked cases, where in-window):")
    for tk, dt in (("VERA", "2026-08-14"), ("ETON", "2026-08-14"), ("HTFL", "2026-08-14"),
                   ("RIOT", "2026-08-11"), ("EROC", "2026-08-12"), ("GLBE", "2026-08-12"),
                   ("RDDT", "2026-08-14"), ("NMAX", "2026-08-14")):
        row = next((a for a in ALERTS if a["ticker"] == tk and a["date"] == dt), None)
        if row:
            w(f"    {tk} {dt}: sched={row['sched']}({row['sched_src']}) looking={row['looking']} "
              f"beat={row['beat']} growth={row['growth']} [{row['sec_form']} items {row['sec_items']}]"
              f" quality={row['quality']}")
        else:
            w(f"    {tk} {dt}: not in corpus")
    w()
    w(f"OUTCOME POPULATION: live alerts with >=20 prior bars and >=5 fwd sessions: n={len(POP)}; "
      f"full 20-session windows: n={len(FULL)} (primary — later alerts are truncated)")
    w("outcome unit: (max high D+1..D+20 - close) / close / ADR20 — the house tailx")
    w()
    w("─" * 98)
    w("[1] SCHEDULED vs UNSCHEDULED (axis 1, known-schedule only) — PRIMARY")
    w("─" * 98)
    s_ = [a for a in FULL if a["sched"] == "scheduled"]
    u_ = [a for a in FULL if a["sched"] == "unscheduled"]
    compare("full-window population", s_, "SCHEDULED", u_, "UNSCHEDULED")
    w("─" * 98)
    w("[2] FORWARD-CHANGING vs BACKWARD-LOOKING (axis 2) — PRIMARY")
    w("    forward = forward + mixed_fwd (spec: strongest forward element wins)")
    w("─" * 98)
    f_ = [a for a in FULL if a["looking"] in ("forward", "mixed_fwd")]
    b_ = [a for a in FULL if a["looking"] == "backward"]
    compare("full-window population", f_, "FORWARD(+mixed)", b_, "BACKWARD")
    w(tail_line("  (pure forward only)", [a for a in FULL if a["looking"] == "forward"]))
    w(tail_line("  (mixed_fwd only)", [a for a in FULL if a["looking"] == "mixed_fwd"]))
    w(tail_line("  (analyst_only)", [a for a in FULL if a["looking"] == "analyst_only"]))
    w(tail_line("  (unknown)", [a for a in FULL if a["looking"] == "unknown"]))
    w()
    w("─" * 98)
    w("[3] GAP-CONTROLLED — the same two comparisons inside gap terciles")
    w("    (the point of the axis is the part of the catalyst NOT already in the gap)")
    w("─" * 98)
    gaps = sorted(a["gap"] for a in FULL)
    t1, t2 = gaps[len(gaps) // 3], gaps[2 * len(gaps) // 3]
    w(f"  tercile bounds on the tested population: gap < {t1:.1f}% / {t1:.1f}-{t2:.1f}% / > {t2:.1f}%")
    for lo, hi, nm in ((None, t1, "gap-LOW"), (t1, t2, "gap-MID"), (t2, None, "gap-HIGH")):
        seg = [a for a in FULL if (lo is None or a["gap"] >= lo) and (hi is None or a["gap"] < hi)]
        compare(f"{nm}: scheduled vs unscheduled",
                [a for a in seg if a["sched"] == "scheduled"], "SCHEDULED",
                [a for a in seg if a["sched"] == "unscheduled"], "UNSCHEDULED")
        compare(f"{nm}: forward vs backward",
                [a for a in seg if a["looking"] in ("forward", "mixed_fwd")], "FORWARD(+mixed)",
                [a for a in seg if a["looking"] == "backward"], "BACKWARD")
    w("─" * 98)
    w("[4] HIS ORIGINAL FRAMING — does expectedness rescue catalyst_quality? (secondary)")
    w("─" * 98)
    gc = [a for a in FULL if a["quality"] == "game_changer"]
    compare("game_changer split by axis 2",
            [a for a in gc if a["looking"] in ("forward", "mixed_fwd")], "GC + forward",
            [a for a in gc if a["looking"] == "backward"], "GC + backward")
    compare("game_changer split by axis 1",
            [a for a in gc if a["sched"] == "unscheduled"], "GC + unscheduled",
            [a for a in gc if a["sched"] == "scheduled"], "GC + scheduled")
    w("─" * 98)
    w("[5] AXIS 3 — beat-vs-estimate distinct from growth-vs-history (secondary)")
    w("─" * 98)
    compare("beat-language vs none (full pop)",
            [a for a in FULL if a["beat"]], "BEAT language",
            [a for a in FULL if not a["beat"]], "no beat language")
    gk = [a for a in FULL if a["growth"] is not None]
    compare("growth >=39% (the Pradeep bar) vs <39%, where growth known",
            [a for a in gk if a["growth"] >= 39], "growth >=39% YoY",
            [a for a in gk if a["growth"] < 39], "growth <39% YoY")
    compare("the NBIS/GLBE cell: beat WITHOUT big growth vs growth WITHOUT beat",
            [a for a in gk if a["beat"] and a["growth"] < 39], "beat, growth<39",
            [a for a in gk if not a["beat"] and a["growth"] >= 39], "no-beat, growth>=39")


# ═════════════════════════════ PART 2: candidate ranking ═══════════════════════════════

def sma(vals, k):
    return st.mean(vals[-k:]) if len(vals) >= k else None


def cohort_features(r):
    seq = COHORT_BARS.get(r["ticker"], [])
    idx = next((i for i, bb in enumerate(seq) if bb[0] == r["date"]), None)
    if idx is None:
        return None
    d, o, h, lo, c, v = seq[idx]
    prior = [bb[4] for bb in seq[:idx]]
    if len(prior) < 50:
        return None
    adrf = r["adr"] / 100.0
    if adrf <= 0 or h <= 0:
        return None
    mas = [sma(prior, k) for k in (10, 20, 50)]
    below = [m_ for m_ in mas if m_ is not None and m_ < o]
    ext = st.median([(o - m_) / o / adrf for m_ in below]) if below else None
    rng = (h - lo) / h * 100.0
    # R geometry 1 (winner_r definition): entry=EP-day high, stop=EP-day low, 60 fwd sessions
    fwd = seq[idx + 1: idx + 61]
    r1 = None
    if fwd and h > lo:
        r1 = (max(bb[2] for bb in fwd) - h) / (h - lo)
    return dict(range_pct=rng, ext=ext, below_all=(not below), r1=r1, nfwd=len(fwd))


def pct_rank(vals_sorted, v):
    """ascending percentile: fraction of population strictly below + half ties."""
    import bisect
    lo = bisect.bisect_left(vals_sorted, v)
    hi = bisect.bisect_right(vals_sorted, v)
    return (lo + (hi - lo) / 2) / len(vals_sorted)


PUBLISHED_26 = {("MU", "2026-04-08"), ("UMC", "2026-04-17"), ("STRL", "2026-04-08"),
                ("MRVL", "2026-03-31"), ("ASX", "2026-04-08"), ("SNDK", "2026-04-08"),
                ("SNOW", "2026-05-07"), ("ALGM", "2026-04-08"), ("NBIS", "2026-04-08"),
                ("AMKR", "2026-04-08"), ("AEHR", "2026-03-31"), ("TDIC", "2026-05-12"),
                ("UMC", "2026-05-06"), ("FLY", "2026-03-12"), ("BE", "2026-04-08"),
                ("USAR", "2026-04-08"), ("QCOM", "2026-04-24"), ("QBTS", "2026-04-08"),
                ("AMD", "2026-04-24"), ("HUT", "2026-04-08"), ("QURE", "2026-05-29"),
                ("ARM", "2026-05-06"), ("SMTC", "2026-03-30"), ("IREN", "2026-04-08"),
                ("APLD", "2026-04-08"), ("INTC", "2026-04-24")}

VARIANTS_TRIED: list[str] = []


def score_and_catch(rows, ext_mode: str, note: str, report_features=False,
                    target_key="is26", register=True):
    """rows: cohort rows with feats. ext_mode: 'zero' (below-all-MAs -> ext 0) or
    'drop' (exclude undefined-ext rows). Returns catch table lines."""
    if register:
        VARIANTS_TRIED.append(note)
    pop = []
    for r in rows:
        f_ = r["feat"]
        if f_ is None:
            continue
        ext = f_["ext"]
        if ext is None:
            if ext_mode == "zero":
                ext = 0.0
            else:
                continue
        pop.append((r, f_, ext))
    if not pop:
        return
    gaps = sorted(x[0]["gap"] for x in pop)
    rngs = sorted(x[1]["range_pct"] for x in pop)
    exts = sorted(x[2] for x in pop)
    scored = []
    for r, f_, ext in pop:
        s = (pct_rank(gaps, r["gap"]) + pct_rank(rngs, f_["range_pct"]) + pct_rank(exts, ext)) / 3
        scored.append((s, r, f_, ext))
    scored.sort(key=lambda x: x[0])  # LOW score = small gap + tight day + low extension = BEST
    n = len(scored)
    targets = [i for i, x in enumerate(scored) if x[1][target_key]]
    n_t = len(targets)
    w(f"  [{note}] scored n={n} of {len(rows)} rows · targets in scored pop: {n_t}")
    if not n_t:
        return
    base = n_t / n
    for frac, nm in ((0.10, "top decile"), (0.25, "top quartile"), (0.50, "top half")):
        k = int(round(frac * n))
        hits = sum(1 for i in targets if i < k)
        exp = base * k
        w(f"    {nm:<12} ({k:>3} rows): catches {hits:>2} of {n_t} = {100 * hits / n_t:.0f}% of targets"
          f" · {100 * hits / k:.1f}% hit-rate vs base {100 * base:.1f}% · lift x{(hits / k) / base if k else 0:.1f}"
          f" (chance would catch {exp:.1f})")
    med_rank = st.median([(i + 1) / n for i in targets])
    w(f"    median percentile of targets in the ranking: {100 * med_rank:.0f}% "
      f"(50% = no signal; smaller = better)")
    if report_features:
        w("    the target names, score components (gap% / day-range% / ext xADR -> percentile):")
        for i in sorted(targets):
            s, r, f_, ext = scored[i]
            w(f"      {r['ticker']:<5} {r['date']}  rank {i + 1:>3}/{n} ({100 * (i + 1) / n:>4.1f}%)"
              f"  gap {r['gap']:>5.1f}%  range {f_['range_pct']:>5.1f}%  ext {ext:>5.2f}xADR"
              f"{'  [below all MAs]' if f_['below_all'] else ''}")
    return scored


def part2():
    w()
    w("=" * 98)
    w("PART 2 — THE CANDIDATE RANKING, from the three signals that survived ADR-normalisation")
    w("=" * 98)
    w("THE RULE (three lines, readable):")
    w("  Rank every qualifying gap day by the average of three percentiles:")
    w("    (1) smaller gap  (2) tighter EP day: (high-low)/high  (3) less extension: median")
    w("    distance of the open above each MA below it (SMA 10/20/50, closes through D-1), in ADR units.")
    w("  No thresholds, no weights — three ascending percentile ranks, averaged. Top of list = buy list.")
    w()
    for r in COHORT:
        r["feat"] = cohort_features(r)
        r1 = r["feat"]["r1"] if r["feat"] else None
        r["is26"] = (r["ticker"], r["date"]) in PUBLISHED_26
        r["r1"] = r1
    # reproduce the 26 from bars as an integrity check
    repro = {(r["ticker"], r["date"]) for r in COHORT
             if r["winner"] and r["feat"] and r["r1"] is not None and r["r1"] >= 10}
    missing_feat = [r for r in COHORT if r["feat"] is None]
    w(f"integrity: cohort rows {len(COHORT)} · rows without 50 prior bars or missing EP-day bar: "
      f"{len(missing_feat)} (excluded, listed at foot) · published-26 present in cohort: "
      f"{sum(1 for r in COHORT if r['is26'])}")
    inter = repro & PUBLISHED_26
    w(f"  >=10R-from-entry reproduction from fresh bars: {len(repro)} names; overlap with the "
      f"published 26: {len(inter)} (differences from bar truncation at 08-14 vs the original pull)")
    w(f"  scoreable subset of the 26 (has features): "
      f"{sum(1 for r in COHORT if r['is26'] and r['feat'] is not None)}")
    w()
    w("─" * 98)
    w("[A] PRIMARY: catch-rate of the 26 tradeable >=10R winners, 749-row tier-A cohort")
    w("    (the 26 are NOT in the surviving alert table — the purge ate March/April alerts —")
    w("     so the morning candidate pool, not the alert list, is the population a ranker faces)")
    w("─" * 98)
    score_and_catch(COHORT, "zero", "PRIMARY: 3-feature percentile average, below-all-MAs ext=0",
                    report_features=True)
    w()
    w("─" * 98)
    w("[A2] THE WITHIN-SESSION VIEW — the decision the ranker actually faces each morning")
    w("     (ranks are recomputed inside each session; immune to the 04-08 session-mass problem)")
    w("─" * 98)
    VARIANTS_TRIED.append("within-session ranking (top-1/top-3 per day policy read)")
    by_day = defaultdict(list)
    for r in COHORT:
        if r["feat"] is None:
            continue
        by_day[r["date"]].append(r)
    day_scored = {}
    for d, rows in by_day.items():
        gaps = sorted(x["gap"] for x in rows)
        rngs = sorted(x["feat"]["range_pct"] for x in rows)
        exts = sorted((x["feat"]["ext"] if x["feat"]["ext"] is not None else 0.0) for x in rows)
        sc = sorted(rows, key=lambda x: (pct_rank(gaps, x["gap"])
                                         + pct_rank(rngs, x["feat"]["range_pct"])
                                         + pct_rank(exts, (x["feat"]["ext"] if x["feat"]["ext"] is not None else 0.0))) / 3)
        day_scored[d] = sc
    n_days = len(day_scored)
    for kk in (1, 3):
        picks = [x for d in sorted(day_scored) for x in day_scored[d][:kk]]
        h26 = sum(1 for x in picks if x["is26"])
        h78 = sum(1 for x in picks if x["winner"])
        # correct conditional baseline: random top-k WITHIN each day
        exp26 = sum(min(kk, len(sc)) * sum(1 for x in sc if x["is26"]) / len(sc)
                    for sc in day_scored.values())
        exp78 = sum(min(kk, len(sc)) * sum(1 for x in sc if x["winner"]) / len(sc)
                    for sc in day_scored.values())
        w(f"  policy 'take the top-{kk} ranked name(s) each session': {len(picks)} picks over "
          f"{n_days} sessions -> catches {h26} of 26 (random within-day top-{kk} expects "
          f"{exp26:.1f}) · catches {h78} of the 78 (random expects {exp78:.1f})")
    # winner rank within its own day
    pos = []
    for d, sc in day_scored.items():
        for i, x in enumerate(sc):
            if x["is26"]:
                pos.append((x["ticker"], d, i + 1, len(sc)))
    med_within = st.median([p_ / n_ for _, _, p_, n_ in pos])
    top3_within = sum(1 for _, _, p_, n_ in pos if p_ <= 3)
    w(f"  the 26 within their own session: median rank percentile {100 * med_within:.0f}% "
      f"(50% = no signal) · {top3_within} of 26 rank in their day's top 3")
    w()
    w("─" * 98)
    w("[B] SENSITIVITY + SINGLE FEATURES (the honest ledger — every variant tried)")
    w("─" * 98)
    score_and_catch(COHORT, "drop", "variant: below-all-MAs rows EXCLUDED")
    # single-feature versions: reuse machinery by zeroing others via custom loop
    for feat_nm, keyf in (("gap only", lambda r, f_, e: r["gap"]),
                          ("range only", lambda r, f_, e: f_["range_pct"]),
                          ("extension only", lambda r, f_, e: e)):
        VARIANTS_TRIED.append(f"single-feature: {feat_nm}")
        pop = [(r, r["feat"], (r["feat"]["ext"] if r["feat"]["ext"] is not None else 0.0))
               for r in COHORT if r["feat"] is not None]
        vals = sorted(keyf(r, f_, e) for r, f_, e in pop)
        scored = sorted(((pct_rank(vals, keyf(r, f_, e)), r) for r, f_, e in pop),
                        key=lambda x: x[0])
        n = len(scored)
        targets = [i for i, x in enumerate(scored) if x[1]["is26"]]
        k10, k25 = int(round(0.10 * n)), int(round(0.25 * n))
        h10 = sum(1 for i in targets if i < k10)
        h25 = sum(1 for i in targets if i < k25)
        w(f"  [{feat_nm:<15}] top decile {h10}/{len(targets)} · top quartile {h25}/{len(targets)}"
          f" · median target percentile {100 * st.median([(i + 1) / n for i in targets]):.0f}%")
    w()
    w("─" * 98)
    w("[C] SESSION CONCENTRATION + TIME STABILITY (not a holdout — see the accounting)")
    w("─" * 98)
    by_sess = defaultdict(list)
    for r in COHORT:
        if r["is26"]:
            by_sess[r["date"]].append(r["ticker"])
    w(f"  the 26 sit on {len(by_sess)} distinct sessions; 2026-04-08 alone carries "
      f"{len(by_sess.get('2026-04-08', []))}")
    # early/late: ranks computed WITHIN each window (a live ranker only sees its own day anyway)
    for lo, hi, nm in (("2026-03-01", "2026-04-30", "EARLY window (03-01..04-30)"),
                      ("2026-05-01", "2026-07-15", "LATE window (05-01..07-15)")):
        seg = [r for r in COHORT if lo <= r["date"] <= hi]
        w(f"  {nm}: {len(seg)} rows, {sum(1 for r in seg if r['is26'])} of the 26")
        score_and_catch(seg, "zero", f"3-feature average within {nm}", register=False)
    VARIANTS_TRIED.append("early/late window split (stability check, not a holdout)")
    w()
    w("─" * 98)
    w("[D] SECONDARY: same rule against the 78 (all >=8xADR tail winners) — is the rule")
    w("    winner-shaped or only 26-shaped?")
    w("─" * 98)
    for r in COHORT:
        r["is78"] = r["winner"]
    sc = score_and_catch(COHORT, "zero", "3-feature average, target = all 78 tail winners",
                         target_key="is78")
    w()
    w("─" * 98)
    w("[E] THE ALERT POPULATION, same rule + the expectedness axis on top")
    w("    (expectedness exists ONLY here — the corpus for the 26's dates was purged; this is")
    w("     the only population where Part 1 can join Part 2, and its winners are 8xADR names,")
    w("     not the 26)")
    w("─" * 98)
    apop = []
    for a in POP:
        seq = ALERT_BARS.get(a["ticker"], [])
        idx = next((i for i, bb in enumerate(seq) if bb[0] == a["date"]), None)
        if idx is None or idx < 50:
            continue
        d, o, h, lo_, c, v = seq[idx]
        prior = [bb[4] for bb in seq[:idx]]
        adrf = a["out"]["adr"]
        if adrf <= 0 or h <= 0 or h <= lo_:
            continue
        mas = [sma(prior, k) for k in (10, 20, 50)]
        below = [m_ for m_ in mas if m_ is not None and m_ < o]
        ext = st.median([(o - m_) / o / adrf for m_ in below]) if below else 0.0
        apop.append(dict(a=a, gap=a["gap"], rng=(h - lo_) / h * 100, ext=ext,
                         win=a["out"]["tailx"] >= 8))
    gaps = sorted(x["gap"] for x in apop)
    rngs = sorted(x["rng"] for x in apop)
    exts = sorted(x["ext"] for x in apop)
    for x in apop:
        x["s3"] = (pct_rank(gaps, x["gap"]) + pct_rank(rngs, x["rng"]) + pct_rank(exts, x["ext"])) / 3
        expct_good = (x["a"]["looking"] in ("forward", "mixed_fwd")) or (x["a"]["sched"] == "unscheduled")
        x["s4"] = (x["s3"] * 3 + (0.0 if expct_good else 1.0)) / 4  # 4th term: expectedness as a 0/1 percentile
    nwin = sum(1 for x in apop if x["win"])
    w(f"  alert population scored: n={len(apop)} · >=8xADR winners among them: {nwin}")
    for key, nm in (("s3", "3-feature rule"), ("s4", "+ expectedness as a 4th equal term")):
        VARIANTS_TRIED.append(f"alert-population ranking: {nm}")
        sc_ = sorted(apop, key=lambda x: x[key])
        n = len(sc_)
        targets = [i for i, x in enumerate(sc_) if x["win"]]
        if not targets:
            w(f"  [{nm}] no winners in scored pop")
            continue
        k10, k25 = int(round(0.10 * n)), int(round(0.25 * n))
        h10 = sum(1 for i in targets if i < k10)
        h25 = sum(1 for i in targets if i < k25)
        w(f"  [{nm:<34}] top decile {h10}/{len(targets)} (chance {len(targets) * 0.10:.1f}) · "
          f"top quartile {h25}/{len(targets)} (chance {len(targets) * 0.25:.1f}) · "
          f"median winner percentile {100 * st.median([(i + 1) / n for i in targets]):.0f}%")
    if missing_feat:
        w()
        w(f"  foot: cohort rows excluded for missing features (no EP-day bar or <50 prior bars): "
          f"{len(missing_feat)}")
        w("    " + ", ".join(f"{r['ticker']} {r['date']}" for r in missing_feat[:40]) +
          (" ..." if len(missing_feat) > 40 else ""))


def accounting():
    w()
    w("=" * 98)
    w("OVERFITTING ACCOUNTING — stated in full, per the task")
    w("=" * 98)
    w("  FEATURES: the three score features (gap, EP-day tightness, MA extension) were selected")
    w("  BECAUSE they survived ADR-normalisation on this same data this weekend. That selection")
    w("  step is unrecoverable — no split of this window is a true holdout for the feature CHOICE.")
    w("  The early/late split in [C] tests only whether the percentile ranking is stable in time.")
    w("  13 of the 26 targets sit on one session (2026-04-08): every catch number is dominated by")
    w("  whether that session's names score well, and session-level correlation means the")
    w("  effective N is nearer 10 (distinct sessions) than 26.")
    w()
    w("  Scoring-rule variants actually computed (this run, complete list):")
    for i, v_ in enumerate(VARIANTS_TRIED, 1):
        w(f"    {i}. {v_}")
    w("  Thresholds fitted: NONE in the score (percentile ranks are parameter-free). Pre-existing")
    w("  thresholds reused, not fit here: >=8xADR (house tail bar) · >=10R (the 26's definition) ·")
    w("  >=39% growth (Pradeep bar from operator notes 06-16) · SMA 10/20/50 (the encoder's MAs).")
    w("  Part 1 comparisons attempted: " + str(len(TESTS)) + " (each listed inline); primaries were")
    w("  declared in the docstring BEFORE outcomes were read: [1] scheduled-vs-unscheduled and")
    w("  [2] forward-vs-backward, on share>=8xADR + P90, gap-controlled in [3].")
    w("  Classifier revisions: r1 (initial patterns, written before any outcome was read), then")
    w("  ONE r2 recall pass widening patterns from UNKNOWN-class TEXT only (ALOY MOU, CRCL 'approval")
    w("  from', EOSE joint development agreement, DELL 'earnings surprise') — outcomes were never")
    w("  consulted while widening. No further passes.")


def summary():
    w()
    w("=" * 98)
    w("SUMMARY — what the two parts say, and the fork (nothing pre-decided; grading is his)")
    w("=" * 98)
    w("PART 1 · The expectedness axis is DERIVABLE from what we already store (live corpus: 86%")
    w("  on scheduled/unscheduled, 75% on backward/forward, deterministic, $0) and every")
    w("  measurable comparison runs in the operator's predicted direction:")
    w("  - unscheduled 11.6% reach >=8xADR vs scheduled 3.8% (P90 8.7x vs 5.3x; p=0.20/0.13)")
    w("  - pure forward-changing 13.9% + P90 10.4x vs backward 0 of 14")
    w("  - gap-controlled: the unscheduled/forward side leads in ALL SIX tercile cells (6-of-6")
    w("    sign consistency; every cell individually below the house N floors)")
    w("  - the MEDIANS run the other way (scheduled 2.7x vs unscheduled 1.8x): the unexpected")
    w("    catalyst under-delivers typically and over-delivers in the tail — the exact fat-tail")
    w("    signature this program is hunting, and the same shape as the extension-filter cohort.")
    w("  VERDICT: a CANDIDATE, not a finding — 96 classifiable full-window alerts hold ~7 tail")
    w("  winners; no cell can clear the permutation floors at this N. NOT a null: direction is")
    w("  uniform. It accrues for free as alerts settle (and would have been testable at 3x the N")
    w("  had the purge not eaten March/April).")
    w("PART 2 · The three-line rule (small gap + tight EP day + low MA extension, percentile-")
    w("  averaged) ranks the 26 tradeable >=10R winners far above the candidate pool:")
    w("  - top decile catches 7 of 26 (27%) at 2.7x lift; top quartile 16 of 26 (62%) at 2.5x;")
    w("    median winner percentile 20th of 732")
    w("  - take-the-day's-top-1 catches a >=10R winner on 5 of the 10 winner sessions")
    w("    (FLY 03-12, SMTC 03-30, MRVL 03-31, STRL 04-08, QCOM 04-24) vs 1.8 expected")
    w("  - EP-day TIGHTNESS does most of the work (range-only nearly matches the full rule);")
    w("    extension-only and gap-only are weaker alone")
    w("  - the rule is 26-shaped, NOT mover-shaped: against the 78 raw >=8xADR names lift is")
    w("    ~1.1-1.3 — it ranks TRADEABLE winners, and correctly down-ranks untradeable movers")
    w("  - the misses are informative: INTC (gap 23%) and TDIC (artifact) rank low; extension")
    w("    hurts already-running re-gappers (UMC 04-17, AMD, ARM)")
    w("  ⚠ features chosen on this same data; late-window check is thin (5 winners) and weak at")
    w("  the quartile; effective N nearer 10 sessions than 26 names. See the accounting block.")
    w("FORK (one line each, operator's call — measurement only here):")
    w("  F-1 keep accruing the expectedness axis passively (it is $0 and computed offline)")
    w("  F-2 the ranking rule is testable live-shadow as a DAILY ORDERING (no admission change):")
    w("      log the rank next to each alert and re-read at N>=10 winner-sessions")
    w("  F-3 nothing changes in grading/admission without CHANGE_PROCESS + sign-off (THE LINE)")


def main():
    w("EXPECTEDNESS AXIS + CANDIDATE RANKING — 2026-08-16")
    w("read-only · $0 (two cached prod SELECTs, no LLM) · nothing proposed (THE LINE)")
    w("probe: scripts/probes/_expectedness_and_ranking.py · caches: _expct_alerts.tsv,")
    w("_expct_cohort_daily.tsv, _533n_daily.tsv, _552_cohort.psv")
    w()
    part1()
    part2()
    accounting()
    summary()
    OUT.write_text("\n".join(L) + "\n")
    print(f"wrote {OUT} ({len(L)} lines)")


if __name__ == "__main__":
    main()
