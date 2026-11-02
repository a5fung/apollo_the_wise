#!/usr/bin/env python3
"""Big winners vs breakout v1, step 3 (2026-11-01): join the episodes (01) to the rebuilt winner nights (02), the replay's list /
coverage / trades tables, the QQQ phase and the SIC sector; assign each winner its v1 status (PLAN.md §2), the gate attribution
(§3), the features at the anchor night and at the catch (§4); write the winners database and the tables.

Writes  big_winners_2017_2024.tsv     one row per big winner (both factors; `factor` column)
        out/tables.md                 every generated table (RESULTS.md quotes from it)
        out/numbers.json              the headline numbers
        03_run.log
Descriptive only: medians and quartiles with n; no bar, no verdict. R = profit per share / risk per share (fill - stop)."""
import json, sys, time
from collections import Counter
import numpy as np, pandas as pd

HERE = "/Users/alvinfung/apollo_the_wise/scripts/probes/_breakout_v1_replay_1101/big_winners_1101"
REPLAY_OUT = "/Users/alvinfung/apollo_the_wise/scripts/probes/_breakout_v1_replay_1101/out"
SIC = "/Users/alvinfung/apollo_data/cb702/cb702_sic.psv"
LAST_NIGHT = "2024-12-30"
LOG, T = [], []


def log(s):
    print(s, flush=True); LOG.append(s)


def A(s=""):
    T.append(s)


SIC2_NAME = {"01": "agriculture", "02": "agriculture", "07": "agri services", "08": "forestry", "09": "fishing", "10": "metal mining", "12": "coal",
             "13": "oil & gas extraction", "14": "nonmetallic minerals", "15": "building construction", "16": "heavy construction", "17": "construction trades",
             "20": "food", "21": "tobacco", "22": "textiles", "23": "apparel", "24": "lumber", "25": "furniture", "26": "paper", "27": "printing",
             "28": "chemicals / pharma / biotech", "29": "petroleum refining", "30": "rubber & plastics", "31": "leather", "32": "stone / glass", "33": "primary metals",
             "34": "fabricated metal", "35": "machinery & computers", "36": "electronics & semis", "37": "transport equipment (autos, EV, aero)", "38": "instruments & medical devices",
             "39": "misc manufacturing", "40": "railroads", "41": "transit", "42": "trucking", "44": "water transport", "45": "air transport", "46": "pipelines", "47": "transport services",
             "48": "communications", "49": "utilities", "50": "wholesale durable", "51": "wholesale nondurable", "52": "retail building", "53": "general stores", "54": "food stores",
             "55": "auto dealers", "56": "apparel stores", "57": "home furnishing stores", "58": "restaurants", "59": "misc retail", "60": "banks", "61": "credit", "62": "brokers",
             "63": "insurance", "64": "insurance agents", "65": "real estate", "67": "holding / investment / SPAC", "70": "hotels", "72": "personal services",
             "73": "business services / software", "75": "auto repair", "78": "motion pictures", "79": "amusement / gaming", "80": "health services", "81": "legal",
             "82": "education", "83": "social services", "87": "engineering / R&D services", "89": "services nec", "99": "nonclassifiable"}


def q(x):
    x = pd.Series(x, dtype="float64").dropna()
    if len(x) == 0:
        return "—", 0
    return f"{x.median():.3g} ({x.quantile(.25):.3g} .. {x.quantile(.75):.3g})", len(x)


def qfmt(x, fmt="{:.3g}"):
    x = pd.Series(x, dtype="float64").dropna()
    if len(x) == 0:
        return "— (n = 0)"
    return f"{fmt.format(x.median())} ({fmt.format(x.quantile(.25))} .. {fmt.format(x.quantile(.75))}) n = {len(x)}"


def pct(a, b):
    return f"{a} ({100.0 * a / b:.0f}%)" if b else f"{a} (—)"


