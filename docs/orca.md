# Orca and workspace-memory

Orca and workspace-memory solve different parts of multi-agent work. Orca coordinates live work through tasks, messages and handoffs. workspace-memory recalls finished work from local agent history and journals.

Orca gives each task its own linked worktree, but workspace-memory treats the Git repository as the identity. Every task worktree shares the journal in the main working tree, and wsm keeps a small registry of worktree paths it has seen. Recall therefore includes sessions from current and removed task worktrees, while the journal remains after Orca cleans a worktree up.

For a bare repository with linked worktrees, the shared journal lives at `<common-dir>/agent-memory/journal/`. Non-Git Orca folder workspaces keep their existing folder-local memory.

Put this at the top of every worker specification:

```sh
wsm brief
```

Paste its output into the `orca orchestration worker-start --spec` text. This gives the worker an explicit recall and logging contract even when that agent has no session hook.

Use `wsm handoff "<topic>"` when a finished agent needs to give another agent a compact, evidence-backed brief. Paste the redacted Markdown it prints into the handoff specification.

A coordinator may use `wsm recall --all "<topic>"` to look across workspaces. This is deliberately explicit, prints a warning and still excludes every path on the private-workspace list. Marking a repository's main working tree private also covers all of its current and recorded worktrees.

Orca-launched Codex sessions use account-specific home directories under Orca's application support directory. cass already discovers and indexes those locations, so no Orca session export is needed.

For the full picture, including diagrams of a worker hand-off, see [architecture.md](architecture.md).
