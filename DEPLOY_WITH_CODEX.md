# Deploy TiboWatch with Codex / 交给 Codex 部署

Use this file as a standalone prompt for an agent that can operate your Linux server. After downloading the repository, ask: **Read DEPLOY_WITH_CODEX.md and deploy TiboWatch on my authorized server.**

把这份文件交给能操作服务器的 Codex 即可。正常情况下，你只需按提示提供 Bark 地址，并确认手机收到测试。下面是完整执行提示词；agent 应使用用户的语言交流。

---

## Deployment task

Deploy TiboWatch from `https://github.com/hkwsg/tibowatch` on the Linux server I have authorized you to use. Aim to complete setup, rather than only returning commands for me to run. Reuse the supplied repository checkout and server context when available.

Read this prompt and the repository guidance, then the selected version's README and deployment scripts. Read `AGENTS.md` and `docs/ENGINEERING.md` when present; older releases may not contain these new guides. Give one brief setup summary, then perform routine steps within granted permissions. Ask only for missing target access, the Bark address, necessary permission prompts and phone confirmation. Do not ask me to choose an architecture or repeat information already supplied.

### 1. Identify the target and version

Use the current server or the authorized SSH connection I have named. Check the OS, systemd, Python, installation permissions and whether TiboWatch already exists. Use a persistent server, not an unrelated temporary chat environment. If you have no execution access to the target, explain that in one sentence and provide the handoff for a Codex session that does.

Use my specified version; otherwise use the published `v1.1.0` tag for this guide. Pin and report the selected tag/commit. The [fixed release entry](https://github.com/hkwsg/tibowatch/blob/v1.1.0/DEPLOY_WITH_CODEX.md) describes the RSS-based implementation: verify the selected code reads `feed.xml` and contains the documented entry points. Do not silently substitute the older non-RSS v1.0.0 or an unreleased `main`. If I explicitly request a different release, follow that version's documentation.

### 2. Prepare the supported environment

The supplied installation targets Linux with systemd and Python 3.11+. Reuse installed tools. Install only missing prerequisites covered by my installation authorization; use the normal permission prompt if required. An existing working installation follows the update path below, not fresh setup.

Run the repository's offline checks. On a fresh target, run `sudo sh deploy/install.sh` from the selected checkout root to install the dedicated service user, code and units. The script does not enable the timer or configure translation automatically.

### 3. Set up optional translation

Check the existing Codex executable and login without displaying credential contents. I authorize reuse of my existing local ChatGPT/Codex login for this deployment when available. For file-based authentication, provision only the necessary auth cache to the service-side Codex home, with its owner and permissions as described in the engineering guide. Preserve the original login.

Populate `/etc/tibo-watch/runtime.env` from the example using the actual executable path and service-side `CODEX_HOME`. Keep the service non-root and retain its isolation. Check the chosen version's model and timeout instead of assuming a model is available to every account.

When translation is available, use one synthetic title/body to verify it with the service identity, environment and resource limits, without sending a phone notification or changing the live RSS state. Translation takes one attempt; it does not require another account, an API key, a daemon or a different model. If CLI/auth/model access is unavailable, finish an English-only installation and report that clearly. Do not treat an English fallback as a successful Chinese translation.

### 4. Ask for the Bark address once

If it has not already been provided or configured, ask in the user's language:

> 请打开 iPhone 上的 Bark，复制它显示的推送地址，然后粘贴到本次私有部署的配置输入处。它通常类似 https://api.day.app/你的设备Key。

Prefer a non-echoing terminal or secret input. If I already supplied the address in this private deployment conversation, use it for the authorized local configuration without requesting it again. Do not repeat the complete address in your response, command-line arguments, logs or repository files. Never request it in a public GitHub issue. The local-input option avoids adding the address to chat history.

Validate the URL locally. The current configuration supports the HTTPS `api.day.app` origin. If Bark copied a sample URL with a notification title/body after the device key, normalize it to the base device address locally before passing it to the existing configuration logic. Require the exact HTTPS `api.day.app` authority (no userinfo or explicit port), take the first path segment as the device key and validate it as 8–256 ASCII letters, digits, underscores or hyphens. Strip only the sample title/body suffix and query/fragment; reject unsupported origins or invalid keys. The CLI itself accepts only the base address without query/fragment, not the copied sample URL. Do not open the push URL just to check it: that can send a notification.

Use `sudo python3 /opt/tibo-watch/watcher.py configure-bark` in a non-echoing terminal, or an equivalent authorized secret-input path that applies the same validation and protected file permissions. Save only to the task's local configuration. Reuse a valid existing Bark configuration on updates.

### 5. Activate and verify

For a fresh installation, run `sudo /opt/tibo-watch/activate.sh`. It sends one labeled installation test, establishes a healthy RSS baseline and enables the timer. Preserve its attempt marker, so repeating setup does not replay the test or historical alerts. If the test result is uncertain or activation fails, inspect the recorded state and timer status; do not delete the marker, automatically resend the test or claim activation succeeded.

Check the configured source, state initialization, pending count, service result and timer enabled/active state. A finished oneshot being inactive is normal. `Result=success` alone does not prove a healthy source: source failures can be recorded in state with exit code zero. Verify a fresh successful source fetch and no health reason as well. Check the repeated-poll result without inventing new RSS business items. Genuine new upstream content during setup can legitimately produce a separate alert; distinguish it from the installation test.

Ask me once whether the iPhone received the test. Record server acceptance separately from my confirmation. If I have not replied, report that phone receipt remains unconfirmed rather than inventing it. The deployment can otherwise report its actual running state.

### Existing installation: preserve it

First check its installed code, state version and timer. An already-correct installation may need only verification. Preserve Bark/auth configuration, state and test markers.

For an authorized state-v1 to RSS/state-v2 update, follow the documented `upgrade.sh` path and resolve pending items before migration. For an installation already using state v2, use ordinary code/unit maintenance; do not repeat the v1 migration or reset the baseline. Back up the matching code/state and pause only this task while updating. On a failed update, explain what is running or paused and the recovery action; do not label it complete.

### Completion report

Return a short summary containing:

- Selected tag/commit and installation location.
- RSS/source check and timer/service status.
- Translation: verified Chinese, English-only, or enabled but not verified.
- Bark: service accepted / failed / not tested; phone receipt: confirmed / unconfirmed.
- Any remaining action, plus the status and pause commands.

Keep setup focused on TiboWatch. Leave SSH, networking and unrelated applications as they were, and keep credentials out of shared artifacts. Do not publish a deployment report containing the user's host or device details to the upstream repository.
