# TiboWatch engineering and operations

[README](../README.md) · [中文介绍](../README.zh-CN.md) · [Deployment prompt](../DEPLOY_WITH_CODEX.md)

This guide describes the RSS-based implementation. Read it for implementation details or maintenance; the deployment prompt is the starting point for a new installation.

## Data flow and source map

```text
systemd timer
  → watcher.py run-once
  → request + parse_rss
  → ingest: GUID and title/body fingerprint
  → select_payloads: one optional translate call
  → deliver: persisted payload to Bark
```

| Location | Responsibility |
| --- | --- |
| `watcher.py` | HTTP/RSS, state, dedupe, CLI translation, delivery and operational commands |
| `tests/test_watcher.py` | Offline cases using synthetic input, temporary state and mocks |
| `deploy/install.sh` | Install code, the service user and systemd units; preserve existing task configuration |
| `deploy/activate.sh` | Fresh-install test, healthy baseline and timer activation |
| `deploy/upgrade.sh` | Reviewed state-v1 to RSS/state-v2 upgrade with protected snapshots |
| `deploy/tibo-watch.service` / `.timer` | Runtime identity, limits and scheduling |
| `deploy/runtime.env.example` | Optional runtime settings supplied by the operator or deployment agent |

SaveMeTibo's `feed.xml` supplies title, description, GUID, publication date and link. XML text is preserved after entity decoding; embedded HTML text is not rendered. GUID plus exact title/body content decides whether an item changed. Date/link-only changes do not create another notification.

Initial RSS data becomes a quiet baseline. An edit supersedes an older pending version of the same GUID. The service does not infer event severity, rewrite the message or add commentary. Upstream removal alone does not create a local retraction message.

## Translation and delivery

The application passes title/body through stdin to a single noninteractive `codex exec` process, using a temporary directory, a JSON output schema and the final-response file. It disables tool use in the configured invocation, excludes Bark credentials from the child environment and reads only the two expected output fields.

Before invocation, the pending job records the original-English fallback and its attempt marker. Success replaces that job's selected title/body. Failure or interruption leaves English selected. Bark retries reuse the selection without another model call. Structural JSON checks do not verify translation meaning.

State version 2 separates observed fingerprints, pending selections and accepted requests. A file lock, atomic writes and backup protect state. Bark acceptance requires HTTP 200 and integer JSON `code=200`; it is not a phone receipt acknowledgment. Ambiguous network failures can still duplicate a notification.

## Defaults in this implementation

| Setting | Value |
| --- | --- |
| Feed | `https://savemetibo.com/feed.xml` |
| Bark endpoint | `https://api.day.app/push` |
| Poll interval | 5 minutes, up to 15 seconds jitter |
| HTTP timeout / input cap | 10 seconds / 2 MiB |
| Translation | `gpt-5.6-luna`, one attempt, 30-second timeout |
| Per-run work | Up to 5 payload selections and 5 sends |
| Service deadline | 240 seconds |
| Outgoing JSON budget | 3000 UTF-8 bytes, including key and envelope |
| Bark retry delays | 5 / 10 / 20 / 60 minutes; longer Retry-After takes precedence |

`config.example.json` documents defaults; it is not a loaded configuration file. Check the selected code and units before using values from another release. Oversize selected payloads stay pending with `payload_too_large`, rather than being silently truncated. Pending alerts do not have a six-hour expiry. A failed source fetch pauses queue processing until a healthy fetch, with local status rather than an additional Bark health message. An old publication date alone does not make a quiet feed unhealthy.

## Installation paths and settings

| Path | Content |
| --- | --- |
| `/opt/tibo-watch` | Installed code, owned by root and read-only to the service |
| `/etc/tibo-watch/bark.env` | Bark device key, root-owned 0600 in a 0700 directory |
| `/etc/tibo-watch/runtime.env` | Optional runtime settings, loaded by systemd |
| `/var/lib/tibo-watch` | State, lock, backups and service-side CLI context |
| `/etc/systemd/system/tibo-watch.*` | This task's service and timer |

