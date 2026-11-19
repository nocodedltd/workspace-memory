#!/usr/bin/env bash
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1

ROOT=$(cd -- "$(dirname -- "$0")" && pwd)
AGENTS=auto
NO_HOOKS=0
NO_SCHEDULE=0
NO_INSTRUCTIONS=0
NO_GLOBAL_IGNORE=0
DRY_RUN=0
YES=0
COPY=0
ACCEPT=0
CASS_VERSION=0.11.0
MINIMUM_CASS_VERSION=0.11.0

usage() {
  echo "Usage: ./install.sh [--agents auto|claude,codex,grok,gemini,opencode] [--no-hooks] [--no-schedule] [--no-instructions] [--no-global-ignore] [--cass-version X] [--accept-cass-licence] [--copy] [--dry-run] [--yes]"
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --agents) AGENTS=$2; shift 2 ;;
    --no-hooks) NO_HOOKS=1; shift ;;
    --no-schedule) NO_SCHEDULE=1; shift ;;
    --no-instructions) NO_INSTRUCTIONS=1; shift ;;
    --no-global-ignore) NO_GLOBAL_IGNORE=1; shift ;;
    --cass-version) CASS_VERSION=${2#v}; shift 2 ;;
    --accept-cass-licence) ACCEPT=1; shift ;;
    --copy) COPY=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    --yes) YES=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

case "$(uname -s)" in
  Darwin) OS=darwin ;;
  Linux) OS=linux ;;
  *) echo "workspace-memory supports macOS and Linux (including WSL), not Windows native." >&2; exit 2 ;;
esac
case "$(uname -m)" in
  arm64|aarch64) ARCH=arm64 ;;
  x86_64|amd64) ARCH=amd64 ;;
  *) echo "Unsupported architecture: $(uname -m)" >&2; exit 2 ;;
esac

for dependency in python3 curl tar; do
  command -v "$dependency" >/dev/null 2>&1 || { echo "Missing dependency: $dependency" >&2; exit 2; }
done
python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)' || { echo "Python 3.9 or newer is required." >&2; exit 2; }
absolute_path() {
  python3 -c 'import os,sys; print(os.path.abspath(sys.argv[1]))' "$1"
}
PYTHON_PATH=$(python3 -c 'import sys; print(sys.executable)')
if command -v shasum >/dev/null 2>&1; then
  HASH_COMMAND=shasum
elif command -v sha256sum >/dev/null 2>&1; then
  HASH_COMMAND=sha256sum
else
  echo "Missing dependency: shasum or sha256sum" >&2
  exit 2
fi

if [ "$AGENTS" = auto ]; then
  detected=""
  for pair in "claude:$HOME/.claude" "codex:$HOME/.codex" "grok:$HOME/.grok" "gemini:$HOME/.gemini" "opencode:$HOME/.config/opencode"; do
    agent=${pair%%:*}
    directory=${pair#*:}
    if [ -d "$directory" ] || command -v "$agent" >/dev/null 2>&1; then
      detected=${detected:+$detected,}$agent
    fi
  done
  AGENTS=${detected:-claude,codex}
fi

echo "workspace-memory will:"
echo "  install wsm under $HOME/.local/bin"
echo "  use or install cass $CASS_VERSION"
echo "  configure agents: $AGENTS"
[ "$NO_HOOKS" -eq 1 ] && echo "  skip hooks"
[ "$NO_INSTRUCTIONS" -eq 1 ] && echo "  skip global instructions"
[ "$NO_SCHEDULE" -eq 1 ] && echo "  skip the refresh schedule"
[ "$NO_GLOBAL_IGNORE" -eq 0 ] && echo "  add .memsearch/ and .agent-memory/ to the global Git excludes"
[ "$NO_GLOBAL_IGNORE" -eq 1 ] && echo "  skip global Git excludes"
echo "  keep all journals and search data on this machine"

if [ "$DRY_RUN" -eq 1 ]; then
  echo "Dry run complete. Nothing changed."
  exit 0
fi
if [ "$YES" -ne 1 ]; then
  printf "Continue? [y/N] "
  read -r answer
  case "$answer" in y|Y|yes|YES) ;; *) echo "Cancelled."; exit 1 ;; esac
fi

