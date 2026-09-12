# Contributing to TiboWatch

Useful contributions include fixes, clearer setup instructions and focused improvements to RSS forwarding. Start with [AGENTS.md](AGENTS.md) and [the engineering guide](docs/ENGINEERING.md).

Fork the repository and use a focused branch. Describe the problem and the resulting behavior in your pull request. Discuss larger changes before adding dependencies or changing notification semantics; the project is intentionally small.

## Check your change

```sh
python3 -m unittest discover -s tests -v
python3 -m py_compile watcher.py
sh -n deploy/install.sh
sh -n deploy/activate.sh
sh -n deploy/upgrade.sh
git diff --check
```

Use temporary state and mocked RSS, Bark and CLI calls in tests. Real phone/model requests belong to an authorized deployment check, not CI. Include regression coverage for behavior changes.

For documentation, verify relative links and commands against the checkout, keep both READMEs aligned, and update the deployment prompt when setup changes. Report what was actually checked; a test count alone does not describe deployment coverage.

Keep credentials and personal runtime files out of commits. Report vulnerabilities through [SECURITY.md](SECURITY.md). Contributions are distributed under the project's [MIT license](LICENSE).
