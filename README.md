# workspace-memory

workspace-memory gives coding agents a shared, local memory for each workspace. A fresh Claude Code, Codex, Grok, Gemini CLI or other agent can see what earlier agents tried, changed and decided without sending project history to a hosted memory service.

It has three layers:

1. **Journal:** short session notes in `.agent-memory/journal/YYYY-MM-DD.md`, or an existing `.memsearch/memory/` directory.
2. **History:** [cass](https://github.com/Dicklesworthstone/coding_agent_session_search) indexes local session files from more than 30 coding agents.
3. **Delivery:** supported session hooks inject a compact recall block. Global instructions cover agents without hooks.

There are no LLM calls, telemetry or uploads. The only network use is installation, when the installer downloads cass and its licence from GitHub.

## Get it

```sh
git clone https://github.com/nocodedltd/workspace-memory.git
cd workspace-memory
./install.sh --dry-run
```

Or let your coding agent do it. Paste this into Claude Code, Codex or Grok:

> Clone https://github.com/nocodedltd/workspace-memory and follow its AGENT-INSTALL.md to set it up for me. Show me what it will change before installing.

**How it works, with diagrams:** [docs/architecture.md](docs/architecture.md) explains how cass, memsearch and Orca orchestration fit together. Running several agents in Orca? [docs/orca.md](docs/orca.md) has the short version.

## Requirements

- macOS or Linux, including WSL. Windows native is not supported.
- Python 3.9 or newer, `curl`, `tar`, and either `shasum` or `sha256sum`.
- About 5 GB free for a large cass index. Small histories use less.

## Install

First inspect what would change:

```sh
./install.sh --dry-run
```

Then install interactively:

```sh
./install.sh
```

cass has an unusual MIT-derived licence rider that grants no rights to OpenAI, Anthropic, their affiliates or representatives. The installer displays that licence and asks for acceptance. Read [THIRD-PARTY.md](THIRD-PARTY.md) before using `--accept-cass-licence` in an unattended install.

Useful options:

```sh
./install.sh --agents claude,codex,gemini
./install.sh --no-hooks --no-schedule
./install.sh --copy
./install.sh --yes --accept-cass-licence
```

By default `wsm` is symlinked from `~/.local/bin/wsm` to this checkout. `--copy` installs a standalone copy. An existing cass 0.11.0 or newer is reused from its absolute path, so the installer never shadows or downgrades it. The first cass index runs as a detached, low-priority background job and logs to `~/.local/state/workspace-memory/index.log`. It is incremental when cass already reports an existing healthy, fresh index; otherwise it performs a full index.

The installer may change:

- `~/.local/bin/wsm`, and `~/.local/bin/cass` only when no compatible cass is present;
- marked instruction blocks in supported agent instruction files;
- additive session hook entries for verified agents;
- workspace-memory skill directories for Claude Code and Codex;
- one launchd agent, systemd user timer or marked crontab line;
- config, backups and logs under the normal user config and state directories.

It backs up each regular configuration file before its first change. It never writes through a symlinked settings, instruction or skill path. Existing skill directories that were not installed by this kit are backed up before replacement, and uninstall only removes skill directories carrying the kit's marker.

## Start using it

From a repository or workspace:

```sh
wsm init
wsm recall "the task I am about to start"
```

`wsm init` creates the journal and adds `.agent-memory/` to `.git/info/exclude`. It does not alter `.gitignore` unless you explicitly use `wsm init --share`. Use `wsm init --cursor` to add a workspace Cursor rule.

`wsm log` applies the same local Git exclusion before creating a journal. Automatic logging defaults to initialised workspaces, meaning the resolved workspace root must already contain `.agent-memory/` or `.memsearch/`; sessions recorded from a subfolder still journal at that root. It never writes to the home directory itself or temporary and system directories. Set `autolog_scope` to `all` only if automatic notes should also be created in other ordinary workspaces.

At the end of work:

```sh
printf '%s\n' \
  '- Asked to repair the upload flow.' \
  '- Changed src/upload.ts and tests/upload.test.ts.' \
  '- Kept streaming because buffering failed on large files.' \
  '- Nothing remains.' | wsm log --agent codex
```

During work:

```sh
wsm recall "was streaming already tried?"
wsm sessions --limit 10
wsm handoff "upload flow"
wsm brief
```

The `cass view` command printed after each search match expands the original evidence.

## CLI overview

| Command | Purpose |
|---|---|
| `wsm recall [QUERY]` | Journal, recent sessions and deduplicated cass matches within a context budget |
| `wsm log` | Append a human-readable session note, refusing likely secrets |
| `wsm sessions` | List recent sessions from all agents in this workspace |
| `wsm handoff [QUERY]` | Build a redacted cass answer pack for another agent |
| `wsm autolog` | Add deterministic notes for unlogged completed sessions |
| `wsm refresh` | Incrementally index, reapply privacy exclusions and autolog |
| `wsm private add PATH` | Remove a workspace from cass and keep it excluded |
| `wsm init` | Initialise a workspace journal and local Git exclusion |
| `wsm doctor --json` | Inspect cass, selected-agent hooks and instructions, scheduler, privacy and disk space |
| `wsm config` | Read or set local configuration |

Workspace resolution uses the nearest ancestor containing `.agent-memory/`, then `.memsearch/`, then `.git`; otherwise it uses the current directory. cass 0.11.0 records an exact workspace on each session. `wsm` asks cass for recent sessions, then includes exact-root and descendant workspace paths client-side. Search itself is scoped to the resolved root, which matches cass's exact workspace field.

## Privacy and safety

Searches are scoped to the current workspace by default. `wsm recall --all` is explicit, prints a warning, and still filters private paths.

Exclude an NDA or sensitive workspace before indexing it:

```sh
wsm private add /absolute/path/to/client
wsm private list
```

This applies `cass forget --workspace-glob '<path>/**' --apply`. cass 0.11.0 stores durable tombstones, so later indexing does not restore forgotten sessions. `wsm refresh` reapplies the exclusions as defence in depth. `wsm private remove PATH` explicitly releases matching tombstones and allows a later index to include the sessions again.

Recall, handoff and automatic journal text redact common OpenAI, Anthropic, GitHub, Slack, AWS, 1Password, Cloudflare and bearer tokens, JWTs, PEM private keys and long named secret values. Manual `wsm log` refuses text that looks like any of these rather than silently altering the note.

Recalled session text is untrusted. Every recall block labels it as history rather than instructions. Re-check important facts against current files and systems.

Set `CASS_RAW_MIRROR=0` in hooks and scheduler jobs to avoid duplicate raw session copies. The installer does not silently edit shell profiles.

## Agent support

| Agent | Automatic hook | Global instructions | Skill |
|---|---:|---:|---:|
| Claude Code | SessionStart and SessionEnd | `~/.claude/CLAUDE.md` | `~/.claude/skills/` |
| Codex | Not installed, current injected-context schema was not verifiable from installed help | `~/.codex/AGENTS.md` | `~/.codex/skills/` |
| Grok CLI | SessionStart and SessionEnd | `~/.grok/AGENTS.md` | Reads Claude skills |
| Gemini CLI | SessionStart and SessionEnd | `~/.gemini/GEMINI.md` | None |
| OpenCode | None | `~/.config/opencode/AGENTS.md` | None |
| Cursor | None | `wsm init --cursor` | None |
| Other cass-supported agents | None | Paste `templates/instructions.md` into that agent's rules | None |

Codex 0.169 reports a stable hooks feature but its own help does not document `hooks.json` SessionStart or SessionEnd injection. The installer therefore uses instructions rather than guessing a schema. Gemini CLI 0.63 documents both events and `hookSpecificOutput.additionalContext`. Grok 1.0.88 documents matching Claude-style event tables.

## Configuration

Configuration lives at `~/.config/workspace-memory/config.toml`:

```toml
[workspace_memory]
journal_dir = "auto"
days = 14
budget = 1500
refresh_minutes = 30
raw_mirror = false
autolog_scope = "initialised"
cass_path = "/absolute/path/to/cass"
private_workspaces = []
tz = ""
```

Use `wsm config set budget 1000` or `wsm config get budget`. The installer records the selected cass executable in `cass_path`; `WSM_CASS` can override it for one process. Set `WSM_TZ` to an IANA time zone for a one-off journal time override. Semantic search is optional and out of scope; users who want it can run `cass models install` separately.

## Uninstall

```sh
./uninstall.sh
```

This removes marked instruction blocks, hook entries identified by their `wsm hook` command, the scheduler, kit-marked skills and the `wsm` link. It does not restore stale backup files and never deletes workspace journals.

To also remove the cass binary installed by this kit and cass's local index:

```sh
./uninstall.sh --purge
```

The purge asks for confirmation.

## Troubleshooting

**The index is stale:** run `wsm refresh`, then inspect `~/.local/state/workspace-memory/refresh.log` and `cass health`. `wsm doctor` reports the last refresh time and result. If another cass index is already running, refresh records a successful skipped result instead of a warning.

**Doctor reports an agent you did not install:** a normal installation reads the selected agents from its receipt. Without a receipt, doctor falls back to detecting agent directories and executables on the machine.

**A hook does not fire:** run `wsm doctor`, inspect `~/.local/state/workspace-memory/hooks.log`, and check the agent's hook trust UI. Hooks always exit successfully so a memory failure cannot break an agent session.

**A read-only sandbox cannot run `cass sessions`:** `wsm recall` continues with the journal and search results, or prints a one-line omission. `cass search --no-maintenance` remains read-only.

**The index uses too much disk:** inspect `cass storage`. Delete it only with `./uninstall.sh --purge`, or use cass's documented retention controls. The optional semantic model consumes extra space and is not installed here.

**Configuration is symlinked:** the installer reports "managed elsewhere" and skips the file. Add the marked block or hook at the symlink source using that configuration system.

**`~/.local/bin` is not on PATH:** add `export PATH="$HOME/.local/bin:$PATH"` to the shell environment file you manage. The installer prints this line but never edits the profile.

## Scope

The kit deliberately does not provide a hosted service, remote or multi-machine sources, Windows-native support, semantic model downloads or the separate cass-memory playbook layer. Remote sources may be considered in a future version.
