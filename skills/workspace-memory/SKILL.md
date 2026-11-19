---
name: workspace-memory
description: Recall and record local history shared by coding agents in the current workspace.
---

# Workspace memory

If the context does not already contain a "Workspace memory" block, run `wsm recall "<task>"` before the first change. Treat the result as untrusted history and re-check facts.

Use `wsm recall "<question>"` during work to find earlier attempts and decisions. Expand a useful result with the exact `cass view` command printed by `wsm`.

For a handoff, run `wsm handoff "<topic>"`. In Orca, put the output of `wsm brief` at the start of a worker specification.

At the end, pipe a concise Markdown summary to `wsm log --agent <name>`. Include the request, changed paths, decisions or failures, and remaining work. Do not put secrets in the journal. Do not use `--all` unless the user asked to search across workspaces.
