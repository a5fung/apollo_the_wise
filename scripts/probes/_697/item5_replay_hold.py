"""#697 item 5 (2026-10-11): replay the one-day hold on the STORED stage chain. READ-ONLY, no DB, no network.

Input : item5_q1_hold_rows.out  (ticker, scan_date, stage, held_from_stage, reason) for every ticker that read
        WATCH-or-better in the last 70 scan dates (60 reported + 10 warm-up). One prod SELECT, captured once.
Method: a stored row's RAW read is recoverable: `held_from_stage` when the row is a hold, else `stage`. The hysteresis
        step depends only on (raw read today, yesterday's stored stage, was yesterday a hold) — so the whole chain is
        re-threaded per ticker through the SHIPPED `flag_detector.stage_after_hold`, once with the old behaviour
        (yesterday_was_held always False) and once with the new one (the flag threaded from the re-threaded chain).
        "Yesterday" mirrors `db.get_yesterday_flag_stages`: the ticker's most recent prior row within 5 CALENDAR days.
        A full re-thread, not a first-order count: un-holding night 2 changes night 3's comparison base.
Not seen: a raw read that itself depends on stage history (TRIGGERED's "COILED in the last 5 days" - it reads STORED
        labels, so the per-night reading is NOT history-free for TRIGGERED) and the universe carry (items 1+2), which keys
        on stored stages. The TRIGGERED dependence is checked explicitly below for every real TRIGGERED read (does an
        UN-HELD COILED, i.e. a raw reading no re-threading can remove, sit in its 5-day window, and how close to the edge);
        a breakout that only the BARS would show cannot be replayed from stored rows. The carry shift is second order and
        is named in the SSoT, not modelled here.
Shadow: item5_q3_shadow_parents.out = every stored row of the five intraday shadow tables since 2026-07-01 with the parent
        row it was scanned from (one read-only prod SELECT). All five scans take their watchlist from the latest stored
        TIGHTENING/COILED/TRIGGERED rows, so a parent whose label falls to WATCH is a row that would not have been written.

Run from the repo root:  PYTHONPATH=. python scripts/probes/_697/item5_replay_hold.py > scripts/probes/_697/item5_replay_hold.out
"""
import collections
import os
from datetime import date

from agents.market_intelligence import flag_detector as fd

HERE = os.path.dirname(os.path.abspath(__file__))
REPORT_DAYS = 60
LOOKBACK = 5  # calendar days, db.get_yesterday_flag_stages / get_recent_flag_stages


def load():
    rows = collections.defaultdict(list)
    for ln in open(os.path.join(HERE, "item5_q1_hold_rows.out")):
        p = ln.rstrip("\n").split("\t")
        if len(p) < 6 or p[0] == "ticker":
            continue
        t, d, stage, held, reason, _ = p[:6]
        rows[t].append({"d": date.fromisoformat(d), "stage": stage, "held": held or None, "reason": reason})
    for t in rows:
        rows[t].sort(key=lambda r: r["d"])
    return rows


def raw_read(r):
    return r["held"] or r["stage"]


def thread(rows_t, new_rule):
    """Re-thread one ticker's chain; returns [(stage, held_from)] aligned to rows_t."""
    out = []
    for i, r in enumerate(rows_t):
        prev = None
        if i > 0 and (r["d"] - rows_t[i - 1]["d"]).days <= LOOKBACK:
            prev = out[i - 1]
        if prev is None:
            # first row of the pull / a gap beyond the 5-day window: no yesterday, nothing to hold against
            out.append((r["stage"], r["held"]))
            continue
        pst, pheld = prev
        raw = raw_read(r)
        if raw in ("unqualified", "INVALIDATED"):
            # these come from compute_flag_metrics' EARLY returns, which sit above the hysteresis: never held
            out.append((raw, None))
            continue
        out.append(fd.stage_after_hold(raw, pst, bool(pheld) if new_rule else False))
    return out


SHADOW_TABLES = ("break", "support_test", "undercut_rally", "ma_pullback", "low_vol_rest")
WATCHLIST = ("TIGHTENING", "COILED", "TRIGGERED")   # the stages every intraday scan reads as its watchlist


