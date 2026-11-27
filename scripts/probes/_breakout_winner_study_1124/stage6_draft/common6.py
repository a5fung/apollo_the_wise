"""Stage 6 DRAFT shared: sha asserts (all four documents + the feature table), the components table, the draft flag. Outcome-free."""
import hashlib, sys
from pathlib import Path
import numpy as np, pandas as pd
H6 = Path(__file__).resolve().parent
ROOT = H6.parent
REPO6 = H6.parents[3]
sys.path.insert(0, str(H6)); sys.path.insert(0, str(ROOT / "stage2"))
import gr1
import s2lib as L
SH = {"docs/analysis/breakout_winner_study_prereg_DRAFT_2026-11-24.md": "3eb2b9b0247bc0ba7bf0d8e6f1efd67da1078fc090373c83c1bc14599339042a",
      "docs/analysis/breakout_winner_study_prereg_amendment_A1_2026-11-26.md": "4a7beda14378ed2dea42308d92364dd92de4907aa3c7da4aaaffdffe75d17b10",
      "docs/analysis/breakout_winner_study_prereg_amendment_A2_2026-11-26.md": "0a6cc4174ef27d187e49100e966023340f7eb0e31cc2d552f4c5ea594f622f6b",
      "docs/analysis/breakout_winner_study_prereg_amendment_A3_2026-11-26.md": "a0c11a3685bc83369a9fba29766368e82734432ea9a3a464fd363787e6d34268"}
CUT = "2024-12-31"


def assert_all():
    for p, h in SH.items():
        assert hashlib.sha256((REPO6 / p).read_bytes()).hexdigest() == h, f"{p} sha differs - STOP"
    L.assert_docs()
    return "prereg 3eb2b9b0 / A1 4a7beda1 / A2 0a6cc417 / A3 a0c11a36 / feature table d629ef0a asserted"


def components():
    F = pd.read_csv(H6 / "gr1_components.tsv.gz", sep="\t", keep_default_na=False, na_values=[""], dtype={"ticker": str})
    assert F.E.max() <= CUT and F.D.max() <= CUT
    F["gr1_null"] = F.gr1_null.fillna("")
    sc = F.gr1_null == ""
    base = sc & (F.trough_age <= gr1.T_MAX_AGE) & (F.drop_adr >= gr1.DROP_ADR_MIN) & (F.recover >= gr1.RECOVER_MIN)
    F["gr1"] = np.where(sc, (base & (F.at_level <= gr1.AT_LEVEL_MAX)).astype(float), np.nan)
    F["alt1"] = np.where(sc, base.astype(float), np.nan)
    return F


class Out:
    def __init__(self, name):
        self.L, self.name = [], name
    def __call__(self, s=""):
        print(s, flush=True); self.L.append(s)
    def save(self):
        (H6 / self.name).write_text("\n".join(self.L) + "\n")
