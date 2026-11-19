# Security policy

## Reporting a vulnerability

Please report security issues privately, not in a public issue.

Use GitHub's private reporting: open the **Security** tab of this repository and choose **Report a vulnerability**. Include what you found, how to reproduce it, and what an attacker could do with it.

You'll get an acknowledgement within five working days. Please give us a reasonable chance to fix the issue before you disclose it publicly.

## What is in scope

- `bin/wsm`, `install.sh`, `uninstall.sh` and the templates they write.
- Anything that could make workspace-memory send data off the machine, write outside the paths documented in the README, write through a symlink, leak a journal into git, surface a private workspace, or fail to redact a secret.
- The website in `site/`.

## What is not

- Vulnerabilities in [cass](https://github.com/Dicklesworthstone/coding_agent_session_search), memsearch, Orca or the coding agents themselves. Report those to their own maintainers.

## Supported versions

Only the latest commit on `main` is supported.
