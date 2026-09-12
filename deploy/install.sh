#!/bin/sh
set -eu
[ "$(id -u)" = 0 ] || { echo 'Run with sudo'; exit 1; }
app=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
# Refuse unrelated existing resources; our marker establishes ownership.
if [ ! -f /opt/tibo-watch/.tibo-watch-owned ]; then
    for path in /opt/tibo-watch /etc/tibo-watch /var/lib/tibo-watch /etc/systemd/system/tibo-watch.service /etc/systemd/system/tibo-watch.timer; do
        if [ -e "$path" ]; then echo 'Existing resource needs ownership review'; exit 1; fi
    done
    if getent passwd tibo-watch >/dev/null; then echo 'Existing user needs ownership review'; exit 1; fi
    /usr/sbin/useradd --system --user-group --home-dir /var/lib/tibo-watch --shell /usr/sbin/nologin tibo-watch
    install -d -o root -g root -m 755 /opt/tibo-watch
    touch /opt/tibo-watch/.tibo-watch-owned
fi
for path in /opt/tibo-watch /etc/tibo-watch /var/lib/tibo-watch; do
    [ ! -L "$path" ] || { echo 'Symlink refused'; exit 1; }
done
install -d -o root -g root -m 700 /etc/tibo-watch
install -d -o tibo-watch -g tibo-watch -m 700 /var/lib/tibo-watch
install -o root -g root -m 644 "$app/watcher.py" /opt/tibo-watch/watcher.py
install -o root -g root -m 644 "$app/config.example.json" /opt/tibo-watch/config.example.json
install -o root -g root -m 755 "$app/deploy/activate.sh" /opt/tibo-watch/activate.sh
install -o root -g root -m 644 "$app/deploy/tibo-watch.service" /etc/systemd/system/tibo-watch.service
install -o root -g root -m 644 "$app/deploy/tibo-watch.timer" /etc/systemd/system/tibo-watch.timer
systemd-analyze verify /etc/systemd/system/tibo-watch.service /etc/systemd/system/tibo-watch.timer
systemctl daemon-reload
echo 'Installed. Timer enablement is a separate gated action. Credentials and state preserved.'
