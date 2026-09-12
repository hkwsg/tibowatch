# TiboWatch

[简体中文](README.zh-CN.md)

A lightweight forwarder for [SaveMeTibo's published RSS alerts](https://savemetibo.com/feed.xml), with optional Simplified Chinese translation and Bark notifications for iPhone.

**SaveMeTibo publishes → TiboWatch optionally translates → Bark delivers.** TiboWatch does not perform a second editorial interpretation of events. RSS `title` and `description` are the authoritative visible content, without added timestamps, source labels, cautions, explanations or internal IDs.

> v1.1 is under review. Existing v1 installations should continue running until the upgrade is approved. The v1.0.0 release remains available separately.

## Architecture

```mermaid
flowchart LR
    A[SaveMeTibo RSS] --> B[GUID + content dedupe]
    B --> C[One optional Codex translation]
    C --> D[Persist exact title/body]
    D --> E[Bark API]
    E --> F[APNs → iPhone]
```

If translation fails for any reason, the original RSS English title and body are selected immediately. There is no larger-model fallback, translation retry loop, translation service or extra notification queue. The existing local pending queue stores the selected payload for Bark retries.

## Requirements

- Linux with systemd (for example, recent Debian or Ubuntu), Python 3.11+, and standard `sudo`, `useradd`, `runuser`, `install` tools.
- Outbound HTTPS to SaveMeTibo and `api.day.app`; no inbound ports.
- Bark iOS app registered with `api.day.app`.
- Optional: an existing authenticated local Codex CLI accessible to the **watcher service user**, supporting the flags below. Missing CLI/login/model/quota means immediate English fallback.

No database, Docker, Telegram, X API, browser automation or Python dependencies. The installer does not install or authenticate Codex, copy login files, change networking or modify other services.

## New installation

After reviewing the version you intend to install:

```sh
git clone https://github.com/hkwsg/tibowatch.git
cd tibowatch
python3 -m unittest discover -s tests -v
sudo sh deploy/install.sh
sudo python3 /opt/tibo-watch/watcher.py configure-bark
sudo /opt/tibo-watch/activate.sh
```

Enter the base Bark device address in your trusted terminal when prompted; input is hidden. Only the `api.day.app` HTTPS origin is accepted, without title/body suffixes or query parameters. Do not put the address in shell arguments, issues, screenshots or Git.

Activation sends one clearly labeled installation test, then requires a healthy baseline before enabling the timer. The initial healthy RSS fetch baselines existing items without replaying history or invoking Codex. Repeating activation does not resend an already-attempted installation test; an uncertain test result requires manual review. Existing real pending items may be sent separately by the production check.

## One best-effort translation

Each genuinely new/changed alert gets at most one direct subprocess invocation using **only `gpt-5.6-luna`**. There is no model availability probe on quiet polls. CLI invocation:

```sh
codex exec --ephemeral --ignore-user-config --ignore-rules \
  --skip-git-repo-check --sandbox read-only --model gpt-5.6-luna \
  -c 'approval_policy="never"' -c features.shell_tool=false \
  -c features.unified_exec=false -c 'web_search="disabled"' \
  -c project_doc_max_bytes=0 --output-schema <temporary-schema> \
  --output-last-message <temporary-output> -
```

The program uses an argument array and JSON text through stdin, never a shell command string. It uses a temporary working directory, an **8-second timeout**, discarded stdout/stderr, no Bark key in the subprocess environment, and strict final JSON parsing with exactly `title` and `body` string fields. It kills the process group on timeout. The prompt requests complete translation, no summary/omission/commentary, and preservation of product names such as Codex, Astra and ChatGPT. Structural validation cannot prove semantic translation accuracy.

The original English fallback and an attempt marker are saved **before** invocation. If the process crashes during translation, the next run sends that stored English rather than translating again. A successful selection replaces it atomically. Bark retries never retranslate, even when login or models later become available. Up to five payload selections and five sends are processed per poll; excess items remain in the same persistent queue.

The systemd unit can read optional non-secret `/etc/tibo-watch/runtime.env` settings; see [deploy/runtime.env.example](deploy/runtime.env.example):

- `TIBOWATCH_TRANSLATE=0` disables translation (default: enabled).
- `TIBOWATCH_CODEX_BIN` selects an accessible installed executable (default: `codex` on PATH).
- `CODEX_HOME`, if supplied, must refer to an existing CLI login accessible to the service user.

A login belonging to another account is **not** automatically accessible to `tibo-watch`. `ProtectHome=true` also blocks home-directory CLI binaries/login files in the system service. Do not relax secret permissions, run the watcher as root or copy another user's credentials to work around this. Without an appropriately provisioned existing CLI context, use the English fallback. No login files are read by TiboWatch itself; the CLI handles its own authentication.

CLI behavior is documented in [OpenAI's non-interactive guide](https://developers.openai.com/codex/noninteractive/) and [configuration reference](https://developers.openai.com/codex/config-reference/). Older CLI versions rejecting any flag simply trigger English fallback.

## Dedupe and content rules

- First healthy RSS run: historical baseline, no notification or translation.
- New GUID: one candidate; changed title/description for an existing GUID: one new candidate.
- Identical title/description: no notification, even if order, `pubDate` or `link` changes.
- `pubDate` only orders new candidates chronologically. `guid` is internal identity.
- Bark click target is the RSS link when it is valid HTTPS without user-info or whitespace (any valid port); otherwise it is `https://savemetibo.com/`. Click targets are not fetched by the watcher.
- XML text/CDATA is preserved after XML entity decoding. Embedded HTML is left as provided, not rendered or stripped. Original content is never censored, summarized or silently truncated.
- The conservative outgoing JSON budget is **3000 UTF-8 bytes**, including key/envelope. An oversize selected payload remains pending with `payload_too_large`; it is never shortened or replaced after selection.
- Feed errors, invalid XML, conflicting duplicate GUIDs and unexpectedly empty feeds preserve state and appear in local status/logs. No extra Bark source/outage/editorial alerts are generated. A quiet feed is not stale merely because no new alert was published.

## Reliability and operation

State uses a file lock, atomic replacement, fsync and a rolling backup. Observed content and accepted sends are separate; pending is persisted before sending. Bark success requires HTTP 200 plus integer JSON `code=200`. Retries use 5/10/20/60-minute backoff, respect longer `Retry-After`, and slow authentication failures to at least a day. Failed feed checks pause queue processing until a healthy fetch. Pending items are retained without a six-hour expiry.

```sh
sudo -u tibo-watch python3 /opt/tibo-watch/watcher.py status
sudo -u tibo-watch python3 /opt/tibo-watch/watcher.py check-source
sudo -u tibo-watch python3 /opt/tibo-watch/watcher.py dry-run
sudo systemctl start tibo-watch.service
systemctl list-timers tibo-watch.timer
sudo journalctl -u tibo-watch.service -n 20 --no-pager
sudo systemctl disable --now tibo-watch.timer
```

`dry-run` does not write state, translate or send. `status` shows fetch age, failures, pending errors and translation outcomes for pending items, without message bodies. A completed oneshot normally becomes inactive: check `Result=success`, `ExecMainStatus=0` and timer activity. Resume a validated installation with `sudo systemctl enable --now tibo-watch.timer`. Pausing the timer does not stop an already-running oneshot.

`config.example.json` documents fixed defaults; it is not loaded at runtime. The timer remains five minutes with up to 15 seconds jitter; HTTP timeout is 10 seconds and input size limit is 2 MiB.

## Upgrade from v1 — only after review

Do not use the installation-test path to migrate. Run the reviewed release's helper:

```sh
sudo sh deploy/upgrade.sh
```

It pauses only this task's timer, refuses to proceed while a oneshot is active or any pending notification is unresolved, and saves a protected pre-upgrade state snapshot before installing code. Resolve v1 pending items rather than deleting them. It runs the new service twice and re-enables the timer only after fresh RSS/state checks pass. Any failure leaves the timer paused for inspection.

The first healthy new run migrates state version 1 → 2, makes an additional v1 backup, preserves the installation-test marker, and baselines RSS without replay. Migration refuses nonempty v1 pending queues. Credentials are untouched. Retain the old code and protected state backups for rollback: v1 cannot read v2 state. For rollback, stop this task and restore a matched old code/state pair before resuming; account for notifications already accepted since the snapshot.

## Security and limitations

The Bark key is a secret, held in root-only `/etc/tibo-watch/bark.env` (0600, directory 0700), read by the systemd manager. Normal execution uses the non-root `tibo-watch` account, read-only installed code, and writable task state only. TLS is verified, POST redirects are blocked, and no request body/key is logged. Root is needed for installation, not normal forwarding. See [SECURITY.md](SECURITY.md).

SaveMeTibo is third-party, not an official OpenAI API or a guarantee of all Tibo posts. Published alerts do not prove your personal account has reset. Five minutes is a local interval, not an end-to-end SLA. VPS, Bark or upstream failures cannot guarantee self-reporting through the same failed path. Ambiguous network timeouts may duplicate delivery; strict exactly-once is not guaranteed. Translation availability and semantic accuracy are not guaranteed. Historical fingerprints grow over time; monitor local state size.

To remove: disable the timer, stop this service if necessary, remove only its units and code, then daemon-reload. Retain credentials/state and the dedicated user by default, deleting them only by explicit choice. Do not remove shared software or change networking.

## Development

```sh
python3 -m unittest discover -s tests -v
python3 -m py_compile watcher.py
sh -n deploy/install.sh
sh -n deploy/activate.sh
sh -n deploy/upgrade.sh
git diff --check
```

Tests use synthetic RSS, temporary state and mocked CLI/Bark calls. CI checks Python 3.11 and 3.14. See [CONTRIBUTING.md](CONTRIBUTING.md), [CHANGELOG.md](CHANGELOG.md), and [LICENSE](LICENSE).

This project is not affiliated with OpenAI, Tibo, X, Bark, or SaveMeTibo.
