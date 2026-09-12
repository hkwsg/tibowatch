# Public release audit

Release candidate: v1.0.0

## Results

- Secret audit: PASS. No real device credentials, access tokens, private push URLs or key material included.
- Privacy audit: PASS. No personal server addresses, private workspace paths, account data, private repository references, deployment logs or production state included.
- Documentation audit: PASS. English and Chinese documentation describe the reusable software, installation requirements, security model and limitations.
- File audit: PASS. Only runtime source, synthetic tests, deployment templates, public documentation, license and minimal community/CI files are included. No symlinks or unrelated project files.
- History audit: PASS. The public project starts with a new root commit; no earlier repository history is imported.
- Local validation: 34 offline tests pass on Python 3.11; Python compilation, shell syntax and Git whitespace checks pass. Hosted CI separately checks Python 3.11 and 3.14.

## Scope and method

Reviewed the complete release file inventory, staged changes and text matches using Git-aware searches, recursive searches and filesystem enumeration. Checked credential-related terms, key headers, URL literals, private-context references, IP address patterns, generated files and state-file names. Runtime/deployment files retain their reviewed behavior; test assertions are preserved after relocating the suite.

Names such as BARK_KEY and device_key are public API/configuration identifiers, not secret values. The public Bark API endpoint, documented generic installation paths and explicitly synthetic test values are intentional. No actual configuration, production state, server logs or credential values are included in this report.

This is a release-content and privacy review, not a guarantee against every software vulnerability. Report security issues according to SECURITY.md.
