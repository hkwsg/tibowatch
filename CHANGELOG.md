# Changelog

## v1.1.0 — 2026-09-13

- Forward published SaveMeTibo RSS alerts instead of interpreting status.json events.
- Translate each new/changed alert once through the local Codex CLI; use the original English on failure.
- Persist the selected notification across Bark retries without retranslation or silent truncation.
- Reuse the deploying user's existing Codex login with a minimal local service auth context.
- Allow 30 seconds for translation and 240 seconds for a service run.
- Preserve state safety, quiet RSS initialization and existing installation-test markers during v1 migration.
- Add a standalone Codex deployment prompt, agent navigation and clearer English/Chinese documentation.
- Keep source failures in local status rather than adding Bark commentary or health alerts.

## v1.0.0

Initial public release.

- SaveMeTibo signal polling and Bark iOS notifications.
- Semantic deduplication, reset lifecycle, corrections and linked team hints.
- Persistent retries, source-health monitoring and systemd deployment.