if [ "$NO_GLOBAL_IGNORE" -eq 0 ]; then
  if command -v git >/dev/null 2>&1; then
    global_ignore=$(git config --global --path --get core.excludesFile 2>/dev/null || true)
    if [ -z "$global_ignore" ]; then
      global_ignore="$HOME/.config/git/ignore"
      mkdir -p "$(dirname "$global_ignore")"
      git config --global core.excludesFile "$global_ignore"
    else
      global_ignore=$(python3 - "$global_ignore" "$HOME" <<'PY'
import os, sys
value = os.path.expanduser(sys.argv[1])
print(value if os.path.isabs(value) else os.path.join(sys.argv[2], value))
PY
)
      mkdir -p "$(dirname "$global_ignore")"
    fi
    touch "$global_ignore"
    for ignore_entry in '.memsearch/' '.agent-memory/'; do
      grep -Fqx "$ignore_entry" "$global_ignore" || printf '%s\n' "$ignore_entry" >> "$global_ignore"
    done
    echo "Global Git excludes updated at $global_ignore."
  else
    echo "Warning: git is unavailable, so global memory excludes were not added."
  fi
fi

STATE="$HOME/.local/state/workspace-memory"
BIN="$HOME/.local/bin"
timestamp=$(date +%Y%m%d-%H%M%S)
BACKUP="$STATE/backups/$timestamp"
mkdir -p "$STATE" "$BIN" "$BACKUP"

cass_installed=0
cass_ok=0
CASS_PATH=""
version_at_least() {
  python3 - "$1" "$2" <<'PY'
import re, sys
def parts(value):
    numbers = [int(item) for item in re.findall(r"\d+", value)[:3]]
    return tuple((numbers + [0, 0, 0])[:3])
raise SystemExit(0 if parts(sys.argv[1]) >= parts(sys.argv[2]) else 1)
PY
}
if command -v cass >/dev/null 2>&1; then
  CASS_PATH=$(absolute_path "$(command -v cass)")
  installed_version=$(cass --version 2>/dev/null | awk '{print $2}' | head -1 || true)
  if version_at_least "$installed_version" "$MINIMUM_CASS_VERSION"; then
    cass_ok=1
    echo "Using existing cass $installed_version at $CASS_PATH."
  else
    echo "Existing cass ${installed_version:-unknown} is older than $MINIMUM_CASS_VERSION; installing cass $CASS_VERSION locally."
  fi
fi

if [ "$cass_ok" -ne 1 ]; then
  if [ "$ACCEPT" -ne 1 ] && [ ! -t 0 ]; then
    echo "cass licence acceptance is required in non-interactive mode; rerun with --accept-cass-licence after reviewing THIRD-PARTY.md." >&2
    exit 2
  fi
  asset="cass-$OS-$ARCH.tar.gz"
  if [ "$CASS_VERSION" = 0.11.0 ]; then
    expected=$(python3 - "$ROOT/manifest/cass-releases.json" "$OS-$ARCH" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as handle:
    entry = json.load(handle)["platforms"].get(sys.argv[2])
if not entry:
    raise SystemExit(f"No pinned cass binary is published for {sys.argv[2]}; install cass {json.load(open(sys.argv[1]))['version']} separately, then rerun.")
print(entry["sha256"])
PY
)
  else
    expected=$(curl -fsSL "https://github.com/Dicklesworthstone/coding_agent_session_search/releases/download/v$CASS_VERSION/$asset.sha256" | awk '{print $1}')
  fi
  licence_url="https://raw.githubusercontent.com/Dicklesworthstone/coding_agent_session_search/v$CASS_VERSION/LICENSE"
  licence_file=$(mktemp)
  archive=$(mktemp)
  extract_dir=$(mktemp -d)
  trap 'rm -f "${licence_file:-}" "${archive:-}"; rm -rf "${extract_dir:-}"' EXIT
  curl -fsSL "$licence_url" -o "$licence_file"
  if [ "$ACCEPT" -ne 1 ]; then
    cat "$licence_file"
    printf "Accept this cass licence? [y/N] "
    read -r answer
    case "$answer" in y|Y|yes|YES) ;; *) echo "cass licence not accepted."; exit 1 ;; esac
  fi
  curl -fL --progress-bar "https://github.com/Dicklesworthstone/coding_agent_session_search/releases/download/v$CASS_VERSION/$asset" -o "$archive"
  if [ "$HASH_COMMAND" = shasum ]; then
    actual=$(shasum -a 256 "$archive" | awk '{print $1}')
  else
    actual=$(sha256sum "$archive" | awk '{print $1}')
  fi
  if [ "$actual" != "$expected" ]; then
    echo "cass checksum mismatch for $asset" >&2
    exit 5
  fi
  tar -xzf "$archive" -C "$extract_dir"
  cass_source=$(find "$extract_dir" -type f -name cass -perm -u+x | head -1)
  [ -n "$cass_source" ] || { echo "cass archive did not contain an executable." >&2; exit 5; }
  install -m 0755 "$cass_source" "$BIN/cass"
  if [ "$OS" = darwin ]; then
    xattr -d com.apple.quarantine "$BIN/cass" 2>/dev/null || true
  fi
  cass_installed=1
  CASS_PATH="$BIN/cass"
