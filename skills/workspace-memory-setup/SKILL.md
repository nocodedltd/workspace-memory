---
name: workspace-memory-setup
description: Install, repair, diagnose or uninstall workspace-memory for a user.
---

# Set up workspace-memory

Read `README.md` and `THIRD-PARTY.md` before installing. Explain that cass has a licence rider excluding OpenAI, Anthropic and their representatives, then obtain the user's acceptance. Run `./install.sh --dry-run` first. Never pass `--accept-cass-licence` until the user has accepted it.

Use `./install.sh` for installation, `wsm doctor --json` for diagnosis, and `./uninstall.sh` to reverse changes. Use `./uninstall.sh --purge` only when the user also wants the cass binary and local cass index removed. Workspace journals are deliberately retained.

Do not write through symlinked instruction or settings files. The installer reports those as managed elsewhere. Add the marked instruction block at the symlink source only if the user has explicitly included that managed source in scope.
