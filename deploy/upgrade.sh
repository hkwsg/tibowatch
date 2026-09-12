#!/bin/sh
# Run only after reviewing the release. Does not resend the installation test.
set -eu
export PYTHONDONTWRITEBYTECODE=1
[ "$(id -u)" = 0 ] || { echo 'Run with sudo'; exit 1; }
app=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
systemctl disable --now tibo-watch.timer
if systemctl is-active --quiet tibo-watch.service; then
    echo 'Wait for the current oneshot to finish; timer remains paused.'
    exit 1
fi
/usr/sbin/runuser -u tibo-watch -- /usr/bin/python3 - "$app" <<'PY'
import json, sys
sys.path.insert(0, sys.argv[1])
from watcher import State, Fault
with State('/var/lib/tibo-watch') as storage:
    s=storage.load()
    if s['pending']:
        raise SystemExit('Pending notifications require resolution; no code installed, timer paused.')
    # Keep a separate pre-upgrade snapshot, without replacing existing snapshots.
    target=storage.directory / 'state.pre-rss-upgrade.json'
    if not target.exists():
        storage.atomic(target, json.dumps(s, ensure_ascii=False, sort_keys=True))
PY
sh "$app/deploy/install.sh"
systemctl start tibo-watch.service
systemctl start tibo-watch.service
/usr/sbin/runuser -u tibo-watch -- /usr/bin/python3 - <<'PY'
import json,time
s=json.load(open('/var/lib/tibo-watch/state.json'))
assert s['version']==2 and s['initialized'], 'RSS migration/baseline required'
assert not s['health'].get('reason'), 'Healthy RSS source required'
assert time.time()-s.get('last_source_success',0)<300, 'Fresh successful fetch required'
print('RSS baseline and repeated execution passed; existing installation-test marker retained.')
PY
systemctl enable --now tibo-watch.timer
