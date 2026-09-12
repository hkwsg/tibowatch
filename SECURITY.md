# Security

## Private configuration

A Bark push address contains a device key. Enter it through the deployment's private input; the non-echoing local option avoids adding it to chat history. If supplied in a private deployment conversation, use it only for that authorized setup and keep it out of public issues, repository files and reports.

Codex login files contain account credentials. Provision only the deploying user's authorized minimal auth context locally; do not ask them to paste auth.json into a conversation. Keep the service auth directory 0700 and auth file 0600. Bark configuration remains root-owned 0600. If a credential is exposed, replace it using the relevant service and update the local configuration.

## Runtime model

The watcher runs as a dedicated non-root user, opens no inbound port, verifies TLS and keeps writable state separate from installed code. Translation passes public alert text to the user's existing Codex CLI account; Bark keys are excluded from that subprocess. Translation failures use English. Detailed paths and controls are in [the engineering guide](docs/ENGINEERING.md).

These controls assume a trusted host. They do not make a compromised server safe or guarantee third-party source availability.

## Reporting a vulnerability

Security fixes target the latest v1 release. Use GitHub private vulnerability reporting in this repository's Security tab when available. Otherwise open a minimal issue requesting a private contact channel, without sensitive details.

Include the affected version and a small reproduction using synthetic data. Keep real credentials, device addresses and personal server logs out of public reports.
