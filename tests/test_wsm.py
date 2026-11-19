import contextlib
import importlib.util
from importlib.machinery import SourceFileLoader
import io
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
WSM = ROOT / "bin/wsm"
FAKE = ROOT / "tests/fake_cass"
spec = importlib.util.spec_from_loader("wsm_module", SourceFileLoader("wsm_module", str(WSM)))
wsm = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(wsm)


class EnvironmentCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="workspace memory ", dir=ROOT.parent)
        self.root = Path(self.temp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.workspace = self.root / "project"
        self.workspace.mkdir()
        (self.workspace / ".git").mkdir()
        self.environment = {
            "HOME": str(self.home),
            "WSM_CONFIG": str(self.home / ".config/workspace-memory/config.toml"),
            "WSM_STATE_DIR": str(self.home / ".local/state/workspace-memory"),
            "WSM_CASS": str(FAKE),
            "_WSM_TEST_ALLOWED_ROOT": str(self.root),
            "FAKE_WORKSPACE": str(self.workspace.resolve()),
            "PATH": str(ROOT / "tests") + os.pathsep + os.environ.get("PATH", ""),
        }
        self.patch = mock.patch.dict(os.environ, self.environment, clear=False)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def run_wsm(self, *arguments, cwd=None, input_text=None, extra=None):
        env = os.environ.copy()
        env.update(self.environment)
        if extra:
            env.update(extra)
        return subprocess.run(
            [str(WSM), *arguments], cwd=cwd or self.workspace, env=env,
            text=True, input=input_text, capture_output=True, timeout=8, check=False,
        )


class WorkspaceTests(EnvironmentCase):
    def test_git_workspace_resolution(self):
        nested = self.workspace / "a/b"
        nested.mkdir(parents=True)
        self.assertEqual(wsm.resolve_workspace(nested), self.workspace.resolve())

    def test_agent_memory_precedes_git(self):
        nested = self.workspace / "package/src"
        nested.mkdir(parents=True)
        (self.workspace / "package/.agent-memory").mkdir()
        self.assertEqual(wsm.resolve_workspace(nested), (self.workspace / "package").resolve())

    def test_memsearch_compatibility(self):
        memory = self.workspace / ".memsearch/memory"
        memory.mkdir(parents=True)
        self.assertEqual(wsm.journal_dir(self.workspace), memory)

    def test_agent_memory_default(self):
        self.assertEqual(wsm.journal_dir(self.workspace), self.workspace / ".agent-memory/journal")

    def test_init_uses_git_info_exclude(self):
        result = self.run_wsm("init")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(".agent-memory/", (self.workspace / ".git/info/exclude").read_text())
        self.assertFalse((self.workspace / ".gitignore").exists())

    def test_repository_gitignore_excludes_memory(self):
        entries = (ROOT / ".gitignore").read_text().splitlines()
        self.assertIn(".agent-memory/", entries)
        self.assertIn(".memsearch/", entries)


class RecallTests(EnvironmentCase):
    def setUp(self):
        super().setUp()
        journal = self.workspace / ".agent-memory/journal"
        journal.mkdir(parents=True)
        (journal / "2026-11-18.md").write_text("older journal\n")
        (journal / "2026-11-19.md").write_text("newer journal\n")

    def test_recall_deduplicates_and_filters_noise(self):
        result = self.run_wsm("recall", "upload", "--budget", "1000")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.count("Implemented bounded retry"), 1)
        self.assertNotIn("cass search upload", result.stdout)
        self.assertIn("Failed buffering", result.stdout)

    def test_recall_budget(self):
        result = self.run_wsm("recall", "upload", "--budget", "100")
        self.assertLessEqual(len(result.stdout.rstrip("\n")), 400)
        self.assertIn("trimmed", result.stdout)

    def test_recall_json(self):
        result = self.run_wsm("recall", "upload", "--json")
        data = json.loads(result.stdout)
        self.assertEqual(data["workspace"], str(self.workspace.resolve()))
        self.assertEqual(len(data["hits"]), 2)

    def test_read_only_sessions_fallback(self):
        result = self.run_wsm("recall", extra={"FAKE_CASS_MODE": "error"})
        self.assertEqual(result.returncode, 0)
        self.assertIn("unavailable in this sandbox", result.stdout)

    def test_all_prints_warning(self):
        result = self.run_wsm("recall", "upload", "--all")
        self.assertIn("WARNING: searching all non-private workspaces", result.stdout)


