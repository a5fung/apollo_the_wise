"""EXPLORATORY (post-hoc), #491 cohort only: is 'moves with AI more than bitcoin' just BETA?
Both reference sets below are HIGH-BETA equity groups the board itself built: the other live E-CRYPTO
themes (bitcoin proxies: treasuries, exchanges) vs the live E-AIINFRA themes. Cohort (12 names) excluded
from both. If converts still prefer the AI-infra themes over the equally speculative bitcoin-proxy themes,
beta alone does not explain the split. Same maths (engine module), same 60-session window, same 0.10 bar."""
import statistics
import identity_test as it
eco = it.load_taxonomy(); themes = it.load_themes(); closes = it.load_closes()
ex, sess = it.excess_for(closes, it.RUN_DATE)
coh = set(it.COHORT_491)
crypto = sorted({m for t in themes if t["e_code"] == "E-CRYPTO" and t["name"] != "Bitcoin Mining Stocks Rotation Reversal" for m in t["tickers"]} - coh)
ai = sorted({m for t in themes if t["e_code"] == "E-AIINFRA" for m in t["tickers"]} - coh)
rc, nc = it.ref_series(ex, crypto); ra, na = it.ref_series(ex, ai)
out = [f"window {sess[1]}..{sess[-1]}; bitcoin-proxy themes basket n={nc} {crypto}",
       f"AI-infra themes basket n={na}; sep(bitcoin-proxy, AI-infra themes) = {it.corr(rc, ra):.2f}",
       f"reference affinity to IBIT: bitcoin-proxy basket {it.corr(rc, ex['IBIT']):.2f} | AI-infra basket {it.corr(ra, ex['IBIT']):.2f}"]
diffs = []
for m in it.COHORT_491:
    c, a = it.corr(ex[m], rc), it.corr(ex[m], ra)
    diffs.append(a - c)
    out.append(f"  {m:<5} bitcoin-proxy themes {c:+.2f}  AI-infra themes {a:+.2f}  diff {a-c:+.2f} {'MISFIT' if a-c >= it.IDENTITY_GAP_BAR else ''}")
out.append(f"cohort median diff {statistics.median(diffs):+.2f}; misfits {sum(d >= it.IDENTITY_GAP_BAR for d in diffs)} of {len(diffs)}")
open(it.HERE / "identity_beta_check_out.txt", "w").write("\n".join(out) + "\n"); print("\n".join(out))
