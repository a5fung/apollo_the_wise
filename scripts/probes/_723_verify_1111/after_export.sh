#!/bin/bash
D=/Users/alvinfung/apollo_the_wise/scripts/probes/_723_verify_1111
until [ "$(TZ=America/New_York date +%H%M)" -ge 1850 ]; do sleep 60; done
W=$(mktemp -d); cd ~/portfolio-app2 && git fetch -q origin && git show origin/main:live_breadth.py > $W/live_breadth.py && git show origin/main:apollo_breadth_snapshot.json > $W/snap.json && git show origin/live-breadth:apollo_breadth_live.json > $W/live.json
cd $W && python3 - <<'PY' > $D/after_export.out 2>&1
import json,sys; sys.path.insert(0,'.')
from datetime import datetime,date; from zoneinfo import ZoneInfo
import live_breadth as lb
live=json.load(open('live.json')); snap=json.load(open('snap.json'))
now=datetime.now(ZoneInfo("America/New_York")); sa=snap.get('as_of')
print('now',now.isoformat(timespec='seconds'),'live',live.get('as_of'),'snapshot as_of',sa)
print('is_live',lb.is_live(live,now),'holds_close',lb.holds_close(live,date.fromisoformat(str(sa)[:10]),now))
PY
