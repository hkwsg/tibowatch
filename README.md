# TiboWatch — Codex reset alerts for iPhone

[简体中文](README.zh-CN.md) · [Deploy with Codex](DEPLOY_WITH_CODEX.md) · [Engineering guide](docs/ENGINEERING.md)

**Get Codex reset notifications on your iPhone without watching X or keeping Telegram open.**

TiboWatch is a small, self-hosted Linux app that forwards [SaveMeTibo's published RSS alerts](https://savemetibo.com/feed.xml) through [Bark](https://github.com/Finb/Bark). It can translate new alerts into Simplified Chinese using your existing Codex CLI login. If translation is unavailable, the original English still goes through.

These instructions describe the RSS-based v1.1 implementation. The deployment guide checks the selected code version before installing.

## Deploy with one prompt

Open Codex on your Linux server, or use a Codex session with authorized SSH access to it. Paste this:

```text
Please deploy https://github.com/hkwsg/tibowatch on my authorized Linux server.
Read DEPLOY_WITH_CODEX.md and follow its setup workflow for the selected version.
Check the environment yourself, ask me for my Bark push address when needed,
then complete configuration, the phone test and scheduled operation.
Reuse my existing Codex login for translation when available.
```

The complete, standalone prompt is in **[DEPLOY_WITH_CODEX.md](DEPLOY_WITH_CODEX.md)**. It also works from a downloaded repository: ask Codex to read that file and start.

On a prepared server, your part is to provide the Bark address once and confirm the test on your phone. Codex handles the setup. A ChatGPT session without access to your server can explain the project and prepare the same handoff for an agent that has access.

## What you need

| Requirement | Purpose |
| --- | --- |
| A Linux server with systemd, Python 3.11+ and installation permissions | Runs the five-minute polling task |
| An iPhone with Bark installed and notifications enabled | Receives alerts through `api.day.app` |
| Optional: an existing, compatible Codex CLI and login | Translates new English alerts into Simplified Chinese |

There is no X API key, Telegram account, database or Docker requirement. Translation uses the CLI account's existing access and quota; it does not run on every poll.

## What a notification looks like

Illustrative upstream alert:

```text
Codex — Reset landed

Limits are back.
```

With Chinese translation, it may read:

```text
Codex — 重置已完成

额度已恢复。
```

The notification contains the upstream title and body, or their translation. TiboWatch adds no source label, timestamp or commentary. Tapping it opens the RSS item's valid HTTPS link, or the SaveMeTibo homepage if that link is missing or unsafe.

## How it works

```text
SaveMeTibo RSS → detect new/changed items → optional one-shot translation → Bark → iPhone
```

SaveMeTibo supplies the published community alerts. TiboWatch checks the feed about every five minutes, identifies items by GUID and title/body content, and remembers what it has processed.

The first run establishes a baseline without replaying history. New items and edits to an existing item's title/body become notifications. Repeated polls and date/link-only changes stay quiet. A failed Bark request stays queued; retrying it does not translate the message again.

## Common questions

**Will my phone need Telegram or an active connection to my server?**

No Telegram is involved. The server submits notifications to Bark; the phone receives them through Apple's push delivery. Bark notification permission and normal phone connectivity are still needed.

**How many notifications will I get?**

That depends on what SaveMeTibo publishes or edits. A five-minute check is not a five-minute notification. There is no fixed weekly message count.

**Does Codex need to stay open?**

No. systemd runs the watcher on schedule. With translation enabled, a short Codex CLI process starts only for a new or changed alert, with one attempt and a 30-second limit.

**Do I need another ChatGPT account or an API key?**

No additional account is needed when reusing your own existing compatible CLI login. Translation is optional; without it, TiboWatch forwards the English text.

**Can I deploy it on Windows or macOS?**

The supplied service scripts target Linux with systemd. Codex running on another computer can deploy to an authorized Linux server over SSH.

## Read more

- [Deployment prompt](DEPLOY_WITH_CODEX.md): agent-led setup, including Bark input and verification.
- [Engineering guide](docs/ENGINEERING.md): source map, settings, commands, upgrades and troubleshooting.
- [Agent guide](AGENTS.md): where coding agents should start.
- [Contributing](CONTRIBUTING.md), [security](SECURITY.md), [changelog](CHANGELOG.md) and [MIT license](LICENSE).

SaveMeTibo is an independent community source, not confirmation of your personal account balance. TiboWatch is not affiliated with OpenAI, Tibo, X, Bark or SaveMeTibo.
