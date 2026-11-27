import numpy as np
from datetime import date
import r4_common as C
import v1_replay as R
S = R.load_store("B"); D = S.D; cal = D.cal
nights = [ci for ci, d in enumerate(cal) if date(2022, 4, 1) <= d and ci + 1 < len(cal) and cal[ci + 1] <= date(2024, 10, 4)]
facts = [R.ticker_facts(S, k) for k in range(len(D.tickers))]
row_tid = np.repeat(np.arange(len(D.tickers), dtype=np.int64), (D.stop - D.start).astype(np.int64))
order = np.argsort(D.ci, kind="stable"); rows_at = R._RowsAt(order, D.ci[order], row_tid)
tot = d2 = 0
for ci in nights:
    members, _ = R.night_members(S, facts, ci, rows_at)
    tot += len(members); d2 += sum(1 for m in members if S.raw_src[m["i"]] == 2)
print(f"era-B RS-pool member name-nights ({len(nights)} nights): {tot:,}; derived-only (raw_src 2): {d2:,} = {d2 / tot:.2%}")
