"""Stage 1d (part 1): era-B list rebuild at the pinned sha, same bridge-set rule as 1b (set(failed) <= CONTEXT_GATES), nights D 2022-04-01 ..
the last D whose E+60 is a session inside the sealed file (<= 2024-12-31). Sealed copy only. Output captured once."""
import json, random, time
from lib import *
OUTP = OUT_DATA / "bws1124_eraB_list_ctx.parquet"


def trunc_check(S, n_nights=3, per=150):
    """No-forward-read proof: v1_gates on bars cut at D equals v1_gates on the full bars (failed set, level, prior_move)."""
    D = S.D; facts = G["facts"]
    cal = D.cal
    ns = [i for i, d in enumerate(cal) if d >= date(2022, 7, 1)][100:100 + n_nights * 40:40][:n_nights]
    rows = work((ns, True))
    df = pd.DataFrame(rows, columns=ALL_COLS)
    rng = random.Random(1124)
    sample = df.sample(min(per * n_nights, len(df)), random_state=1124)
    bad = 0
    for r in sample.itertuples():
        k = D.tid[r.ticker]; bars, cidx = runner.bars_for(D, k)
        Di = r.bars_to_d - 1
        tb = cb.daily_bars_from_arrays(bars.dates[:Di + 1], bars.o[:Di + 1], bars.h[:Di + 1], bars.l[:Di + 1], bars.c[:Di + 1], bars.v[:Di + 1])
        g = bv.v1_gates(tb, Di, rs_best=r.rs_best, raw_close=r.raw_close, cidx=cidx[:Di + 1])
        if ",".join(g["failed"]) != r.failed or not np.isclose(g["level"], r.level, rtol=1e-12) or not np.isclose(g["prior_move"], r.prior_move, rtol=1e-12):
            bad += 1
    print(f"truncation check: {len(sample)} name-nights, {bad} differ between full bars and bars cut at D", flush=True)
    assert bad == 0
    return len(sample)


def main():
    t = time.time()
    S = setup_store("B"); D = S.D; cal = D.cal
    assert cal[-1] <= date(2024, 12, 31)
    print(f"store B ready in {time.time() - t:.0f}s; calendar {cal[0]}..{cal[-1]} ({len(cal)}); setup raw_src counts {np.bincount(S.raw_src.astype(int), minlength=3).tolist()}", flush=True)
    n_tr = trunc_check(S)
    last_ci = len(cal) - 1
    nights = [i for i, d in enumerate(cal) if d >= date(2022, 4, 1) and i + 61 <= last_ci]
    print(f"era-B nights {cal[nights[0]]} .. {cal[nights[-1]]}: {len(nights)}; E(last) {cal[nights[-1] + 1]}, E+60 = {cal[nights[-1] + 61]}", flush=True)
    assert not OUTP.exists(), "captured once"
    t = time.time()
    df = run_nights(nights, keep_all=False)
    df.to_parquet(OUTP, index=False)
    OUTP.with_suffix(".cal.txt").write_text("\n".join(d.isoformat() for d in cal))
    live = df[df.failed == ""]
    per = df.groupby("ci").agg(l=("ticker", "size"), f=("fire", "sum")).reindex(nights).fillna(0)
    perl = live.groupby("ci").agg(l=("ticker", "size"), f=("fire", "sum")).reindex(nights).fillna(0)
    res = dict(nights=len(nights), first_D=str(cal[nights[0]]), last_D=str(cal[nights[-1]]), bridge_rows=len(df), bridge_break_rows=int(df.fire.sum()),
               live_rows=len(live), live_break_rows=int(live.fire.sum()), listed_median_bridge=float(per.l.median()), listed_median_live=float(perl.l.median()),
               break_median_bridge=float(per.f.median()), break_median_live=float(perl.f.median()), trunc_sample=n_tr,
               raw_src_live_rows={int(k): int(v) for k, v in live.raw_src.value_counts().items()}, secs=round(time.time() - t))
    (HERE / "1d_build_result.json").write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps(res, indent=1), flush=True)


if __name__ == "__main__":
    main()
