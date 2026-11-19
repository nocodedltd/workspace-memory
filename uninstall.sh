#!/usr/bin/env bash
set -euo pipefail

PURGE=0
YES=0
while [ "$#" -gt 0 ]; do
  case "$1" in
    --purge) PURGE=1; shift ;;
    --yes) YES=1; shift ;;
    -h|--help) echo "Usage: ./uninstall.sh [--purge] [--yes]"; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done

STATE="$HOME/.local/state/workspace-memory"
BIN="$HOME/.local/bin"
RECEIPT="$STATE/install.json"
if [ -f "$RECEIPT" ]; then
  readarray_data=$(python3 - "$RECEIPT" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as handle: data=json.load(handle)
print(data.get("root", ""))
print(data.get("agents", "claude,codex,grok,gemini,opencode"))
print("1" if data.get("cass_installed") else "0")
print(data.get("schedule", "none"))
print(data.get("cass_path", ""))
PY
)
  ROOT=$(printf '%s\n' "$readarray_data" | sed -n '1p')
  AGENTS=$(printf '%s\n' "$readarray_data" | sed -n '2p')
  CASS_INSTALLED=$(printf '%s\n' "$readarray_data" | sed -n '3p')
  SCHEDULE=$(printf '%s\n' "$readarray_data" | sed -n '4p')
  CASS_PATH=$(printf '%s\n' "$readarray_data" | sed -n '5p')
else
  ROOT=$(cd -- "$(dirname -- "$0")" && pwd)
  AGENTS=claude,codex,grok,gemini,opencode
  CASS_INSTALLED=0
  SCHEDULE=none
  CASS_PATH=""
fi

WSM_COMMAND="$BIN/wsm"
if [ -x "$WSM_COMMAND" ]; then
  "$WSM_COMMAND" _agent-config uninstall --agents "$AGENTS" --command "$WSM_COMMAND" || true
elif [ -x "$ROOT/bin/wsm" ]; then
  "$ROOT/bin/wsm" _agent-config uninstall --agents "$AGENTS" --command "$WSM_COMMAND" || true
fi

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

for agent in claude codex; do
  skill_dir="$HOME/.$agent/skills/workspace-memory"
  if path_has_symlink "$skill_dir"; then
    echo "$agent skill: managed elsewhere (symlink), skipped"
  elif [ -f "$skill_dir/.workspace-memory-installed" ]; then
    rm -rf "$skill_dir"
  fi
done

case "$SCHEDULE" in
  launchd)
    launchctl bootout "gui/$(id -u)/com.workspace-memory.refresh" >/dev/null 2>&1 || true
    rm -f "$HOME/Library/LaunchAgents/com.workspace-memory.refresh.plist"
    ;;
  systemd)
    systemctl --user disable --now workspace-memory-refresh.timer >/dev/null 2>&1 || true
    rm -f "$HOME/.config/systemd/user/workspace-memory-refresh.service" "$HOME/.config/systemd/user/workspace-memory-refresh.timer"
    systemctl --user daemon-reload >/dev/null 2>&1 || true
    ;;
  cron)
    if command -v crontab >/dev/null 2>&1; then
      crontab -l 2>/dev/null | grep -v '# workspace-memory$' > "$STATE/crontab.tmp" || true
      crontab "$STATE/crontab.tmp"
      rm -f "$STATE/crontab.tmp"
    fi
    ;;
esac

rm -f "$BIN/wsm"

if [ "$PURGE" -eq 1 ]; then
  if [ "$YES" -ne 1 ]; then
    printf "Purge cass installed by workspace-memory and its local index? [y/N] "
    read -r answer
    case "$answer" in y|Y|yes|YES) ;; *) echo "Purge cancelled; regular uninstall completed."; exit 0 ;; esac
  fi
  CASS_DATA=""
  if [ -n "$CASS_PATH" ] && [ -x "$CASS_PATH" ]; then
    CASS_DATA=$("$CASS_PATH" health --json 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin).get("data_dir", ""))' 2>/dev/null || true)
  fi
  [ "$CASS_INSTALLED" = 1 ] && [ -n "$CASS_PATH" ] && rm -f "$CASS_PATH"
  case "$CASS_DATA" in
    "$HOME"/*cass*|"$HOME"/*coding-agent*) rm -rf "$CASS_DATA" ;;
  esac
  rm -rf "$HOME/.local/share/cass" "$HOME/.local/share/coding-agent-search" "$HOME/.local/share/com.coding-agent-search.coding-agent-search" "$HOME/Library/Application Support/cass" "$HOME/Library/Application Support/com.coding-agent-search.coding-agent-search" "$HOME/.cache/cass"
  rm -f "$HOME/.config/workspace-memory/config.toml"
  rmdir "$HOME/.config/workspace-memory" 2>/dev/null || true
fi

rm -f "$RECEIPT" "$STATE/index.pid"
[ "$PURGE" -eq 1 ] && rm -rf "$STATE"
echo "Uninstalled workspace-memory. Workspace journals were left in place."
