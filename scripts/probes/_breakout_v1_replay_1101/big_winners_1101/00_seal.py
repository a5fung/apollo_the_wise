#!/usr/bin/env python3
"""Step 0: the SEALED inputs (nothing dated >= 2025-01-01 parsed), made with the replay's own functions into THIS study's scratch:
the cb702 daily copy (stream-filtered on the date column) and the sealed split list. Idempotent."""
import os, sys
SCRATCH = "/private/tmp/claude-501/-Users-alvinfung-apollo-the-wise/d30e3944-e07e-4b44-97de-010acba78d0b/scratchpad/Cfollow/big_winners"
os.environ["BV1_SCRATCH"] = SCRATCH
sys.path.insert(0, "/Users/alvinfung/apollo_the_wise/scripts/probes/_breakout_v1_replay_1101")
sys.path.insert(0, "/Users/alvinfung/apollo_the_wise")
import v1_replay as R
from pathlib import Path
assert str(R.SCRATCH) == SCRATCH, R.SCRATCH
dst = R.sealed_copy_of_daily(R.CB / "daily_closes_all.csv.gz", R.SCRATCH / "pop" / "cb702_daily_lt2025.csv.gz")
splits, n_skipped = R.load_splits_sealed(R.CB / "cb702_splits.psv")
print("sealed daily:", dst, Path(str(dst) + ".src.json").read_text())
print("sealed splits:", R.SCRATCH / "pop" / "splits_sealed.psv", "tickers", len(splits), "rows skipped (>= 2025)", n_skipped)
