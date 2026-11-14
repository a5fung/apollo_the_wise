#!/usr/bin/env python3
"""#717 context checks: the CAPTURE (2026-11-14; offline, $0, read-only, ERA A ONLY; research, no rule changed).

FIXTURES ONLY. `_717_shape_1114/01_capture.py` verbatim with W = 200 instead of 80 (the 126-session return of the
scorecard / High-tier rows needs 127 bars; the era-A fires already have it in bv1_rank_1114/fires_trend.parquet and their
80-bar windows in bv1_shape_1114/fires_windows.npy — neither is rebuilt). The fixture loader reads only the scorecard
fixtures and features_eraA.parquet (asserted <= 2022-03-31 inside 01_measure.py); `cb702/` is never opened.

    python3 scripts/probes/_717_context_1114/01_capture.py > scripts/probes/_717_context_1114/01_fixtures.out
"""
import importlib.util, os
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
spec = importlib.util.spec_from_file_location("m01", os.path.join(REPO, "scripts/probes/_717_reasons_1114/01_measure.py"))
M1 = importlib.util.module_from_spec(spec); spec.loader.exec_module(M1)
W = 200
STASH = []


def window(bars, D):
    out = np.full((4, W), np.nan, np.float32)
    a = max(0, D - W + 1)
    for j, x in enumerate((bars.o, bars.h, bars.l, bars.c)):
        seg = np.asarray(x[a:D + 1], float)
        out[j, W - len(seg):] = seg
    return out


def recorder(bars, D, P, adr, level):
    STASH.append(window(bars, D))
    return {"wid": len(STASH) - 1, "base_len": D - P}


if __name__ == "__main__":
    M1.reason_measures = recorder
    M1.HERE = HERE                                   # scorecard_rows.tsv / high_rows.tsv land in THIS folder
    M1.stage_fixtures()
    np.save(os.path.join(HERE, "fixtures_windows200.npy"), np.stack(STASH))
    print(f"fixtures windows: {len(STASH)} x 4 x {W} -> fixtures_windows200.npy")
