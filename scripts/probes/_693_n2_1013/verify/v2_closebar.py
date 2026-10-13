# #693 verifier: what close_bar_for returns for the origin/main PLAN line (read-only).
import sys
sys.path.insert(0, "scripts")
from check_plan import close_bar_for
line = open(sys.argv[1]).read()
print(close_bar_for(line))
