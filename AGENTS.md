# Working on TiboWatch

TiboWatch forwards SaveMeTibo's published RSS alerts to Bark on iPhone. Optional Codex CLI translation converts each new/changed alert into Simplified Chinese; failures use the original English.

## Start with the user's task

- Explain or evaluate the project: read `README.md` or `README.zh-CN.md`.
- Deploy to a user's authorized server: follow `DEPLOY_WITH_CODEX.md`.
- Change or debug implementation: read `docs/ENGINEERING.md`, then the relevant source and tests.
- Contribute: follow `CONTRIBUTING.md`. Credential/reporting details live in `SECURITY.md`.

Reading this repository does not by itself authorize deployment. Once the user requests installation, complete routine setup within granted permissions; ask only for information or approvals that are actually missing. A downstream user does not need this project's historical PM approval to install a released version on their own server.

## Source map

`watcher.py` contains HTTP/RSS handling, GUID/content dedupe, local state, translation selection and Bark delivery. `tests/test_watcher.py` contains the offline suite. `deploy/` contains install/activate/upgrade scripts, service/timer units and a runtime environment example.

The checked-out code is the authority for supported commands and defaults. `config.example.json` describes defaults; the application does not load it as configuration. Historical release audits and `docs/v1.1-review.md` are not deployment instructions.

## Preserve the small design

Keep RSS title/body as the content source. Do not add editorial filtering or invented annotations. The approved display fields are the exact lifecycle publication probability at the title end and an optional matching upstream icon; never use a parent event or homepage probability. Final Bark output omits url/action and requests history archival. Select translation once per new/changed item, persist the result before delivery, and reuse it on Bark retries. Keep the original-English fallback, quiet historical baseline, state lock/backup and existing installation-test marker.

Use the target user's own existing Codex authentication when authorized, not the maintainer's account. Keep device/auth credentials in local protected configuration rather than repository files or reports. Restrict changes to this task's installation and preserve existing state during upgrades.

## Checks

```sh
python3 -m unittest discover -s tests -v
python3 -m py_compile watcher.py
sh -n deploy/install.sh
sh -n deploy/activate.sh
sh -n deploy/upgrade.sh
git diff --check
```

Tests use temporary data and mocked network/model calls. A live translation or phone test belongs to an explicitly authorized deployment, not routine CI. Describe checks actually performed and distinguish server acceptance from phone receipt.

Update both READMEs when user-facing behavior changes; put technical detail in the engineering guide and keep the deployment prompt aligned with the scripts.