class RedactionTests(unittest.TestCase):
    # Fake values are assembled at run time so the source never contains a string
    # that secret scanners (for example GitHub push protection) read as a real key.
    FILLER = "abcdefghijklmnopqrstuvwxyz123456"
    CASES = [
        "sk" + "-" + FILLER[:22], "sk" + "-ant-" + FILLER[:22],
        "gh" + "p_" + FILLER, "github" + "_pat_" + FILLER,
        "xo" + "xb-1234567890-" + FILLER[:12], "AK" + "IA" + "ABCDEFGHIJKLMNOP",
        "op" + "s_" + FILLER, "cf" + "at_" + FILLER,
        "ey" + "Jabc.defghi.jklmnop", "Bearer " + FILLER[:26],
        "api" + "_key=" + FILLER[:26], "-----BEGIN " + "PRIVATE KEY-----\nabc\n-----END " + "PRIVATE KEY-----",
    ]

    def test_every_secret_shape_is_redacted(self):
        for secret in self.CASES:
            with self.subTest(secret=secret[:12]):
                self.assertIn("[REDACTED]", wsm.redact(secret))

    def test_plain_text_survives(self):
        self.assertEqual(wsm.redact("ordinary project note"), "ordinary project note")


class LogTests(EnvironmentCase):
    def test_log_format(self):
        result = self.run_wsm("log", "-m", "- Changed src/app.py\n- Nothing remains", "--agent", "codex", extra={"WSM_SESSION_ID": "session-1"})
        self.assertEqual(result.returncode, 0, result.stderr)
        content = Path(result.stdout.strip()).read_text()
        self.assertRegex(content, r"## Session \d\d:\d\d \(codex\)")
        self.assertIn("<!-- wsm session=session-1 agent=codex -->", content)
        self.assertIn(".agent-memory/", (self.workspace / ".git/info/exclude").read_text())

    def test_log_refuses_secret(self):
        result = self.run_wsm("log", "-m", "token=abcdefghijklmnopqrstuvwxyz")
        self.assertEqual(result.returncode, 3)
        self.assertIn("named secret", result.stderr)
        self.assertFalse((self.workspace / ".agent-memory").exists())

    def test_log_reads_stdin(self):
        result = self.run_wsm("log", "--agent", "grok", input_text="- Done\n")
        self.assertEqual(result.returncode, 0)
        self.assertIn("- Done", Path(result.stdout.strip()).read_text())


class AutologTests(EnvironmentCase):
    def test_autolog_is_idempotent(self):
        self.assertEqual(self.run_wsm("init").returncode, 0)
        first = self.run_wsm("autolog", "--session", "/sessions/a.jsonl", "--agent", "claude")
        second = self.run_wsm("autolog", "--session", "/sessions/a.jsonl", "--agent", "claude")
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertIn("Added 1 automatic journal entry", first.stdout)
        self.assertIn("Added 0 automatic journal entries", second.stdout)
        journal = next((self.workspace / ".agent-memory/journal").glob("*.md")).read_text()
        self.assertEqual(journal.count("wsm session=a "), 1)
        self.assertIn("First request: Please repair", journal)

    def test_autolog_skips_uninitialised_workspace(self):
        result = self.run_wsm("autolog", "--session", "/sessions/a.jsonl", "--agent", "claude")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Added 0", result.stdout)
        self.assertFalse((self.workspace / ".agent-memory").exists())

    def test_autolog_all_still_rejects_home_and_temp(self):
        self.assertEqual(self.run_wsm("config", "set", "autolog_scope", "all").returncode, 0)
        home_result = self.run_wsm("autolog", "--session", "/sessions/a.jsonl", cwd=self.home)
        self.assertEqual(home_result.returncode, 0, home_result.stderr)
        self.assertFalse((self.home / ".agent-memory").exists())
        self.assertFalse(wsm._autolog_workspace_allowed(Path("/tmp"), wsm.load_config()))
        self.assertFalse(wsm._autolog_workspace_allowed(Path("/var"), wsm.load_config()))

    def test_temp_roots_are_refused_without_test_override(self):
        with mock.patch.dict(os.environ, {"_WSM_TEST_ALLOWED_ROOT": ""}):
            self.assertFalse(wsm._autolog_workspace_allowed(Path("/tmp"), wsm.load_config()))
            self.assertFalse(wsm._autolog_workspace_allowed(Path("/private/tmp"), wsm.load_config()))

    def test_autolog_all_allows_normal_existing_workspace(self):
        self.assertEqual(self.run_wsm("config", "set", "autolog_scope", "all").returncode, 0)
        result = self.run_wsm("autolog", "--session", "/sessions/a.jsonl", "--agent", "claude")
        self.assertIn("Added 1", result.stdout)
        self.assertIn(".agent-memory/", (self.workspace / ".git/info/exclude").read_text())

    def test_autolog_uses_initialised_root_for_session_subfolder(self):
        self.assertEqual(self.run_wsm("init").returncode, 0)
        subfolder = self.workspace / "src"
        (subfolder / "package").mkdir(parents=True)
        result = self.run_wsm("autolog", extra={"FAKE_WORKSPACE": str(subfolder)})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Added 2", result.stdout)
        journal = next((self.workspace / ".agent-memory/journal").glob("*.md")).read_text()
        self.assertIn("wsm session=a ", journal)
        self.assertIn("wsm session=b ", journal)
        self.assertFalse((subfolder / ".agent-memory").exists())

    def test_memsearch_marker_prevents_duplicate_autolog(self):
        memory = self.workspace / ".memsearch/memory"
        memory.mkdir(parents=True)
        (memory / "2026-11-19.md").write_text("<!-- session:a agent:claude -->\n")
        result = self.run_wsm("autolog", "--session", "/sessions/a.jsonl", "--agent", "claude")
        self.assertIn("Added 0", result.stdout)
        self.assertEqual((memory / "2026-11-19.md").read_text().count("session:a"), 1)


