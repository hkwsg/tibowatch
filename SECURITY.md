# Security

## Supported versions

Security fixes target the latest v1 release. Update to the latest patch before reporting a problem.

## Reporting a vulnerability

Use GitHub's private vulnerability reporting entry under this repository's Security tab when available. Do not include real device keys, private push addresses, credentials or server logs in a public issue. If private reporting is unavailable, open a minimal issue asking for a private reporting channel without disclosing exploit details or sensitive data.

Include the affected version, expected and actual behavior, and a minimal reproduction using synthetic data. Do not test against somebody else's device or infrastructure. There is no guaranteed response-time commitment.

## Handling secrets

Treat your Bark device key as a credential. Use the hidden-input configuration command in a trusted terminal; never paste the key into GitHub, chat, screenshots or command-line arguments. If exposed, replace it through the Bark service/app and update the protected local configuration. Restrict access to backups as well as live configuration.

The service uses a dedicated non-root user, verifies TLS, opens no inbound port and only writes its task state directory. These controls do not protect a compromised host or replace operating-system security updates. Public notification content passes through the selected Bark service.

## Optional translation

When enabled, newly published alert text is sent to the local Codex CLI and its model provider for translation. Bark credentials are excluded from the subprocess environment. Authentication remains the CLI's responsibility; do not copy another user's login files or weaken permissions to make them accessible to the watcher account. RSS content is untrusted input, not executable instructions.