def load_shadow():
    out = []
    for ln in open(os.path.join(HERE, "item5_q3_shadow_parents.out")):
        p = ln.rstrip("\n").split("\t")
        if len(p) != 5 or p[0] not in SHADOW_TABLES:        # skips SET, the header and the "(N rows)" footer
            continue
        out.append({"tbl": p[0], "ticker": p[1], "d": p[2], "parent_date": date.fromisoformat(p[3]), "parent_stage": p[4]})
    return out


def new_chain(rows):
    """{ticker: (rows, re-threaded NEW-rule [(stage, held_from)])}"""
    return {t: (rs, thread(rs, True)) for t, rs in rows.items()}


def report_window(rows):
    all_dates = sorted({r["d"] for rs in rows.values() for r in rs})
    return set(all_dates[-REPORT_DAYS:])


def shadow_effect(chain, window, shadow):
    """chain = {ticker: {scan_date: (stored row, new (stage, held))}}. For every shadow row whose parent row is in the
    replay window: does the parent still sit on the watchlist under the new rule (unchanged / relabelled / lost)?
    A shadow row whose recorded parent_stage differs from the STORED stage of its parent row says nothing about the hold
    rule (the stored row is not a label the hysteresis produced - e.g. `unqualified` is never held; why the two differ is not
    established here): counted apart as `parent_differs`, in no other bucket."""
    count = {t: collections.Counter() for t in SHADOW_TABLES}
    relabelled, lost, differs = [], [], []
    stage_match = stage_total = 0
    for sh in shadow:
        pd_, t = sh["parent_date"], sh["ticker"]
        if pd_ not in window or t not in chain or pd_ not in chain[t]:
            continue
        r, (nst, _nhf) = chain[t][pd_]
        count[sh["tbl"]]["in_window"] += 1
        stage_total += 1
        stage_match += r["stage"] == sh["parent_stage"]
        row = dict(sh, new_stage=nst, stored_stage=r["stage"])
        if r["stage"] != sh["parent_stage"]:
            count[sh["tbl"]]["parent_differs"] += 1
            differs.append(row)
        elif nst not in WATCHLIST:
            count[sh["tbl"]]["lost"] += 1
            lost.append(row)
        elif nst != sh["parent_stage"]:
            count[sh["tbl"]]["relabelled"] += 1
            relabelled.append(row)
        else:
            count[sh["tbl"]]["unchanged"] += 1
    return {"count": count, "relabelled": relabelled, "lost": lost, "differs": differs,
            "stage_match": stage_match, "stage_total": stage_total}


