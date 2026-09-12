# Contributing

Keep TiboWatch small: Python standard library, a single public feed, local state, and systemd deployment. Discuss changes that add dependencies or alter notification behavior before implementing them.

1. Fork the repository and create a focused branch.
2. Preserve the existing offline test coverage. Add meaningful synthetic regression cases for behavior changes.
3. Run:

   ```sh
   python3 -m unittest discover -s tests -v
   python3 -m py_compile watcher.py
   git diff --check
   ```

4. Describe the problem, the resulting behavior and actual validation in your pull request. Update both READMEs when user-facing instructions change.

Tests must use temporary state and mock network calls. Do not run the installer on a shared host as part of tests, send real notifications from CI, or commit credentials, device addresses, live state, logs or personal infrastructure details. Credential-like strings in tests are deliberately synthetic.

By contributing, you agree that your contribution may be distributed under this project's MIT license. Report vulnerabilities as described in SECURITY.md.