fi

if [ "$COPY" -eq 1 ]; then
  install -m 0755 "$ROOT/bin/wsm" "$BIN/wsm"
else
  ln -sfn "$ROOT/bin/wsm" "$BIN/wsm"
fi
PATH="$BIN:$PATH"
export PATH
"$BIN/wsm" config set cass_path "$CASS_PATH"
RAW_MIRROR=0
[ "$("$BIN/wsm" config get raw_mirror)" = true ] && RAW_MIRROR=1
REFRESH_MINUTES=$("$BIN/wsm" config get refresh_minutes)
REFRESH_SECONDS=$((REFRESH_MINUTES * 60))

case ":$PATH:" in
  *":$BIN:"*) ;;
  *) echo "Warning: $BIN is not on PATH. Add: export PATH=\"\$HOME/.local/bin:\$PATH\"" ;;
esac

path_has_symlink() {
  python3 - "$HOME" "$1" <<'PY'
import os, sys
home = os.path.abspath(sys.argv[1])
target = os.path.abspath(sys.argv[2])
relative = os.path.relpath(target, home)
if relative == os.pardir or relative.startswith(os.pardir + os.sep):
    raise SystemExit(0)
current = home
if os.path.islink(current):
    raise SystemExit(0)
for part in relative.split(os.sep):
    current = os.path.join(current, part)
    if os.path.islink(current):
        raise SystemExit(0)
raise SystemExit(1)
PY
}

install_skill() {
  agent=$1
  skill_dir="$HOME/.$agent/skills/workspace-memory"
  if path_has_symlink "$skill_dir"; then
    echo "$agent skill: managed elsewhere (symlink), skipped"
    return
  fi
  mkdir -p "$(dirname "$skill_dir")"
  if [ -e "$skill_dir" ] && [ ! -f "$skill_dir/.workspace-memory-installed" ]; then
    skill_backup="$BACKUP/skills/$agent/workspace-memory"
    mkdir -p "$(dirname "$skill_backup")"
    cp -R "$skill_dir" "$skill_backup"
  fi
  rm -rf "$skill_dir"
  cp -R "$ROOT/skills/workspace-memory" "$skill_dir"
  printf '%s\n' "workspace-memory $ROOT" > "$skill_dir/.workspace-memory-installed"
}

for agent in claude codex; do
  case ",$AGENTS," in
    *",$agent,"*)
      install_skill "$agent"
      ;;
  esac
done

config_args=("$BIN/wsm" _agent-config install --agents "$AGENTS" --command "$BIN/wsm" --backup "$BACKUP" --raw-mirror "$RAW_MIRROR")
[ "$NO_HOOKS" -eq 1 ] && config_args+=(--no-hooks)
[ "$NO_INSTRUCTIONS" -eq 1 ] && config_args+=(--no-instructions)
"${config_args[@]}"