def main():
    rows = load()
    all_dates = sorted({r["d"] for rs in rows.values() for r in rs})
    window = set(all_dates[-REPORT_DAYS:])
    print(f"tickers: {len(rows)}; scan dates in pull: {len(all_dates)} ({all_dates[0]} .. {all_dates[-1]}); reported window: last {REPORT_DAYS} ({sorted(window)[0]} .. {sorted(window)[-1]})")

    # ── validity: the OLD rule, re-threaded from raw reads, must reproduce what prod stored ──
    n = ok = 0
    bad = []
    for t, rs in rows.items():
        old = thread(rs, new_rule=False)
        for r, (st, hf) in zip(rs, old):
            if r["d"] not in window:
                continue
            n += 1
            if (st, hf) == (r["stage"], r["held"]):
                ok += 1
            else:
                bad.append((t, r["d"], r["stage"], r["held"], st, hf))
    print(f"\nVALIDITY  old rule re-threaded from raw reads reproduces the stored (stage, held_from_stage): {ok} of {n} rows")
    for b in bad[:10]:
        print("  mismatch", b)

    # ── per-night effect ──
    per_night = collections.defaultdict(lambda: collections.Counter())
    changed = []          # (ticker, date, old stage, new stage, raw)
    held_old = collections.Counter()
    held_new = collections.Counter()
    stage_old = collections.defaultdict(collections.Counter)
    stage_new = collections.defaultdict(collections.Counter)
    consec_old = consec_new = 0
    held_with_next = held_rearmed = 0
    pushes_old = collections.Counter()
    pushes_new = collections.Counter()
    push_rows_changed = []
    new_chain = {}
    for t, rs in rows.items():
        old = thread(rs, False)
        new = thread(rs, True)
        new_chain[t] = (rs, new)
        for i, r in enumerate(rs):
            d = r["d"]
            if d not in window:
                continue
            (ost, ohf), (nst, nhf) = old[i], new[i]
            stage_old[d][ost] += 1
            stage_new[d][nst] += 1
            if ohf:
                held_old[ost] += 1
                per_night[d]["held_old"] += 1
            if nhf:
                held_new[nst] += 1
                per_night[d]["held_new"] += 1
            if (ost, ohf) != (nst, nhf):
                changed.append((t, d, ost, nst, raw_read(r)))
                per_night[d]["rows_changed"] += 1
                if ohf and not nhf:
                    per_night[d]["unheld"] += 1
            # consecutive holds: a held row whose previous row (<=5d) was also held
            if i > 0 and (d - rs[i - 1]["d"]).days <= LOOKBACK:
                if ohf and old[i - 1][1]:
                    consec_old += 1
                if nhf and new[i - 1][1]:
                    consec_new += 1
                # re-arm rate: of the held rows that HAVE a next row (<=5d), how many were followed by another hold
            if i + 1 < len(rs) and (rs[i + 1]["d"] - d).days <= LOOKBACK and ohf:
                held_with_next += 1
                if old[i + 1][1]:
                    held_rearmed += 1
            # NEW TODAY pushes (approximation of stage_transitions: entered TIGHTENING/COILED, prev rank < new rank)
            if i > 0 and (d - rs[i - 1]["d"]).days <= LOOKBACK:
                for label, chain, tally in (("old", old, pushes_old), ("new", new, pushes_new)):
                    prev_st = chain[i - 1][0]
                    cur = chain[i][0]
                    if cur in fd._PUSH_STAGES and fd._PUSH_RANK.get(prev_st, 0) < fd._PUSH_RANK[cur]:
                        tally[d] += 1
            elif i == 0:
                pass

    tot_changed = len(changed)
    print(f"\nHOLDS in the window (stored/old): {sum(held_old.values())} rows -> by held stage {dict(held_old)}")
    print(f"HOLDS in the window (new rule)  : {sum(held_new.values())} rows -> by held stage {dict(held_new)}")
    print(f"rows whose stage/held label changes under the new rule: {tot_changed}")
    print(f"held rows whose previous row (<=5d) was ALSO a hold: old {consec_old} / new {consec_new}   (post-deploy invariant: new = 0)")
    print(f"re-arm rate (old): of {held_with_next} held rows that have a next-night row, {held_rearmed} were followed by another hold ({100*held_rearmed/max(held_with_next,1):.0f}%)")

    nights = sorted(window)
    print("\nPER NIGHT  date  held_old held_new unheld(rows that stop being a hold) rows_changed")
    for d in nights:
        c = per_night[d]
        print(f"  {d}  {c['held_old']:>3} {c['held_new']:>3}   {c['unheld']:>3}   {c['rows_changed']:>3}")
    ns = [per_night[d]["rows_changed"] for d in nights]
    nz = sum(1 for x in ns if x)
    print(f"nights with >=1 changed row: {nz} of {len(nights)}; median/night {sorted(ns)[len(ns)//2]}, max {max(ns)}")

    print("\nCHANGED ROWS  (ticker, date, stored stage -> new stage, raw read that night)")
    ch_by = collections.Counter()
    for t, d, o, nw, raw in sorted(changed, key=lambda x: (x[1], x[0])):
        print(f"  {t:6} {d}  {o:10} -> {nw:10}  raw {raw}")
        ch_by[(o, nw)] += 1
    print("changed rows by (stored -> new):", dict(ch_by))

    print("\nBOARD EFFECT  nights x stage counts, old -> new (only nights that differ)")
    for d in nights:
        diffs = []
        for s in ("TRIGGERED", "COILED", "TIGHTENING", "WATCH"):
            if stage_old[d][s] != stage_new[d][s]:
                diffs.append(f"{s} {stage_old[d][s]}->{stage_new[d][s]}")
        if diffs:
            print(f"  {d}  " + ", ".join(diffs))
    for s in ("TRIGGERED", "COILED", "TIGHTENING", "WATCH"):
        o = sum(stage_old[d][s] for d in nights)
        nw = sum(stage_new[d][s] for d in nights)
        print(f"  total {s:10} rows in window: {o} -> {nw}")

    po, pn = sum(pushes_old.values()), sum(pushes_new.values())
    print(f"\nNEW TODAY pushes (approx: entered TIGHTENING/COILED from a lower stage), window total: old {po} -> new {pn}")
    for d in nights:
        if pushes_old[d] != pushes_new[d]:
            print(f"  {d}  {pushes_old[d]} -> {pushes_new[d]}")

    # ── the real TRIGGERED reads: raw TRIGGERED (held NULL, stage TRIGGERED) ──
    print("\nREAL TRIGGERED READS (stored stage TRIGGERED, no hold) and the COILED that licensed them")
    real = 0
    unchanged = 0
    for t, (rs, new) in sorted(new_chain.items()):
        for i, r in enumerate(rs):
            if r["d"] not in window or r["stage"] != "TRIGGERED" or r["held"]:
                continue
            real += 1
            # recent_stages = stored stages of the ticker's rows in [d-5 days, d), the last _COILED_LOOKBACK_DAYS of them
            idx = [j for j in range(i) if 0 < (r["d"] - rs[j]["d"]).days <= LOOKBACK][-fd._COILED_LOOKBACK_DAYS:]
            old_coiled = [(rs[j]["d"].isoformat(), "held" if rs[j]["held"] else "raw") for j in idx if rs[j]["stage"] == "COILED"]
            new_coiled = [(rs[j]["d"].isoformat(), "held" if new[j][1] else "raw") for j in idx if new[j][0] == "COILED"]
            raw_coiled = [x for x in new_coiled if x[1] == "raw"]
            # margin: calendar days from the read back to the NEAREST un-held COILED (the licence expires at LOOKBACK days)
            margin = min(((r["d"] - date.fromisoformat(x[0])).days for x in raw_coiled), default=None)
            # row itself unchanged by the new rule (a raw TRIGGERED is never held)
            same_row = new[i] == (r["stage"], r["held"])
            ok = same_row and bool(raw_coiled)
            unchanged += ok
            print(f"  {t:6} {r['d']}  row unchanged: {same_row} | COILED in window, old {old_coiled} | new {new_coiled} | "
                  f"{'licensed by an UN-HELD COILED, cannot move' if raw_coiled else 'NO un-held COILED in window -> needs bars for coiled_today'}"
                  f"{'' if margin is None else f' | nearest un-held COILED {margin}d before (the licence lasts {LOOKBACK}d)'}")
    print(f"real TRIGGERED reads: {real}; unchanged and licensed by an un-held COILED: {unchanged}")

    # ── the five intraday scans' watchlist = latest TIGHTENING/COILED/TRIGGERED rows (flag_detector ~2462/2821/3077/3306/3673) ──
    print("\nSTORED INTRADAY SHADOW ROWS (item5_q3_shadow_parents.out): does the parent row still sit on the watchlist?")
    chain = {t: {r["d"]: (r, new[i]) for i, r in enumerate(rs)} for t, (rs, new) in new_chain.items()}
    eff = shadow_effect(chain, window, load_shadow())
    for tbl in SHADOW_TABLES:
        c = eff["count"][tbl]
        print(f"  {tbl:15} parent in window {c['in_window']:>3}: unchanged {c['unchanged']:>3}, relabelled {c['relabelled']:>2}, "
              f"LEAVES the watchlist {c['lost']:>2}, parent row differs from what the scan saw {c['parent_differs']:>2}")
    for row in eff["relabelled"]:
        print(f"  relabelled  {row['tbl']:15} {row['ticker']:6} {row['d']} parent {row['parent_date']} "
              f"stored {row['parent_stage']:10} -> new {row['new_stage']}")
    for row in eff["lost"]:
        print(f"  LOST        {row['tbl']:15} {row['ticker']:6} {row['d']} parent {row['parent_date']} "
              f"stored {row['parent_stage']:10} -> new {row['new_stage']} (this shadow row would not have been written)")
    for row in eff["differs"]:
        print(f"  NOT THE RULE {row['tbl']:15} {row['ticker']:6} {row['d']} parent {row['parent_date']}: the scan saw {row['parent_stage']}, "
              f"the stored row says {row['stored_stage']} (not a hold-rule effect; cause not established) - excluded from the counts")
    tot = sum(eff["count"][t]["lost"] for t in SHADOW_TABLES)
    print(f"shadow rows that would not have been written: {tot} of {sum(eff['count'][t]['in_window'] for t in SHADOW_TABLES)} "
          f"with a parent in the window ({eff['count']['break']['lost']} breaks + {tot - eff['count']['break']['lost']} in the other four tables)")
    print(f"join check: the shadow row's recorded parent_stage equals the stored stage of that parent row on "
          f"{eff['stage_match']} of {eff['stage_total']} rows (the rest are listed above and excluded)")

    # ── what `verify_hold_live.sql` should read, old vs new, over the same 60 scan dates ──
    def probe(chain_idx):
        after_hold = viol = fing = first = 0
        per_night_fing = collections.Counter()
        per_night_viol = collections.Counter()
        for t, (rs, new) in new_chain.items():
            ch = thread(rs, chain_idx)
            for i, r in enumerate(rs):
                if r["d"] not in window or i == 0 or (r["d"] - rs[i - 1]["d"]).days > LOOKBACK:
                    continue
                (st, hf), (pst, phf) = ch[i], ch[i - 1]
                if phf:
                    after_hold += 1
                    if hf:
                        viol += 1
                        per_night_viol[r["d"]] += 1
                    elif st in ("WATCH", "TIGHTENING", "COILED", "TRIGGERED") and fd._STAGE_ORDER.index(st) < fd._STAGE_ORDER.index(pst):
                        fing += 1
                        per_night_fing[r["d"]] += 1
                elif hf:
                    first += 1
        return after_hold, viol, fing, first, per_night_fing, per_night_viol

    print("\nEXPECTED verify_hold_live.sql over the same 60 scan dates (after_hold, violators, fingerprint, first_holds):")
    oa = probe(False)
    na = probe(True)
    print(f"  old rule (= prod, probe baseline 43/24/0/20): {oa[:4]}")
    print(f"  new rule                                    : {na[:4]}")
    # how long must the verify window be? share of k-session windows with zero rows of the signature
    for k in (1, 3, 5, 10, 20):
        w_n = [nights[i:i + k] for i in range(0, len(nights) - k + 1)]
        zero_f = sum(1 for ws in w_n if not any(na[4][d] for d in ws)) / len(w_n)
        zero_v = sum(1 for ws in w_n if not any(oa[5][d] for d in ws)) / len(w_n)
        print(f"  {k:>2}-session windows: {100*zero_f:3.0f}% have NO fingerprint row under the new rule (check inconclusive); "
              f"{100*zero_v:3.0f}% have NO violator under the old rule (the broken code would pass)")

    # ── the held-TRIGGERED rows the carry would re-print (WDAY-shape) ──
    print("\nHELD TRIGGERED rows (stored): these are the rows printed in the digest's TRIGGERED section with no fresh breakout")
    for t, (rs, new) in sorted(new_chain.items()):
        for i, r in enumerate(rs):
            if r["d"] in window and r["stage"] == "TRIGGERED" and r["held"]:
                print(f"  {t:6} {r['d']}  held from {r['held']}  -> new rule: {new[i][0]}{' (held from ' + new[i][1] + ')' if new[i][1] else ''}")


if __name__ == "__main__":
    main()