class PrivacyAndConfigTests(EnvironmentCase):
    def test_private_add_list_remove(self):
        target = self.root / "private"
        target.mkdir()
        self.assertEqual(self.run_wsm("private", "add", str(target)).returncode, 0)
        self.assertIn(str(target), self.run_wsm("private", "list").stdout)
        self.assertEqual(self.run_wsm("private", "remove", str(target)).returncode, 0)
        self.assertNotIn(str(target), self.run_wsm("private", "list").stdout)

    def test_config_modern_parser(self):
        value = wsm.parse_config('[workspace_memory]\ndays = 7\nraw_mirror = false\nprivate_workspaces = ["/x"]\n')
        self.assertEqual(value["days"], 7)
        self.assertEqual(value["private_workspaces"], ["/x"])

    def test_config_python39_fallback(self):
        value = wsm.parse_config('days = 9\nraw_mirror = true\ntz = "Asia/Bangkok"\n', force_fallback=True)
        self.assertEqual(value, {"days": 9, "raw_mirror": True, "tz": "Asia/Bangkok"})

    def test_config_command_round_trip(self):
        self.assertEqual(self.run_wsm("config", "set", "budget", "777").returncode, 0)
        self.assertEqual(self.run_wsm("config", "get", "budget").stdout.strip(), "777")

    def test_autolog_scope_rejects_unknown_value(self):
        result = self.run_wsm("config", "set", "autolog_scope", "everywhere")
        self.assertEqual(result.returncode, 2)
        self.assertIn("initialised", result.stderr)


class HookTests(EnvironmentCase):
    def test_hook_formats_for_supported_agents(self):
        payload = json.dumps({"cwd": str(self.workspace), "session_id": "abc"})
        for agent in ("claude", "codex", "grok", "gemini"):
            with self.subTest(agent=agent):
                result = self.run_wsm("hook", "session-start", "--agent", agent, input_text=payload)
                self.assertEqual(result.returncode, 0, result.stderr)
                output = json.loads(result.stdout)
                self.assertEqual(output["hookSpecificOutput"]["hookEventName"], "SessionStart")
                self.assertIn("Workspace memory", output["hookSpecificOutput"]["additionalContext"])

    def test_hook_never_fails_when_cass_errors(self):
        result = self.run_wsm("hook", "session-start", "--agent", "claude", input_text=json.dumps({"cwd": str(self.workspace)}), extra={"FAKE_CASS_MODE": "error"})
        self.assertEqual(result.returncode, 0)
        self.assertIn("Workspace memory", result.stdout)

    def test_hook_times_out_hanging_cass(self):
        result = self.run_wsm("hook", "session-start", "--agent", "gemini", input_text=json.dumps({"cwd": str(self.workspace)}), extra={"FAKE_CASS_MODE": "hang"})
        self.assertEqual(result.returncode, 0)
        self.assertIn("Workspace memory", result.stdout)

    def test_hook_empty_and_invalid_payloads_still_recall(self):
        for payload in ("", "not-json"):
            with self.subTest(payload=payload):
                result = self.run_wsm("hook", "session-start", "--agent", "claude", input_text=payload)
                self.assertEqual(result.returncode, 0, result.stderr)
                output = json.loads(result.stdout)
                self.assertIn("Workspace memory", output["hookSpecificOutput"]["additionalContext"])


