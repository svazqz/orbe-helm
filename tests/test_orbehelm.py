"""Behavioral tests use independent temporary roots and never start a real agent."""
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import shlex
import subprocess
import sys
import tempfile
import tomllib
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from orbehelm.core import OrbeHelmError, build, resolve
from orbehelm.adapters import launch, doctor
from orbehelm.cli import main
from orbehelm.composition import MARKER, SECTION_TITLES, compose, parse_sections

REPO = Path(__file__).resolve().parents[1]


def section_document(title="Test Definition", **sections):
    parts = [MARKER, f"# {title}"]
    for name in SECTION_TITLES:
        mode, body = sections.get(name, ("append", ""))
        parts.append(f"## {name} [{mode}]\n\n{body}")
    return "\n\n".join(parts) + "\n"


class OrbeHelmTests(unittest.TestCase):
    def setUp(self):
        # These tests isolate launch behavior; service readiness has dedicated coverage.
        for target in ('orbehelm.adapters.require_server', 'orbehelm.cli.require_server',
                       'orbehelm.delegation_runner.require_server'):
            readiness = patch(target)
            readiness.start()
            self.addCleanup(readiness.stop)
        self.tmp = tempfile.TemporaryDirectory(dir=REPO / "tests")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for name in ["definitions", "registry", "examples"]:
            shutil.copytree(REPO / name, self.root / name)
        self.project = self.root / "work"
        self.project.mkdir()

    def resolved(self, **kwargs):
        return resolve(self.root, project=self.project, **kwargs)

    def write(self, rel, data):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data))

    def profile(self, **extra):
        data = {"schema_version": 1, "instructions": ["definitions/profiles/developer.md"]}
        data.update(extra)
        self.write("definitions/profiles/developer.json", data)

    def test_composition_and_dependency_order(self):
        result = self.resolved(spec="php", skillsets=["quality", "quality"])
        self.assertEqual(len(result["instructions"]), 3)
        self.assertEqual([x["name"] for x in result["skills"]], ["testing", "review"])
        self.assertIn("PHP", result["instructions"][-1]["content"])

    def test_cache_reuse_change_and_tamper_repair(self):
        first, cached = build(self.root, self.resolved())
        self.assertFalse(cached)
        mtime = (first / "instructions.md").stat().st_mtime_ns
        again, cached = build(self.root, self.resolved())
        self.assertTrue(cached)
        self.assertEqual(mtime, (again / "instructions.md").stat().st_mtime_ns)
        (first / "instructions.md").write_text("tampered")
        repaired, cached = build(self.root, self.resolved())
        self.assertFalse(cached)
        self.assertIn("# Agent Instructions", (repaired / "instructions.md").read_text())
        base = self.root / "definitions/base/instructions.md"
        base.write_text(base.read_text() + "\nNew rule.\n")
        changed, cached = build(self.root, self.resolved())
        self.assertNotEqual(first, changed)
        self.assertFalse(cached)

    def test_skill_resources_invalidate_and_are_copied(self):
        first, _ = build(self.root, self.resolved(skillsets=["quality"]))
        resource = self.root / "examples/skills/testing/data.txt"
        resource.write_text("one")
        second, _ = build(self.root, self.resolved(skillsets=["quality"]))
        self.assertNotEqual(first, second)
        self.assertEqual((second / "skills/testing/data.txt").read_text(), "one")

    def test_transitive_dependency_order_and_corrupt_install_repair(self):
        self.write("registry/skills/testing.json", {"schema_version": 1,
            "source": "examples/skills/testing", "skills": ["review"]})
        result = self.resolved(skillsets=["quality"])
        self.assertEqual([s["name"] for s in result["skills"]], ["review", "testing"])
        build(self.root, result)
        cached = self.root / "state/skills" / result["skills"][0]["sha256"]
        (cached / "SKILL.md").unlink()
        build(self.root, result)
        self.assertTrue((cached / "SKILL.md").is_file())

    def test_skill_build_json_resource_is_checked_for_tampering(self):
        (self.root / "examples/skills/testing/build.json").write_text("original")
        result = self.resolved(skillsets=["quality"])
        output, _ = build(self.root, result)
        (output / "skills/testing/build.json").write_text("tampered")
        output, cached = build(self.root, result)
        self.assertFalse(cached)
        self.assertEqual((output / "skills/testing/build.json").read_text(), "original")

    def test_authentication_uses_wrapper_store(self):
        from orbehelm.adapters import authenticate
        with patch("orbehelm.adapters.shutil.which", return_value="/bin/codex"), patch("orbehelm.adapters.subprocess.call", return_value=0) as call:
            self.assertEqual(authenticate(self.root, "codex"), 0)
        self.assertEqual(call.call_args.args[0], ["codex", "login"])
        self.assertEqual(call.call_args.kwargs["env"]["CODEX_HOME"], str(self.root / "state/auth/codex"))

    def test_unicode_instructions_produce_valid_toml(self):
        path = self.root / "definitions/profiles/developer.md"
        path.write_text(path.read_text() + "\nSupport Unicode: 🚀 café.\n")
        output, _ = build(self.root, self.resolved())
        data = tomllib.loads((output / "config.toml").read_text())
        self.assertIn("🚀 café", data["developer_instructions"])

    def test_cycle_rejected(self):
        for name, dep in [("testing", "review"), ("review", "testing")]:
            self.write(f"registry/skills/{name}.json", {"schema_version": 1,
                "source": f"examples/skills/{name}", "skills": [dep]})
        with self.assertRaisesRegex(OrbeHelmError, "Cyclic"):
            self.resolved(skillsets=["quality"])

    def test_missing_profile_unknown_fields_and_traversal(self):
        with self.assertRaises(OrbeHelmError):
            self.resolved(profile="missing")
        self.profile(unknown=True)
        with self.assertRaisesRegex(OrbeHelmError, "unknown fields"):
            self.resolved()
        self.profile(instructions=["../outside.md"])
        with self.assertRaisesRegex(OrbeHelmError, "escapes"):
            self.resolved()

    def test_symlink_skill_rejected(self):
        (self.root / "examples/skills/testing/leak").symlink_to(REPO / "README.md")
        with self.assertRaisesRegex(OrbeHelmError, "symlinks"):
            self.resolved(skillsets=["quality"])

    def test_pin_mismatch_rejected(self):
        self.write("registry/skills/testing.json", {"schema_version": 1,
            "source": "examples/skills/testing", "sha256": "0" * 64})
        with self.assertRaisesRegex(OrbeHelmError, "pinned"):
            self.resolved(skillsets=["quality"])

    def test_project_layer_and_adapter_artifacts(self):
        shutil.copy2(self.root / "examples/project/orbehelm.project.json", self.project)
        shutil.copy2(self.root / "examples/project/instructions.md", self.project)
        result = self.resolved()
        self.assertEqual(result["instructions"][-1]["path"], str(self.project / "instructions.md"))
        for agent in ["codex", "claude", "opencode"]:
            output, _ = build(self.root, result, agent)
            plan = launch(self.root, output, result, agent, "Task", dry_run=True)
            self.assertIn(agent, shlex.split(plan))
            if agent == "codex":
                config = tomllib.loads((output / "config.toml").read_text())
                self.assertIn("Example Project", config["developer_instructions"])
            elif agent == "claude":
                self.assertEqual(json.loads((output / "mcp.json").read_text()), {"mcpServers": {}})
                self.assertIn("--strict-mcp-config", shlex.split(plan))
            else:
                self.assertEqual(json.loads((output / "opencode.json").read_text())["instructions"], [str(output / "instructions.md")])

    def test_mcp_translation_and_environment_not_persisted(self):
        self.profile(mcp=["sample", "docs"])
        self.write("registry/mcp/sample.json", {"schema_version": 1, "type": "stdio",
            "command": "server", "args": ["--test"], "env": {"TOKEN": "TOKEN"}})
        result = self.resolved()
        with patch.dict(os.environ, {"TOKEN": "secret-test-value"}):
            for agent in ["codex", "claude", "opencode"]:
                output, _ = build(self.root, result, agent)
                for file in output.rglob("*"):
                    if file.is_file():
                        self.assertNotIn("secret-test-value", file.read_text())
                if agent == "codex":
                    cfg = tomllib.loads((output / "config.toml").read_text())
                    self.assertEqual(cfg["mcp_servers"]["sample"]["env_vars"], ["TOKEN"])

    def test_run_records_exit_and_sets_home_without_global_changes(self):
        result = self.resolved()
        output, _ = build(self.root, result)
        with patch("orbehelm.adapters.doctor", return_value={"ok": True}), patch("orbehelm.adapters.subprocess.call", return_value=7) as call:
            code = launch(self.root, output, result, "codex", "private prompt")
        self.assertEqual(code, 7)
        env = call.call_args.kwargs["env"]
        home = Path(env["CODEX_HOME"])
        self.assertTrue(home.is_relative_to(self.root / "state/orbes"))
        records = list((self.root / "state/orbes").glob("*/orbe.json"))
        data = records[0].read_text()
        self.assertNotIn("private prompt", data)
        self.assertEqual(json.loads(data)["exit_code"], 7)
        self.assertFalse((home / "auth.json").exists())

    def test_sessions_reuse_runtime_and_resume_each_adapter(self):
        for agent in ("codex", "claude", "opencode"):
            result = self.resolved()
            output, _ = build(self.root, result, agent)
            with patch("orbehelm.adapters.doctor", return_value={"ok": True}), \
                    patch("orbehelm.adapters.subprocess.call", return_value=0) as child:
                launch(self.root, output, result, agent)
                first_env = child.call_args.kwargs["env"]
                if agent == "codex":
                    transcript = Path(first_env["CODEX_HOME"]) / "sessions/first.jsonl"
                elif agent == "claude":
                    transcript = Path(first_env["CLAUDE_CONFIG_DIR"]) / "projects/work/first.jsonl"
                else:
                    transcript = Path(first_env["XDG_DATA_HOME"]) / "opencode/placeholder"
                transcript.parent.mkdir(parents=True, exist_ok=True)
                transcript.write_text("test transcript")
                launch(self.root, output, result, agent, "continue task")
                self.assertEqual(child.call_args.kwargs["env"], first_env)
                args = child.call_args.args[0]
                self.assertIn("--last" if agent == "codex" else "--continue", args)
                self.assertEqual(args[-1], "continue task")
                launch(self.root, output, result, agent, new_orbe=True)
                fresh_env = child.call_args.kwargs["env"]
                self.assertNotEqual(first_env, fresh_env)
                self.assertNotIn("--continue", child.call_args.args[0])
                self.assertTrue(transcript.exists())
                launch(self.root, output, result, agent)
                self.assertEqual(child.call_args.kwargs["env"], fresh_env)

    def test_session_metadata_reaches_children_and_tracks_reuse_and_rotation(self):
        names = ("ORBEHELM_ORBE_ID", "ORBEHELM_ORBE_DIR", "ORBEHELM_PROFILE",
                 "ORBEHELM_SPECIALIZATION", "ORBEHELM_PROJECT")
        fake = self.root / "inspect_session.py"
        observed = self.root / "observed.json"
        fake.write_text(f"#!{sys.executable}\nimport json, os, sys\n"
                        "from pathlib import Path\n"
                        f"Path(sys.argv[-1]).write_text(json.dumps({{k: os.environ.get(k) for k in {names!r}}}))\n")
        fake.chmod(0o755)
        inherited = {name: "stale-parent-value" for name in names}
        for agent in ("codex", "claude", "opencode"):
            result = self.resolved(spec="python")
            output, _ = build(self.root, result, agent)
            before = {p: p.read_bytes() for p in output.rglob("*") if p.is_file()}
            with patch.dict(os.environ, inherited), \
                    patch("orbehelm.adapters.doctor", return_value={"ok": True}), \
                    patch("orbehelm.adapters.command", return_value=[str(fake), str(observed)]):
                launch(self.root, output, result, agent)
                first = json.loads(observed.read_text())
                self.assertEqual(first["ORBEHELM_PROFILE"], "developer")
                self.assertEqual(first["ORBEHELM_SPECIALIZATION"], "python")
                self.assertEqual(first["ORBEHELM_PROJECT"], str(self.project.resolve()))
                directory = Path(first["ORBEHELM_ORBE_DIR"])
                self.assertTrue(directory.is_absolute())
                record = json.loads((directory / "orbe.json").read_text())
                self.assertEqual(first["ORBEHELM_ORBE_ID"], record["orbe_id"])
                launch(self.root, output, result, agent)
                self.assertEqual(json.loads(observed.read_text()), first)
                launch(self.root, output, result, agent, new_orbe=True)
                fresh = json.loads(observed.read_text())
                self.assertNotEqual(fresh["ORBEHELM_ORBE_ID"], first["ORBEHELM_ORBE_ID"])
                self.assertNotEqual(fresh["ORBEHELM_ORBE_DIR"], first["ORBEHELM_ORBE_DIR"])
                plain = self.resolved()
                plain_output, _ = build(self.root, plain, agent)
                launch(self.root, plain_output, plain, agent)
                self.assertEqual(json.loads(observed.read_text())["ORBEHELM_SPECIALIZATION"], "")
            self.assertEqual(before, {p: p.read_bytes() for p in output.rglob("*") if p.is_file()})
            instructions = (output / "instructions.md").read_text()
            for name in names:
                self.assertIn(name, instructions)
            self.assertIn("not the host CLI conversation", instructions)
            self.assertNotIn(first["ORBEHELM_ORBE_ID"], instructions)

    def test_existing_session_dry_run_is_read_only_and_can_preview_fresh_launch(self):
        result = self.resolved()
        output, _ = build(self.root, result)
        with patch("orbehelm.adapters.doctor", return_value={"ok": True}), \
                patch("orbehelm.adapters.subprocess.call", return_value=0) as child:
            launch(self.root, output, result, "codex")
        home = Path(child.call_args.kwargs["env"]["CODEX_HOME"])
        transcript = home / "sessions/first.jsonl"
        transcript.parent.mkdir()
        transcript.write_text("saved")
        before = {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        plan = launch(self.root, output, result, "codex", dry_run=True)
        self.assertIn("resume --last", plan)
        self.assertIn(str(home), plan)
        fresh = launch(self.root, output, result, "codex", dry_run=True, new_orbe=True)
        self.assertNotIn("resume", fresh)
        after = {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_session_identity_ignores_build_changes_and_separates_profiles(self):
        result = self.resolved()
        output, _ = build(self.root, result)
        with patch("orbehelm.adapters.doctor", return_value={"ok": True}), \
                patch("orbehelm.adapters.subprocess.call", return_value=0) as child:
            launch(self.root, output, result, "codex")
            home = child.call_args.kwargs["env"]["CODEX_HOME"]
            changed = resolve(self.root, project=self.project, skillsets=["quality"])
            new_output, _ = build(self.root, changed)
            launch(self.root, new_output, changed, "codex")
            self.assertEqual(child.call_args.kwargs["env"]["CODEX_HOME"], home)
            self.assertEqual((Path(home) / "config.toml").read_bytes(),
                             (new_output / "config.toml").read_bytes())
            specialized = resolve(self.root, spec="python", project=self.project)
            specialized_output, _ = build(self.root, specialized)
            launch(self.root, specialized_output, specialized, "codex")
            self.assertNotEqual(child.call_args.kwargs["env"]["CODEX_HOME"], home)

    def test_session_lock_rejects_concurrent_launch_and_releases_after_failure(self):
        result = self.resolved()
        output, _ = build(self.root, result)
        def competing_launch(*args, **kwargs):
            with self.assertRaisesRegex(OrbeHelmError, "already running"):
                launch(self.root, output, result, "codex")
            raise OSError("test launch failure")
        with patch("orbehelm.adapters.doctor", return_value={"ok": True}), \
                patch("orbehelm.adapters.subprocess.call", side_effect=competing_launch):
            with self.assertRaisesRegex(OrbeHelmError, "test launch failure"):
                launch(self.root, output, result, "codex")
        with patch("orbehelm.adapters.doctor", return_value={"ok": True}), \
                patch("orbehelm.adapters.subprocess.call", return_value=0):
            self.assertEqual(launch(self.root, output, result, "codex"), 0)
        records = list((self.root / "state/orbes").glob("*/orbe.json"))
        self.assertEqual(len(records), 1)
        self.assertEqual(json.loads(records[0].read_text())["launch_count"], 2)

    def test_strict_refuses_launch_and_doctor_detects_missing_cli(self):
        result = self.resolved()
        output, _ = build(self.root, result)
        with self.assertRaisesRegex(OrbeHelmError, "Strict isolation"):
            launch(self.root, output, result, "codex", strict=True)
        with patch("orbehelm.adapters.shutil.which", return_value=None):
            self.assertFalse(doctor(result, "codex")["ok"])

    def test_cli_default_launch_is_dry_runnable_and_errors_are_clean(self):
        with contextlib.redirect_stdout(io.StringIO()) as stdout:
            code = main(["--root", str(self.root), "--project", str(self.project),
                         "--profile=developer", "--spec=php", "--skillset=quality", "--dry-run"])
        self.assertEqual(code, 0)
        self.assertIn("codex --no-daemon", stdout.getvalue())
        self.assertTrue(stdout.getvalue().startswith("cd "))
        with contextlib.redirect_stderr(io.StringIO()) as stderr:
            code = main(["resolve", "--root", str(self.root), "--profile=../bad"])
        self.assertEqual(code, 2)
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_dry_run_prints_a_quoted_command_for_prebuilt_configurations(self):
        project = self.root / "project with ' quotes $ and spaces"
        project.mkdir()
        tools = self.root / "fake-bin"
        tools.mkdir()
        fake = (f"#!{sys.executable}\nimport json, os, sys\n"
                "print(json.dumps({'args': sys.argv[1:], 'cwd': os.getcwd(), "
                "'home': os.environ.get('CODEX_HOME'), "
                "'config': os.environ.get('OPENCODE_CONFIG_CONTENT')}))\n")
        prompt = "Keep 'quotes', $HOME, $(touch unexpected-file), and `commands` literal."
        for agent in ("codex", "claude", "opencode"):
            output, _ = build(self.root, resolve(self.root, project=project), agent)
            executable = tools / agent
            executable.write_text(fake)
            executable.chmod(0o755)
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr), \
                    patch("orbehelm.adapters.subprocess.call") as child, \
                    patch("orbehelm.adapters.doctor") as health:
                code = main(["--root", str(self.root), "--project", str(project),
                             "--agent", agent, "--prompt", prompt, "--dry-run"])
            self.assertEqual(code, 0)
            self.assertEqual(stderr.getvalue(), "")
            child.assert_not_called()
            health.assert_not_called()
            shell_command = stdout.getvalue().strip()
            self.assertEqual(len(shell_command.splitlines()), 1)
            self.assertTrue(shell_command.startswith("cd "))
            self.assertFalse((self.root / "state/orbes").exists())
            env = dict(os.environ, PATH=str(tools) + os.pathsep + os.environ.get("PATH", ""))
            completed = subprocess.run(["/bin/sh", "-c", shell_command], env=env,
                                       capture_output=True, text=True, check=True, cwd=self.root)
            observed = json.loads(completed.stdout)
            self.assertEqual(observed["cwd"], str(project))
            self.assertEqual(observed["args"][-1], prompt)
            self.assertFalse((project / "unexpected-file").exists())
            if agent == "codex":
                home = Path(observed["home"])
                self.assertEqual(home, output)
                self.assertTrue((home / "config.toml").is_file())
            elif agent == "opencode":
                self.assertIn("instructions", json.loads(observed["config"]))

    def test_dry_run_never_creates_or_modifies_files(self):
        def snapshot():
            return {str(p.relative_to(self.root)): (p.stat().st_mtime_ns, p.read_bytes() if p.is_file() else None)
                    for p in [self.root, *self.root.rglob("*")]}
        for agent in ("codex", "claude", "opencode"):
            with self.subTest(agent=agent):
                before = snapshot()
                with contextlib.redirect_stdout(io.StringIO()) as stdout, \
                        patch("orbehelm.cli.build") as builder, \
                        patch("orbehelm.adapters.launch_environment") as prepare, \
                        patch("orbehelm.adapters.subprocess.call") as child:
                    code = main(["--root", str(self.root), "--project", str(self.project),
                                 "--agent", agent, "--skillset", "quality", "--dry-run"])
                self.assertEqual(code, 0)
                builder.assert_not_called()
                prepare.assert_not_called()
                child.assert_not_called()
                self.assertEqual(before, snapshot())
                self.assertIn(agent, stdout.getvalue())
                self.assertFalse((self.root / "generated").exists())
                self.assertFalse((self.root / "state").exists())

    def test_dry_run_does_not_authenticate_or_run_other_commands(self):
        for command in ("auth", "build", "doctor", "resolve", "list", "status", "skills"):
            with self.subTest(command=command), contextlib.redirect_stderr(io.StringIO()), \
                    patch("orbehelm.cli.authenticate") as authenticate:
                self.assertEqual(main([command, "--root", str(self.root), "--dry-run"]), 2)
                authenticate.assert_not_called()

    def test_every_definition_uses_the_common_template(self):
        paths = [self.root / "definitions/base/instructions.md", self.root / "definitions/TEMPLATE.md"]
        paths += list((self.root / "definitions/profiles").glob("*.md"))
        paths += list((self.root / "definitions/specializations").rglob("*.md"))
        for path in paths:
            with self.subTest(path=path.name):
                sections = parse_sections(path.read_text(), path)
                self.assertEqual(tuple(s[0] for s in sections), SECTION_TITLES)
                self.assertNotIn("Requires the shared base", path.read_text())

    def test_section_append_override_clear_and_empty_inheritance(self):
        documents = [
            section_document(**{
                "Purpose and judgment": ("append", "Base purpose."),
                "Responsibilities": ("append", "Base duty."),
                "Workflow": ("append", "Old workflow."),
                "Communication": ("append", "Base communication."),
            }),
            section_document(**{
                "Responsibilities": ("append", "Profile duty."),
                "Workflow": ("override", "New workflow."),
                "Communication": ("override", ""),
            }),
            section_document(**{"Workflow": ("append", "Extra step.")}),
        ]
        result = compose([{"path": str(i), "content": doc} for i, doc in enumerate(documents)])
        self.assertIn("Base purpose.", result)
        self.assertIn("Base duty.\n\nProfile duty.", result)
        self.assertIn("New workflow.\n\nExtra step.", result)
        self.assertNotIn("Old workflow.", result)
        self.assertNotIn("Base communication.", result)
        self.assertNotIn("## Communication", result)
        self.assertNotIn("## Completion criteria", result)
        for token in (MARKER, "[append]", "[override]", "Test Definition", "null", "{{"):
            self.assertNotIn(token, result)
        self.assertEqual(result.count("## Responsibilities"), 1)
        self.assertLess(result.index("## Purpose"), result.index("## Responsibilities"))
        self.assertLess(result.index("## Responsibilities"), result.index("## Workflow"))

    def test_section_overrides_follow_specialization_skillset_and_project_order(self):
        duty = "Responsibilities"
        def document(body, mode="override"):
            return section_document(**{duty: (mode, body)})
        (self.root / "definitions/profiles/developer.md").write_text(document("Profile replacement."))
        (self.root / "definitions/specializations/developer/php.md").write_text(document("Specialization addition.", "append"))
        (self.root / "definitions/skillsets/extra.md").write_text(document("Skillset replacement."))
        self.write("definitions/skillsets/extra.json", {"schema_version": 1,
            "instructions": ["definitions/skillsets/extra.md"]})
        before = self.resolved(spec="php")["composed_instructions"]
        self.assertIn("Profile replacement.\n\nSpecialization addition.", before)
        selected = self.resolved(spec="php", skillsets=["extra"])["composed_instructions"]
        self.assertNotIn("Profile replacement.", selected)
        self.assertIn("Skillset replacement.", selected)
        self.write("work/orbehelm.project.json", {"schema_version": 1, "instructions": ["instructions.md"]})
        (self.project / "instructions.md").write_text(document("Project replacement."))
        result = self.resolved(spec="php", skillsets=["extra"])
        output, _ = build(self.root, result)
        rendered = (output / "instructions.md").read_text()
        self.assertIn("Project replacement.", rendered)
        self.assertNotIn("Skillset replacement.", rendered)
        self.assertEqual(rendered, result["composed_instructions"])
        self.assertIn("Profile replacement.", result["instructions"][1]["content"])
        self.assertTrue(result["sources"])

    def test_malformed_sections_fail_during_resolution(self):
        valid = section_document()
        cases = [
            "# Old format\n\nUnstructured role.",
            valid.replace(MARKER, "<!-- orbehelm:sections:v2 -->"),
            valid.replace("## Responsibilities [append]", "## Duties [append]"),
            valid.replace("## Workflow [append]", "## Workflow [merge]"),
            valid.replace("## Workflow [append]", "## Responsibilities [append]"),
            valid.replace("## Communication [append]", ""),
            valid.replace("## Workflow [append]", "## Communication [append]").replace(
                "## Execution and evidence [append]", "## Workflow [append]"),
            valid.replace("# Test Definition", "# Test Definition\n\nRequires the shared base instructions."),
            valid + "\n# Another document\n",
            valid + "\n```python\nunfinished = True\n",
        ]
        for content in cases:
            with self.subTest(content=content):
                (self.root / "definitions/profiles/developer.md").write_text(content)
                with self.assertRaises(OrbeHelmError):
                    self.resolved()

    def test_fenced_code_and_subheadings_are_preserved(self):
        body = "### Details\n\n```markdown\n## Not a section\n# Not a title\n```\n\n~~~text\n## Also not a section\n~~~"
        result = compose([{"path": "test.md", "content": section_document(**{
            "Responsibilities": ("append", body)})}])
        self.assertIn(body, result)

    def test_plain_optional_context_is_preserved_and_bad_marker_is_rejected(self):
        self.write("work/orbehelm.project.json", {"schema_version": 1, "instructions": ["instructions.md"]})
        context = self.project / "instructions.md"
        context.write_text("# Project Notes\n\nPreserve these instructions.")
        self.assertIn(context.read_text(), self.resolved()["composed_instructions"])
        context.write_text(section_document().replace(MARKER, "<!-- orbehelm:sections:v9 -->"))
        with self.assertRaises(OrbeHelmError):
            self.resolved()

    def test_all_profiles_build_cleanly_for_every_adapter(self):
        for profile in sorted((self.root / "definitions/profiles").glob("*.json")):
            for agent in ("codex", "claude", "opencode"):
                with self.subTest(profile=profile.stem, agent=agent):
                    result = self.resolved(profile=profile.stem, skillsets=["quality"])
                    output, _ = build(self.root, result, agent)
                    text = (output / "instructions.md").read_text()
                    self.assertIn("# Selected Skill testing", text)
                    self.assertIn("# Selected Skill review", text)
                    self.assertNotIn(MARKER, text)
                    self.assertNotIn("[append]", text)
                    self.assertNotIn("Requires the shared base", text)
                    self.assertNotIn("Add one relevant technology", text)
                    for heading in SECTION_TITLES:
                        self.assertLessEqual(text.count(f"## {heading}\n"), 1)
                    if agent == "codex":
                        config = tomllib.loads((output / "config.toml").read_text())
                        self.assertEqual(config["developer_instructions"], text)
                    elif agent == "claude":
                        from orbehelm.adapters import command
                        self.assertEqual(command(output, agent)[2], str(output / "instructions.md"))
                    else:
                        self.assertEqual(json.loads((output / "opencode.json").read_text())["instructions"],
                                         [str(output / "instructions.md")])


if __name__ == "__main__":
    unittest.main()
