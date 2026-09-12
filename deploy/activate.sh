#!/bin/sh
set -eu
[ "$(id -u)" = 0 ] || exit 1
[ -s /etc/tibo-watch/bark.env ] || { echo WAITING_FOR_BARK_KEY; exit 1; }
# Root reads only this task's credential, strictly parses it and drops privileges.
# The key is passed in the child environment, never arguments or shell source.
python3 - <<'PYCODE'
import os, pathlib, pwd, re, subprocess
p=pathlib.Path('/etc/tibo-watch/bark.env')
st=p.lstat()
assert not p.is_symlink() and st.st_uid == 0 and st.st_mode & 0o777 == 0o600
text=p.read_text()
m=re.fullmatch(r'BARK_KEY=([A-Za-z0-9_-]{8,256})\n',text)
assert m, 'Invalid credential file format'
u=pwd.getpwnam('tibo-watch')
subprocess.run(['/usr/bin/python3','/opt/tibo-watch/watcher.py','test-push'],
    env={'PATH':'/usr/bin:/bin','BARK_KEY':m[1],'PYTHONDONTWRITEBYTECODE':'1'},
    user=u.pw_uid, group=u.pw_gid, extra_groups=[], check=True)
PYCODE
systemctl start tibo-watch.service
/usr/sbin/runuser -u tibo-watch -- /usr/bin/python3 - <<'PY'
import json, time
s=json.load(open('/var/lib/tibo-watch/state.json'))
assert s.get('test_push') == 'accepted_by_push_service', 'Installation test not accepted'
assert s['initialized'] and not s['health'].get('reason'), 'Healthy baseline required'
assert time.time()-s['last_source_success'] < 300, 'Fresh source required'
print('Bark accepted; DEVICE_RECEIPT_UNCONFIRMED')
PY
systemctl enable --now tibo-watch.timer
systemctl start tibo-watch.service
systemctl show tibo-watch.timer -p ActiveState -p UnitFileState -p NextElapseUSecMonotonic
