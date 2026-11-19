# Orca and workspace-memory

Orca and workspace-memory solve different parts of multi-agent work. Orca coordinates live work through tasks, messages and handoffs. workspace-memory recalls finished work from local agent history and journals.

The workspace root is the Orca worktree path. Put this at the top of every worker specification:

```sh
wsm brief
```

Paste its output into the `orca orchestration worker-start --spec` text. This gives the worker an explicit recall and logging contract even when that agent has no session hook.

Use `wsm handoff "<topic>"` when a finished agent needs to give another agent a compact, evidence-backed brief. Paste the redacted Markdown it prints into the handoff specification.

A coordinator may use `wsm recall --all "<topic>"` to look across workspaces. This is deliberately explicit, prints a warning and still excludes every path on the private-workspace list.

Orca-launched Codex sessions use account-specific home directories under Orca's application support directory. cass already discovers and indexes those locations, so no Orca session export is needed.