def main():
    t0 = time.time()
    eps = pd.read_csv(f"{HERE}/out/episodes_all.tsv.gz", sep="\t", dtype={"ticker": str}, keep_default_na=False, na_values=[""])
    nights = pd.read_csv(f"{HERE}/out/v1_nights.tsv.gz", sep="\t", dtype={"ticker": str, "failed": str, "first_failed": str, "pool": str}, keep_default_na=False, na_values=[""], low_memory=False)
    qqq = pd.read_csv(f"{HERE}/out/qqq_nights.tsv", sep="\t").set_index("scan_date")
    cov = pd.read_csv(f"{REPLAY_OUT}/list_coverage.tsv", sep="\t", dtype={"ticker": str})
    tr = pd.read_csv(f"{REPLAY_OUT}/trades.tsv.gz", sep="\t", dtype=str, keep_default_na=False)
    for c in ("r_2c", "realized_r", "r_0c", "sessions_held", "list_rank", "fill", "stop", "total_r"):
        tr[c] = pd.to_numeric(tr[c], errors="coerce")
    tr_by = {(t, d): r for t, d, r in zip(tr.ticker, tr.D, tr.to_dict("records"))}
    cov_by = {(t, d): (lp, f) for t, d, lp, f in zip(cov.ticker, cov.scan_date, cov.level_pass, cov.fired)}
    sic = {}
    for ln in open(SIC):
        f = ln.rstrip("\n").split("|")
        if len(f) >= 6 and f[3]:
            sic[f[0]] = (f[3][:2], f[4])
    log(f"episodes {len(eps)}, winner nights {len(nights)}, trades {len(tr)}, coverage {len(cov)}, sic {len(sic)}; {time.time() - t0:.0f}s")
    # calendars (from the nights table's own scan dates + the episode dates) — the window is by DATE
    nk = nights.set_index(["ticker", "scan_date"])
    nk = nk[~nk.index.duplicated(keep="first")]
    night_dates = sorted(set(nights.scan_date))
    # the SPY calendar of each store to walk the window dates: rebuild from the episode table's own indices is not possible here, so
    # take the window as every scan night in [trough_date, s50_date] that exists in the nights table for that ticker (02 evaluated them all)
    by_ticker = {t: g.sort_values("scan_date") for t, g in nights.groupby("ticker")}
    # ALSO the loose cross-check: listed anywhere in [t-20 sessions, p] — from the list file by date; approximate t-20 as 28 calendar days
    lst = pd.concat([pd.read_csv(f"{REPLAY_OUT}/list_era{e}.tsv.gz", sep="\t", dtype={"ticker": str}) for e in ("A", "B")], ignore_index=True)
    lst_by = {t: set(g.scan_date) for t, g in lst.groupby("ticker")}

    rows = []
    GATES = ["history", "universe", "rs", "prior_move", "higher_lows", "surf", "tightening", "breakdown"]
    FEAT = ["prior_move", "base_len", "tight_ratio", "surf_best", "rs_best", "r21", "r63", "r126", "adr20", "raw_close", "dv20",
            "E_volx50", "E_gap_pct", "E_range_adr", "E_close_loc", "E_fired", "pass_higher_lows", "pass_breakdown", "pass_surf", "pass_tightening", "pass_prior_move", "pass_rs"]
    for r in eps.itertuples():
        g = by_ticker.get(r.ticker)
        row = {"ticker": r.ticker, "factor": r.factor, "set": "+100%" if r.factor == 2.0 else "+50%", "store": r.store,
               "era": "2017-21" if r.trough_date <= "2021-12-31" else "2022-24", "trough_year": r.trough_date[:4],
               "trough_date": r.trough_date, "s25_date": r.s25_date, "s50_date": r.s50_date, "peak_date": r.peak_date, "sessions_t_to_p": r.sessions_t_to_p,
               "close_t": r.close_t, "close_p": r.close_p, "gain_pct": 100 * r.gain, "ret63_into_trough_pct": 100 * r.ret63_t if pd.notna(r.ret63_t) else np.nan,
               "ext_truncated": r.ext_truncated, "class": r.class_p, "breakout_date": r.b_date if isinstance(r.b_date, str) else "",
               "base_len_1022": r.L_p if r.L_p > 0 else np.nan, "base_depth_pct_1022": 100 * r.base_depth_pct if pd.notna(r.base_depth_pct) else np.nan,
               "base_span_adr20_1022": r.span_adr20, "base_contains_trough": r.base_contains_trough,
               "bo_vol_x_1022": r.bo_vol_x, "bo_gap_open_pct_1022": 100 * r.bo_gap_open_pct if pd.notna(r.bo_gap_open_pct) else np.nan, "bo_expansion_1022": r.bo_expansion,
               "gain_made_at_b_close": r.gain_made_at_b_close, "gap_start_date": r.gap_date if isinstance(r.gap_date, str) else "",
               "anchor_date": r.anchor_date, "sector_sic2": "", "sector": "unknown"}
        if r.ticker in sic:
            row["sector_sic2"] = sic[r.ticker][0]; row["sector"] = SIC2_NAME.get(sic[r.ticker][0], sic[r.ticker][1].lower()[:30])
        # the window nights
        if g is None:
            row.update(window_nights=0, listed=0); rows.append(row); continue
        w = g[(g.scan_date >= r.trough_date) & (g.scan_date <= r.s50_date) & (g.scan_date <= LAST_NIGHT)]
        w = w[w.night_in_replay == 1]
        row["window_nights"] = len(w)
        row["window_cut_by_seal"] = int(r.s50_date > LAST_NIGHT)
        listed = w[w.in_list == 1]
        row["listed"] = int(len(listed) > 0); row["n_listed_nights"] = len(listed)
        row["first_listed_date"] = listed.scan_date.iloc[0] if len(listed) else ""
        row["ever_listed_t20_to_p"] = int(any(r.trough_date <= d <= r.peak_date or (d < r.trough_date and (pd.Timestamp(r.trough_date) - pd.Timestamp(d)).days <= 28) for d in lst_by.get(r.ticker, ())))
        # fired (daily bars) on a listed night — my recompute and the replay's coverage flag
        fired_mine = listed[listed.E_fired == 1]
        row["fired"] = int(len(fired_mine) > 0); row["n_fired_nights"] = len(fired_mine)
        row["fired_replay"] = int(any(cov_by.get((r.ticker, d), (0, 0))[1] == 1 for d in listed.scan_date))
        # the minute walk
        fills = []
        for d in listed.scan_date:
            t = tr_by.get((r.ticker, d))
            if t is None:
                continue
            if t["outcome"] == "filled":
                fills.append(t)
        row["n_filled_nights"] = len(fills); row["filled"] = int(len(fills) > 0)
        outcomes = Counter(tr_by[(r.ticker, d)]["outcome"] for d in listed.scan_date if (r.ticker, d) in tr_by)
        row["listed_outcomes"] = ";".join(f"{k}:{v}" for k, v in sorted(outcomes.items()))
        if fills:
            c = fills[0]
            row.update(catch_D=c["D"], catch_E=c["E"], catch_list_rank=c["list_rank"], catch_fill=c["fill"], catch_stop=c["stop"],
                       catch_r_2c=c["r_2c"], catch_realized_r=c["realized_r"], catch_status=c["status"], catch_exit_date=c["exit_date"],
                       catch_sessions_held=c["sessions_held"], catch_slot=int(c["adm_cap"] == "True"), catch_why_no_slot=c["why_cap"], catch_decisive=int(c["decisive"] == "True"),
                       catch_still_in_at_s50=int(c["exit_date"] >= r.s50_date) if c["exit_date"] else 0,
                       catch_stop_pct=100 * (c["fill"] - c["stop"]) / c["fill"] if c["fill"] else np.nan,
                       sum_r_2c_all_fills=float(np.nansum([f["r_2c"] for f in fills])), best_r_2c=float(np.nanmax([f["r_2c"] for f in fills])),
                       any_fill_still_in_at_s50=int(any(f["exit_date"] >= r.s50_date for f in fills if f["exit_date"])),
                       any_fill_slot=int(any(f["adm_cap"] == "True" for f in fills)))
            if isinstance(r.b_date, str) and r.b_date:
                row["catch_E_minus_b_days"] = (pd.Timestamp(c["E"]) - pd.Timestamp(r.b_date)).days
            # the features at the catch's own night
            if (r.ticker, c["D"]) in nk.index:
                cr = nk.loc[(r.ticker, c["D"])]
                for fcol in FEAT:
                    row[f"catch_{fcol}"] = cr.get(fcol, np.nan)
                row["catch_qqq_above_50d"] = qqq.qqq_above_50d.get(c["D"], np.nan); row["catch_qqq_phase_10_20"] = qqq.qqq_phase_10_20.get(c["D"], np.nan)
        # status group
        if row["filled"]:
            row["group"] = "filled: made money" if row["catch_r_2c"] > 0 else "filled: lost"
        elif row["listed"]:
            row["group"] = "listed, fired, not filled" if row["fired"] else "listed, never fired"
        else:
            row["group"] = "never listed"
        # the anchor night: the gate vector + features
        a = nk.loc[(r.ticker, r.anchor_date)] if (r.ticker, r.anchor_date) in nk.index else None
        if a is not None and a.get("night_in_replay", 0) == 1:
            row["anchor_in_list"] = a.in_list; row["anchor_pool"] = a.pool
            if pd.notna(a.get("ok", np.nan)):
                row["anchor_ok"] = int(a.ok); row["anchor_failed"] = a.failed if isinstance(a.failed, str) else ""
                row["anchor_n_failed"] = a.n_failed; row["anchor_first_failed"] = a.first_failed if isinstance(a.first_failed, str) else ""
                for gname in GATES:
                    row[f"anchor_pass_{gname}"] = a.get(f"pass_{gname}", np.nan)
            else:
                row["anchor_first_failed"] = a.pool; row["anchor_failed"] = a.pool; row["anchor_n_failed"] = np.nan
            for fcol in FEAT:
                row[f"anchor_{fcol}"] = a.get(fcol, np.nan)
            row["anchor_qqq_above_50d"] = qqq.qqq_above_50d.get(r.anchor_date, np.nan); row["anchor_qqq_phase_10_20"] = qqq.qqq_phase_10_20.get(r.anchor_date, np.nan)
        else:
            row["anchor_first_failed"] = "anchor night outside the replay"
        # the nearest miss over the window (rows with a gate vector)
        wv = w[w.ok.notna()] if "ok" in w else w.iloc[0:0]
        if len(wv):
            mn = wv.n_failed.min()
            best = wv[wv.n_failed == mn].iloc[-1]                      # ties -> the latest night
            row.update(nearest_miss_n_failed=int(mn), nearest_miss_date=best.scan_date,
                       nearest_miss_gates=best.failed if isinstance(best.failed, str) else "",
                       nearest_miss_gate=(best.failed if mn == 1 else ("none" if mn == 0 else f"{int(mn)} gates")))
            # per-gate: the share of window nights each gate failed
            for gname in GATES:
                col = wv[f"pass_{gname}"]
                col = pd.to_numeric(col, errors="coerce")
                row[f"win_fail_share_{gname}"] = float((col == 0).mean()) if col.notna().any() else np.nan
        rows.append(row)
    db = pd.DataFrame(rows)
    cols_first = ["ticker", "set", "era", "trough_year", "trough_date", "breakout_date", "s50_date", "peak_date", "gain_pct", "sessions_t_to_p", "class", "group",
                  "listed", "fired", "filled", "catch_D", "catch_r_2c", "catch_realized_r", "catch_status", "catch_slot", "anchor_first_failed", "nearest_miss_gate", "sector"]
    db = db[cols_first + [c for c in db.columns if c not in cols_first]]
    db.sort_values(["set", "trough_date", "ticker"]).to_csv(f"{HERE}/big_winners_2017_2024.tsv", sep="\t", index=False, float_format="%.5g")
    log(f"wrote big_winners_2017_2024.tsv: {len(db)} rows, {len(db.columns)} columns")

    # ═══════════════ tables ═══════════════
    N = {}
    for sset in ("+100%", "+50%"):
        d = db[db.set == sset]
        A(f"## The {sset} set" + (" (a close that at least doubled from its low within 63 sessions) — HEADLINE" if sset == "+100%" else " (at least +50%) — beside"))
        A()
        A("### Composition")
        A()
        A("| item | 2017–21 | 2022–24 | all |")
        A("|---|---|---|---|")
        for era in ("2017-21", "2022-24"):
            pass
        def tri(fn):
            return " | ".join(fn(d[d.era == e]) for e in ("2017-21", "2022-24")) + " | " + fn(d)
        A(f"| big winners (episodes) | {tri(lambda x: f'n = {len(x)}')} |")
        A(f"| by trough year | {tri(lambda x: ', '.join(f'{k}: {v}' for k, v in sorted(x.trough_year.value_counts().items())))} |")
        A(f"| gain low → peak, % (median, quartiles) | {tri(lambda x: qfmt(x.gain_pct, '{:.0f}'))} |")
        A(f"| sessions low → peak | {tri(lambda x: qfmt(x.sessions_t_to_p, '{:.0f}'))} |")
        A(f"| 63-session return INTO the low, % | {tri(lambda x: qfmt(x.ret63_into_trough_pct, '{:.0f}'))} |")
        A(f"| close at the low, $ | {tri(lambda x: qfmt(x.close_t, '{:.1f}'))} |")
        A(f"| breakout class (10-22 rule) | {tri(lambda x: ', '.join(f'{k}: {v}' for k, v in x['class'].value_counts().items()))} |")
        A(f"| peak extension cut by a store's end (gain under-measured) | {tri(lambda x: f'n = {int(x.ext_truncated.sum())}')} |")
        A(f"| window (low → half-way) cut by the 2024-12-30 last night | {tri(lambda x: f'n = {int(x.window_cut_by_seal.sum())}')} |")
        A()
        A("### Did breakout v1 see it — the funnel (nights D from the low t to the half-way point s50; E = D + 1)")
        A()
        A("| step | 2017–21 | 2022–24 | all |")
        A("|---|---|---|---|")
        def funnel(x):
            n = len(x)
            out = [f"n = {n}"]
            return out
        steps = [("big winners", lambda x: len(x)),
                 ("LISTED on some night in the window (passed every v1 gate; 'fits the criteria')", lambda x: int(x.listed.sum())),
                 ("… FIRED: the next day cleared the level on ≥ 1.2× volume (daily bars)", lambda x: int(x.fired.sum())),
                 ("… FILLED: the minute walk bought it (the replay's trades table)", lambda x: int(x.filled.sum())),
                 ("… the catch took one of the 5 slots in the PRIMARY capped book", lambda x: int((x.catch_slot == 1).sum())),
                 ("… some fill (not only the first) took a slot", lambda x: int((x.any_fill_slot == 1).sum())),
                 ("… the catch was refused a slot because the 5 slots were full", lambda x: int((x.catch_why_no_slot == "block:max_positions").sum())),
                 ("… the catch MADE MONEY (R at 2c > 0)", lambda x: int((x.catch_r_2c > 0).sum())),
                 ("… the catch made ≥ 3R", lambda x: int((x.catch_r_2c >= 3).sum())),
                 ("… the catch made ≥ 10R", lambda x: int((x.catch_r_2c >= 10).sum())),
                 ("… the catch was still in the trade at the half-way point", lambda x: int((x.catch_still_in_at_s50 == 1).sum())),
                 ("… SOME fill (not only the first) still in at the half-way point", lambda x: int((x.any_fill_still_in_at_s50 == 1).sum())),
                 ("listed ANYWHERE in [low − 20 sessions, peak] (loose cross-check)", lambda x: int(x.ever_listed_t20_to_p.sum()))]
        for name, fn in steps:
            A(f"| {name} | " + " | ".join(pct(fn(d[d.era == e]), len(d[d.era == e])) for e in ("2017-21", "2022-24")) + f" | {pct(fn(d), len(d))} |")
        A()
        A(f"Fired by my daily-bar recompute vs the replay's coverage flag on the same listed nights: {int(d.fired.sum())} vs {int(d.fired_replay.sum())} winners "
          f"(disagreements {int((d.fired != d.fired_replay).sum())}). Listed nights per listed winner: {qfmt(d[d.listed == 1].n_listed_nights, '{:.0f}')}; "
          f"filled nights per filled winner: {qfmt(d[d.filled == 1].n_filled_nights, '{:.0f}')}. "
          f"Sum of R over EVERY fill of a filled winner: {qfmt(d[d.filled == 1].sum_r_2c_all_fills, '{:+.2f}')}; best fill's R: {qfmt(d[d.filled == 1].best_r_2c, '{:+.2f}')}.")
        A()
        A("Status groups (one per winner): " + ", ".join(f"{k}: n = {v}" for k, v in d.group.value_counts().items()) + ". "
          f"Filled on a night whose daily bar did NOT clear level + 1.2× volume (the minute walk's own pace rule bought it): {int(((d.filled == 1) & (d.fired == 0)).sum())} winners; "
          f"fired on daily bars but the minute walk never bought: {int(((d.fired == 1) & (d.filled == 0)).sum())}. "
          f"Of the catches that made ≥ 3R, took a slot in the primary 5-slot book: {int(((d.catch_r_2c >= 3) & (d.catch_slot == 1)).sum())} of {int((d.catch_r_2c >= 3).sum())}; "
          f"of those that made money: {int(((d.catch_r_2c > 0) & (d.catch_slot == 1)).sum())} of {int((d.catch_r_2c > 0).sum())}.")
        A()
        # catch detail
        f = d[d.filled == 1]
        A("### The catches (the FIRST filled night of each filled winner)")
        A()
        A("| item | 2017–21 | 2022–24 | all |")
        A("|---|---|---|---|")
        A(f"| R at 2c (median, quartiles) | {tri(lambda x: qfmt(x[x.filled == 1].catch_r_2c, '{:+.2f}'))} |")
        A(f"| mean R at 2c | {tri(lambda x: f'{x[x.filled == 1].catch_r_2c.mean():+.2f} (n = {int(x.filled.sum())})')} |")
        A(f"| R at 0c (median) | {tri(lambda x: qfmt(x[x.filled == 1].catch_realized_r, '{:+.2f}'))} |")
        A(f"| exit status | {tri(lambda x: ', '.join(f'{k}: {v}' for k, v in x[x.filled == 1].catch_status.value_counts().items()))} |")
        A(f"| sessions held | {tri(lambda x: qfmt(x[x.filled == 1].catch_sessions_held, '{:.0f}'))} |")
        A(f"| the stop below the fill, % of price | {tri(lambda x: qfmt(x[x.filled == 1].catch_stop_pct, '{:.1f}'))} |")
        A(f"| breakout day E minus the 10-22 breakout day b, calendar days (negative = bought before it) | {tri(lambda x: qfmt(x[x.filled == 1].catch_E_minus_b_days, '{:+.0f}'))} |")
        A(f"| list rank that night | {tri(lambda x: qfmt(x[x.filled == 1].catch_list_rank, '{:.0f}'))} |")
        A(f"| took a slot in the primary book | {tri(lambda x: pct(int((x.catch_slot == 1).sum()), int(x.filled.sum())))} |")
        A()
        # gate attribution for the never listed
        nl = d[d.listed == 0]
        A(f"### Never listed in the window (n = {len(nl)}): which gate kept it out")
        A()
        A("Anchor night = the night before the 10-22 breakout day (b − 1); the gap day − 1 for a gap start; s25 − 1 otherwise. Anchor kinds: "
          + ", ".join(f"{k}: {v}" for k, v in nl['class'].value_counts().items()) + ".")
        A()
        A("**(ii) The share of never-listed winners each gate FAILED on the anchor night (every gate evaluated; a winner can fail several) — the table quoted**")
        A()
        A("| gate | 2017–21 | 2022–24 | all |")
        A("|---|---|---|---|")
        for gname in GATES:
            def fs(x, gname=gname):
                col = pd.to_numeric(x.get(f"anchor_pass_{gname}"), errors="coerce")
                return pct(int((col == 0).sum()), int(col.notna().sum()))
            A(f"| {gname} | " + " | ".join(fs(nl[nl.era == e]) for e in ("2017-21", "2022-24")) + f" | {fs(nl)} |")
        def fs2(x):
            col = pd.to_numeric(x.get("anchor_n_failed"), errors="coerce")
            return f"{qfmt(col, '{:.0f}')}"
        A(f"| gates failed per winner (median, quartiles) | " + " | ".join(fs2(nl[nl.era == e]) for e in ("2017-21", "2022-24")) + f" | {fs2(nl)} |")
        def only_rs(x):
            return pct(int((x.anchor_failed == "rs").sum()), len(x))
        A(f"| fails ONLY the rs gate at the anchor (every structure gate passes) | " + " | ".join(only_rs(nl[nl.era == e]) for e in ("2017-21", "2022-24")) + f" | {only_rs(nl)} |")
        for lo in (90, 95, 97):
            def band(x, lo=lo):
                v = pd.to_numeric(x.anchor_rs_best, errors="coerce")
                return pct(int((v >= lo).sum()), int(v.notna().sum()))
            A(f"| RS percentile at the anchor ≥ {lo} (of those in the RS pool) | " + " | ".join(band(nl[nl.era == e]) for e in ("2017-21", "2022-24")) + f" | {band(nl)} |")
        A(f"| no gate vector (not in the store / no bar / anchor outside the replay) | " + " | ".join(pct(int(pd.to_numeric(x.anchor_n_failed, errors='coerce').isna().sum()), len(x)) for x in (nl[nl.era == '2017-21'], nl[nl.era == '2022-24'])) + f" | {pct(int(pd.to_numeric(nl.anchor_n_failed, errors='coerce').isna().sum()), len(nl))} |")
        A()
        A("**(i) The FIRST failing gate in v1's order on the anchor night (order-dependent: rs is tested before the structure gates)**")
        A()
        A("| first failing gate | 2017–21 | 2022–24 | all |")
        A("|---|---|---|---|")
        nl = nl.copy(); nl["anchor_first_failed"] = nl.anchor_first_failed.fillna("passed every gate (listed on the anchor night, which falls AFTER the half-way point)")
        for gname, _ in nl.anchor_first_failed.value_counts().items():
            A(f"| {gname} | " + " | ".join(pct(int((nl[nl.era == e].anchor_first_failed == gname).sum()), len(nl[nl.era == e])) for e in ("2017-21", "2022-24")) + f" | {pct(int((nl.anchor_first_failed == gname).sum()), len(nl))} |")
        A()
        A("**(iii) The NEAREST MISS over the whole window (the night with the fewest failing gates; ties → the latest night)**")
        A()
        A("| nearest-miss gate(s) | 2017–21 | 2022–24 | all |")
        A("|---|---|---|---|")
        nm = nl.nearest_miss_gate.fillna("no gate vector")
        for gname, _ in nm.value_counts().head(14).items():
            A(f"| {gname} | " + " | ".join(pct(int((nm[nl.era == e] == gname).sum()), len(nl[nl.era == e])) for e in ("2017-21", "2022-24")) + f" | {pct(int((nm == gname).sum()), len(nl))} |")
        two = nl[nl.nearest_miss_n_failed == 2].nearest_miss_gates.value_counts().head(8)
        A()
        A("The two-gate nearest misses, which pairs: " + ", ".join(f"{k}: {v}" for k, v in two.items()) + ".")
        A()
        A("**Which gate failed on what share of the window's nights (never-listed winners; median share per winner)**")
        A()
        A("| gate | 2017–21 | 2022–24 | all |")
        A("|---|---|---|---|")
        for gname in GATES:
            A(f"| {gname} | " + " | ".join(qfmt(nl[nl.era == e][f"win_fail_share_{gname}"], "{:.2f}") for e in ("2017-21", "2022-24")) + f" | {qfmt(nl[f'win_fail_share_{gname}'], '{:.2f}')} |")
        A()
        # listed-but-not-filled attribution
        lnf = d[(d.listed == 1) & (d.filled == 0)]
        A(f"### Listed but never filled (n = {len(lnf)}): what the listed nights did")
        A()
        oc = Counter()
        for s in lnf.listed_outcomes:
            for kv in str(s).split(";"):
                if ":" in kv:
                    k, v = kv.split(":"); oc[k] += int(v)
        A("Outcomes over their listed nights (the replay's minute walk): " + ", ".join(f"{k}: {v}" for k, v in oc.most_common()) + ". "
          f"Of them, fired on daily bars on some night: {int(lnf.fired.sum())}; never fired: {int((lnf.fired == 0).sum())}.")
        A()
        # features
        groups = ["never listed", "listed, never fired", "listed, fired, not filled", "filled: lost", "filled: made money"]
        feats = [("prior move at the anchor: pole high / pole low − 1 (v1's pole)", "anchor_prior_move", "{:.2f}"),
                 ("v1 base length at the anchor: sessions since the pole top", "anchor_base_len", "{:.0f}"),
                 ("10-22 base length L (sessions)", "base_len_1022", "{:.0f}"),
                 ("10-22 base depth, % (high to low of the base)", "base_depth_pct_1022", "{:.0f}"),
                 ("10-22 base span in ADR20 units", "base_span_adr20_1022", "{:.1f}"),
                 ("tightening ratio: last-5 range / prior-5 range (v1 passes ≤ 1.1)", "anchor_tight_ratio", "{:.2f}"),
                 ("surf: sessions in a row riding a 10/20/50-day line (v1 passes ≥ 5)", "anchor_surf_best", "{:.0f}"),
                 ("RS percentile, best of 1/3/6 months (v1 passes ≥ 98)", "anchor_rs_best", "{:.0f}"),
                 ("1-month return, %", "anchor_r21", "{:.0f}"), ("3-month return, %", "anchor_r63", "{:.0f}"), ("6-month return, %", "anchor_r126", "{:.0f}"),
                 ("63-session return INTO the low, %", "ret63_into_trough_pct", "{:.0f}"),
                 ("ADR20 at the anchor, fraction of price", "anchor_adr20", "{:.3f}"),
                 ("RAW close at the anchor, $", "anchor_raw_close", "{:.1f}"),
                 ("20-session median dollar volume, $M", "anchor_dv20_m", "{:.0f}"),
                 ("volume on the next day over its 50-day mean", "anchor_E_volx50", "{:.2f}"),
                 ("gap at the next open, %", "anchor_E_gap_pct", "{:.1f}"),
                 ("next day's range in ADR20 units", "anchor_E_range_adr", "{:.2f}"),
                 ("next day's close location in its range (0 = low, 1 = high)", "anchor_E_close_loc", "{:.2f}"),
                 ("10-22 breakout day: volume over the 50-day", "bo_vol_x_1022", "{:.2f}"),
                 ("10-22 breakout day: gap at the open, %", "bo_gap_open_pct_1022", "{:.1f}"),
                 ("gain low → peak, %", "gain_pct", "{:.0f}"), ("sessions low → peak", "sessions_t_to_p", "{:.0f}")]
        d = d.copy(); d["anchor_dv20_m"] = d.anchor_dv20 / 1e6
        for c in ("anchor_r21", "anchor_r63", "anchor_r126", "anchor_E_gap_pct", "catch_E_gap_pct"):
            d[c] = 100 * d[c]
        A("### Features at the ANCHOR night, by status group — median (Q1 .. Q3), n (descriptive; no bar)")
        A()
        A("| feature | " + " | ".join(groups) + " |")
        A("|---|" + "---|" * len(groups))
        for label, col, fmt in feats:
            A(f"| {label} | " + " | ".join(qfmt(d[d.group == gname][col], fmt) if col in d else "—" for gname in groups) + " |")
        for label, col in (("v1 higher-lows gate passes", "anchor_pass_higher_lows"), ("v1 breakdown gate passes", "anchor_pass_breakdown"),
                           ("v1 surf gate passes", "anchor_pass_surf"), ("v1 tightening gate passes", "anchor_pass_tightening"),
                           ("v1 prior-move gate passes", "anchor_pass_prior_move"), ("v1 RS gate passes", "anchor_pass_rs"),
                           ("next day fired (level + volume)", "anchor_E_fired"), ("10-22 expansion day (range ≥ 1 ADR, close top 30%, vol ≥ 1.5×)", "bo_expansion_1022"),
                           ("QQQ above its 50-day at the anchor", "anchor_qqq_above_50d"), ("QQQ 10/20 phase on at the anchor", "anchor_qqq_phase_10_20"),
                           ("the 10-22 base contains the low", "base_contains_trough")):
            def sh(x, col=col):
                v = pd.to_numeric(x[col], errors="coerce").dropna()
                return f"{100 * v.mean():.0f}% (n = {len(v)})" if len(v) else "—"
            A(f"| {label} (share yes) | " + " | ".join(sh(d[d.group == gname]) for gname in groups) + " |")
        A()
        A("### Features at the CATCH's own night (filled winners only): made money vs lost — median (Q1 .. Q3), n")
        A()
        cg = ["filled: lost", "filled: made money"]
        A("| feature | " + " | ".join(cg) + " | ≥ 3R (subset of made money) |")
        A("|---|---|---|---|")
        d["catch_dv20_m"] = d.catch_dv20 / 1e6
        for c in ("catch_r21", "catch_r63", "catch_r126"):
            d[c] = 100 * d[c]
        cfeats = [(lab.replace("anchor", "catch night"), col.replace("anchor_", "catch_"), fmt) for lab, col, fmt in feats if col.startswith("anchor_")]
        cfeats += [("10-22 base length L (sessions)", "base_len_1022", "{:.0f}"), ("10-22 base depth, %", "base_depth_pct_1022", "{:.0f}"),
                   ("63-session return INTO the low, %", "ret63_into_trough_pct", "{:.0f}"), ("the stop below the fill, % of price", "catch_stop_pct", "{:.1f}"),
                   ("list rank that night (1 = strongest RS)", "catch_list_rank", "{:.0f}"), ("breakout day minus the 10-22 breakout day, calendar days", "catch_E_minus_b_days", "{:+.0f}"),
                   ("gain low → peak, %", "gain_pct", "{:.0f}"), ("sessions low → peak", "sessions_t_to_p", "{:.0f}")]
        big = d[(d.filled == 1) & (d.catch_r_2c >= 3)]
        for label, col, fmt in cfeats:
            A(f"| {label} | " + " | ".join(qfmt(d[d.group == gname][col], fmt) if col in d else "—" for gname in cg) + f" | {qfmt(big[col], fmt) if col in d else '—'} |")
        for label, col in (("QQQ above its 50-day", "catch_qqq_above_50d"), ("QQQ 10/20 phase on", "catch_qqq_phase_10_20"), ("took a slot in the primary book", "catch_slot")):
            def sh2(x, col=col):
                v = pd.to_numeric(x[col], errors="coerce").dropna()
                return f"{100 * v.mean():.0f}% (n = {len(v)})" if len(v) else "—"
            A(f"| {label} (share yes) | " + " | ".join(sh2(d[d.group == gname]) for gname in cg) + f" | {sh2(big)} |")
        A()
        A("### Sector (2-digit SIC, a 2026 point-in-time classification; 'unknown' = not in the file) — share of each group, top groups")
        A()
        top = d.sector.value_counts().head(12).index.tolist()
        A("| sector | all winners | never listed | listed (fits) | filled: lost | filled: made money |")
        A("|---|---|---|---|---|---|")
        for s in top:
            cells = []
            for sub in (d, d[d.group == "never listed"], d[d.listed == 1], d[d.group == "filled: lost"], d[d.group == "filled: made money"]):
                cells.append(pct(int((sub.sector == s).sum()), len(sub)))
            A(f"| {s} | " + " | ".join(cells) + " |")
        A()
        A("### Market phase at the anchor night")
        A()
        A("| phase | all winners | never listed | listed (fits) | filled: lost | filled: made money |")
        A("|---|---|---|---|---|---|")
        for label, col in (("QQQ above its 50-day", "anchor_qqq_above_50d"), ("QQQ 10/20 phase on (the replay's slice)", "anchor_qqq_phase_10_20")):
            cells = []
            for sub in (d, d[d.group == "never listed"], d[d.listed == 1], d[d.group == "filled: lost"], d[d.group == "filled: made money"]):
                v = pd.to_numeric(sub[col], errors="coerce").dropna()
                cells.append(f"{100 * v.mean():.0f}% (n = {len(v)})" if len(v) else "—")
            A(f"| {label} | " + " | ".join(cells) + " |")
        A()
        A("### By trough year — listed / filled / made money")
        A()
        A("| year | winners | listed | filled | made money | ≥ 3R | still in at half-way |")
        A("|---|---|---|---|---|---|---|")
        for y, g in d.groupby("trough_year"):
            A(f"| {y} | {len(g)} | {pct(int(g.listed.sum()), len(g))} | {pct(int(g.filled.sum()), len(g))} | {pct(int((g.catch_r_2c > 0).sum()), len(g))} | {int((g.catch_r_2c >= 3).sum())} | {int((g.catch_still_in_at_s50 == 1).sum())} |")
        A()
        A("### By breakout class — listed / filled / made money")
        A()
        A("| class | winners | listed | filled | made money | ≥ 3R |")
        A("|---|---|---|---|---|---|")
        for y, g in d.groupby("class"):
            A(f"| {y} | {len(g)} | {pct(int(g.listed.sum()), len(g))} | {pct(int(g.filled.sum()), len(g))} | {pct(int((g.catch_r_2c > 0).sum()), len(g))} | {int((g.catch_r_2c >= 3).sum())} |")
        A()
        # the biggest of the big: top 30 by gain, with status
        A(f"### The 30 biggest moves of the {sset} set and what v1 did")
        A()
        A("| ticker | low | breakout (10-22) | peak | gain % | class | v1 status | catch R (2c) | first failing gate at the anchor | nearest miss | sector |")
        A("|---|---|---|---|---|---|---|---|---|---|---|")
        for r in d.sort_values("gain_pct", ascending=False).head(30).to_dict("records"):
            A(f"| {r['ticker']} | {r['trough_date']} | {r['breakout_date'] or '—'} | {r['peak_date']} | {r['gain_pct']:.0f} | {r['class']} | {r['group']} | "
              f"{'' if pd.isna(r['catch_r_2c']) else f'{r['catch_r_2c']:+.2f}'} | {r['anchor_first_failed'] or '—'} | {r['nearest_miss_gate'] if isinstance(r['nearest_miss_gate'], str) else '—'} | {r['sector']} |")
        A()
        N[sset] = {"n": len(d), "listed": int(d.listed.sum()), "fired": int(d.fired.sum()), "filled": int(d.filled.sum()),
                   "slot": int((d.catch_slot == 1).sum()), "made_money": int((d.catch_r_2c > 0).sum()), "ge3R": int((d.catch_r_2c >= 3).sum()),
                   "ge10R": int((d.catch_r_2c >= 10).sum()), "still_in_s50": int((d.catch_still_in_at_s50 == 1).sum()),
                   "any_fill_still_in_s50": int((d.any_fill_still_in_at_s50 == 1).sum()),
                   "catch_r_2c_mean": float(d[d.filled == 1].catch_r_2c.mean()), "catch_r_2c_median": float(d[d.filled == 1].catch_r_2c.median()),
                   "never_listed": int((d.listed == 0).sum()), "by_era": {e: {"n": len(d[d.era == e]), "listed": int(d[d.era == e].listed.sum()), "filled": int(d[d.era == e].filled.sum()),
                                                                           "made_money": int((d[d.era == e].catch_r_2c > 0).sum())} for e in ("2017-21", "2022-24")},
                   "anchor_fail_share": {g: float((pd.to_numeric(nl[f"anchor_pass_{g}"], errors="coerce") == 0).mean()) for g in GATES},
                   "first_failed": nl.anchor_first_failed.value_counts().to_dict(), "nearest_miss": nm.value_counts().head(10).to_dict(),
                   "groups": d.group.value_counts().to_dict()}
    open(f"{HERE}/out/tables.md", "w").write("\n".join(T) + "\n")
    json.dump(N, open(f"{HERE}/out/numbers.json", "w"), indent=1)
    log(json.dumps(N, indent=1))
    log(f"done in {time.time() - t0:.0f}s")
    open(f"{HERE}/03_run.log", "w").write("\n".join(LOG) + "\n")


if __name__ == "__main__":
    main()