class RefreshTests(EnvironmentCase):
    def test_doctor_reports_last_refresh_result(self):
        result = self.run_wsm("refresh", "--quiet")
        self.assertEqual(result.returncode, 0, result.stderr)
        doctor = self.run_wsm("doctor", "--json")
        data = json.loads(doctor.stdout)
        refresh = next(check for check in data["checks"] if check["name"] == "last_refresh")
        self.assertTrue(refresh["ok"])
        self.assertIn("finished_at", refresh["detail"])

    def test_concurrent_cass_index_is_recorded_as_skipped(self):
        result = self.run_wsm("refresh", extra={"FAKE_CASS_INDEX_CODE": "7"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Refresh skipped", result.stdout)
        status = json.loads((self.home / ".local/state/workspace-memory/refresh-status.json").read_text())
        self.assertTrue(status["ok"])
        self.assertTrue(status["skipped"])
        self.assertEqual(status["return_code"], 7)
        self.assertIn("already running", status["detail"])
        doctor = json.loads(self.run_wsm("doctor", "--json").stdout)
        refresh = next(check for check in doctor["checks"] if check["name"] == "last_refresh")
        self.assertTrue(refresh["ok"])


class DoctorAgentTests(EnvironmentCase):
    def _create_gemini_config(self):
        gemini = self.home / ".gemini"
        gemini.mkdir()
        (gemini / "GEMINI.md").write_text(f"{wsm.START_MARKER}\n")
        (gemini / "settings.json").write_text(json.dumps({"command": "wsm hook session-start"}))

    def test_doctor_uses_agents_from_install_receipt(self):
        self._create_gemini_config()
        receipt = self.home / ".local/state/workspace-memory/install.json"
        receipt.parent.mkdir(parents=True)
        receipt.write_text(json.dumps({"agents": "claude,codex,grok"}))
        doctor = json.loads(self.run_wsm("doctor", "--json").stdout)
        names = {check["name"] for check in doctor["checks"]}
        self.assertNotIn("gemini_instructions", names)
        self.assertNotIn("gemini_hooks", names)

    def test_doctor_detects_agents_when_receipt_is_absent(self):
        self._create_gemini_config()
        doctor = json.loads(self.run_wsm("doctor", "--json").stdout)
        names = {check["name"] for check in doctor["checks"]}
        self.assertIn("gemini_instructions", names)
        self.assertIn("gemini_hooks", names)


class SchedulerTemplateTests(unittest.TestCase):
    def test_schedulers_use_absolute_python_and_cass_placeholders(self):
        launchd = (ROOT / "templates/launchd.plist").read_text()
        systemd = (ROOT / "templates/systemd/workspace-memory-refresh.service").read_text()
        installer = (ROOT / "install.sh").read_text()
        self.assertIn("<string>@PYTHON@</string><string>@WSM@</string>", launchd)
        self.assertIn("<key>WSM_CASS</key><string>@CASS@</string>", launchd)
        self.assertIn('ExecStart="@PYTHON@" "@WSM@"', systemd)
        self.assertIn('Environment="WSM_CASS=@CASS@"', systemd)
        self.assertIn('s|@PYTHON@|$PYTHON_PATH|g', installer)
        self.assertIn('s|@CASS@|$CASS_PATH|g', installer)


class InstallerTests(EnvironmentCase):
    def setUp(self):
        super().setUp()
        os.chmod(FAKE, 0o755)
        self.fake_bin = self.root / "fake-bin"
        self.fake_bin.mkdir()
        (self.fake_bin / "cass").symlink_to(FAKE)
        self.environment["PATH"] = str(self.fake_bin) + os.pathsep + os.environ.get("PATH", "")
        for directory in (".claude", ".codex", ".grok", ".gemini"):
            (self.home / directory).mkdir()
        claude = {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "/guard"}]}], "SessionStart": [{"hooks": [{"type": "command", "command": "/existing-start"}]}]}, "theme": "dark"}
        (self.home / ".claude/settings.json").write_text(json.dumps(claude, indent=2) + "\n")
        (self.home / ".codex/hooks.json").write_text(json.dumps({"hooks": {"Other": [{"command": "/keep"}]}}, indent=2) + "\n")
        (self.home / ".grok/config.toml").write_text('model = "grok-code"\n')
        (self.home / ".gemini/settings.json").write_text(json.dumps({"theme": "default"}, indent=2) + "\n")
        self.targets = {}
        for agent, name in (("claude", "CLAUDE.md"), ("codex", "AGENTS.md"), ("grok", "AGENTS.md"), ("gemini", "GEMINI.md")):
            target = self.root / f"managed-{agent}.md"
            target.write_text(f"managed {agent}\n")
            (self.home / f".{agent}" / name).symlink_to(target)
            self.targets[agent] = target
        self.original_claude = json.loads((self.home / ".claude/settings.json").read_text())
        self.original_codex_bytes = (self.home / ".codex/hooks.json").read_bytes()

    def install(self, extra_args=None, extra_env=None, schedule=False):
        env = os.environ.copy()
        env.update(self.environment)
        env["WSM_TEST_WAIT_INDEX"] = "1"
        if extra_env:
            env.update(extra_env)
        arguments = [str(ROOT / "install.sh"), "--agents", "claude,codex,grok,gemini"]
        if not schedule:
            arguments.append("--no-schedule")
        arguments.extend(["--yes", "--accept-cass-licence"])
        arguments.extend(extra_args or [])
        return subprocess.run(arguments, env=env, cwd=ROOT, text=True, capture_output=True, timeout=30, check=False)

    def test_install_idempotence_and_uninstall(self):
        first = self.install()
        self.assertEqual(first.returncode, 0, first.stderr)
        claude_after = (self.home / ".claude/settings.json").read_bytes()
        grok_after = (self.home / ".grok/config.toml").read_bytes()
        gemini_after = (self.home / ".gemini/settings.json").read_bytes()
        second = self.install()
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual((self.home / ".claude/settings.json").read_bytes(), claude_after)
        self.assertEqual((self.home / ".grok/config.toml").read_bytes(), grok_after)
        self.assertEqual((self.home / ".gemini/settings.json").read_bytes(), gemini_after)
        for agent, target in self.targets.items():
            self.assertEqual(target.read_text(), f"managed {agent}\n")
        claude_data = json.loads(claude_after)
        self.assertEqual(claude_data["hooks"]["PreToolUse"], self.original_claude["hooks"]["PreToolUse"])
        self.assertEqual(claude_data["hooks"]["SessionStart"][0], self.original_claude["hooks"]["SessionStart"][0])
        self.assertEqual((self.home / ".codex/hooks.json").read_bytes(), self.original_codex_bytes)
        hook_command = claude_data["hooks"]["SessionStart"][-1]["hooks"][0]["command"]
        self.assertIn(str(self.home / ".local/bin/wsm"), shlex.split(hook_command))
        grok_text = grok_after.decode()
        encoded_command = re.search(r"^\s*command = (.+)$", grok_text, flags=re.MULTILINE)
        self.assertIsNotNone(encoded_command)
        self.assertIn(str(self.home / ".local/bin/wsm"), shlex.split(json.loads(encoded_command.group(1))))
        env = os.environ.copy()
        env.update(self.environment)
        uninstall = subprocess.run([str(ROOT / "uninstall.sh"), "--yes"], env=env, cwd=ROOT, text=True, capture_output=True, timeout=20, check=False)
        self.assertEqual(uninstall.returncode, 0, uninstall.stderr)
        self.assertEqual(json.loads((self.home / ".claude/settings.json").read_text()), self.original_claude)
        self.assertEqual((self.home / ".grok/config.toml").read_text(), 'model = "grok-code"\n')
        self.assertEqual(json.loads((self.home / ".gemini/settings.json").read_text()), {"theme": "default"})
        self.assertFalse((self.home / ".local/bin/wsm").exists())

    def test_skill_symlink_is_skipped_and_user_skill_is_backed_up(self):
        external = self.root / "managed skills"
        external.mkdir()
        (external / "keep.txt").write_text("untouched\n")
        (self.home / ".codex/skills").symlink_to(external, target_is_directory=True)
        user_skill = self.home / ".claude/skills/workspace-memory"
        user_skill.mkdir(parents=True)
        (user_skill / "KEEP.md").write_text("user skill\n")
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("managed elsewhere (symlink)", result.stdout)
        self.assertEqual((external / "keep.txt").read_text(), "untouched\n")
        self.assertFalse((external / "workspace-memory").exists())
        self.assertTrue((user_skill / ".workspace-memory-installed").exists())
        backups = list((self.home / ".local/state/workspace-memory/backups").glob("*/skills/claude/workspace-memory/KEEP.md"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(), "user skill\n")

    def test_uninstall_preserves_unmarked_user_skill(self):
        user_skill = self.home / ".claude/skills/workspace-memory"
        user_skill.mkdir(parents=True)
        (user_skill / "KEEP.md").write_text("user skill\n")
        env = os.environ.copy()
        env.update(self.environment)
        result = subprocess.run([str(ROOT / "uninstall.sh"), "--yes"], env=env, cwd=ROOT, text=True, capture_output=True, timeout=20, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((user_skill / "KEEP.md").read_text(), "user skill\n")

    def test_newer_existing_cass_is_used_and_recorded(self):
        result = self.install(extra_env={"FAKE_CASS_VERSION": "0.12.1"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Using existing cass 0.12.1", result.stdout)
        self.assertFalse((self.home / ".local/bin/cass").exists())
        config = wsm.parse_config((self.home / ".config/workspace-memory/config.toml").read_text())
        self.assertEqual(Path(config["cass_path"]), self.root / "fake-bin/cass")

    def test_scheduler_uses_real_interpreter_behind_python_shim(self):
        python_shim = self.fake_bin / "python3"
        python_shim.write_text(f"#!/bin/sh\nexec {shlex.quote(sys.executable)} \"$@\"\n")
        python_shim.chmod(0o755)
        fake_uname = self.fake_bin / "uname"
        fake_uname.write_text(
            "#!/bin/sh\n"
            "case \"$1\" in\n"
            "  -s) echo Linux ;;\n"
            "  -m) echo arm64 ;;\n"
            "  *) exec /usr/bin/uname \"$@\" ;;\n"
            "esac\n"
        )
        fake_uname.chmod(0o755)
        fake_systemctl = self.fake_bin / "systemctl"
        fake_systemctl.write_text("#!/bin/sh\nexit 0\n")
        fake_systemctl.chmod(0o755)
        result = self.install(schedule=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        service = (self.home / ".config/systemd/user/workspace-memory-refresh.service").read_text()
        self.assertIn(f'ExecStart="{sys.executable}"', service)
        self.assertNotIn(str(python_shim), service)

    def test_initial_index_uses_configured_raw_mirror(self):
        config = dict(wsm.DEFAULTS)
        config["raw_mirror"] = True
        wsm.save_config(config)
        env_log = self.root / "cass-env.log"
        result = self.install(extra_env={"FAKE_CASS_ENV_LOG": str(env_log)})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("index:1", env_log.read_text())

    def test_existing_healthy_fresh_index_uses_incremental_index(self):
        cass_log = self.root / "cass.log"
        result = self.install(extra_env={"FAKE_CASS_FRESH": "1", "FAKE_CASS_LOG": str(cass_log)})
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = [json.loads(line) for line in cass_log.read_text().splitlines()]
        self.assertIn(["index"], calls)
        self.assertNotIn(["index", "--full"], calls)

    def test_background_index_does_not_hold_install_output_open(self):
        delay = 4.0
        started = time.monotonic()
        result = self.install(extra_env={"WSM_TEST_WAIT_INDEX": "0", "FAKE_CASS_INDEX_SLEEP": str(delay)})
        elapsed = time.monotonic() - started
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertLess(elapsed, delay - 1)
        index_log = self.home / ".local/state/workspace-memory/index.log"
        deadline = time.monotonic() + delay + 2
        while time.monotonic() < deadline:
            if index_log.exists() and "indexed" in index_log.read_text():
                break
            time.sleep(0.1)
        self.assertIn("indexed", index_log.read_text())

    def test_noninteractive_licence_error_is_clear(self):
        env = os.environ.copy()
        env.update(self.environment)
        env["PATH"] = "/usr/bin:/bin"
        result = subprocess.run(
            [str(ROOT / "install.sh"), "--agents", "claude", "--no-schedule", "--yes"],
            env=env, cwd=ROOT, text=True, input="", capture_output=True, timeout=10, check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("--accept-cass-licence", result.stderr)

    def test_dry_run_changes_nothing(self):
        before = {path: path.read_bytes() for path in self.home.rglob("*") if path.is_file() and not path.is_symlink()}
        env = os.environ.copy()
        env.update(self.environment)
        result = subprocess.run([str(ROOT / "install.sh"), "--agents", "claude", "--dry-run"], env=env, cwd=ROOT, text=True, capture_output=True, timeout=10, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        after = {path: path.read_bytes() for path in self.home.rglob("*") if path.is_file() and not path.is_symlink()}
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
