# Changelog

## v1.1.2 — 2026-09-13

- Add an optional fixed notification icon via `TIBOWATCH_ICON_URL`.
- Include the final owner-approved PNG and pin the example URL to its immutable commit.
- Persist the selected icon with each alert; configuration changes do not alter pending retries.
- Keep the existing upstream-icon fallback, text-first payload budget, RSS/translation behavior and state v2 compatibility.

## v1.1.1 — 2026-09-13

- Omit Bark external click URLs and request history archival, including pending retries.
- Append the matching SaveMeTibo publication probability to the notification title.
- Preserve upstream emoji and optionally reuse matching upstream PNG icons.
- Keep RSS dedupe, one Luna translation, English fallback and state v2 compatibility; no repeat migration or credential setup.

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
