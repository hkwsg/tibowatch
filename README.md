# TiboWatch

[简体中文](README.zh-CN.md)

A lightweight, self-hosted watcher for public Codex reset and quota signals, with Bark notifications for iPhone.

TiboWatch polls the third-party [SaveMeTibo](https://savemetibo.com/) JSON feed and sends relevant changes through your existing [Bark](https://github.com/Finb/Bark) push service. It monitors reset, quota, banked-reset and team-hint signals. It does **not** query your personal Codex account.

## Architecture

```mermaid
flowchart LR
    A[Public signal source] --> B[TiboWatch]
    B --> C[Semantic dedupe]
    C --> D[Bark]
    D --> E[iPhone]
```

SaveMeTibo → TiboWatch → Bark API → Apple Push Notification Service (APNs) → iPhone.

A systemd timer runs a short Python process every five minutes, with a little scheduling jitter. Local JSON state tracks observed events and accepted notifications. No inbound ports are opened.

## Features

- Reset watch signals with evidence, confirmed and landed states.
- Explicit corrections/retractions and observation-ended notices for previously notified events.
- Linked `team_hint` updates, preserving the canonical event's state.
- Semantic deduplication across repeated polls and process restarts.
- A quiet first-run historical baseline: existing events are not replayed.
- Persistent pending notifications, bounded retries and `Retry-After` handling.
- Stale-source detection, outage alerts and recovery notices.
- Python standard library only: no database, Docker dependency, Telegram, X API, browser automation or LLM.

Notifications use fixed Chinese titles and explanations with a truncated upstream English summary. English notification localization is not included in v1.

## Requirements

- Linux with systemd, such as a recent Debian or Ubuntu installation.
- Python **3.11+**, including `zoneinfo`, and system time-zone data.
- `sudo` for installation, plus standard system tools (`useradd`, `runuser`, `install`).
- Outbound HTTPS access to SaveMeTibo and `api.day.app`.
- The Bark iOS app registered with `api.day.app`, with notifications allowed.

The default installer targets a system-wide Linux installation. It does not upgrade your OS, install Python, change networking or install a Bark server. CI checks Python 3.11 and 3.14; other distribution combinations are not exhaustively tested.

## Quick start

```sh
git clone https://github.com/hkwsg/tibowatch.git
cd tibowatch
python3 -m unittest discover -s tests -v
sudo sh deploy/install.sh
```

The installer creates an independent `tibo-watch` user, code directory and systemd units. It preserves existing task state and credentials on repeat installs; it refuses unrelated existing resources. It does not enable the timer automatically.

Configure Bark **in your own trusted terminal**:

```sh
sudo python3 /opt/tibo-watch/watcher.py configure-bark
```

Paste the base push address from the Bark app when prompted. Input is hidden. Use the device address only, without a title/body suffix or query parameters. Only `https://api.day.app/` is accepted as the service origin. Do not put the address in shell arguments, Git, issues or screenshots.

Then activate:

```sh
sudo /opt/tibo-watch/activate.sh
```

Activation sends one clearly labeled installation test, runs a production check, and enables the timer only after push-service acceptance and a healthy baseline. Existing real pending notifications may also be sent by that production check; they are separate from the installation test.

Check the notification on your iPhone. Bark accepting a request does not prove delivery to the device. The CLI reports device receipt as unconfirmed; it cannot observe your phone.

Repeating activation does not automatically resend the installation test. If the test reports an uncertain result, inspect status before doing anything else. A maintainer should review the test marker under the state lock before any intentional retest; do not delete state or repeatedly retry to force a notification.

## Status and operation

```sh
# State summary: last run, last healthy source, freshness, retries, push acceptance
sudo -u tibo-watch python3 /opt/tibo-watch/watcher.py status

# Validate the public feed without changing state
sudo -u tibo-watch python3 /opt/tibo-watch/watcher.py check-source

# Read-only simulation: no production writes or notifications
sudo -u tibo-watch python3 /opt/tibo-watch/watcher.py dry-run

# Run the configured production service immediately
sudo systemctl start tibo-watch.service

# Scheduling and logs
systemctl list-timers tibo-watch.timer
sudo journalctl -u tibo-watch.service -n 20 --no-pager
```

A completed oneshot service normally shows `inactive`; check `Result=success`, `ExecMainStatus=0`, and whether the timer is enabled and active. No notifications can mean no new signal: check source age, `health.reason`, `push_status` and `pending_count` before diagnosing a fault.

Pause:

```sh
sudo systemctl disable --now tibo-watch.timer
```

This does not stop a currently running oneshot. If needed, stop that task separately with `sudo systemctl stop tibo-watch.service`. Resume a previously validated installation with `sudo systemctl enable --now tibo-watch.timer`.

Rotate your Bark key with the same hidden-input configuration command; subsequent service runs read the new value. Do not edit credentials through shell command arguments.

## Defaults and behavior

| Setting | v1 default |
| --- | --- |
| Feed | `https://savemetibo.com/status.json` |
| Bark endpoint | `https://api.day.app/push` |
| Polling | 5 minutes, with up to 15 seconds of timer jitter |
| HTTP timeout / response limit | 10 seconds / 2 MiB |
| Stale / outage thresholds | 30 / 60 minutes; explicit upstream outage also applies |
| Ordinary catch-up window | 6 hours |
| Same-state update cooldown | 30 minutes, retaining the latest pending version |
| Per-run send limit | 5 queued notifications |
| Notification time zone | `Asia/Shanghai`; does not change the OS time zone |

`config.example.json` documents fixed defaults; it is **not** loaded as a runtime configuration file. Changing those defaults currently requires reviewing the source or unit files.

State transitions and explicit corrections bypass the ordinary update cooldown. Linked hints use separate supplement semantics and cannot downgrade a confirmed or landed event. A simultaneous useful canonical update takes priority over its hint. Identical normalized text, timestamp-only changes, probability changes and array reorder do not trigger another notification. Text matching is deterministic, not general natural-language understanding.

State is written atomically with a lock and backup. Failed sends remain pending; retries use 5/10/20/60-minute backoff and respect longer `Retry-After` values. Authentication failures back off for at least a day. A damaged primary state attempts backup recovery; unrecoverable state requires manual intervention rather than silently becoming a fresh installation.

## Security model

The Bark device key is a **secret**. Never commit it. It is stored in the root-only `/etc/tibo-watch/bark.env` file (0600; parent directory 0700). The systemd manager reads the EnvironmentFile and passes the key to the dedicated `tibo-watch` process. The watcher does not require root for normal operation and cannot read the protected configuration directory itself.

Code lives under `/opt/tibo-watch`; only `/var/lib/tibo-watch` is writable to the service. No inbound listener, reverse proxy, Telegram session or personal account credential is needed. Requests verify TLS. Bark uses POST JSON, redirects are not followed, notification URLs are restricted, and logs omit request bodies and keys. Notifications use the ordinary `active` level with no automatic clipboard copying.

Public message content passes through the existing Bark service. This is not an entirely self-operated push infrastructure. See [SECURITY.md](SECURITY.md) for reporting and handling security issues.

## Updating and removing

Before an update, pause the timer and, if necessary, stop the service. Keep a protected backup of the current code and state. Check the new release and run its tests, then rerun the installer. Resume only after checking state compatibility and source health. A repeat install preserves credentials/state and the timer's current enablement state.

To remove the installation, disable the timer and stop the task. Remove only its two unit files from `/etc/systemd/system/`, run `sudo systemctl daemon-reload`, and remove its code directory. By default, retain task state, credentials and the dedicated user for recovery. Delete those separately only when you intentionally want to discard them. Do not remove shared Python packages or change networking.

## Known limitations

- SaveMeTibo is a third-party source, not an official OpenAI API. It does not guarantee coverage of every Tibo post on X.
- A community reset signal does not prove that your personal Codex account quota has reset.
- Five minutes is the local polling interval, **not an end-to-end SLA** from a post to a phone notification.
- VPS, Bark or upstream failures cannot reliably announce themselves through the same failed path. There is no independent heartbeat or fallback source.
- An ambiguous network timeout can mean the service accepted a notification without the watcher seeing the response. Strict exactly-once delivery is not guaranteed.
- Future upstream schema or lifecycle changes may need adaptation. Unknown core structures degrade safely; missing events alone are not treated as retractions.
- Historical dedupe records are retained; monitor local state size during long-running deployments.

## Development and license

```sh
python3 -m unittest discover -s tests -v
python3 -m py_compile watcher.py
```

The 34 offline tests use synthetic data, temporary state and mock HTTP; no real device key is required. See [CONTRIBUTING.md](CONTRIBUTING.md), [CHANGELOG.md](CHANGELOG.md), and the [MIT license](LICENSE).

## Disclaimer

This project is not affiliated with OpenAI, Tibo, X, Bark, or SaveMeTibo.
