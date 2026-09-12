# Changelog

## v1.1.0 (unreleased)

- Forward published SaveMeTibo RSS title/description instead of interpreting status.json events.
- Try one local gpt-5.6-luna translation per new/changed alert; fall back immediately to original English on any error.
- Persist the selected exact payload across Bark retries; never retranslate retries or silently truncate.
- Keep atomic state, backup, lock, retry limits and secure Bark configuration.
- Baseline RSS on v1 migration, preserve the installation test, refuse unresolved pending notifications.
- Keep source failures local; remove automatic Bark editorial/health notifications.

## v1.0.0

Initial public release.

- SaveMeTibo signal polling
- Bark iOS notifications
- Semantic deduplication
- Watch / confirmed / landed lifecycle
- Correction handling
- Linked team_hint updates
- Stale/outage monitoring
- Persistent retry queue
- systemd deployment
