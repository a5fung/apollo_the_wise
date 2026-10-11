"""#700 — capture the 10-11 head's checked line and the fold length under the PRE-#700 renderer into
tests/fixtures/weekly_review_1011.json["before"].

Run ONCE against origin/main code (before `system_review.py` was changed); the fixture then carries the
numbers `test_the_1011_fixture_renders_under_the_budget` compares against. Re-running it against the new
renderer would overwrite the baseline with the new numbers, so it refuses when the new renderer is
present.

    python scripts/probes/_700_review_noise/capture_before.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))

from scripts.probes._700_review_noise import harness_1011 as h  # noqa: E402


def main() -> None:
    import agents.market_intelligence.system_review as sr
    if hasattr(sr, "split_narrative_blocks"):
        raise SystemExit("refusing: the #700 renderer is present - `before` must be captured from the old code")
    head, fold, meta = h.render_1011(prior=h.NO_PRIOR)
    checked_line = head.splitlines()[-1]
    phrases = checked_line.removeprefix("_Also checked — ").removesuffix("._").split(" · ")
    fx = h.load_fixture()
    fx["before"] = {"fold_chars": len(fold), "fold_lines": fold.count("\n") + 1,
                    "head_lines": meta["head_lines"], "checked_phrases": phrases,
                    "needs_me": meta["needs_me"], "needs_you": meta["needs_you"]}
    h.FIXTURE.write_text(json.dumps(fx, indent=1, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    print(json.dumps(fx["before"], indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