schedule=none
if [ "$NO_SCHEDULE" -ne 1 ]; then
  if [ "$OS" = darwin ]; then
    destination="$HOME/Library/LaunchAgents/com.workspace-memory.refresh.plist"
    mkdir -p "$(dirname "$destination")"
    sed -e "s|@PYTHON@|$PYTHON_PATH|g" -e "s|@WSM@|$BIN/wsm|g" -e "s|@CASS@|$CASS_PATH|g" -e "s|@STATE@|$STATE|g" -e "s|@INTERVAL@|$REFRESH_SECONDS|g" -e "s|@RAW_MIRROR@|$RAW_MIRROR|g" "$ROOT/templates/launchd.plist" > "$destination"
    launchctl bootout "gui/$(id -u)/com.workspace-memory.refresh" >/dev/null 2>&1 || true
    launchctl bootstrap "gui/$(id -u)" "$destination" >/dev/null 2>&1 || true
    schedule=launchd
  elif command -v systemctl >/dev/null 2>&1 && systemctl --user show-environment >/dev/null 2>&1; then
    units="$HOME/.config/systemd/user"
    mkdir -p "$units"
    sed -e "s|@PYTHON@|$PYTHON_PATH|g" -e "s|@WSM@|$BIN/wsm|g" -e "s|@CASS@|$CASS_PATH|g" -e "s|@STATE@|$STATE|g" -e "s|@RAW_MIRROR@|$RAW_MIRROR|g" "$ROOT/templates/systemd/workspace-memory-refresh.service" > "$units/workspace-memory-refresh.service"
    sed -e "s|@MINUTES@|$REFRESH_MINUTES|g" "$ROOT/templates/systemd/workspace-memory-refresh.timer" > "$units/workspace-memory-refresh.timer"
    systemctl --user daemon-reload
    systemctl --user enable --now workspace-memory-refresh.timer
    schedule=systemd
  elif command -v crontab >/dev/null 2>&1; then
    current=$(crontab -l 2>/dev/null || true)
    quoted_python=$(python3 -c 'import shlex,sys; print(shlex.quote(sys.argv[1]))' "$PYTHON_PATH")
    quoted_wsm=$(python3 -c 'import shlex,sys; print(shlex.quote(sys.argv[1]))' "$BIN/wsm")
    quoted_cass=$(python3 -c 'import shlex,sys; print(shlex.quote(sys.argv[1]))' "$CASS_PATH")
    line="*/$REFRESH_MINUTES * * * * CASS_RAW_MIRROR=$RAW_MIRROR WSM_CASS=$quoted_cass $quoted_python $quoted_wsm refresh --quiet # workspace-memory"
    printf '%s\n' "$current" | grep -v '# workspace-memory$' > "$STATE/crontab.tmp" || true
    printf '%s\n' "$line" >> "$STATE/crontab.tmp"
    crontab "$STATE/crontab.tmp"
    rm -f "$STATE/crontab.tmp"
    schedule=cron
  else
    echo "Warning: no user scheduler is available, run 'wsm refresh' when needed."
  fi
fi

python3 - "$STATE/install.json" "$ROOT" "$AGENTS" "$cass_installed" "$CASS_VERSION" "$schedule" "$COPY" "$CASS_PATH" <<'PY'
import json, sys
path, root, agents, cass_installed, version, schedule, copied, cass_path = sys.argv[1:]
with open(path, "w", encoding="utf-8") as handle:
    json.dump({"root": root, "agents": agents, "cass_installed": cass_installed == "1", "cass_version": version, "cass_path": cass_path, "schedule": schedule, "copied": copied == "1"}, handle, indent=2)
    handle.write("\n")
PY

index_log="$STATE/index.log"
index_arguments=(index --full)
if "$CASS_PATH" status --json 2>/dev/null | python3 -c 'import json,sys; data=json.load(sys.stdin); index=data.get("index") or {}; raise SystemExit(0 if data.get("healthy") and index.get("exists") and index.get("fresh") else 1)' 2>/dev/null; then
  index_arguments=(index)
fi
if [ "${WSM_TEST_WAIT_INDEX:-0}" = 1 ]; then
  CASS_RAW_MIRROR=$RAW_MIRROR nice -n 15 "$CASS_PATH" "${index_arguments[@]}" >"$index_log" 2>&1 || status=$?
  status=${status:-0}
  if [ "$status" -eq 9 ] && "$CASS_PATH" health >/dev/null 2>&1; then status=0; fi
  [ "$status" -eq 0 ] || { echo "Initial cass index failed, see $index_log" >&2; exit "$status"; }
else
  (status=0; CASS_RAW_MIRROR=$RAW_MIRROR nice -n 15 "$CASS_PATH" "${index_arguments[@]}" >"$index_log" 2>&1 || status=$?; if [ "$status" -eq 9 ] && "$CASS_PATH" health >/dev/null 2>&1; then status=0; fi; exit "$status") </dev/null >/dev/null 2>&1 &
  index_pid=$!
  echo "$index_pid" > "$STATE/index.pid"
  disown "$index_pid" 2>/dev/null || true
fi

WSM_NO_SCHEDULE=$([ "$NO_SCHEDULE" -eq 1 ] && echo 1 || echo 0) "$BIN/wsm" doctor || true
echo "Hooks and scheduled jobs use CASS_RAW_MIRROR=$RAW_MIRROR. Add the matching export to your shell profile only if you want interactive cass commands to use it."
echo "Installed. Session-start hooks recall local history, session-end hooks journal and refresh it."
echo "Run 'wsm init' in a workspace, or 'wsm doctor' to inspect the installation."
