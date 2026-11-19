# Changelog

## 0.1.1, 2026-11-19

- Shared one repository journal across linked worktrees, kept it after worktree cleanup and recalled sessions from current and recorded former worktrees.
- Wrote local exclusions to Git's common directory, including for submodules, and kept bare-repository journals inside the common directory.
- Extended repository privacy to all known worktrees and read worktree-local memsearch notes alongside the shared journal.
- Prevented journal leakage by applying the local Git exclusion whenever `.agent-memory` is created.
- Restricted automatic logging to initialised workspaces by default and excluded home, temporary and system directories.
- Made skill installation and removal symlink-safe and ownership-aware.
- Reused compatible cass installations, recorded their absolute path and embedded the real Python interpreter in scheduler jobs, including behind pyenv or asdf shims.
- Added memsearch-aware deduplication, root-aware autologging for sessions started in workspace subfolders, refresh status diagnostics, resilient hook input handling and correctly quoted hook commands.
- Improved non-interactive licence errors and honoured the configured raw-mirror setting during the first index.
- Detached the background first index from installer streams and avoided a redundant full rebuild when cass already has a healthy, fresh index.
- Treated cass index contention as a successful skipped refresh and limited doctor checks to agents selected in the install receipt.
- Expanded regression coverage for every review finding.

## 0.1.0, 2026-11-19

- Initial local-first workspace memory kit.
- Added journal, cass history, automatic recall hooks, installer, uninstaller, privacy controls and Orca guidance.
