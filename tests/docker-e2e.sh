#!/usr/bin/env bash
set -euo pipefail

apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3 curl ca-certificates tar coreutils shellcheck >/dev/null
shellcheck /workspace/install.sh /workspace/uninstall.sh

mkdir -p /root/.claude/projects/-home-test-project /root/.codex /home/test/project/.git
cp /workspace/tests/fixtures/claude-session.jsonl /root/.claude/projects/-home-test-project/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa.jsonl
cp /workspace/tests/fixtures/claude-settings.json /root/.claude/settings.json
cp /workspace/tests/fixtures/codex-hooks.json /root/.codex/hooks.json

WSM_TEST_WAIT_INDEX=1 /workspace/install.sh --yes --accept-cass-licence
cd /home/test/project
/root/.local/bin/wsm recall "nebulawombat" --budget 700 > /tmp/recall.txt
grep -qi "nebulawombat" /tmp/recall.txt
grep -q "claude_code" /tmp/recall.txt
grep -q "Investigate the nebulawombat upload failure" /tmp/recall.txt
/root/.local/bin/wsm private add /home/test/project
/root/.local/bin/wsm refresh --quiet
/root/.local/bin/cass sessions --workspace /home/test/project --limit 10 --json > /tmp/private-sessions.json
python3 -c 'import json; assert json.load(open("/tmp/private-sessions.json"))["sessions"] == []'
/root/.local/bin/wsm private remove /home/test/project
/root/.local/bin/wsm refresh --quiet
/root/.local/bin/wsm recall "nebulawombat" --budget 700 > /tmp/reincluded-recall.txt
if ! grep -q "Investigate the nebulawombat upload failure" /tmp/reincluded-recall.txt; then
  sed -n '1,100p' /tmp/reincluded-recall.txt
  /root/.local/bin/cass forget --list --json || true
  /root/.local/bin/cass sessions --workspace /home/test/project --limit 10 --json || true
  exit 1
fi
/root/.local/bin/wsm doctor --json > /tmp/doctor.json || true
python3 -c 'import json; d=json.load(open("/tmp/doctor.json")); assert any(c["name"] == "cass_health" and c["ok"] for c in d["checks"])'

cd /workspace
/workspace/uninstall.sh --purge --yes
test ! -e /root/.local/bin/wsm
test ! -e /root/.local/bin/cass
test ! -e /root/.local/state/workspace-memory
test ! -e /root/.config/workspace-memory
test ! -e /root/.config/systemd/user/workspace-memory-refresh.timer
grep -q 'existing-guard' /root/.claude/settings.json
test "$(grep -c 'wsm hook' /root/.claude/settings.json || true)" -eq 0
grep -q 'existing-codex-hook' /root/.codex/hooks.json

echo "DOCKER_E2E_OK"
sed -n '1,80p' /tmp/recall.txt
