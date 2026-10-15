#!/usr/bin/env python3
"""READ-ONLY capture of prod container state for #624 heartbeat 4 (10-15). No writes."""
import subprocess, datetime
H = "apollo@87.99.134.162"
FILES = ["agents/market_intelligence/ep_detector.py", "agents/market_intelligence/lowcap_paper_lane.py",
         "agents/market_intelligence/db.py", "agents/market_intelligence/broker/skip_reasons.py",
         "agents/market_intelligence/scheduler.py"]
def sh(cmd):
    r = subprocess.run(["ssh", H, cmd], capture_output=True, text=True)
    return (r.stdout + r.stderr).rstrip()
print(f"# read-only: docker ps on prod host, run {datetime.datetime.now(datetime.timezone.utc).isoformat()} UTC")
print(sh("docker ps --format '{{.Names}}|{{.Image}}|{{.Status}}|{{.CreatedAt}}'"))
print()
print(sh("for c in apollo-market apollo-execution apollo-orchestrator; do docker inspect --format '/{{.Name}} started={{.State.StartedAt}} image={{.Image}}' $c; done"))
print("server HEAD", sh("git -C /home/apollo/apollo_the_wise log -1 --format='%h %ci %s'"))
for c in ("apollo-market", "apollo-execution"):
    print(f"\n# md5 inside {c} (read-only)")
    print(sh(f"docker exec {c} md5sum " + " ".join(FILES)))
    print(sh(f"docker exec {c} grep -c lowcap_paper_lane agents/market_intelligence/ep_detector.py agents/market_intelligence/scheduler.py"))
