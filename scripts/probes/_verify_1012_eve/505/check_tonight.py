# Reads q_tonight.out (psql -A -F tab). PASS only if: a theme_parent_pass_ran row exists, 0 errors, no 'industries unreadable',
# >=1 ask, and EVERY ask line carries (industry overlap >= 0.50) OR (shared tickers >= 1).
import re, sys
rows = [l.rstrip("\n").split("\t") for l in open("q_tonight.out").read().splitlines()[1:] if "\t" in l]
ran = [r for r in rows if r[2] == "theme_parent_pass_ran"]
print("heartbeat rows:", len(ran))
if not ran: print("NOT YET"); sys.exit(0)
summary, detail = ran[-1][3], ran[-1][4]
print(summary)
bad = []
for r in rows:
    if r[2] in ("theme_parent_pass_linked","theme_parent_pass_distinct","theme_parent_pass_inverted"):  # error rows carry no 'why'; counted separately below
        d = r[4]
        sh = re.search(r"shared tickers (\d+)", d); ov = re.search(r"industry overlap ([0-9.]+)", d)
        ok = (sh and int(sh.group(1)) >= 1) or (ov and float(ov.group(1)) >= 0.50)
        print(("OK  " if ok else "BAD ") + r[2].replace("theme_parent_pass_","") + " | " + d[:170])
        if not ok: bad.append(d[:120])
print("errors:", sum(1 for r in rows if r[2]=="theme_parent_pass_error"), "| unreadable flag:", "industries unreadable" in summary, "| BAD asks:", len(bad))
