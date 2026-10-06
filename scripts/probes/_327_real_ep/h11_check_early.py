"""#327 H11 — POST-HOC, UNREGISTERED read of the one positive session bucket (s01-02) seen in h11_out.txt, so its
weight can be stated honestly: composition, ex-May, permutation p. Shown only; never a draw."""
from collections import Counter
from h11_report import items, cell, row_line
X = items()
A_ = [x for x in X if x["era"] == "A" and x["bucket"] == "s01-02"]
L = ["POST-HOC (unregistered) — ERA A fires at session 1-2, either MA"]
c = cell(A_, "m_either", perm=True)
L.append(row_line("s01-02 ERA A", c, show_p=True))
L.append(row_line("s01-02 ex-May", cell([x for x in A_ if x["month"] != "2026-05"], "m_either")))
L.append(row_line("s01-02 Part A", cell([x for x in A_ if x["part"] == "A"], "m_either")))
L.append(row_line("s01-02 Part B", cell([x for x in A_ if x["part"] == "B"], "m_either")))
m = [x for x in A_ if x["m_either"] and x["o"] not in (None, "abstain")]
L.append("  matched composition: rung " + str(dict(Counter(x["rung"] for x in m))) + " · month " + str(dict(Counter(x["month"] for x in m))))
L.append("  matched +2-first hits: " + ", ".join(sorted(f"{x['ticker']} {x['ep_date']} {x['rung']}" for x in m if x["o"] == "target")))
B_ = [x for x in X if x["era"] == "B" and x["bucket"] == "s01-02"]
L.append(row_line("s01-02 ERA B", cell(B_, "m_either")))
open("h11_check_early_out.txt", "w").write("\n".join(L) + "\n")