For translation, the deployment agent can configure these non-secret values using actual local paths:

```ini
TIBOWATCH_TRANSLATE=1
TIBOWATCH_CODEX_BIN=/usr/bin/codex
CODEX_HOME=/var/lib/tibo-watch/codex
```

The example executable path is not a promise that every installation uses it. `TIBOWATCH_TRANSLATE=0` disables translation; absent settings use the source defaults. Installation does not automatically populate `runtime.env`.

Reuse the deploying user's existing, authorized Codex login. With file-based storage, provision only the necessary `auth.json` into the service-side `CODEX_HOME`; keep that directory 0700 and the file 0600, owned by `tibo-watch`. The CLI manages authentication. Keyring-backed logins may require another supported setup or English-only operation; do not assume an auth file exists.

Do not point `CODEX_HOME` at the interactive user's home or copy the full `.codex`, configuration or history. Auth contents stay out of Git, logs, chat and reports. Install a compatible CLI outside the protected home only when authorized; otherwise use English-only forwarding.

The non-root service retains `ProtectHome=true`, `ProtectSystem=strict` and its resource limits. An interactive-user success is not proof of service-context success. Check translation using the actual service environment. No automatic credential-sync service is included; if authentication stops working, English fallback remains available and the local auth context can be refreshed when needed. See [SECURITY.md](../SECURITY.md).

## Everyday commands

```sh
# State summary and current source check
sudo -u tibo-watch python3 /opt/tibo-watch/watcher.py status
sudo -u tibo-watch python3 /opt/tibo-watch/watcher.py check-source

# Read-only simulation: no state writes, translation or Bark send
sudo -u tibo-watch python3 /opt/tibo-watch/watcher.py dry-run

# Run using the configured systemd environment
sudo systemctl start tibo-watch.service
systemctl show tibo-watch.service -p Result -p ExecMainStatus
systemctl list-timers tibo-watch.timer
sudo journalctl -u tibo-watch.service -n 20 --no-pager

# Pause / resume an already-configured installation
sudo systemctl disable --now tibo-watch.timer
sudo systemctl enable --now tibo-watch.timer
```

`status` reads local state; `check-source` fetches/parses the current feed without writing state. Both it and `dry-run` require outbound access, but neither calls Codex or Bark.

A successful oneshot normally returns to inactive. Source errors can still exit zero: inspect state health and the latest successful source fetch as well as the service result. Check the timer separately. Pausing a timer does not stop a running invocation; stop this service separately only when necessary.

## Updates and removal

An existing working installation should not use fresh-install activation merely to update code. Retain its test marker, credential files and state.

For state v1, `deploy/upgrade.sh` pauses scheduling, rejects unresolved pending work, snapshots state, installs the reviewed code and checks new runs before resuming. First healthy RSS initialization creates the new baseline without replaying history. Use the matching release's procedure.

For state v2, perform normal code/unit maintenance: back up, pause this task, let an active run finish, install the selected code, reload systemd if needed, verify state/source and resume only after successful checks. If verification fails, keep the timer paused and report the recovery action. Do not rerun a v1 migration or delete state. Rollback requires matching code and state, accounting for any accepted notifications since the backup.

Removal starts by disabling the timer and stopping this service, then removing its units/code and reloading systemd. Keep state and credentials by default; delete them only when the user intends to discard them.

## Quick troubleshooting

| Symptom | First check |
| --- | --- |
| No notifications | Source health, pending count and timer; the upstream may simply be quiet |
| English instead of Chinese | CLI/auth availability in the service context and the selected payload; retries do not retranslate |
| `payload_too_large` | Pending error and upstream content size; the app did not shorten the message |
| Upgrade paused | Pending work, migration snapshot and source validation result |
| Bark accepted, phone silent | Phone connectivity, Bark notification permission and iOS notification settings |

`status` translation counters describe pending jobs, not lifetime totals. Zero counters after delivery do not prove translation was disabled.

Historical review notes and release audits are evidence for particular snapshots, not current deployment instructions. SaveMeTibo remains an independent upstream; five-minute polling is not an end-to-end delivery guarantee.
