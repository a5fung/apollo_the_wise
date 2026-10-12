# pure-function check, NO send: what chat does THIS container's real env + code pick for today's actual texts?
from agents.market_intelligence import constants as c
tests = {
 "paper Untracked fill page (trade_stream.py:838)": f"{c.mode_prefix('paper')}💱 *Untracked buy:* KO @$88.40 x 3\nOrder d9b5320c not in our records — direct Alpaca action.",
 "paper Untracked sell page": f"{c.mode_prefix('paper')}💱 *Untracked sell:* KO @$88.58 x 3",
 "live-tagged page": f"{c.mode_prefix('live')}💱 *Untracked buy:* X @$1.00 x 1",
 "untagged system alert": "🚨 coverage drift (system)",
 "mixed-book tag": f"{c.BOTH_BOOKS_TAG}stream down",
 "mode unknown tag": f"{c.UNRESOLVED_MODE_TAG}ORB pipeline crashed",
}
import os
print("env TELEGRAM_PAPER_CHAT_ID =", repr(os.environ.get("TELEGRAM_PAPER_CHAT_ID")))
for k, v in tests.items():
    print(f"{k:55s} -> {c.paper_chat_id_for(v)}")
